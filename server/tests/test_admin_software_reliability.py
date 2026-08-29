"""Chat 3 acceptance coverage for Chat 1's migration-010 Admin Software contract.

The test class is intentionally skipped until the migration-010 service is present on
this branch. It becomes active automatically once Chat 1's implementation is merged.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import unittest

from server.gravity.admin import AdminService
from server.gravity.config import Settings
from server.gravity.database import Database
from server.gravity.membership import MembershipService
from server.gravity.notification import NotificationService

try:
    from server.gravity.admin_software import (
        AdminSoftwareConflict,
        AdminSoftwareService,
    )
except ModuleNotFoundError:
    ADMIN_SOFTWARE_AVAILABLE = False
else:
    ADMIN_SOFTWARE_AVAILABLE = True


ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "admin-software-reliability-test-secret-long-enough"


class MutableClock:
    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> float:
        return float(self.value)


@unittest.skipUnless(ADMIN_SOFTWARE_AVAILABLE, "migration 010 Admin Software service is not integrated")
class AdminSoftwareReliabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        runtime = Path(self.temporary.name)
        self.settings = Settings.load(
            root_dir=ROOT,
            environ={
                "SECRET_KEY": TEST_SECRET,
                "GRAVITY_DATA_DIR": str(runtime / "data"),
                "GRAVITY_LOG_DIR": str(runtime / "logs"),
                "GRAVITY_BACKUP_DIR": str(runtime / "backups"),
                "APP_BASE_URL": "http://127.0.0.1:8787",
            },
        )
        self.settings.ensure_directories()
        self.database = Database(self.settings.database_path, self.settings.migrations_dir)
        self.database.migrate()
        self.clock = MutableClock(int(datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc).timestamp()))
        self.admin = AdminService(self.database, self.settings, clock=self.clock)
        self.memberships = MembershipService(self.database, clock=self.clock)
        self.notifications = NotificationService(
            self.database, self.memberships, self.settings, clock=self.clock,
        )
        with self.database.session() as connection:
            connection.execute(
                "INSERT INTO admin_users(id,username,password_hash,role,status,encrypted_totp_secret,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                ("admin-qa", "qa-owner", "x", "owner", "active", "x", self.clock.value, self.clock.value),
            )
        for plan_id in ("plan-basic-monthly", "plan-pro-monthly", "plan-elite-monthly"):
            self.memberships.update_plan(plan_id, {"status": "active"}, actor_admin_user_id="admin-qa")
        self.service = AdminSoftwareService(
            self.database,
            self.memberships,
            self.admin,
            self.notifications,
            clock=self.clock,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def customer_payload(phone: str, *, initial_payment: int = 30_000) -> dict[str, object]:
        return {
            "displayName": "Synthetic Gym Member",
            "phone": phone,
            "planId": "plan-basic-monthly",
            "amountPaidPaise": initial_payment,
            "paymentMethod": "cash",
        }

    def create_customer(self, phone: str = "+919800000001", *, initial_payment: int = 30_000):
        return self.service.create_customer_bundle(
            self.customer_payload(phone, initial_payment=initial_payment),
            actor_admin_user_id="admin-qa",
        )

    def database_counts(self) -> dict[str, int]:
        with self.database.session() as connection:
            return {
                "customers": connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
                "profiles": connection.execute("SELECT COUNT(*) FROM customer_profiles").fetchone()[0],
                "memberships": connection.execute("SELECT COUNT(*) FROM memberships").fetchone()[0],
                "payments": connection.execute("SELECT COUNT(*) FROM membership_payments").fetchone()[0],
                "reminders": connection.execute("SELECT COUNT(*) FROM notification_reminders").fetchone()[0],
            }

    def test_golden_customer_fee_renewal_history_and_suppression_workflow(self) -> None:
        created = self.create_customer()
        customer_id = created["customer"]["id"]
        first_membership = created["membership"]
        self.assertEqual(self.database_counts(), {
            "customers": 1, "profiles": 1, "memberships": 1, "payments": 1, "reminders": 0,
        })
        self.assertEqual(created["paymentSummary"], {
            "totalPaise": 99900, "paidPaise": 30000, "pendingPaise": 69900,
        })

        second_payment = self.service.record_payment(
            first_membership["id"],
            {"amountPaise": 40_000, "method": "upi"},
            actor_admin_user_id="admin-qa",
        )
        self.assertEqual(second_payment["summary"]["pendingPaise"], 29900)
        self.assertEqual(self.database_counts()["payments"], 2)

        self.clock.value = int(first_membership["endsAt"]) - 6 * 86400
        self.assertEqual(self.notifications.scan_expiring(7)["created"], 1)
        renewal = self.service.renew_membership(
            customer_id,
            {"planId": "plan-pro-monthly", "amountPaise": 50_000, "paymentMethod": "cash"},
            actor_admin_user_id="admin-qa",
        )
        self.assertEqual(renewal["membership"]["status"], "scheduled")
        self.assertEqual(renewal["paymentSummary"], {
            "totalPaise": 149900, "paidPaise": 50000, "pendingPaise": 99900,
        })
        self.assertEqual(self.database_counts(), {
            "customers": 1, "profiles": 1, "memberships": 2, "payments": 3, "reminders": 1,
        })
        with self.database.session() as connection:
            reminder = connection.execute(
                "SELECT state FROM notification_reminders WHERE membership_id=?",
                (first_membership["id"],),
            ).fetchone()
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(reminder["state"], "suppressed")

        self.clock.value = int(first_membership["endsAt"]) + 1
        detail = self.service.customer_detail(customer_id)
        self.assertEqual(detail["membership"]["current"]["id"], renewal["membership"]["id"])
        self.assertEqual([item["id"] for item in detail["membership"]["history"]], [first_membership["id"]])
        self.assertEqual(detail["membership"]["history"][0]["status"], "expired")

    def test_customer_and_initial_membership_failure_roll_back_together(self) -> None:
        with mock.patch.object(
            self.memberships,
            "_create_membership_connection",
            side_effect=RuntimeError("membership fault"),
        ):
            with self.assertRaisesRegex(RuntimeError, "membership fault"):
                self.create_customer(phone="+919800000002", initial_payment=0)
        self.assertEqual(self.database_counts(), {
            "customers": 0, "profiles": 0, "memberships": 0, "payments": 0, "reminders": 0,
        })

    def test_customer_membership_and_initial_payment_failure_roll_back_together(self) -> None:
        with mock.patch.object(
            self.service,
            "_record_payment_connection",
            side_effect=RuntimeError("payment fault"),
        ):
            with self.assertRaisesRegex(RuntimeError, "payment fault"):
                self.create_customer(phone="+919800000003", initial_payment=10_000)
        self.assertEqual(self.database_counts(), {
            "customers": 0, "profiles": 0, "memberships": 0, "payments": 0, "reminders": 0,
        })

    def test_renewal_and_payment_failure_roll_back_the_new_membership(self) -> None:
        first = self.create_customer(phone="+919800000004", initial_payment=0)
        with mock.patch.object(
            self.service,
            "_record_payment_connection",
            side_effect=RuntimeError("renewal payment fault"),
        ):
            with self.assertRaisesRegex(RuntimeError, "renewal payment fault"):
                self.service.renew_membership(
                    first["customer"]["id"],
                    {"planId": "plan-pro-monthly", "amountPaise": 10_000, "paymentMethod": "cash"},
                    actor_admin_user_id="admin-qa",
                )
        self.assertEqual(self.database_counts(), {
            "customers": 1, "profiles": 1, "memberships": 1, "payments": 0, "reminders": 0,
        })

    def test_parallel_same_phone_create_has_one_success_and_one_conflict(self) -> None:
        def create_once():
            try:
                return "created", self.create_customer(phone="+919800000005", initial_payment=0)
            except AdminSoftwareConflict:
                return "conflict", None

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _value: create_once(), range(2)))
        self.assertEqual(sorted(result[0] for result in results), ["conflict", "created"])
        self.assertEqual(self.database_counts()["customers"], 1)
        self.assertEqual(self.database_counts()["memberships"], 1)

    def test_duplicate_payment_requests_are_currently_not_idempotent(self) -> None:
        created = self.create_customer(phone="+919800000006", initial_payment=0)
        membership_id = created["membership"]["id"]
        payload = {"amountPaise": 10_000, "method": "cash"}
        self.service.record_payment(membership_id, payload, actor_admin_user_id="admin-qa")
        self.service.record_payment(membership_id, payload, actor_admin_user_id="admin-qa")
        self.assertEqual(self.database_counts()["payments"], 2)
        detail = self.service.customer_detail(created["customer"]["id"])
        self.assertEqual(detail["membership"]["current"]["payment"]["pendingPaise"], 79900)

    def test_duplicate_renewal_requests_are_currently_not_idempotent(self) -> None:
        created = self.create_customer(phone="+919800000007", initial_payment=0)
        payload = {"planId": "plan-pro-monthly", "amountPaidPaise": 0, "paymentMethod": "cash"}
        self.service.renew_membership(created["customer"]["id"], payload, actor_admin_user_id="admin-qa")
        self.service.renew_membership(created["customer"]["id"], payload, actor_admin_user_id="admin-qa")
        with self.database.session() as connection:
            scheduled = connection.execute(
                "SELECT COUNT(*) FROM memberships WHERE customer_id=? AND status='scheduled'",
                (created["customer"]["id"],),
            ).fetchone()[0]
        self.assertEqual(scheduled, 2)

    def test_notification_reconcile_failure_happens_after_the_renewal_commit(self) -> None:
        """Record the retry-risk boundary so it is visible in the release evidence.

        The service commits the renewal first and suppresses notifications in a
        second transaction. An infrastructure error must not erase a valid
        membership, but clients also must not retry without server idempotency.
        """
        created = self.create_customer(phone="+919800000008", initial_payment=0)
        with mock.patch.object(self.notifications, "reconcile", side_effect=RuntimeError("notification fault")):
            with self.assertRaisesRegex(RuntimeError, "notification fault"):
                self.service.renew_membership(
                    created["customer"]["id"],
                    {"planId": "plan-pro-monthly", "amountPaidPaise": 0},
                    actor_admin_user_id="admin-qa",
                )
        self.assertEqual(self.database_counts()["memberships"], 2)


if __name__ == "__main__":
    unittest.main()
