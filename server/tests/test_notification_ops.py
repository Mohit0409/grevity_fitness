from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts" / "run-notifications.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("notification_runner", RUNNER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class NotificationOperationsRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_runner()

    def fake_success(self, command, **_kwargs):
        if "--scan-notifications" in command:
            window = int(command[-1])
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=repr(
                    {
                        "scan": {
                            "daysBefore": window,
                            "created": window % 2,
                            "deduped": 2,
                            "suppressedRenewed": 1,
                        }
                    }
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=repr({"delivery": {"attempted": 3, "sent": 2, "failed": 0, "skipped": 1}}),
            stderr="",
        )

    def test_required_windows_are_scanned_once_and_aggregate_safely(self) -> None:
        with TemporaryDirectory() as temporary:
            runtime = Path(temporary) / "runtime"
            with patch.object(self.runner, "_provider_readiness", return_value={"email": {"status": "blocked"}}), patch.object(
                self.runner.subprocess, "run", side_effect=self.fake_success
            ) as run:
                report, exit_code = self.runner.run_cycle(ROOT, runtime, Path(sys.executable), 30, 30)

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(self.runner.SCAN_WINDOWS, (7, 3, 1, 0))
        self.assertEqual([item["scan_window"] for item in report["scan_results"]], [7, 3, 1, 0])
        self.assertEqual(report["delivery_sent"], 2)
        self.assertEqual(run.call_count, 5)

    def test_duplicate_lock_skips_without_running_delivery(self) -> None:
        with TemporaryDirectory() as temporary:
            runtime = Path(temporary) / "runtime"
            runtime.mkdir()
            (runtime / "notification-runner.lock").write_text(
                json.dumps({"pid": 1, "token": "other"}), encoding="utf-8"
            )
            with patch.object(self.runner, "_provider_readiness", return_value={}), patch.object(
                self.runner, "_process_running", return_value=True
            ), patch.object(self.runner.subprocess, "run") as run:
                report, exit_code = self.runner.run_cycle(ROOT, runtime, Path(sys.executable), 30, 30)

        self.assertEqual((exit_code, report["status"]), (0, "already_running"))
        run.assert_not_called()

    def test_dead_lock_is_recovered_for_the_next_scheduled_run(self) -> None:
        with TemporaryDirectory() as temporary:
            runtime = Path(temporary) / "runtime"
            runtime.mkdir()
            (runtime / "notification-runner.lock").write_text(
                json.dumps({"pid": 999999999, "token": "crashed"}), encoding="utf-8"
            )
            with patch.object(self.runner, "_provider_readiness", return_value={}), patch.object(
                self.runner.subprocess, "run", side_effect=self.fake_success
            ):
                report, exit_code = self.runner.run_cycle(ROOT, runtime, Path(sys.executable), 30, 30)

        self.assertEqual((exit_code, report["status"]), (0, "ok"))

    def test_stale_lock_recovers_even_if_pid_was_reused(self) -> None:
        with TemporaryDirectory() as temporary:
            runtime = Path(temporary) / "runtime"
            runtime.mkdir()
            lock_path = runtime / "notification-runner.lock"
            lock_path.write_text(json.dumps({"pid": 12345, "token": "stale"}), encoding="utf-8")
            self.runner.os.utime(lock_path, (1, 1))
            with patch.object(self.runner, "_provider_readiness", return_value={}), patch.object(
                self.runner, "_process_running", return_value=True
            ), patch.object(self.runner.time, "time", return_value=1_000), patch.object(
                self.runner.subprocess, "run", side_effect=self.fake_success
            ):
                report, exit_code = self.runner.run_cycle(ROOT, runtime, Path(sys.executable), 30, 30)

        self.assertEqual((exit_code, report["status"]), (0, "ok"))

    def test_cli_rejects_lock_budget_shorter_than_worst_case_cycle(self) -> None:
        with TemporaryDirectory() as temporary:
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER_PATH),
                    "--runtime-dir",
                    str(Path(temporary) / "runtime"),
                    "--timeout-seconds",
                    "300",
                    "--stale-lock-seconds",
                    "1200",
                    "--status",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale lock timeout", result.stderr)

    def test_failed_delivery_is_safe_and_retries_on_a_later_cycle(self) -> None:
        def failed_delivery(command, **_kwargs):
            if "--scan-notifications" in command:
                return self.fake_success(command)
            return subprocess.CompletedProcess(
                command,
                1,
                stdout=repr({"delivery": {"attempted": 2, "sent": 1, "failed": 1, "skipped": 0}}),
                stderr="provider-secret-must-not-appear",
            )

        with TemporaryDirectory() as temporary:
            runtime = Path(temporary) / "runtime"
            with patch.object(self.runner, "_provider_readiness", return_value={}), patch.object(
                self.runner.subprocess, "run", side_effect=failed_delivery
            ):
                report, exit_code = self.runner.run_cycle(ROOT, runtime, Path(sys.executable), 30, 30)
            state = json.loads((runtime / "notification-state.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(report["failure"], "notification_delivery_failed")
        self.assertEqual(report["delivery_failed"], 1)
        self.assertIn("last_successful_scan_at", state)
        self.assertNotIn("last_successful_delivery_at", state)
        self.assertEqual(state["consecutive_failures"], 1)
        self.assertNotIn("provider-secret-must-not-appear", json.dumps(report))

    def test_scan_failure_does_not_attempt_delivery_or_log_raw_output(self) -> None:
        def failed_scan(command, **_kwargs):
            return subprocess.CompletedProcess(command, 2, stdout="", stderr="config-secret-must-not-appear")

        with TemporaryDirectory() as temporary:
            runtime = Path(temporary) / "runtime"
            with patch.object(self.runner, "_provider_readiness", return_value={}), patch.object(
                self.runner.subprocess, "run", side_effect=failed_scan
            ) as run:
                report, exit_code = self.runner.run_cycle(ROOT, runtime, Path(sys.executable), 30, 30)

        self.assertEqual((exit_code, report["failure"]), (1, "notification_scan_failed"))
        self.assertEqual(run.call_count, 1)
        self.assertNotIn("config-secret-must-not-appear", json.dumps(report))

    def test_notification_log_rotates_without_exposing_runtime_output(self) -> None:
        with TemporaryDirectory() as temporary:
            log = Path(temporary) / "notifications.log"
            log.write_bytes(b"x" * self.runner.MAX_LOG_BYTES)
            self.runner._write_log(log, {"event": "notification_cycle", "status": "ok"})
            self.assertTrue((Path(str(log) + ".1")).is_file())
            self.assertEqual(json.loads(log.read_text(encoding="utf-8"))["status"], "ok")

    def test_provider_and_owner_readiness_never_return_raw_values(self) -> None:
        blocked = self.runner._provider_readiness(ROOT, {})
        configured = self.runner._provider_readiness(
            ROOT,
            {
                "SMTP_HOST": "smtp.example.test",
                "SMTP_USERNAME": "mailer",
                "SMTP_PASSWORD": "smtp-secret",
                "EMAIL_FROM": "not-an-output@example.test",
                "SMS_PROVIDER": "sms-provider",
                "SMS_API_KEY": "sms-secret",
                "WHATSAPP_PROVIDER": "whatsapp-provider",
                "WHATSAPP_ACCESS_TOKEN": "whatsapp-secret",
                "WHATSAPP_PHONE_NUMBER_ID": "phone-id",
                "OWNER_EMAIL": "owner@example.test",
                "OWNER_PHONE": "+911234567890",
                "OWNER_WHATSAPP": "+919876543210",
            },
        )

        self.assertEqual(blocked["email"]["status"], "blocked_external_config")
        self.assertEqual(blocked["sms"]["status"], "blocked_external_config")
        self.assertEqual(blocked["whatsapp"]["status"], "blocked_external_config")
        self.assertEqual(blocked["owner_email"]["status"], "missing_recipient")
        self.assertEqual(configured["email"]["status"], "ready")
        self.assertEqual(configured["sms"]["status"], "blocked_adapter_missing")
        self.assertEqual(configured["whatsapp"]["status"], "blocked_adapter_missing")
        self.assertEqual(configured["owner_email"]["status"], "configured")
        self.assertEqual(configured["owner_phone"]["status"], "configured")
        self.assertEqual(configured["owner_whatsapp"]["status"], "configured")
        serialized = json.dumps(configured)
        self.assertNotIn("smtp-secret", serialized)
        self.assertNotIn("sms-secret", serialized)
        self.assertNotIn("whatsapp-secret", serialized)
        self.assertNotIn("owner@example.test", serialized)
        self.assertNotIn("+911234567890", serialized)


if __name__ == "__main__":
    unittest.main()
