from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from server.gravity.config import Settings
from server.gravity.database import Database
from server.gravity.delivery import DeliveryAdapterError, MSG91SMSAdapter, MetaWhatsAppAdapter, NotificationDispatcher, SMTPEmailAdapter
from server.gravity.membership import MembershipService
from server.gravity.notification import NotificationService

ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "phase-nine-delivery-secret-long-enough"


class MutableClock:
    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> float:
        return float(self.value)


class FakeAdapter:
    channel = "email"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[dict[str, str]] = []

    def send(self, *, recipient: str, subject: str, body: str, context: dict[str, object] | None = None) -> str | None:
        if self.fail:
            raise DeliveryAdapterError("fake_provider_down")
        self.sent.append({"recipient": recipient, "subject": subject, "body": body})
        return "fake-message-1"


class DeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        runtime = Path(self.temporary.name)
        self.settings = Settings.load(root_dir=ROOT, environ={
            "SECRET_KEY": TEST_SECRET,
            "GRAVITY_DATA_DIR": str(runtime / "data"),
            "GRAVITY_LOG_DIR": str(runtime / "logs"),
            "GRAVITY_BACKUP_DIR": str(runtime / "backups"),
        })
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
                "INSERT INTO admin_users(id,username,password_hash,role,status,encrypted_totp_secret,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                ("admin-1", "owner", "x", "owner", "active", "x", start, start),
            )
        self.memberships.update_plan(
            "plan-basic-monthly", {"status": "active"}, actor_admin_user_id="admin-1"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def prepare_reminder(self) -> None:
        membership = self.memberships.create_membership(
            "customer-1", "plan-basic-monthly", actor_admin_user_id="admin-1"
        )
        self.clock.value = int(membership["endsAt"]) - 5 * 86400
        result = self.notifications.scan_expiring(7)
        self.assertEqual(result["created"], 1)

    def test_dispatch_resolves_contact_at_send_time_without_persisting_it(self) -> None:
        self.prepare_reminder()
        adapter = FakeAdapter()
        result = NotificationDispatcher(self.notifications, {"email": adapter}).process_due()
        self.assertEqual(result, {"attempted": 1, "sent": 1, "failed": 0, "skipped": 0})
        self.assertEqual(adapter.sent[0]["recipient"], "member@example.com")
        self.assertIn("membership expiry reminder", adapter.sent[0]["subject"].lower())
        reminder = self.notifications.list_admin()[0]
        self.assertEqual(reminder["state"], "pending")
        statuses = {item["channel"]: item["status"] for item in reminder["deliveries"] if item["recipientRole"] == "customer"}
        self.assertEqual(statuses["email"], "sent")
        self.assertEqual(statuses["sms"], "blocked_external_config")
        self.assertEqual(statuses["whatsapp"], "blocked_external_config")
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT recipient_ref,provider_message_id FROM notification_deliveries ORDER BY channel"
            ).fetchall()
            payload = connection.execute(
                "SELECT payload_json FROM notification_reminders LIMIT 1"
            ).fetchone()["payload_json"]
        serialized = str([tuple(row) for row in rows]) + payload
        self.assertNotIn("member@example.com", serialized)
        self.assertNotIn("+919999999999", serialized)

    def test_smtp_adapter_uses_starttls_and_returns_message_id_without_network(self) -> None:
        settings = replace(
            self.settings, smtp_host="smtp.example.test", smtp_port=587, smtp_security="starttls",
            smtp_username="mailer", smtp_password="secret-password", email_from="gym@example.test",
        )
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        with patch("server.gravity.delivery.smtplib.SMTP", return_value=client) as smtp:
            message_id = SMTPEmailAdapter(settings).send(
                recipient="member@example.com", subject="Reminder", body="Membership reminder",
            )
        smtp.assert_called_once_with("smtp.example.test", 587, timeout=15)
        client.starttls.assert_called_once_with()
        client.login.assert_called_once_with("mailer", "secret-password")
        client.send_message.assert_called_once()
        self.assertTrue(str(message_id).startswith("<"))

    def test_meta_whatsapp_adapter_sends_role_template_without_network(self) -> None:
        settings = replace(
            self.settings,
            whatsapp_provider="meta",
            whatsapp_access_token="meta-secret",
            whatsapp_phone_number_id="phone-id",
            whatsapp_graph_version="v26.0",
            whatsapp_customer_template="gravity_expiry_customer",
            whatsapp_owner_template="gravity_expiry_owner",
            whatsapp_template_language="en_US",
        )
        context = {
            "recipientRole": "customer", "displayName": "Member One", "triggerDays": 7,
            "payload": {"planName": "Monthly", "endsAt": self.clock.value + 7 * 86400, "membershipNumber": "GF-1"},
        }
        with patch("server.gravity.delivery._post_json", return_value={"messages": [{"id": "wamid.test"}]}) as post:
            message_id = MetaWhatsAppAdapter(settings).send(
                recipient="+919999999999", subject="ignored", body="ignored", context=context,
            )
        self.assertEqual(message_id, "wamid.test")
        request = post.call_args.kwargs
        self.assertIn("/v26.0/phone-id/messages", post.call_args.args[0])
        self.assertEqual(request["payload"]["to"], "919999999999")
        self.assertEqual(request["payload"]["template"]["name"], "gravity_expiry_customer")
        self.assertEqual(len(request["payload"]["template"]["components"][0]["parameters"]), 5)

    def test_msg91_sms_adapter_sends_dlt_flow_without_network(self) -> None:
        settings = replace(
            self.settings,
            sms_provider="msg91",
            sms_api_key="msg91-secret",
            sms_customer_flow_id="flow-customer",
            sms_owner_flow_id="flow-owner",
            sms_sender_id="GRAVTY",
        )
        context = {
            "recipientRole": "owner", "displayName": "Member One", "triggerDays": 3,
            "payload": {"planName": "Monthly", "endsAt": self.clock.value + 3 * 86400, "membershipNumber": "GF-1"},
        }
        with patch("server.gravity.delivery._post_json", return_value={"type": "success", "message": "request-1"}) as post:
            message_id = MSG91SMSAdapter(settings).send(
                recipient="+919888888888", subject="ignored", body="ignored", context=context,
            )
        self.assertEqual(message_id, "request-1")
        request = post.call_args.kwargs
        self.assertEqual(post.call_args.args[0], "https://control.msg91.com/api/v5/flow")
        self.assertEqual(request["payload"]["flow_id"], "flow-owner")
        self.assertEqual(request["payload"]["sender"], "GRAVTY")
        self.assertEqual(request["payload"]["recipients"][0]["mobiles"], "919888888888")
        self.assertEqual(set(request["payload"]["recipients"][0]), {"mobiles", "name", "expiry"})

    def test_dispatch_failure_uses_retry_state_without_leaking_exception(self) -> None:
        self.prepare_reminder()
        adapter = FakeAdapter(fail=True)
        result = NotificationDispatcher(self.notifications, {"email": adapter}).process_due()
        self.assertEqual(result, {"attempted": 1, "sent": 0, "failed": 1, "skipped": 0})
        reminder = self.notifications.list_admin()[0]
        email = next(item for item in reminder["deliveries"] if item["channel"] == "email")
        self.assertEqual(email["status"], "failed")
        self.assertEqual(email["attemptCount"], 1)
        self.assertEqual(email["lastErrorCode"], "fake_provider_down")


if __name__ == "__main__":
    unittest.main()
