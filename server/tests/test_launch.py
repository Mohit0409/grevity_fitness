from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from server.gravity.admin import AdminService
from server.gravity.config import Settings
from server.gravity.database import Database
from server.gravity.launch import LaunchGate
from server.gravity.operations import BackupManager


ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "phase-eleven-launch-secret-long-enough"


class LaunchGateTests(unittest.TestCase):
    def _settings(self, runtime: Path) -> Settings:
        service_account = runtime / "service.json"
        service_account.write_text("{}", encoding="utf-8")
        return Settings.load(root_dir=ROOT, environ={
            "GRAVITY_ENV": "production",
            "GRAVITY_HOST": "127.0.0.1",
            "APP_BASE_URL": "https://gravity.example",
            "GRAVITY_DATA_DIR": str((runtime / "data").resolve()),
            "GRAVITY_LOG_DIR": str((runtime / "logs").resolve()),
            "GRAVITY_BACKUP_DIR": str((runtime / "backups").resolve()),
            "GRAVITY_TRUST_PROXY": "true",
            "GRAVITY_TRUSTED_PROXY_CIDRS": "127.0.0.1/32",
            "SECRET_KEY": TEST_SECRET,
            "FIREBASE_PROJECT_ID": "gravity-authe",
            "FIREBASE_WEB_API_KEY": "api-key",
            "FIREBASE_AUTH_DOMAIN": "gravity.example",
            "FIREBASE_APP_ID": "app-id",
            "FIREBASE_SERVICE_ACCOUNT_PATH": str(service_account.resolve()),
            "RAZORPAY_MODE": "live",
            "RAZORPAY_KEY_ID": "rzp-key",
            "RAZORPAY_KEY_SECRET": "rzp-secret",
            "RAZORPAY_WEBHOOK_SECRET": "webhook-secret",
            "OWNER_PHONE": "+917999526112",
            "BUSINESS_NAME": "Gravity Fitness",
            "BUSINESS_ADDRESS": "Verified business address",
            "BUSINESS_GSTIN": "23ABCDE1234F1Z5",
            "TAX_INVOICE_ENABLED": "true",
        })

    def _complete_operational_state(self, settings: Settings) -> Database:
        database = Database(settings.database_path, settings.migrations_dir)
        database.migrate()
        AdminService(database, settings).bootstrap_owner("owner", "Gravity!Owner123")
        with database.session() as connection:
            connection.execute(
                "UPDATE membership_plans SET status='active' WHERE id='plan-basic-monthly'"
            )
        BackupManager(settings, database).create_backup("launch-test")
        return database

    def test_incomplete_operational_state_fails_closed_without_secret_leak(self):
        with TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            database = Database(settings.database_path, settings.migrations_dir)
            database.migrate()
            report = LaunchGate(settings, database).report()
        self.assertFalse(report["launchReady"])
        self.assertIn("active_owner", report["blockers"])
        self.assertIn("active_membership_plan", report["blockers"])
        self.assertIn("recent_verified_backup", report["blockers"])
        self.assertIn("recovery_drill", report["blockers"])
        self.assertNotIn(TEST_SECRET, json.dumps(report, sort_keys=True))

    def test_complete_synthetic_launch_state_passes(self):
        with TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            database = self._complete_operational_state(settings)
            report = LaunchGate(settings, database).report()
        self.assertTrue(report["launchReady"])
        self.assertEqual(report["blockers"], [])
        self.assertTrue(report["operations"]["database"]["migrationsCurrent"])
        self.assertTrue(report["operations"]["business"]["activeOwner"])
        self.assertEqual(report["operations"]["business"]["activePlanCount"], 1)
        self.assertTrue(report["operations"]["backup"]["verified"])
        self.assertTrue(report["operations"]["backup"]["recoveryDrillPassed"])

    def test_stale_backup_blocks_launch_even_when_recovery_is_valid(self):
        with TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            database = self._complete_operational_state(settings)
            future = datetime.now(timezone.utc) + timedelta(hours=25)
            report = LaunchGate(settings, database, clock=lambda: future).report()
        self.assertFalse(report["launchReady"])
        self.assertIn("recent_verified_backup", report["blockers"])
        self.assertNotIn("recovery_drill", report["blockers"])
        self.assertTrue(report["operations"]["backup"]["verified"])
        self.assertFalse(report["operations"]["backup"]["recent"])
