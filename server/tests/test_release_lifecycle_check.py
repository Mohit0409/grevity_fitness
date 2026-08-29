from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "release-lifecycle-check.py"
spec = importlib.util.spec_from_file_location("release_lifecycle_check", CHECKER)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class ReleaseLifecycleCheckTests(unittest.TestCase):
    def base_evidence(self) -> dict:
        boot = "2026-08-29T10:00:00+00:00"
        return {
            "now": "2026-08-29T12:00:00+00:00",
            "bootTime": boot,
            "collectionBlockers": [],
            "release": {
                "expectedSha": "abc123", "actualSha": "abc123", "clean": True, "detached": True,
                "projectRoot": "C:/gravity-release", "stateProjectRoot": "C:/gravity-release",
                "expectedPython": "C:/gravity-release/.venv/Scripts/python.exe",
                "stateExecutable": "C:/gravity-release/.venv/Scripts/python.exe",
                "processExecutable": "C:/gravity-release/.venv/Scripts/python.exe",
                "pid": 4200, "pidFile": 4200, "statePid": 4200,
                "processStartedAt": "2026-08-29T10:05:00+00:00",
                "stateStartedAt": "2026-08-29T10:05:01+00:00",
                "commandValid": True, "listenerValid": True, "healthOk": True, "port": 8787,
            },
            "taskVerification": {"ready": True, "blockers": []},
            "tasks": [
                {"name": "GravityFitness-Watchdog", "present": True, "enabled": True, "lastTaskResult": 0,
                 "lastRunTime": "2026-08-29T11:59:00+00:00", "nextRunTime": "2026-08-29T12:00:00+00:00"},
                {"name": "GravityFitness-DailyBackup", "present": True, "enabled": True, "lastTaskResult": 0,
                 "lastRunTime": "2026-08-29T02:00:00+00:00", "nextRunTime": "2026-08-30T02:00:00+00:00"},
                {"name": "GravityFitness-Notifications", "present": True, "enabled": True, "lastTaskResult": 0,
                 "lastRunTime": "2026-08-29T11:50:00+00:00", "nextRunTime": "2026-08-29T12:50:00+00:00"},
            ],
            "ngrok": {
                "managed": True, "pid": 4300, "pidFile": 4300, "statePid": 4300,
                "expectedExecutable": "C:/Program Files/ngrok/ngrok.exe",
                "stateExecutable": "C:/Program Files/ngrok/ngrok.exe",
                "processExecutable": "C:/Program Files/ngrok/ngrok.exe",
                "expectedConfig": "C:/ProgramData/GravityFitness/ngrok.yml",
                "stateConfig": "C:/ProgramData/GravityFitness/ngrok.yml",
                "target": "http://127.0.0.1:8787",
                "stateStartedAt": "2026-08-29T10:06:01+00:00",
                "processStartedAt": "2026-08-29T10:06:00+00:00",
                "commandValid": True, "tunnelCount": 1,
                "tunnelUrl": "https://gravity.example.test", "stateUrl": "https://gravity.example.test",
                "publicHealthOk": True,
            },
            "notifications": {
                "statePresent": True,
                "lastSuccessfulScanAt": "2026-08-29T11:50:30+00:00",
                "lastSuccessfulDeliveryAt": "2026-08-29T11:50:35+00:00",
                "lastReportStatus": "ok", "consecutiveFailures": 0,
                "providerReadiness": {"email": "ready", "sms": "blocked_adapter_missing"},
                "lockPresent": False,
            },
            "backup": {
                "evidencePresent": True,
                "lastVerifiedAt": "2026-08-29T09:30:00+00:00",
                "recoveryDrillPassed": True,
            },
        }

    def test_healthy_post_reboot_evidence_is_ready(self) -> None:
        report = checker.evaluate(self.base_evidence())
        self.assertTrue(report["ready"], report["blockers"])
        self.assertEqual(report["blockers"], [])

    def test_wrong_release_sha_and_foreign_pid_fail(self) -> None:
        evidence = self.base_evidence()
        evidence["release"]["actualSha"] = "wrong"
        evidence["release"]["statePid"] = 9999
        report = checker.evaluate(evidence)
        self.assertFalse(report["ready"])
        self.assertIn("release_sha_mismatch", report["blockers"])
        self.assertIn("gravity_pid_ownership_mismatch", report["blockers"])

    def test_missing_task_and_failed_task_result_fail(self) -> None:
        evidence = self.base_evidence()
        evidence["tasks"] = [item for item in evidence["tasks"] if item["name"] != "GravityFitness-Watchdog"]
        notifications = next(item for item in evidence["tasks"] if item["name"] == "GravityFitness-Notifications")
        notifications["lastTaskResult"] = 1
        report = checker.evaluate(evidence)
        self.assertIn("task_runtime_missing:GravityFitness-Watchdog", report["blockers"])
        self.assertIn("task_last_result_failed:GravityFitness-Notifications", report["blockers"])

    def test_unmanaged_or_mismatched_ngrok_fails(self) -> None:
        evidence = self.base_evidence()
        evidence["ngrok"]["managed"] = False
        evidence["ngrok"]["stateConfig"] = "C:/wrong/ngrok.yml"
        report = checker.evaluate(evidence)
        self.assertIn("ngrok_unmanaged", report["blockers"])
        self.assertIn("ngrok_config_mismatch", report["blockers"])

    def test_stale_notification_state_after_boot_fails(self) -> None:
        evidence = self.base_evidence()
        evidence["notifications"]["lastSuccessfulScanAt"] = "2026-08-29T09:00:00+00:00"
        evidence["notifications"]["lastSuccessfulDeliveryAt"] = "2026-08-29T09:01:00+00:00"
        evidence["notifications"]["lockPresent"] = True
        report = checker.evaluate(evidence)
        self.assertIn("notification_scan_not_from_current_boot", report["blockers"])
        self.assertIn("notification_delivery_not_from_current_boot", report["blockers"])
        self.assertIn("notification_runner_lock_present", report["blockers"])

    def test_backup_without_recorded_recovery_drill_fails(self) -> None:
        evidence = self.base_evidence()
        evidence["backup"]["recoveryDrillPassed"] = False
        report = checker.evaluate(evidence)
        self.assertIn("backup_recovery_drill_not_recorded", report["blockers"])

    def test_missing_backup_evidence_is_warning_not_mutating_gate(self) -> None:
        evidence = self.base_evidence()
        evidence["backup"] = {"evidencePresent": False}
        report = checker.evaluate(evidence)
        self.assertTrue(report["ready"])
        self.assertIn("backup_evidence_unavailable", report["warnings"])

    def test_stale_backup_evidence_is_warning(self) -> None:
        evidence = self.base_evidence()
        evidence["backup"]["lastVerifiedAt"] = "2026-08-27T00:00:00+00:00"
        report = checker.evaluate(evidence)
        self.assertTrue(report["ready"])
        self.assertIn("backup_evidence_stale", report["warnings"])
        self.assertGreater(report["backup"]["ageHours"], 36)

    def test_collection_failure_is_fail_closed(self) -> None:
        evidence = self.base_evidence()
        evidence["collectionBlockers"] = ["boot_time_unavailable"]
        report = checker.evaluate(evidence)
        self.assertFalse(report["ready"])
        self.assertIn("boot_time_unavailable", report["blockers"])


if __name__ == "__main__":
    unittest.main()
