#!/usr/bin/env python3
"""Run destructive-looking admin QA only against disposable temporary SQLite databases."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter
import argparse
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.gravity.admin import AdminService, AdminSessionIdentity
from server.gravity.admin_software import AdminSoftwareService
from server.gravity.config import Settings
from server.gravity.database import Database
from server.gravity.membership import MembershipService
from server.gravity.notification import NotificationService
from server.gravity.payment import PaymentNotFound, PaymentService


VOLUMES = (100, 500, 1_000, 5_000)


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


def settings_for(runtime: Path) -> Settings:
    base = Settings.load(root_dir=ROOT, environ={
        "SECRET_KEY": "admin-qa-temporary-secret-long-enough",
        "RAZORPAY_KEY_ID": "rzp_test_admin_qa",
        "RAZORPAY_KEY_SECRET": "admin-qa-razorpay-secret",
        "RAZORPAY_WEBHOOK_SECRET": "admin-qa-webhook-secret",
    })
    return replace(
        base,
        data_dir=runtime / "data",
        log_dir=runtime / "logs",
        backup_dir=runtime / "backups",
        database_path=runtime / "data" / "gravity.sqlite3",
    )


def build_dataset(runtime: Path, customer_count: int) -> tuple[Settings, Database, int]:
    settings = settings_for(runtime)
    settings.ensure_directories()
    database = Database(settings.database_path, settings.migrations_dir)
    database.migrate()
    now = int(time.time())
    customers = []
    memberships = []
    payments = []
    manual_payments = []
    reminders = []
    deliveries = []
    for index in range(customer_count):
        customer_id = f"qa-customer-{index:05d}"
        membership_id = f"qa-membership-{index:05d}"
        reminder_id = f"qa-reminder-{index:05d}"
        status = "disabled" if index and index % 50 == 0 else "active"
        created_at = now - index
        customers.append((
            customer_id, status, f"Synthetic Member {index:05d}", f"member{index:05d}@example.test",
            f"+919{index:09d}", created_at, created_at,
        ))
        ends_at = now + ((index % 30) + 1) * 86400
        memberships.append((
            membership_id, f"GF-QA-{index:05d}", customer_id, "plan-basic-monthly", "Basic", 99900,
            "INR", 1, "active", now - 20 * 86400, ends_at, "import", created_at, created_at,
        ))
        paid = index % 2 == 0
        payments.append((
            f"qa-payment-{index:05d}", customer_id, "plan-basic-monthly", "Basic", 99900, "INR", 1,
            "razorpay", "paid" if paid else "created", f"qa-receipt-{index:05d}",
            f"qa-order-{index:05d}", f"qa-provider-payment-{index:05d}" if paid else None,
            created_at, created_at, created_at if paid else None,
        ))
        if index % 2 == 0:
            manual_payments.append((
                f"qa-manual-payment-{index:05d}", membership_id, 10_000, "INR", "cash", None,
                created_at, "recorded", "qa-admin", f"qa-manual-{index:05d}", created_at,
            ))
        reminders.append((
            reminder_id, f"membership_expiry:{membership_id}:7", "membership_expiry", customer_id,
            membership_id, 7, ends_at - 7 * 86400, "pending", "{}", created_at, created_at,
        ))
        for recipient_role in ("customer", "owner"):
            for channel, recipient_ref in (("email", "email"), ("sms", "phone"), ("whatsapp", "whatsapp")):
                deliveries.append((
                    f"qa-delivery-{index:05d}-{recipient_role}-{channel}", reminder_id, channel,
                    recipient_role, recipient_ref, "blocked_external_config", 0, created_at, created_at,
                ))
    with database.session() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO admin_users(id,username,password_hash,role,status,encrypted_totp_secret,created_at,updated_at) "
            "VALUES ('qa-admin','qa-admin','x','owner','active','x',?,?)",
            (now, now),
        )
        connection.execute("UPDATE membership_plans SET status='active',updated_at=? WHERE id='plan-basic-monthly'", (now,))
        connection.executemany(
            "INSERT INTO customers(id,status,display_name,email,phone_e164,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            customers,
        )
        connection.executemany(
            "INSERT INTO memberships(id,membership_number,customer_id,plan_id,plan_name_snapshot,"
            "plan_price_paise_snapshot,currency_snapshot,duration_months_snapshot,status,starts_at,ends_at,"
            "source,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            memberships,
        )
        connection.executemany(
            "INSERT INTO payment_intents(id,customer_id,plan_id,plan_name_snapshot,amount_paise,currency,"
            "duration_months_snapshot,provider,status,receipt_reference,provider_order_id,provider_payment_id,"
            "created_at,updated_at,paid_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            payments,
        )
        connection.executemany(
            "INSERT INTO membership_payments(id,membership_id,amount_paise,currency,method,note,paid_at,status,"
            "recorded_by_admin_user_id,idempotency_key,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            manual_payments,
        )
        connection.executemany(
            "INSERT INTO notification_reminders(id,dedupe_key,event_type,customer_id,membership_id,trigger_days,"
            "trigger_at,state,payload_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            reminders,
        )
        connection.executemany(
            "INSERT INTO notification_deliveries(id,reminder_id,channel,recipient_role,recipient_ref,status,"
            "attempt_count,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            deliveries,
        )
        connection.commit()
    return settings, database, now


def measure(callable_, repeats: int = 5) -> dict[str, float]:
    samples = []
    for _ in range(repeats):
        started = perf_counter()
        callable_()
        samples.append((perf_counter() - started) * 1000)
    return {
        "medianMs": round(median(samples), 3),
        "maximumMs": round(max(samples), 3),
    }


def query_plans(database: Database) -> dict[str, list[str]]:
    statements = {
        "customerList": (
            "SELECT id FROM customers WHERE ?='' OR lower(COALESCE(display_name,'')) LIKE ? "
            "OR lower(COALESCE(email,'')) LIKE ? OR COALESCE(phone_e164,'') LIKE ? "
            "ORDER BY created_at DESC LIMIT 100",
            ("", "%%", "%%", "%%"),
        ),
        "dashboardCustomers": (
            "SELECT status,COUNT(*) FROM customers GROUP BY status",
            (),
        ),
        "membershipExpiry": (
            "SELECT m.id FROM memberships m JOIN customers c ON c.id=m.customer_id "
            "WHERE m.status='active' AND m.ends_at>? AND m.ends_at<=? ORDER BY m.ends_at ASC",
            (0, 4_000_000_000),
        ),
        "notificationAdmin": (
            "SELECT r.id FROM notification_reminders r JOIN customers c ON c.id=r.customer_id "
            "ORDER BY r.created_at DESC LIMIT 100",
            (),
        ),
        "manualPaymentHistory": (
            "SELECT id FROM membership_payments WHERE status='recorded' ORDER BY paid_at DESC LIMIT 100",
            (),
        ),
        "pendingFees": (
            "SELECT m.id FROM memberships m JOIN customers c ON c.id=m.customer_id "
            "WHERE c.status!='deleted' AND m.status!='cancelled' ORDER BY m.ends_at ASC LIMIT 300",
            (),
        ),
    }
    result = {}
    with database.session() as connection:
        for name, (sql, parameters) in statements.items():
            rows = connection.execute(f"EXPLAIN QUERY PLAN {sql}", parameters).fetchall()
            result[name] = [str(row[3]) for row in rows]
    return result


def performance_volume(customer_count: int) -> dict[str, object]:
    with TemporaryDirectory(prefix=f"gravity-admin-perf-{customer_count}-") as temporary:
        settings, database, _now = build_dataset(Path(temporary), customer_count)
        session = AdminSessionIdentity(
            session_id="qa-session", admin_user_id="qa-admin", csrf_hash="x",
            admin={"id": "qa-admin", "role": "owner", "permissions": ["*"]},
        )
        admin = AdminService(database, settings)
        memberships = MembershipService(database)
        notifications = NotificationService(database, memberships, settings)
        admin_software = AdminSoftwareService(database, memberships, admin, notifications)
        search_value = f"Synthetic Member {customer_count // 2:05d}"
        timings = {
            "customerList": measure(lambda: admin_software.list_customers(limit=100)),
            "customerSearch": measure(lambda: admin_software.list_customers(query=search_value, limit=100)),
            "dashboardStats": measure(admin_software.dashboard),
            "membershipExpiry": measure(lambda: memberships.expiring_within(30)),
            "notificationList": measure(lambda: notifications.list_admin(100)),
            "pendingFees": measure(lambda: admin_software.fees(pending_only=True, limit=300)),
            "manualPaymentHistory": measure(lambda: admin_software.list_payments(limit=100)),
        }
        with database.session() as connection:
            foreign_keys_ok = not connection.execute("PRAGMA foreign_key_check").fetchall()
        return {
            "customers": customer_count,
            "temporaryDatabase": True,
            "foreignKeysOk": foreign_keys_ok,
            "timings": timings,
            "queryPlans": query_plans(database),
            "pendingFeeCalculation": {"status": "measured", "source": "membership_payments"},
        }


def reliability_diagnostics() -> dict[str, object]:
    with TemporaryDirectory(prefix="gravity-admin-reliability-") as temporary:
        settings, database, now = build_dataset(Path(temporary), 1)
        memberships = MembershipService(database, clock=lambda: float(now))
        admin = AdminService(database, settings, clock=lambda: float(now))
        notifications = NotificationService(database, memberships, settings, clock=lambda: float(now))
        software = AdminSoftwareService(
            database, memberships, admin, notifications, clock=lambda: float(now),
        )
        payment_payload = {"amountPaise": 1_000, "method": "cash"}
        payment_one = software.record_payment(
            "qa-membership-00000", payment_payload, actor_admin_user_id="qa-admin",
            idempotency_key="qa-payment-replay-0001",
        )
        payment_two = software.record_payment(
            "qa-membership-00000", payment_payload, actor_admin_user_id="qa-admin",
            idempotency_key="qa-payment-replay-0001",
        )
        renewal_payload = {"planId": "plan-basic-monthly", "amountPaidPaise": 0}
        renewal_one = software.renew_membership(
            "qa-customer-00000", renewal_payload, actor_admin_user_id="qa-admin",
            idempotency_key="qa-renewal-replay-0001",
        )
        renewal_two = software.renew_membership(
            "qa-customer-00000", renewal_payload, actor_admin_user_id="qa-admin",
            idempotency_key="qa-renewal-replay-0001",
        )
        with database.session() as connection:
            payment_rows = connection.execute("SELECT COUNT(*) FROM membership_payments").fetchone()[0]
            renewal_rows = connection.execute(
                "SELECT COUNT(*) FROM memberships WHERE customer_id='qa-customer-00000' AND status='scheduled'"
            ).fetchone()[0]
        return {
            "paymentReplaySingle": payment_one["payment"]["id"] == payment_two["payment"]["id"] and payment_rows == 2,
            "renewalReplaySingle": renewal_one["membership"]["id"] == renewal_two["membership"]["id"] and renewal_rows == 1,
            "foreignKeysOk": database.health().get("database") == "ok",
        }


def report(volumes: tuple[int, ...]) -> dict[str, object]:
    performance = [performance_volume(volume) for volume in volumes]
    diagnostics = reliability_diagnostics()
    capabilities = {
        "adminCustomerCreate": hasattr(AdminSoftwareService, "create_customer_bundle"),
        "adminManualPaymentRecord": hasattr(AdminSoftwareService, "record_payment"),
        "pendingFeeLedger": hasattr(AdminSoftwareService, "fees"),
    }
    blockers = []
    for name, available in capabilities.items():
        if not available:
            blockers.append(name)
    if not diagnostics["paymentReplaySingle"]:
        blockers.append("duplicatePaymentProtection")
    if not diagnostics["renewalReplaySingle"]:
        blockers.append("duplicateRenewalProtection")
    if not diagnostics["foreignKeysOk"]:
        blockers.append("foreignKeyIntegrity")
    return {
        "temporaryDatabasesOnly": True,
        "volumes": performance,
        "capabilities": capabilities,
        "reliabilityDiagnostics": diagnostics,
        "indexAudit": {
            "ledger": "migration 010 supplies membership/date payment indexes; plans are emitted per volume",
            "note": "Leading-wildcard name search and membership filtering need a joined/FTS design if latency or filter completeness becomes material.",
        },
        "ready": not blockers,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Gravity admin QA against temporary synthetic databases")
    parser.add_argument("--volumes", default=",".join(str(value) for value in VOLUMES))
    parser.add_argument("--fail-on-blockers", action="store_true")
    args = parser.parse_args()
    try:
        volumes = tuple(int(value.strip()) for value in args.volumes.split(",") if value.strip())
    except ValueError:
        parser.error("--volumes must be a comma-separated list of positive integers")
    if not volumes or any(value < 1 or value > 50_000 for value in volumes):
        parser.error("--volumes must contain values between 1 and 50000")
    result = report(volumes)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.fail_on_blockers and not result["ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
