from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import hmac
import json
import unittest

from server.gravity.config import Settings
from server.gravity.database import Database
from server.gravity.membership import MembershipService
from server.gravity.payment import (
    PaymentConflict,
    PaymentService,
    PaymentUnavailable,
    PaymentVerificationError,
)


ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "phase-six-payment-test-secret-long-enough"
KEY_SECRET = "rzp_test_key_secret_for_gravity"
WEBHOOK_SECRET = "rzp_test_webhook_secret_for_gravity"


class MutableClock:
    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> float:
        return float(self.value)

class FakeProvider:
    def __init__(self) -> None:
        self.orders = []
        self.counter = 0

    @property
    def configured(self) -> bool:
        return True

    def create_order(self, *, amount_paise, currency, receipt, notes):
        self.counter += 1
        order = {
            "id": f"order_test_{self.counter:03d}",
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt,
            "notes": notes,
        }
        self.orders.append(order)
        return order


class PaymentServiceTests(unittest.TestCase):
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
                "RAZORPAY_MODE": "test",
                "RAZORPAY_KEY_ID": "rzp_test_gravity",
                "RAZORPAY_KEY_SECRET": KEY_SECRET,
                "RAZORPAY_WEBHOOK_SECRET": WEBHOOK_SECRET,
            },
        )
        self.settings.ensure_directories()
        self.database = Database(self.settings.database_path, self.settings.migrations_dir)
        self.database.migrate()
        start = int(datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc).timestamp())
        self.clock = MutableClock(start)
        self.memberships = MembershipService(self.database, clock=self.clock)
        self.provider = FakeProvider()
        self.service = PaymentService(
            self.database, self.settings, self.memberships,
            provider=self.provider, clock=self.clock,
        )
        with self.database.session() as connection:
            connection.execute(
                "INSERT INTO customers(id,status,display_name,email,phone_e164,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                ("customer-1", "active", "Customer One", "one@example.test", "+919000000001", start, start),
            )
            connection.execute(
                "INSERT INTO admin_users(id,username,password_hash,role,status,encrypted_totp_secret,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                ("admin-1", "owner", "x", "owner", "active", "x", start, start),
            )
        self.memberships.update_plan(
            "plan-basic-monthly", {"status": "active"}, actor_admin_user_id="admin-1",
        )
    def tearDown(self) -> None:
        self.temporary.cleanup()

    def checkout_signature(self, order_id: str, payment_id: str) -> str:
        return hmac.new(
            KEY_SECRET.encode("utf-8"),
            f"{order_id}|{payment_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def webhook(self, event_id: str, event: str, order_id: str, payment_id: str, amount=99900):
        payload = {
            "event": event,
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": order_id,
                        "amount": amount,
                        "currency": "INR",
                    }
                }
            },
        }
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(WEBHOOK_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        return raw, signature, event_id
    def test_intent_uses_server_plan_snapshot(self) -> None:
        intent = self.service.create_intent("customer-1", "plan-basic-monthly")
        self.assertEqual(intent["amountPaise"], 99900)
        self.assertEqual(intent["currency"], "INR")
        self.assertEqual(intent["status"], "created")
        self.assertEqual(intent["checkout"]["keyId"], "rzp_test_gravity")
        self.assertEqual(self.provider.orders[0]["amount"], 99900)
        self.memberships.update_plan(
            "plan-basic-monthly", {"pricePaise": 199900}, actor_admin_user_id="admin-1",
        )
        stored = self.service.get_intent("customer-1", intent["id"])
        self.assertEqual(stored["amountPaise"], 99900)

    def test_checkout_signature_is_verified_and_idempotent(self) -> None:
        intent = self.service.create_intent("customer-1", "plan-basic-monthly")
        order_id = intent["providerOrderId"]
        payment_id = "pay_test_001"
        signature = self.checkout_signature(order_id, payment_id)
        with self.assertRaises(PaymentVerificationError):
            self.service.verify_checkout(
                "customer-1", intent["id"],
                razorpay_order_id=order_id,
                razorpay_payment_id="pay_bad_001",
                razorpay_signature="0" * 64,
            )
        result = self.service.verify_checkout(
            "customer-1", intent["id"],
            razorpay_order_id=order_id,
            razorpay_payment_id=payment_id,
            razorpay_signature=signature,
        )
        self.assertEqual(result["payment"]["status"], "paid")
        self.assertEqual(result["membership"]["source"], "payment")
        self.assertEqual(result["invoice"]["status"], "pending_business_identity")
        again = self.service.verify_checkout(
            "customer-1", intent["id"],
            razorpay_order_id=order_id,
            razorpay_payment_id=payment_id,
            razorpay_signature=signature,
        )
        self.assertEqual(again["membership"]["id"], result["membership"]["id"])
        with self.assertRaises(PaymentConflict):
            self.service.verify_checkout(
                "customer-1", intent["id"],
                razorpay_order_id=order_id,
                razorpay_payment_id="pay_test_002",
                razorpay_signature="0" * 64,
            )

    def test_webhook_dedupes_and_recovers_failed_attempt(self) -> None:
        intent = self.service.create_intent("customer-1", "plan-basic-monthly")
        order_id = intent["providerOrderId"]
        failed_raw, failed_sig, failed_event = self.webhook(
            "evt_failed_001", "payment.failed", order_id, "pay_failed_001",
        )
        failed = self.service.process_webhook(failed_raw, failed_sig, failed_event)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(self.service.get_intent("customer-1", intent["id"])["status"], "failed")

        paid_raw, paid_sig, paid_event = self.webhook(
            "evt_paid_001", "payment.captured", order_id, "pay_captured_001",
        )
        paid = self.service.process_webhook(paid_raw, paid_sig, paid_event)
        self.assertTrue(paid["processed"])
        self.assertEqual(paid["payment"]["status"], "paid")
        self.assertEqual(paid["membership"]["source"], "payment")
        duplicate = self.service.process_webhook(paid_raw, paid_sig, paid_event)
        self.assertEqual(duplicate, {"duplicate": True, "processed": False})
        tampered = paid_raw.replace(b"99900", b"99901")
        with self.assertRaises(PaymentVerificationError):
            self.service.process_webhook(tampered, paid_sig, "evt_tampered_001")

    def test_webhook_amount_mismatch_is_rejected(self) -> None:
        intent = self.service.create_intent("customer-1", "plan-basic-monthly")
        raw, signature, event_id = self.webhook(
            "evt_mismatch_001", "payment.captured",
            intent["providerOrderId"], "pay_mismatch_001", amount=100,
        )
        with self.assertRaises(PaymentVerificationError):
            self.service.process_webhook(raw, signature, event_id)
        self.assertEqual(self.service.get_intent("customer-1", intent["id"])["status"], "created")

    def test_checkout_fails_closed_without_keys(self) -> None:
        root = Path(self.temporary.name)
        disabled = Settings.load(
            root_dir=ROOT,
            environ={
                "SECRET_KEY": TEST_SECRET,
                "GRAVITY_DATA_DIR": str(root / "disabled-data"),
                "GRAVITY_LOG_DIR": str(root / "disabled-logs"),
                "GRAVITY_BACKUP_DIR": str(root / "disabled-backups"),
                "RAZORPAY_KEY_ID": "",
                "RAZORPAY_KEY_SECRET": "",
                "RAZORPAY_WEBHOOK_SECRET": "",
            },
        )
        disabled.ensure_directories()
        db = Database(disabled.database_path, disabled.migrations_dir)
        db.migrate()
        memberships = MembershipService(db, clock=self.clock)
        service = PaymentService(db, disabled, memberships, provider=FakeProvider(), clock=self.clock)
        self.assertFalse(service.public_config()["enabled"])
        self.assertIsNone(service.public_config()["keyId"])
        with self.assertRaises(PaymentUnavailable):
            service.create_intent("customer-1", "plan-basic-monthly")
        with db.session() as connection:
            count = connection.execute("SELECT COUNT(*) FROM payment_intents").fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
