from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from server.gravity.config import Settings
from server.gravity.database import Database
from server.gravity.membership import (
    MembershipConflict,
    MembershipService,
    MembershipValidationError,
)


ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "phase-four-membership-secret-key-long-enough"


class MutableClock:
    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> float:
        return float(self.value)


class MembershipServiceTests(unittest.TestCase):
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
        self.service = MembershipService(self.database, clock=self.clock)
        with self.database.session() as connection:
            for customer_id in ("customer-1", "customer-2"):
                connection.execute(
                    "INSERT INTO customers(id,status,display_name,created_at,updated_at) VALUES (?,?,?,?,?)",
                    (customer_id, "active", customer_id, start, start),
                )
            connection.execute(
                "INSERT INTO admin_users(id,username,password_hash,role,status,encrypted_totp_secret,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                ("admin-1", "owner", "x", "owner", "active", "x", start, start),
            )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def activate(self, *plan_ids: str) -> None:
        for plan_id in plan_ids:
            self.service.update_plan(
                plan_id,
                {"status": "active"},
                actor_admin_user_id="admin-1",
            )

    def test_seeded_plans_and_month_end_snapshot(self) -> None:
        plans = self.service.list_plans(active_only=False)
        self.assertEqual([plan["name"] for plan in plans], ["1 Month", "3 Months", "1 Year"])
        self.assertEqual([plan["pricePaise"] for plan in plans], [120000, 300000, 1000000])
        self.assertEqual([plan["status"] for plan in plans], ["active", "active", "active"])
        self.assertEqual(len(self.service.list_plans()), 3)
        membership = self.service.create_membership(
            "customer-1",
            "plan-basic-monthly",
            actor_admin_user_id="admin-1",
        )
        self.assertEqual(membership["status"], "active")
        self.assertEqual(membership["planName"], "1 Month")
        self.assertEqual(membership["pricePaise"], 120000)
        expected_end = int(datetime(2026, 2, 28, 12, 0, tzinfo=timezone.utc).timestamp())
        self.assertEqual(membership["endsAt"], expected_end)

    def test_renewal_schedules_without_overlap_and_reconciles(self) -> None:
        self.activate("plan-basic-monthly", "plan-pro-monthly", "plan-elite-monthly")
        first = self.service.create_membership(
            "customer-1", "plan-basic-monthly", actor_admin_user_id="admin-1"
        )
        second = self.service.create_membership(
            "customer-1", "plan-pro-monthly", actor_admin_user_id="admin-1"
        )
        self.assertEqual(second["status"], "scheduled")
        self.assertEqual(second["startsAt"], first["endsAt"])
        with self.assertRaises(MembershipConflict):
            self.service.create_membership(
                "customer-1",
                "plan-elite-monthly",
                actor_admin_user_id="admin-1",
                starts_at=int(first["startsAt"]) + 3600,
            )
        self.clock.value = int(first["endsAt"])
        rows = {row["id"]: row for row in self.service.list_customer_memberships("customer-1")}
        self.assertEqual(rows[first["id"]]["status"], "expired")
        self.assertEqual(rows[second["id"]]["status"], "active")
        self.clock.value = int(second["endsAt"])
        rows = {row["id"]: row for row in self.service.list_customer_memberships("customer-1")}
        self.assertEqual(rows[second["id"]]["status"], "expired")

    def test_cancellation_and_expiry_scan(self) -> None:
        self.activate("plan-basic-monthly")
        membership = self.service.create_membership(
            "customer-1", "plan-basic-monthly", actor_admin_user_id="admin-1"
        )
        self.clock.value = int(membership["endsAt"]) - 5 * 86400
        expiring = self.service.expiring_within(7)
        self.assertEqual([row["id"] for row in expiring], [membership["id"]])
        cancelled = self.service.cancel_membership(
            membership["id"], actor_admin_user_id="admin-1", reason="Member requested cancellation"
        )
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.service.expiring_within(7), [])
        with self.database.session() as connection:
            events = connection.execute(
                "SELECT event_type FROM membership_events WHERE membership_id=? ORDER BY id",
                (membership["id"],),
            ).fetchall()
        self.assertEqual([row["event_type"] for row in events], ["created", "activated", "cancelled"])

    def test_payment_reference_is_unique_and_customer_summary_is_server_owned(self) -> None:
        self.activate("plan-basic-monthly", "plan-pro-monthly")
        first = self.service.create_membership(
            "customer-1", "plan-basic-monthly", source="payment", payment_reference="pay_verified_001"
        )
        with self.assertRaises(MembershipConflict):
            self.service.create_membership(
                "customer-2", "plan-pro-monthly", source="payment", payment_reference="pay_verified_001"
            )
        summary = self.service.customer_summary("customer-1")
        self.assertEqual(summary["current"]["id"], first["id"])
        self.assertIsNone(summary["upcoming"])
        self.assertEqual(summary["history"], [])

    def test_plan_updates_are_audited_and_membership_snapshot_is_immutable(self) -> None:
        self.activate("plan-basic-monthly")
        membership = self.service.create_membership(
            "customer-1", "plan-basic-monthly", actor_admin_user_id="admin-1"
        )
        updated = self.service.update_plan(
            "plan-basic-monthly",
            {"name": "Basic Plus", "pricePaise": 129900, "durationMonths": 2},
            actor_admin_user_id="admin-1",
        )
        self.assertEqual(updated["name"], "Basic Plus")
        rows = {row["id"]: row for row in self.service.list_customer_memberships("customer-1")}
        self.assertEqual(rows[membership["id"]]["planName"], "1 Month")
        self.assertEqual(rows[membership["id"]]["pricePaise"], 120000)
        self.assertEqual(rows[membership["id"]]["durationMonths"], 1)
        with self.database.session() as connection:
            events = connection.execute(
                "SELECT event_type FROM membership_plan_events WHERE plan_id=? ORDER BY id",
                ("plan-basic-monthly",),
            ).fetchall()
        self.assertEqual([row["event_type"] for row in events], ["updated"])

    def test_inactive_customer_and_invalid_payment_source_are_rejected(self) -> None:
        with self.database.session() as connection:
            connection.execute("UPDATE customers SET status='disabled' WHERE id='customer-2'")
        with self.assertRaises(MembershipConflict):
            self.service.create_membership(
                "customer-2", "plan-basic-monthly", actor_admin_user_id="admin-1"
            )
        with self.assertRaises(MembershipValidationError):
            self.service.create_membership(
                "customer-1", "plan-basic-monthly", source="payment", payment_reference=None
            )


if __name__ == "__main__":
    unittest.main()
