from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from server.gravity.config import Settings
from server.gravity.database import Database
from server.gravity.delivery import (
    DeliveryAdapterError, NotificationDispatcher, SMSDeliveryAdapter, WhatsAppDeliveryAdapter,
)
from server.gravity.membership import MembershipService
from server.gravity.notification import NotificationService

ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "notification-fanout-secret-key-long-enough"


class MutableClock:
    def __init__(self, value: int) -> None:
        self.value = value
    def __call__(self) -> float:
        return float(self.value)


class FakeAdapter:
    def __init__(self, channel: str, *, fail: bool = False) -> None:
        self.channel = channel
        self.fail = fail
        self.sent: list[dict[str, str]] = []
    def send(self, *, recipient: str, subject: str, body: str, context: dict[str, object] | None = None) -> str | None:
        if self.fail:
            raise DeliveryAdapterError(f"{self.channel}_provider_down")
        self.sent.append({"recipient": recipient, "subject": subject, "body": body})
        return f"{self.channel}-message-{len(self.sent)}"


class NotificationFanoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        runtime = Path(self.temporary.name)
        self.settings = Settings.load(root_dir=ROOT, environ={
            "SECRET_KEY": TEST_SECRET,
            "GRAVITY_DATA_DIR": str(runtime / "data"),
            "GRAVITY_LOG_DIR": str(runtime / "logs"),
            "GRAVITY_BACKUP_DIR": str(runtime / "backups"),
            "OWNER_EMAIL": "owner@example.test",
            "OWNER_PHONE": "+919111111111",
            "OWNER_WHATSAPP": "+919222222222",
        })
        self.settings.ensure_directories()
        self.database = Database(self.settings.database_path, self.settings.migrations_dir)
        self.database.migrate()
        start = int(datetime(2026, 1, 31, 12, 0, tzinfo=timezone.utc).timestamp())
        self.clock = MutableClock(start)
        self.memberships = MembershipService(self.database, clock=self.clock)
        self.notifications = NotificationService(
            self.database, self.memberships, self.settings, clock=self.clock
        )
        with self.database.session() as connection:
            connection.execute(
                "INSERT INTO customers(id,status,display_name,email,phone_e164,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                ("customer-1", "active", "Member One", "member@example.com", "+919999999999", start, start),
            )
            connection.execute(
                "INSERT INTO admin_users(id,username,password_hash,role,status,encrypted_totp_secret,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                ("admin-1", "owner", "x", "owner", "active", "x", start, start),
            )
        self.memberships.update_plan("plan-basic-monthly", {"status": "active"}, actor_admin_user_id="admin-1")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create_membership(self) -> dict[str, object]:
        return self.memberships.create_membership(
            "customer-1", "plan-basic-monthly", actor_admin_user_id="admin-1"
        )

    def test_four_expiry_windows_are_independent_and_owner_is_hidden_from_customer_api(self) -> None:
        membership = self.create_membership()
        ends_at = int(membership["endsAt"])
        for days in (7, 3, 1):
            self.clock.value = ends_at - days * 86400
            result = self.notifications.scan_expiring(days)
            self.assertEqual((result["daysBefore"], result["created"]), (days, 1))
        self.clock.value = ends_at + 60
        result = self.notifications.scan_expiring(0)
        self.assertEqual((result["daysBefore"], result["created"]), (0, 1))
        admin_rows = self.notifications.list_admin()
        self.assertEqual({row["triggerDays"] for row in admin_rows}, {7, 3, 1, 0})
        expiry_row = next(row for row in admin_rows if row["triggerDays"] == 0)
        self.assertEqual(len(expiry_row["deliveries"]), 6)
        self.assertEqual({d["recipientRole"] for d in expiry_row["deliveries"]}, {"customer", "owner"})
        for row in self.notifications.list_customer("customer-1"):
            self.assertTrue(all(d["recipientRole"] == "customer" for d in row["deliveries"]))

    def test_non_overlapping_catchup_bands_prevent_message_bursts(self) -> None:
        membership = self.create_membership()
        self.clock.value = int(membership["endsAt"]) - 2 * 86400
        self.assertEqual(self.notifications.scan_expiring(7)["created"], 0)
        self.assertEqual(self.notifications.scan_expiring(3)["created"], 1)
        self.assertEqual(self.notifications.scan_expiring(1)["created"], 0)

    def test_all_six_deliveries_send_and_complete_only_after_all_are_terminal(self) -> None:
        membership = self.create_membership()
        self.clock.value = int(membership["endsAt"]) - 5 * 86400
        self.assertEqual(self.notifications.scan_expiring(7)["created"], 1)
        adapters = {channel: FakeAdapter(channel) for channel in ("email", "sms", "whatsapp")}
        result = NotificationDispatcher(self.notifications, adapters).process_due()
        self.assertEqual(result, {"attempted": 6, "sent": 6, "failed": 0, "skipped": 0})
        reminder = self.notifications.list_admin()[0]
        self.assertEqual(reminder["state"], "completed")
        self.assertTrue(all(row["status"] == "sent" for row in reminder["deliveries"]))
        self.assertEqual({item["recipient"] for item in adapters["email"].sent}, {"member@example.com", "owner@example.test"})
        self.assertEqual({item["recipient"] for item in adapters["sms"].sent}, {"+919999999999", "+919111111111"})
        self.assertEqual({item["recipient"] for item in adapters["whatsapp"].sent}, {"+919999999999", "+919222222222"})

    def test_missing_owner_email_is_explicit_without_storing_owner_contact_values(self) -> None:
        settings = replace(self.settings, owner_email="")
        service = NotificationService(self.database, self.memberships, settings, clock=self.clock)
        membership = self.create_membership()
        self.clock.value = int(membership["endsAt"]) - 5 * 86400
        self.assertEqual(service.scan_expiring(7)["created"], 1)
        reminder = service.list_admin()[0]
        owner_email = next(d for d in reminder["deliveries"] if d["recipientRole"] == "owner" and d["channel"] == "email")
        self.assertEqual(owner_email["status"], "missing_recipient")
        with self.database.session() as connection:
            payload = connection.execute("SELECT payload_json FROM notification_reminders LIMIT 1").fetchone()[0]
            refs = [dict(row) for row in connection.execute("SELECT recipient_role,recipient_ref FROM notification_deliveries")]
        serialized = payload + json.dumps(refs, sort_keys=True)
        for secret_value in ("member@example.com", "+919999999999", "+919111111111", "+919222222222"):
            self.assertNotIn(secret_value, serialized)

    def test_sms_and_whatsapp_provider_boundaries_wrap_failures_safely(self) -> None:
        sent: list[tuple[str, str]] = []
        sms = SMSDeliveryAdapter(lambda recipient, body: sent.append((recipient, body)) or "sms-1")
        wa = WhatsAppDeliveryAdapter(lambda recipient, body: "wa-1")
        self.assertEqual(sms.send(recipient="+919999999999", subject="x", body="hello"), "sms-1")
        self.assertEqual(wa.send(recipient="+919999999999", subject="x", body="hello"), "wa-1")
        self.assertEqual(sent[0][0], "+919999999999")
        broken = SMSDeliveryAdapter(lambda _recipient, _body: (_ for _ in ()).throw(RuntimeError("secret provider detail")))
        with self.assertRaises(DeliveryAdapterError) as caught:
            broken.send(recipient="+919999999999", subject="x", body="hello")
        self.assertEqual(caught.exception.code, "sms_delivery_failed")

    def test_disabled_customer_suppresses_pending_fanout(self) -> None:
        membership = self.create_membership()
        self.clock.value = int(membership["endsAt"]) - 5 * 86400
        self.assertEqual(self.notifications.scan_expiring(7)["created"], 1)
        with self.database.session() as connection:
            connection.execute("UPDATE customers SET status='disabled' WHERE id='customer-1'")
        self.assertEqual(self.notifications.reconcile(), 1)
        self.assertEqual(self.notifications.list_admin()[0]["state"], "suppressed")
        self.assertEqual(self.notifications.due_deliveries(), [])

    def test_expiry_day_is_not_created_when_renewal_exists(self) -> None:
        first = self.create_membership()
        self.create_membership()
        self.clock.value = int(first["endsAt"]) + 60
        result = self.notifications.scan_expiring(0)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["suppressedRenewed"], 1)
        self.assertEqual(self.notifications.list_admin(), [])


if __name__ == "__main__":
    unittest.main()
