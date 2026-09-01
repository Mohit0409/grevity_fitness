from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from server.gravity.admin import AdminService
from server.gravity.admin_software import AdminSoftwareService
from server.gravity.biometric import (
    BiometricConflict,
    BiometricScanEvent,
    BiometricService,
    MockBiometricAdapter,
)
from server.gravity.config import Settings
from server.gravity.database import Database
from server.gravity.membership import MembershipService
from server.gravity.notification import NotificationService


ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "biometric-attendance-test-secret-key-that-is-long-enough"


class MutableClock:
    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> float:
        return float(self.value)


class BiometricServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        root = Path(self.temporary.name)
        self.settings = Settings.load(
            root_dir=ROOT,
            environ={
                "SECRET_KEY": TEST_SECRET,
                "GRAVITY_DATA_DIR": str(root / "data"),
                "GRAVITY_LOG_DIR": str(root / "logs"),
                "GRAVITY_BACKUP_DIR": str(root / "backups"),
                "APP_BASE_URL": "http://127.0.0.1:8787",
            },
        )
        self.settings.ensure_directories()
        self.database = Database(self.settings.database_path, self.settings.migrations_dir)
        self.database.migrate()
        self.clock = MutableClock(int(datetime(2026, 9, 1, 6, 0, tzinfo=timezone.utc).timestamp()))
        self.admin = AdminService(self.database, self.settings, clock=self.clock)
        self.memberships = MembershipService(self.database, clock=self.clock)
        self.notifications = NotificationService(self.database, self.memberships, self.settings, clock=self.clock)
        with self.database.session() as connection:
            connection.execute(
                "INSERT INTO admin_users(id,username,password_hash,role,status,encrypted_totp_secret,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                ("admin-1", "owner", "x", "owner", "active", "x", self.clock.value, self.clock.value),
            )
        for plan_id in ("plan-basic-monthly", "plan-pro-monthly", "plan-elite-monthly"):
            self.memberships.update_plan(plan_id, {"status": "active"}, actor_admin_user_id="admin-1")
        self.software = AdminSoftwareService(
            self.database, self.memberships, self.admin, self.notifications, clock=self.clock
        )
        self.adapter = MockBiometricAdapter()
        self.biometric = BiometricService(
            self.database, self.settings, self.admin, clock=self.clock, adapters={"mock": self.adapter}
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create_device(self, **overrides) -> dict[str, object]:
        payload = {
            "name": "Gravity Entrance F09",
            "vendor": "zkteco",
            "model": "F09",
            "deviceIdentifier": "1",
            "connectionMode": "mock",
            "timezone": "Asia/Kolkata",
            "commKey": "123456",
        }
        payload.update(overrides)
        return self.biometric.create_device(payload, actor_admin_user_id="admin-1")["device"]

    def create_member(self, *, name: str = "Rahul Sharma", phone: str = "+919876543210", starts_at: int | None = None):
        body = {
            "displayName": name,
            "phone": phone,
            "planId": "plan-basic-monthly",
            "amountPaidPaise": 0,
            "paymentMethod": "cash",
        }
        if starts_at is not None:
            body["startsAt"] = starts_at
        return self.software.create_customer_bundle(body, actor_admin_user_id="admin-1")["customer"]

    def create_staff(self):
        return self.software.create_customer_bundle(
            {
                "personType": "staff",
                "displayName": "Swapnil Coach",
                "phone": "+919876543211",
                "designation": "trainer",
                "joinedAt": self.clock.value,
            },
            actor_admin_user_id="admin-1",
        )["customer"]

    def test_migration_creates_biometric_tables_and_secrets_are_encrypted(self) -> None:
        self.assertEqual(self.database.health(), {"database": "ok", "migrations": "13"})
        device = self.create_device()
        self.assertTrue(device["commKeyConfigured"])
        self.assertNotIn("commKey", device)
        with self.database.session() as connection:
            self.assertEqual(
                connection.execute("SELECT value FROM app_metadata WHERE key='schema_stage'").fetchone()[0],
                "biometric_attendance_v1",
            )
            encrypted = connection.execute(
                "SELECT comm_key_encrypted FROM biometric_devices WHERE id=?", (device["id"],)
            ).fetchone()[0]
            self.assertNotEqual(encrypted, "123456")
            self.assertGreater(connection.execute("SELECT COUNT(*) FROM attendance_events").fetchone()[0], -1)

    def test_mock_sync_users_events_and_status_failures(self) -> None:
        event_time = self.clock.value
        self.adapter.users = []
        self.adapter.events = [BiometricScanEvent("unknown-1", event_time, "fingerprint")]
        device = self.create_device()
        synced = self.biometric.sync_device(device["id"], actor_admin_user_id="admin-1")
        self.assertEqual(synced["stored"], 1)
        self.assertEqual(synced["unmatched"], 1)
        self.assertEqual(synced["device"]["status"], "online")
        self.adapter.mode = "offline"
        tested = self.biometric.test_connection(device["id"], actor_admin_user_id="admin-1")
        self.assertEqual(tested["status"], "offline")
        self.adapter.mode = "auth_failed"
        tested = self.biometric.test_connection(device["id"], actor_admin_user_id="admin-1")
        self.assertEqual(tested["status"], "authentication_failed")

    def test_mapping_unknown_scan_rebuilds_visit_for_member_and_staff_without_membership_cross_over(self) -> None:
        device = self.create_device()
        member = self.create_member()
        staff = self.create_staff()
        self.biometric.record_event(device["id"], BiometricScanEvent("101", self.clock.value, "fingerprint"))
        self.assertEqual(len(self.biometric.unmatched_activity()), 1)

        mapping = self.biometric.create_mapping(
            {"deviceId": device["id"], "deviceUserId": "101", "personId": member["id"]},
            actor_admin_user_id="admin-1",
        )["mapping"]
        self.assertEqual(mapping["person"]["personType"], "member")
        self.assertEqual(self.biometric.unmatched_activity(), [])
        visits = self.biometric.list_attendance(start_date="2026-09-01")["visits"]
        self.assertEqual(len(visits), 1)
        self.assertEqual(visits[0]["personId"], member["id"])
        self.assertEqual(visits[0]["membershipStatus"], "active")

        self.biometric.create_mapping(
            {"deviceId": device["id"], "deviceUserId": "staff-7", "personId": staff["id"]},
            actor_admin_user_id="admin-1",
        )
        staff_scan = self.clock.value + 600
        self.biometric.record_event(device["id"], BiometricScanEvent("staff-7", staff_scan, "fingerprint"))
        staff_rows = self.biometric.list_attendance(start_date="2026-09-01", person_type="staff")["visits"]
        self.assertEqual(staff_rows[0]["personId"], staff["id"])
        self.assertIsNone(staff_rows[0]["membershipStatus"])

        with self.assertRaises(BiometricConflict):
            self.biometric.create_mapping(
                {"deviceId": device["id"], "deviceUserId": "101", "personId": staff["id"]},
                actor_admin_user_id="admin-1",
            )
        removed = self.biometric.remove_mapping(mapping["id"], actor_admin_user_id="admin-1")
        self.assertTrue(removed["removed"])
        self.assertEqual(len(self.biometric.list_attendance(start_date="2026-09-01")["visits"]), 2)

    def test_duplicate_window_visit_gap_expired_member_and_kolkata_midnight(self) -> None:
        device = self.create_device(duplicateWindowSeconds=120, visitGapSeconds=14400)
        old_start = self.clock.value - 70 * 86400
        member = self.create_member(name="Expired Member", phone="+919876543212", starts_at=old_start)
        self.biometric.create_mapping(
            {"deviceId": device["id"], "deviceUserId": "201", "personId": member["id"]},
            actor_admin_user_id="admin-1",
        )

        first = int(datetime(2026, 9, 1, 18, 45, tzinfo=timezone.utc).timestamp())
        self.clock.value = first + 60 * 86400
        self.biometric.record_event(device["id"], BiometricScanEvent("201", first, "fingerprint", device_event_id="a"))
        self.biometric.record_event(device["id"], BiometricScanEvent("201", first + 60, "fingerprint", device_event_id="b"))
        self.biometric.record_event(device["id"], BiometricScanEvent("201", first + 3600, "fingerprint", device_event_id="c"))
        self.biometric.record_event(device["id"], BiometricScanEvent("201", first + 18100, "fingerprint", device_event_id="d"))

        result = self.biometric.list_attendance(start_date="2026-09-02", membership_status="expired")
        self.assertEqual(len(result["visits"]), 2)
        latest, earliest = result["visits"]
        self.assertEqual({latest["date"], earliest["date"]}, {"2026-09-02"})
        self.assertEqual(earliest["scanCount"], 3)
        self.assertEqual(earliest["membershipStatus"], "expired")
        with self.database.session() as connection:
            duplicate_count = connection.execute(
                "SELECT COUNT(*) FROM attendance_events WHERE device_user_id='201' AND is_duplicate=1"
            ).fetchone()[0]
        self.assertEqual(duplicate_count, 1)

    def test_scale_query_handles_year_window(self) -> None:
        device = self.create_device()
        member = self.create_member(name="Scale Member", phone="+919876543213")
        self.biometric.create_mapping(
            {"deviceId": device["id"], "deviceUserId": "301", "personId": member["id"]},
            actor_admin_user_id="admin-1",
        )
        base = int(datetime(2026, 1, 1, 2, 30, tzinfo=timezone.utc).timestamp())
        for day in range(365):
            self.biometric.record_event(
                device["id"],
                BiometricScanEvent("301", base + day * 86400, "fingerprint", device_event_id=f"scale-{day}"),
            )
        rows = self.biometric.list_attendance(start_date="2026-01-01", end_date="2026-12-31", limit=500)["visits"]
        self.assertEqual(len(rows), 365)
