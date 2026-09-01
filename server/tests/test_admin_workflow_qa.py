from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import hashlib
import hmac
import sqlite3
import unittest

from server.gravity.config import Settings
from server.gravity.database import Database
from server.gravity.membership import MembershipService
from server.gravity.notification import NotificationService
from server.gravity.operations import BackupManager
from server.gravity.payment import PaymentService


ROOT = Path(__file__).resolve().parents[2]
KEY_SECRET = "admin-workflow-razorpay-test-secret"


class MutableClock:
    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> float:
        return float(self.value)


class FakeProvider:
    @property
    def configured(self) -> bool:
        return True

    def create_order(self, *, amount_paise, currency, receipt, notes):
        return {
            "id": f"order_{receipt[-12:]}",
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt,
            "notes": notes,
        }


class AdminWorkflowAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.runtime = Path(self.temporary.name)
        self.settings = Settings.load(root_dir=ROOT, environ={
            "SECRET_KEY": "admin-workflow-qa-secret-long-enough",
            "GRAVITY_DATA_DIR": str(self.runtime / "data"),
            "GRAVITY_LOG_DIR": str(self.runtime / "logs"),
            "GRAVITY_BACKUP_DIR": str(self.runtime / "backups"),
            "APP_BASE_URL": "http://127.0.0.1:8787",
            "RAZORPAY_MODE": "test",
            "RAZORPAY_KEY_ID": "rzp_test_admin_workflow",
            "RAZORPAY_KEY_SECRET": KEY_SECRET,
            "RAZORPAY_WEBHOOK_SECRET": "admin-workflow-webhook-secret",
        })
        self.settings.ensure_directories()
        self.database = Database(self.settings.database_path, self.settings.migrations_dir)
        self.database.migrate()
        start = int(datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc).timestamp())
        self.clock = MutableClock(start)
        self.memberships = MembershipService(self.database, clock=self.clock)
        self.notifications = NotificationService(
            self.database, self.memberships, self.settings, clock=self.clock,
        )
        self.payments = PaymentService(
            self.database,
            self.settings,
            self.memberships,
            provider=FakeProvider(),
            clock=self.clock,
        )
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO admin_users(id,username,password_hash,role,status,encrypted_totp_secret,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                ("admin-qa", "qa-owner", "x", "owner", "active", "x", start, start),
            )
            # Current main has no admin customer-create command. This synthetic insert is
            # intentionally isolated to the temporary acceptance database.
            connection.execute(
                "INSERT INTO customers(id,status,display_name,email,phone_e164,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                ("customer-qa", "active", "Synthetic Member", "member@example.test", "+919000000001", start, start),
            )
            connection.commit()
        self.memberships.update_plan(
            "plan-basic-monthly", {"status": "active"}, actor_admin_user_id="admin-qa",
        )

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def checkout_signature(order_id: str, payment_id: str) -> str:
        return hmac.new(
            KEY_SECRET.encode("utf-8"),
            f"{order_id}|{payment_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def test_assign_pay_renew_history_suppression_and_backup_restore(self):
        first = self.memberships.create_membership(
            "customer-qa", "plan-basic-monthly", actor_admin_user_id="admin-qa",
        )
        self.assertEqual(first["status"], "active")

        self.clock.value = int(first["endsAt"]) - 7 * 86400
        scan = self.notifications.scan_expiring(7)
        self.assertEqual(scan["created"], 1)

        unsettled = self.payments.create_intent("customer-qa", "plan-basic-monthly")
        self.assertEqual(unsettled["status"], "created")
        payment_id = "pay_admin_workflow_001"
        paid = self.payments.verify_checkout(
            "customer-qa",
            unsettled["id"],
            razorpay_order_id=unsettled["providerOrderId"],
            razorpay_payment_id=payment_id,
            razorpay_signature=self.checkout_signature(unsettled["providerOrderId"], payment_id),
        )
        self.assertEqual(paid["payment"]["status"], "paid")
        self.assertEqual(paid["membership"]["status"], "scheduled")
        self.assertEqual(paid["membership"]["startsAt"], first["endsAt"])

        self.assertEqual(self.notifications.reconcile(), 1)
        reminders = self.notifications.list_admin()
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["state"], "suppressed")

        self.clock.value = int(first["endsAt"]) + 1
        summary = self.memberships.customer_summary("customer-qa")
        self.assertEqual(summary["current"]["id"], paid["membership"]["id"])
        self.assertIsNone(summary["upcoming"])
        self.assertEqual([item["id"] for item in summary["history"]], [first["id"]])
        self.assertEqual(summary["history"][0]["status"], "expired")

        with self.database.session() as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            connection.execute(
                "INSERT INTO membership_payments(id,membership_id,amount_paise,currency,method,paid_at,status,"
                "recorded_by_admin_user_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                ("manual-admin-workflow-001", first["id"], 12300, "INR", "cash", self.clock.value,
                 "recorded", "admin-qa", self.clock.value),
            )

        manager = BackupManager(self.settings, self.database)
        archive = Path(manager.create_backup("admin-acceptance")["path"])
        drill = manager.recovery_drill(archive)
        expected = {
            "customerRows": 1,
            "membershipRows": 2,
            "paymentRows": 1,
            "paidPaymentRows": 1,
            "paymentAmountPaise": 120000,
            "paidPaymentAmountPaise": 120000,
            "manualPaymentRows": 1,
            "recordedManualPaymentRows": 1,
            "manualPaymentAmountPaise": 12300,
            "recordedManualPaymentAmountPaise": 12300,
            "notificationReminderRows": 1,
            "notificationDeliveryRows": 6,
        }
        for key, value in expected.items():
            self.assertEqual(drill[key], value, key)

        restored = self.runtime / "restored" / "gravity.sqlite3"
        manager.restore_backup(archive, restored)
        with closing(sqlite3.connect(restored)) as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            counts = {
                "customers": connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
                "memberships": connection.execute("SELECT COUNT(*) FROM memberships").fetchone()[0],
                "payments": connection.execute("SELECT COUNT(*) FROM payment_intents").fetchone()[0],
                "manualPayments": connection.execute("SELECT COUNT(*) FROM membership_payments").fetchone()[0],
                "reminders": connection.execute("SELECT COUNT(*) FROM notification_reminders").fetchone()[0],
            }
            manual_balance = connection.execute(
                "SELECT COALESCE(SUM(amount_paise),0) FROM membership_payments WHERE status='recorded'"
            ).fetchone()[0]
            paid_balance = connection.execute(
                "SELECT COALESCE(SUM(amount_paise),0) FROM payment_intents WHERE status='paid'"
            ).fetchone()[0]
        self.assertEqual(counts, {"customers": 1, "memberships": 2, "payments": 1, "manualPayments": 1, "reminders": 1})
        self.assertEqual(paid_balance, 120000)
        self.assertEqual(manual_balance, 12300)

    def test_membership_and_renewal_failures_roll_back_partial_rows(self):
        with mock.patch.object(self.memberships, "_event", side_effect=RuntimeError("synthetic fault")):
            with self.assertRaisesRegex(RuntimeError, "synthetic fault"):
                self.memberships.create_membership(
                    "customer-qa", "plan-basic-monthly", actor_admin_user_id="admin-qa",
                )
        with self.database.session() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM memberships").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM membership_events").fetchone()[0], 0)

        existing = self.memberships.create_membership(
            "customer-qa", "plan-basic-monthly", actor_admin_user_id="admin-qa",
        )
        with mock.patch.object(self.memberships, "_event", side_effect=RuntimeError("renewal fault")):
            with self.assertRaisesRegex(RuntimeError, "renewal fault"):
                self.memberships.create_membership(
                    "customer-qa", "plan-basic-monthly", actor_admin_user_id="admin-qa",
                )
        with self.database.session() as connection:
            memberships = connection.execute("SELECT id FROM memberships").fetchall()
            events = connection.execute("SELECT membership_id FROM membership_events").fetchall()
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual([row[0] for row in memberships], [existing["id"]])
        self.assertTrue(events)
        self.assertTrue(all(row[0] == existing["id"] for row in events))


if __name__ == "__main__":
    unittest.main()
