from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from server.gravity.admin_health import AdminHealthCheck
from server.gravity.config import Settings


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


class FakeLaunchGate:
    def __init__(self, report):
        self.value = report

    def report(self):
        return self.value


def launch_report(*, ready=True):
    return {
        "launchReady": ready,
        "blockers": [] if ready else ["database_health"],
        "readiness": {
            "notifications": {
                "email": {"status": "ready", "configured": True, "adapterReady": True},
                "sms": {"status": "blocked_external_config", "configured": False, "adapterReady": False},
                "whatsapp": {"status": "blocked_external_config", "configured": False, "adapterReady": False},
            }
        },
        "operations": {
            "database": {
                "healthy": ready,
                "migrationsCurrent": ready,
                "appliedMigrations": 9,
                "expectedMigrations": 9,
            },
            "backup": {
                "archive": "gravity-daily-synthetic.zip",
                "verified": ready,
                "recent": ready,
                "recoveryDrillPassed": ready,
            },
        },
    }


class AdminHealthCheckTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        base = Settings.load(root_dir=ROOT, environ={"SECRET_KEY": "x" * 40})
        self.settings = replace(
            base,
            data_dir=self.root / "data",
            log_dir=self.root / "logs",
            backup_dir=self.root / "backups",
            database_path=self.root / "data" / "gravity.sqlite3",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def write_scheduler_state(self, *, status="ok", timestamp="2026-08-29T11:30:00Z", failures=0):
        state = {
            "last_successful_scan_at": timestamp,
            "last_successful_delivery_at": timestamp,
            "consecutive_failures": failures,
            "provider_readiness": {
                "email": {"status": "ready", "address": "email@example.test"},
                "owner_email": {"status": "configured"},
                "unexpected": {"status": "must-never-be-echoed"},
            },
            "last_report": {"status": status, "finished_at": timestamp},
        }
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "notification-state.json").write_text(json.dumps(state), encoding="utf-8")

    def test_daily_health_is_green_and_contains_no_contact_or_secret_values(self):
        self.write_scheduler_state()
        secret = "must-never-appear-in-health-output"
        report = AdminHealthCheck(
            self.settings,
            self.root,
            launch_gate=FakeLaunchGate(launch_report()),
            backend_probe=lambda _url: {
                "service": "Gravity Fitness", "status": "ok", "database": "ok",
                "debug": secret,
            },
            clock=lambda: NOW,
        ).report()
        self.assertTrue(report["healthy"])
        self.assertEqual(report["blockers"], [])
        self.assertTrue(all(report["checks"].values()))
        encoded = json.dumps(report, sort_keys=True)
        self.assertNotIn(secret, encoded)
        self.assertNotIn("phone", encoded.casefold())
        self.assertNotIn("email@example", encoded.casefold())

    def test_backend_and_stale_scheduler_fail_closed_with_safe_statuses(self):
        self.write_scheduler_state(timestamp="2026-08-29T08:00:00Z")
        report = AdminHealthCheck(
            self.settings,
            self.root,
            launch_gate=FakeLaunchGate(launch_report()),
            backend_probe=lambda _url: {},
            clock=lambda: NOW,
        ).report()
        self.assertFalse(report["healthy"])
        self.assertEqual(report["backend"]["status"], "unavailable")
        self.assertEqual(report["notificationScheduler"]["status"], "stale")
        self.assertIn("backend", report["blockers"])
        self.assertIn("notificationScheduler", report["blockers"])

    def test_missing_scheduler_state_is_reported_as_never_run(self):
        report = AdminHealthCheck(
            self.settings,
            self.root,
            launch_gate=FakeLaunchGate(launch_report()),
            backend_probe=lambda _url: {"service": "Gravity Fitness", "status": "ok", "database": "ok"},
            clock=lambda: NOW,
        ).report()
        self.assertFalse(report["healthy"])
        self.assertEqual(report["notificationScheduler"]["status"], "never_run")


if __name__ == "__main__":
    unittest.main()
