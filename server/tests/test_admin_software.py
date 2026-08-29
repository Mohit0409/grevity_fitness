from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import unittest

from server.gravity.admin import AdminService
from server.gravity.admin_software import (
    AdminSoftwareConflict,
    AdminSoftwareService,
)
from server.gravity.config import Settings
from server.gravity.database import Database
from server.gravity.membership import MembershipService
from server.gravity.notification import NotificationService


ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "admin-software-test-secret-key-that-is-long-enough"


class MutableClock:
    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> float:
        return float(self.value)


class AdminSoftwareServiceTests(unittest.TestCase):
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
        start = int(datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc).timestamp())
        self.clock = MutableClock(start)
        self.admin = AdminService(self.database, self.settings, clock=self.clock)
        self.memberships = MembershipService(self.database, clock=self.clock)
        self.notifications = NotificationService(
            self.database, self.memberships, self.settings, clock=self.clock
        )
        with self.database.session() as connection:
            connection.execute(
                "INSERT INTO admin_users(id,username,password_hash,role,status,encrypted_totp_secret,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                ("admin-1", "owner", "x", "owner", "active", "x", start, start),
            )
        for plan_id in ("plan-basic-monthly", "plan-pro-monthly", "plan-elite-monthly"):
            self.memberships.update_plan(
                plan_id, {"status": "active"}, actor_admin_user_id="admin-1"
            )
        self.service = AdminSoftwareService(
            self.database,
            self.memberships,
            self.admin,
            self.notifications,
            clock=self.clock,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create_customer(self, *, phone: str = "+919876543210", paid: int = 30000):
        return self.service.create_customer_bundle(
            {
                "displayName": "Rahul Sharma",
                "phone": phone,
                "planId": "plan-basic-monthly",
                "amountPaidPaise": paid,
                "paymentMethod": "cash",
            },
            actor_admin_user_id="admin-1",
        )

    def test_atomic_add_customer_membership_and_initial_payment(self) -> None:
        created = self.create_customer()
        self.assertEqual(created["customer"]["phone"], "+919876543210")
        self.assertFalse(created["customer"]["phoneVerified"])
        self.assertEqual(created["membership"]["status"], "active")
        self.assertEqual(created["paymentSummary"]["totalPaise"], 99900)
        self.assertEqual(created["paymentSummary"]["paidPaise"], 30000)
        self.assertEqual(created["paymentSummary"]["pendingPaise"], 69900)
        detail = self.service.customer_detail(created["customer"]["id"])
        self.assertEqual(len(detail["membership"]["all"]), 1)
        self.assertEqual(len(detail["payments"]), 1)

        with self.assertRaises(AdminSoftwareConflict):
            self.create_customer(phone="+919876543210")
        with self.database.session() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM memberships").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM membership_payments").fetchone()[0], 1)

    def test_initial_overpayment_rolls_back_entire_customer_transaction(self) -> None:
        with self.assertRaises(AdminSoftwareConflict):
            self.create_customer(phone="+919800000001", paid=100000)
        with self.database.session() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM memberships").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM membership_payments").fetchone()[0], 0)

    def test_multiple_manual_payments_derive_pending_balance(self) -> None:
        created = self.create_customer(paid=30000)
        membership_id = created["membership"]["id"]
        second = self.service.record_payment(
            membership_id,
            {"amountPaise": 40000, "method": "upi"},
            actor_admin_user_id="admin-1",
        )
        self.assertEqual(second["summary"]["paidPaise"], 70000)
        self.assertEqual(second["summary"]["pendingPaise"], 29900)
        final = self.service.record_payment(
            membership_id,
            {"amountPaise": 29900, "method": "cash"},
            actor_admin_user_id="admin-1",
        )
        self.assertEqual(final["summary"]["pendingPaise"], 0)
        with self.assertRaises(AdminSoftwareConflict):
            self.service.record_payment(
                membership_id,
                {"amountPaise": 1, "method": "cash"},
                actor_admin_user_id="admin-1",
            )
        fees = self.service.fees(pending_only=True)
        self.assertEqual(fees["pendingFeesTotalPaise"], 0)
        self.assertEqual(fees["rows"], [])

    def test_renewal_preserves_history_and_suppresses_old_reminders(self) -> None:
        created = self.create_customer(paid=0)
        customer_id = created["customer"]["id"]
        first = created["membership"]
        self.clock.value = int(first["endsAt"]) - 6 * 86400
        scan = self.notifications.scan_expiring(7)
        self.assertEqual(scan["created"], 1)
        renewed = self.service.renew_membership(
            customer_id,
            {"planId": "plan-pro-monthly", "amountPaidPaise": 50000, "paymentMethod": "upi"},
            actor_admin_user_id="admin-1",
        )
        self.assertEqual(renewed["membership"]["status"], "scheduled")
        detail = self.service.customer_detail(customer_id)
        self.assertEqual(len(detail["membership"]["all"]), 2)
        self.assertEqual(detail["membership"]["current"]["id"], first["id"])
        self.assertEqual(detail["membership"]["upcoming"]["id"], renewed["membership"]["id"])
        with self.database.session() as connection:
            reminder = connection.execute(
                "SELECT state FROM notification_reminders WHERE membership_id=?", (first["id"],)
            ).fetchone()
        self.assertEqual(reminder["state"], "suppressed")

    def test_dashboard_and_filters_are_server_calculated(self) -> None:
        one = self.create_customer(phone="+919800000011", paid=20000)
        self.create_customer(phone="+919800000012", paid=99900)
        dashboard = self.service.dashboard()
        self.assertEqual(dashboard["stats"]["totalCustomers"], 2)
        self.assertEqual(dashboard["stats"]["activeMembers"], 2)
        self.assertEqual(dashboard["stats"]["pendingFeesTotalPaise"], 79900)
        pending = self.service.list_customers(membership_status="active")
        self.assertEqual(len(pending), 2)
        searched = self.service.list_customers(query="Rahul")
        self.assertEqual(len(searched), 2)
        self.service.update_customer(
            one["customer"]["id"], {"status": "disabled"}, actor_admin_user_id="admin-1"
        )
        disabled = self.service.list_customers(customer_status="disabled")
        self.assertEqual(len(disabled), 1)


    def test_owner_phone_change_revokes_active_customer_sessions(self) -> None:
        created = self.create_customer(phone="+919800000021", paid=0)
        customer_id = created["customer"]["id"]
        with self.database.session() as connection:
            connection.execute(
                "INSERT INTO customer_sessions(id,customer_id,token_hash,csrf_hash,created_at,last_seen_at,"
                "idle_expires_at,absolute_expires_at) VALUES (?,?,?,?,?,?,?,?)",
                ("session-1", customer_id, "a" * 64, "b" * 64, self.clock.value, self.clock.value,
                 self.clock.value + 3600, self.clock.value + 7200),
            )
            connection.execute("UPDATE customers SET phone_verified=1 WHERE id=?", (customer_id,))
        updated = self.service.update_customer(
            customer_id, {"phone": "+919800000022"}, actor_admin_user_id="admin-1"
        )
        self.assertEqual(updated["phone"], "+919800000022")
        self.assertFalse(updated["phoneVerified"])
        with self.database.session() as connection:
            session = connection.execute(
                "SELECT revoked_at,revoke_reason FROM customer_sessions WHERE id='session-1'"
            ).fetchone()
        self.assertIsNotNone(session["revoked_at"])
        self.assertEqual(session["revoke_reason"], "admin_phone_changed")

    def test_disabling_customer_revokes_active_sessions(self) -> None:
        created = self.create_customer(phone="+919800000023", paid=0)
        customer_id = created["customer"]["id"]
        with self.database.session() as connection:
            connection.execute(
                "INSERT INTO customer_sessions(id,customer_id,token_hash,csrf_hash,created_at,last_seen_at,"
                "idle_expires_at,absolute_expires_at) VALUES (?,?,?,?,?,?,?,?)",
                ("session-disabled", customer_id, "e" * 64, "f" * 64, self.clock.value, self.clock.value,
                 self.clock.value + 3600, self.clock.value + 7200),
            )
        updated = self.service.update_customer(
            customer_id, {"status": "disabled"}, actor_admin_user_id="admin-1"
        )
        self.assertEqual(updated["status"], "disabled")
        with self.database.session() as connection:
            session = connection.execute(
                "SELECT revoked_at,revoke_reason FROM customer_sessions WHERE id='session-disabled'"
            ).fetchone()
        self.assertIsNotNone(session["revoked_at"])
        self.assertEqual(session["revoke_reason"], "admin_disabled")

    def test_customer_filters_apply_before_limit_and_return_late_plan_match(self) -> None:
        now = self.clock.value
        with self.database.session() as connection:
            for index in range(205):
                customer_id = f"bulk-customer-{index:03d}"
                phone = f"+91970{index:07d}"
                connection.execute(
                    "INSERT INTO customers(id,status,display_name,phone_e164,phone_verified,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (customer_id, "active", f"Bulk Member {index:03d}", phone, 0, now, now),
                )
                connection.execute(
                    "INSERT INTO customer_profiles(customer_id,updated_at) VALUES (?,?)",
                    (customer_id, now),
                )
                connection.execute(
                    "INSERT INTO memberships(id,membership_number,customer_id,plan_id,plan_name_snapshot,"
                    "plan_price_paise_snapshot,currency_snapshot,duration_months_snapshot,status,starts_at,ends_at,"
                    "source,created_by_admin_user_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (f"bulk-membership-{index:03d}", f"GF-BULK-{index:03d}", customer_id, "plan-basic-monthly",
                     "Basic", 99900, "INR", 1, "active", now - 86400, now + 20 * 86400,
                     "admin_manual", "admin-1", now, now),
                )
            target_id = "bulk-target-pro"
            connection.execute(
                "INSERT INTO customers(id,status,display_name,phone_e164,phone_verified,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (target_id, "active", "ZZZ Target Pro", "+919799999999", 0, now, now),
            )
            connection.execute(
                "INSERT INTO customer_profiles(customer_id,updated_at) VALUES (?,?)", (target_id, now)
            )
            connection.execute(
                "INSERT INTO memberships(id,membership_number,customer_id,plan_id,plan_name_snapshot,"
                "plan_price_paise_snapshot,currency_snapshot,duration_months_snapshot,status,starts_at,ends_at,"
                "source,created_by_admin_user_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("bulk-target-membership", "GF-BULK-TARGET", target_id, "plan-pro-monthly", "Pro", 149900,
                 "INR", 1, "active", now - 86400, now + 20 * 86400, "admin_manual", "admin-1", now, now),
            )
            connection.execute(
                "INSERT INTO membership_payments(id,membership_id,amount_paise,currency,method,paid_at,status,"
                "recorded_by_admin_user_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                ("bulk-target-payment", "bulk-target-membership", 50000, "INR", "cash", now, "recorded", "admin-1", now),
            )
        unfiltered = self.service.list_customers(limit=200)
        self.assertEqual(len(unfiltered), 200)
        self.assertNotIn(target_id, {item["id"] for item in unfiltered})
        filtered = self.service.list_customers(plan_id="plan-pro-monthly", membership_status="active", limit=200)
        self.assertEqual([item["id"] for item in filtered], [target_id])
        self.assertEqual(filtered[0]["membership"]["payment"]["paidPaise"], 50000)
        self.assertEqual(filtered[0]["membership"]["payment"]["pendingPaise"], 99900)

    def test_pending_fees_filter_and_total_are_applied_before_page_limit(self) -> None:
        now = self.clock.value
        customers = []
        memberships = []
        payments = []
        for index in range(305):
            customer_id = f"fee-paid-customer-{index:03d}"
            membership_id = f"fee-paid-membership-{index:03d}"
            customers.append((customer_id, "active", f"Paid Member {index:03d}", f"+91880{index:07d}", 0, now, now))
            memberships.append((membership_id, f"GF-FEE-PAID-{index:03d}", customer_id, "plan-basic-monthly", "Basic", 99900, "INR", 1, "active", now - 86400, now + (index + 1) * 86400, "admin_manual", "admin-1", now, now))
            payments.append((f"fee-paid-payment-{index:03d}", membership_id, 99900, "INR", "cash", now, "recorded", "admin-1", now))
        for index in range(301):
            customer_id = f"fee-pending-customer-{index:03d}"
            membership_id = f"fee-pending-membership-{index:03d}"
            customers.append((customer_id, "active", f"Pending Member {index:03d}", f"+91881{index:07d}", 0, now, now))
            memberships.append((membership_id, f"GF-FEE-PENDING-{index:03d}", customer_id, "plan-basic-monthly", "Basic", 99900, "INR", 1, "active", now - 86400, now + (400 + index) * 86400, "admin_manual", "admin-1", now, now))
        with self.database.session() as connection:
            connection.executemany(
                "INSERT INTO customers(id,status,display_name,phone_e164,phone_verified,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                customers,
            )
            connection.executemany(
                "INSERT INTO memberships(id,membership_number,customer_id,plan_id,plan_name_snapshot,plan_price_paise_snapshot,currency_snapshot,duration_months_snapshot,status,starts_at,ends_at,source,created_by_admin_user_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                memberships,
            )
            connection.executemany(
                "INSERT INTO membership_payments(id,membership_id,amount_paise,currency,method,paid_at,status,recorded_by_admin_user_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                payments,
            )
        fees = self.service.fees(pending_only=True, limit=300)
        self.assertEqual(len(fees["rows"]), 300)
        self.assertTrue(all(row["membership"]["payment"]["pendingPaise"] == 99900 for row in fees["rows"]))
        self.assertEqual(fees["pendingFeesTotalPaise"], 301 * 99900)

    def test_dashboard_does_not_double_count_membership_history(self) -> None:
        first = self.create_customer(phone="+919800000024", paid=0)
        self.create_customer(phone="+919800000025", paid=0)
        customer_id = first["customer"]["id"]
        with self.database.session() as connection:
            connection.execute(
                "INSERT INTO memberships(id,membership_number,customer_id,plan_id,plan_name_snapshot,"
                "plan_price_paise_snapshot,currency_snapshot,duration_months_snapshot,status,starts_at,ends_at,"
                "source,created_by_admin_user_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("history-membership", "GF-HISTORY-001", customer_id, "plan-basic-monthly", "Basic", 99900,
                 "INR", 1, "expired", self.clock.value - 60 * 86400, self.clock.value - 30 * 86400,
                 "admin_manual", "admin-1", self.clock.value - 60 * 86400, self.clock.value - 30 * 86400),
            )
        dashboard = self.service.dashboard()
        self.assertEqual(dashboard["stats"]["totalCustomers"], 2)
        self.assertEqual(dashboard["stats"]["activeMembers"], 2)
        self.assertEqual(dashboard["stats"]["expiredMembers"], 0)

    def test_migration_009_to_010_preserves_existing_domain_data(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_migrations = root / "migrations"
            old_migrations.mkdir()
            for migration in sorted((ROOT / "server" / "migrations").glob("*.sql")):
                if migration.name.startswith("010_"):
                    continue
                shutil.copy2(migration, old_migrations / migration.name)
            database_path = root / "gravity.sqlite3"
            old_database = Database(database_path, old_migrations)
            self.assertEqual(old_database.migrate(), [f"{index:03d}" for index in range(1, 10)])
            local_clock = MutableClock(int(datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc).timestamp()))
            old_admin = AdminService(old_database, self.settings, clock=local_clock)
            owner = old_admin.bootstrap_owner("upgradeowner", "Gravity!Upgrade123")
            owner_id = str(owner.admin["id"])
            with old_database.session() as connection:
                connection.execute(
                    "INSERT INTO customers(id,status,display_name,phone_e164,phone_verified,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    ("upgrade-customer", "active", "Upgrade Customer", "+919800001111", 1,
                     local_clock.value, local_clock.value),
                )
                connection.execute(
                    "INSERT INTO customer_profiles(customer_id,updated_at) VALUES (?,?)",
                    ("upgrade-customer", local_clock.value),
                )
                connection.execute(
                    "INSERT INTO firebase_identities(project_id,firebase_uid,customer_id,last_sign_in_provider,"
                    "created_at,last_seen_at) VALUES (?,?,?,?,?,?)",
                    ("gravity-authe", "upgrade-uid", "upgrade-customer", "phone",
                     local_clock.value, local_clock.value),
                )
                connection.execute(
                    "INSERT INTO firebase_provider_identities(project_id,sign_in_provider,provider_subject,"
                    "firebase_uid,created_at,last_seen_at) VALUES (?,?,?,?,?,?)",
                    ("gravity-authe", "phone", "+919800001111", "upgrade-uid",
                     local_clock.value, local_clock.value),
                )
                connection.execute(
                    "INSERT INTO customer_sessions(id,customer_id,token_hash,csrf_hash,created_at,last_seen_at,"
                    "idle_expires_at,absolute_expires_at) VALUES (?,?,?,?,?,?,?,?)",
                    ("upgrade-session", "upgrade-customer", "c" * 64, "d" * 64,
                     local_clock.value, local_clock.value, local_clock.value + 3600, local_clock.value + 7200),
                )
            membership_start = local_clock.value
            membership_end = membership_start + 30 * 86400
            with old_database.session() as connection:
                connection.execute(
                    "INSERT INTO memberships(id,membership_number,customer_id,plan_id,plan_name_snapshot,"
                    "plan_price_paise_snapshot,currency_snapshot,duration_months_snapshot,status,starts_at,"
                    "ends_at,source,created_by_admin_user_id,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("upgrade-membership", "GF-UPGRADE-001", "upgrade-customer", "plan-basic-monthly",
                     "Basic", 99900, "INR", 1, "active", membership_start, membership_end, "admin_manual",
                     owner_id, membership_start, membership_start),
                )
                connection.execute(
                    "INSERT INTO notification_reminders(id,dedupe_key,event_type,customer_id,membership_id,"
                    "trigger_days,trigger_at,state,payload_json,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    ("upgrade-reminder", "membership_expiry:upgrade-membership:7", "membership_expiry",
                     "upgrade-customer", "upgrade-membership", 7, membership_end - 7 * 86400, "pending",
                     "{}", membership_start, membership_start),
                )
                connection.execute(
                    "INSERT INTO payment_intents(id,customer_id,plan_id,plan_name_snapshot,amount_paise,currency,"
                    "duration_months_snapshot,provider,status,receipt_reference,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("upgrade-intent", "upgrade-customer", "plan-basic-monthly", "Basic", 99900, "INR", 1,
                     "razorpay", "created", "upgrade-receipt", local_clock.value, local_clock.value),
                )
            upgraded = Database(database_path, ROOT / "server" / "migrations")
            self.assertEqual(upgraded.migrate(), ["010"])
            self.assertEqual(upgraded.health(), {"database": "ok", "migrations": "10"})
            with upgraded.session() as connection:
                self.assertEqual(connection.execute("SELECT value FROM app_metadata WHERE key='schema_stage'").fetchone()[0], "admin_software_v1")
                for table in (
                    "customers", "firebase_identities", "customer_sessions", "memberships",
                    "notification_reminders", "admin_users", "payment_intents",
                ):
                    self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 1, table)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM membership_payments").fetchone()[0], 0)
                columns = {row[1] for row in connection.execute("PRAGMA table_info(customers)")}
                self.assertIn("created_by_admin_user_id", columns)


    def test_payment_idempotency_replays_once_and_rejects_key_reuse(self) -> None:
        created = self.create_customer(phone="+919800000031", paid=0)
        membership_id = created["membership"]["id"]
        first = self.service.record_payment(
            membership_id,
            {"amountPaise": 10000, "method": "cash"},
            actor_admin_user_id="admin-1",
            idempotency_key="payment-test-key-0001",
        )
        replay = self.service.record_payment(
            membership_id,
            {"amountPaise": 10000, "method": "cash"},
            actor_admin_user_id="admin-1",
            idempotency_key="payment-test-key-0001",
        )
        self.assertEqual(replay["payment"]["id"], first["payment"]["id"])
        self.assertEqual(replay["summary"], first["summary"])
        with self.database.session() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM membership_payments").fetchone()[0], 1)
        with self.assertRaises(AdminSoftwareConflict):
            self.service.record_payment(
                membership_id,
                {"amountPaise": 20000, "method": "cash"},
                actor_admin_user_id="admin-1",
                idempotency_key="payment-test-key-0001",
            )

    def test_renewal_idempotency_and_reminder_suppression_are_transactional(self) -> None:
        created = self.create_customer(phone="+919800000032", paid=0)
        customer_id = created["customer"]["id"]
        first = created["membership"]
        self.clock.value = int(first["endsAt"]) - 6 * 86400
        self.assertEqual(self.notifications.scan_expiring(7)["created"], 1)
        payload = {"planId": "plan-pro-monthly", "amountPaidPaise": 20000, "paymentMethod": "upi"}
        renewed = self.service.renew_membership(
            customer_id,
            payload,
            actor_admin_user_id="admin-1",
            idempotency_key="renewal-test-key-0001",
        )
        replay = self.service.renew_membership(
            customer_id,
            payload,
            actor_admin_user_id="admin-1",
            idempotency_key="renewal-test-key-0001",
        )
        self.assertEqual(replay["membership"]["id"], renewed["membership"]["id"])
        self.assertEqual(replay["payment"]["id"], renewed["payment"]["id"])
        with self.database.session() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM memberships").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM membership_payments").fetchone()[0], 1)
            reminder = connection.execute(
                "SELECT state FROM notification_reminders WHERE membership_id=?", (first["id"],)
            ).fetchone()
        self.assertEqual(reminder["state"], "suppressed")
        with self.assertRaises(AdminSoftwareConflict):
            self.service.renew_membership(
                customer_id,
                {"planId": "plan-elite-monthly", "amountPaidPaise": 20000, "paymentMethod": "upi"},
                actor_admin_user_id="admin-1",
                idempotency_key="renewal-test-key-0001",
            )
