from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from server.gravity.config import Settings
from server.gravity.database import Database
from server.gravity.membership import MembershipService
from server.gravity.notification import NotificationService

ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "phase-five-notification-secret-key-long-enough"

class MutableClock:
    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> float:
        return float(self.value)

class NotificationServiceTests(unittest.TestCase):
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
        start = int(datetime(2026, 1, 31, 12, 0, tzinfo=timezone.utc).timestamp())
        self.clock = MutableClock(start)
        self.memberships = MembershipService(self.database, clock=self.clock)
        self.notifications = NotificationService(self.database, self.memberships, clock=self.clock)
        with self.database.session() as connection:
            connection.execute(
                "INSERT INTO customers(id,status,display_name,email,phone_e164,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                ("customer-1", "active", "Member One", "member@example.com", "+919999999999", start, start),
            )
            connection.execute(
                "INSERT INTO customers(id,status,display_name,created_at,updated_at) VALUES (?,?,?,?,?)",
                ("customer-2", "active", "Member Two", start, start),
            )
            connection.execute(
                "INSERT INTO admin_users(id,username,password_hash,role,status,encrypted_totp_secret,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                ("admin-1", "owner", "x", "owner", "active", "x", start, start),
            )
        self.memberships.update_plan(
            "plan-basic-monthly", {"status": "active"}, actor_admin_user_id="admin-1"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def expiring_membership(self, customer_id: str = "customer-1") -> dict[str, object]:
        membership = self.memberships.create_membership(
            customer_id,
            "plan-basic-monthly",
            actor_admin_user_id="admin-1",
        )
        self.clock.value = int(membership["endsAt"]) - 5 * 86400
        return membership

    def test_scan_dedupes_and_stores_no_raw_contact_values(self) -> None:
        membership = self.expiring_membership()
        first = self.notifications.scan_expiring(7)
        second = self.notifications.scan_expiring(7)
        self.assertEqual(first["created"], 1)
        self.assertEqual(second["deduped"], 1)
        reminders = self.notifications.list_admin()
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["membershipId"], membership["id"])
        statuses = {item["channel"]: item["status"] for item in reminders[0]["deliveries"] if item["recipientRole"] == "customer"}
        self.assertEqual(statuses, {
            "email": "blocked_external_config",
            "sms": "blocked_external_config",
            "whatsapp": "blocked_external_config",
        })
        with self.database.session() as connection:
            reminder = connection.execute(
                "SELECT payload_json FROM notification_reminders LIMIT 1"
            ).fetchone()
            deliveries = connection.execute(
                "SELECT channel,recipient_ref FROM notification_deliveries ORDER BY channel"
            ).fetchall()
        self.assertNotIn("member@example.com", reminder["payload_json"])
        self.assertNotIn("+919999999999", reminder["payload_json"])
        serialized = json.dumps([dict(row) for row in deliveries])
        self.assertNotIn("member@example.com", serialized)
        self.assertNotIn("+919999999999", serialized)

    def test_renewal_suppresses_expiry_reminder(self) -> None:
        first = self.memberships.create_membership(
            "customer-1", "plan-basic-monthly", actor_admin_user_id="admin-1"
        )
        self.memberships.create_membership(
            "customer-1", "plan-basic-monthly", actor_admin_user_id="admin-1"
        )
        self.clock.value = int(first["endsAt"]) - 5 * 86400
        result = self.notifications.scan_expiring(7)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["suppressedRenewed"], 1)
        self.assertEqual(self.notifications.list_admin(), [])

    def test_reconcile_suppresses_after_late_renewal(self) -> None:
        membership = self.expiring_membership()
        result = self.notifications.scan_expiring(7)
        self.assertEqual(result["created"], 1)
        self.memberships.create_membership(
            "customer-1", "plan-basic-monthly", actor_admin_user_id="admin-1"
        )
        self.assertEqual(self.notifications.reconcile(), 1)
        reminders = self.notifications.list_admin()
        self.assertEqual(reminders[0]["state"], "suppressed")
        self.assertEqual(reminders[0]["membershipId"], membership["id"])

    def test_missing_recipient_is_recorded_without_contact_copy(self) -> None:
        self.expiring_membership("customer-2")
        self.notifications.scan_expiring(7)
        reminders = self.notifications.list_admin()
        statuses = {item["channel"]: item["status"] for item in reminders[0]["deliveries"] if item["recipientRole"] == "customer"}
        self.assertEqual(statuses, {
            "email": "missing_recipient",
            "sms": "missing_recipient",
            "whatsapp": "missing_recipient",
        })
        self.assertFalse(reminders[0]["customer"]["emailAvailable"])
        self.assertFalse(reminders[0]["customer"]["phoneAvailable"])

    def test_retry_backoff_and_success_complete_reminder(self) -> None:
        self.expiring_membership()
        self.notifications.scan_expiring(7)
        reminder = self.notifications.list_admin()[0]
        email = next(item for item in reminder["deliveries"] if item["channel"] == "email")
        queued = self.notifications.queue_delivery(str(email["id"]))
        self.assertEqual(queued["status"], "queued")
        failed = self.notifications.record_delivery_attempt(
            str(email["id"]), success=False, error_code="smtp_timeout"
        )
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["attemptCount"], 1)
        self.assertEqual(int(failed["nextAttemptAt"]), self.clock.value + 3600)
        self.clock.value = int(failed["nextAttemptAt"])
        due = self.notifications.due_deliveries()
        self.assertEqual([row["id"] for row in due], [email["id"]])
        sent = self.notifications.record_delivery_attempt(
            str(email["id"]), success=True, provider_message_id="provider-001"
        )
        self.assertEqual(sent["status"], "sent")
        self.assertEqual(sent["attemptCount"], 2)
        self.assertEqual(self.notifications.list_admin()[0]["state"], "pending")


if __name__ == "__main__":
    unittest.main()
