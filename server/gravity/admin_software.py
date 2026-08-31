from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping
from uuid import uuid4
import sqlite3
import time

from .admin import AdminService
from .auth import normalize_phone
from .database import Database
from .membership import MembershipService


PAYMENT_METHODS = {"cash", "upi", "card", "bank_transfer", "other"}
CUSTOMER_STATUSES = {"active", "disabled"}
PERSON_TYPES = {"member", "staff"}
STAFF_DESIGNATIONS = {
    "trainer", "receptionist", "manager", "cleaner",
    "floor_trainer", "personal_trainer", "other",
}
HISTORICAL_JOIN_LIMIT_SECONDS = 30 * 366 * 86400
FUTURE_JOIN_LIMIT_SECONDS = 366 * 86400
INDIA_TIMEZONE = timezone(timedelta(hours=5, minutes=30))


class AdminSoftwareError(Exception):
    pass


class AdminSoftwareNotFound(AdminSoftwareError):
    pass


class AdminSoftwareConflict(AdminSoftwareError):
    pass


class AdminSoftwareValidationError(AdminSoftwareError):
    def __init__(self, fields: Mapping[str, str]) -> None:
        super().__init__("Admin software validation failed")
        self.fields = dict(fields)


def _clean_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Name is required")
    normalized = " ".join(value.strip().split())
    if not 2 <= len(normalized) <= 80 or "\x00" in normalized:
        raise ValueError("Name must be 2-80 characters")
    return normalized


def _clean_note(value: object) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("Note must be text")
    cleaned = " ".join(value.strip().split())
    if not cleaned or len(cleaned) > 500 or "\x00" in cleaned:
        raise ValueError("Note must be 1-500 characters")
    return cleaned


def _bounded_limit(value: object, default: int = 100) -> int:
    try:
        return min(max(int(value), 1), 500)
    except (TypeError, ValueError):
        return default


def _clean_idempotency_key(value: object) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise AdminSoftwareValidationError({"idempotencyKey": "Idempotency key must be text"})
    cleaned = value.strip()
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._:")
    if not 8 <= len(cleaned) <= 128 or any(character not in allowed for character in cleaned):
        raise AdminSoftwareValidationError(
            {"idempotencyKey": "Use 8-128 letters, numbers, dots, dashes, underscores, or colons"}
        )
    return cleaned


def _clean_person_type(value: object) -> str:
    normalized = str(value or "member").strip().casefold()
    if normalized not in PERSON_TYPES:
        raise ValueError("Person type must be member or staff")
    return normalized


def _clean_designation(value: object) -> str:
    normalized = str(value or "").strip().casefold().replace(" ", "_")
    if normalized not in STAFF_DESIGNATIONS:
        raise ValueError("Select a staff designation")
    return normalized


def _validated_joined_at(value: object, *, now: int) -> int:
    try:
        joined_at = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Joining date is invalid") from error
    if joined_at <= 0 or joined_at < now - HISTORICAL_JOIN_LIMIT_SECONDS:
        raise ValueError("Joining date is outside the supported 30-year history")
    if joined_at > now + FUTURE_JOIN_LIMIT_SECONDS:
        raise ValueError("Joining date cannot be more than one year in the future")
    return joined_at


class AdminSoftwareService:
    def __init__(
        self,
        database: Database,
        membership_service: MembershipService,
        admin_service: AdminService,
        notification_service,
        *,
        clock=time.time,
    ) -> None:
        self.database = database
        self.membership_service = membership_service
        self.admin_service = admin_service
        self.notification_service = notification_service
        self.clock = clock

    def _now(self) -> int:
        return int(self.clock())

    @staticmethod
    def _safe_customer(row) -> dict[str, object]:
        return {
            "id": row["id"],
            "displayName": row["display_name"],
            "phone": row["phone_e164"],
            "phoneVerified": bool(row["phone_verified"]),
            "email": row["email"],
            "status": row["status"],
            "personType": row["person_type"],
            "joinedAt": int(row["joined_at"]) if row["joined_at"] is not None else None,
            "designation": row["staff_designation"],
            "note": row["admin_note"],
            "createdAt": int(row["created_at"]),
            "lastLoginAt": row["last_login_at"],
        }

    @staticmethod
    def _safe_payment(row) -> dict[str, object]:
        return {
            "id": row["id"],
            "membershipId": row["membership_id"],
            "amountPaise": int(row["amount_paise"]),
            "currency": row["currency"],
            "method": row["method"],
            "note": row["note"],
            "paidAt": int(row["paid_at"]),
            "status": row["status"],
            "createdAt": int(row["created_at"]),
        }

    @staticmethod
    def _payment_summary_from_recorded(membership_row, recorded: int) -> dict[str, int]:
        gateway_paid = 0
        if membership_row["source"] == "payment" and membership_row["payment_reference"]:
            gateway_paid = int(membership_row["plan_price_paise_snapshot"])
        total = int(membership_row["plan_price_paise_snapshot"])
        paid = min(total, int(recorded) + gateway_paid)
        return {"totalPaise": total, "paidPaise": paid, "pendingPaise": max(0, total - paid)}

    @classmethod
    def _payment_summary(cls, connection, membership_row) -> dict[str, int]:
        recorded = int(connection.execute(
            "SELECT COALESCE(SUM(amount_paise),0) FROM membership_payments "
            "WHERE membership_id=? AND status='recorded'",
            (membership_row["id"],),
        ).fetchone()[0])
        return cls._payment_summary_from_recorded(membership_row, recorded)

    def _membership_payload(self, connection, row) -> dict[str, object]:
        item = self.membership_service._safe_membership(row, now=self._now())
        item["payment"] = self._payment_summary(connection, row)
        return item

    @staticmethod
    def _customer_row(connection, customer_id: str):
        row = connection.execute(
            "SELECT id,status,display_name,email,phone_e164,phone_verified,person_type,joined_at,"
            "staff_designation,admin_note,created_at,last_login_at "
            "FROM customers WHERE id=? AND status!='deleted'",
            (customer_id,),
        ).fetchone()
        if row is None:
            raise AdminSoftwareNotFound("Customer not found")
        return row

    def _current_membership_row(self, connection, customer_id: str):
        self.membership_service._reconcile_connection(connection, customer_id=customer_id)
        return connection.execute(
            "SELECT * FROM memberships WHERE customer_id=? AND status='active' "
            "ORDER BY ends_at ASC LIMIT 1",
            (customer_id,),
        ).fetchone()

    def _record_payment_connection(
        self,
        connection,
        membership_id: str,
        *,
        amount_paise: int,
        method: str,
        paid_at: int,
        note: str | None,
        actor_admin_user_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        membership = connection.execute("SELECT * FROM memberships WHERE id=?", (membership_id,)).fetchone()
        if membership is None:
            raise AdminSoftwareNotFound("Membership not found")
        if membership["status"] == "cancelled":
            raise AdminSoftwareConflict("Cannot record payment against a cancelled membership")
        if idempotency_key:
            existing = connection.execute(
                "SELECT * FROM membership_payments WHERE recorded_by_admin_user_id=? AND idempotency_key=?",
                (actor_admin_user_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if (
                    existing["membership_id"] != membership_id
                    or int(existing["amount_paise"]) != amount_paise
                    or existing["method"] != method
                    or existing["note"] != note
                    or existing["status"] != "recorded"
                ):
                    raise AdminSoftwareConflict("Idempotency key was already used for a different payment")
                return self._safe_payment(existing)
        summary = self._payment_summary(connection, membership)
        if amount_paise <= 0:
            raise AdminSoftwareValidationError({"amountPaidPaise": "Amount must be greater than zero"})
        if amount_paise > summary["pendingPaise"]:
            raise AdminSoftwareConflict("Payment exceeds pending membership balance")
        payment_id = uuid4().hex
        now = self._now()
        connection.execute(
            "INSERT INTO membership_payments(id,membership_id,amount_paise,currency,method,note,paid_at,"
            "status,recorded_by_admin_user_id,idempotency_key,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (payment_id, membership_id, amount_paise, membership["currency_snapshot"], method,
             note, paid_at, "recorded", actor_admin_user_id, idempotency_key, now),
        )
        self.admin_service._audit(
            connection,
            actor_admin_user_id,
            "membership_payment_recorded",
            target_type="membership_payment",
            target_id=payment_id,
            metadata={"membershipId": membership_id, "amountPaise": amount_paise, "method": method},
        )
        row = connection.execute("SELECT * FROM membership_payments WHERE id=?", (payment_id,)).fetchone()
        return self._safe_payment(row)

    def _validated_payment(self, payload: Mapping[str, object], *, allow_zero: bool = False) -> tuple[int, str, int, str | None]:
        errors: dict[str, str] = {}
        try:
            amount = int(payload.get("amountPaidPaise", payload.get("amountPaise", 0)))
            if amount < 0 or (amount == 0 and not allow_zero):
                raise ValueError
        except (TypeError, ValueError):
            amount = 0
            errors["amountPaidPaise"] = "Amount must be a positive integer in paise"
        method = str(payload.get("paymentMethod", payload.get("method", ""))).strip().casefold()
        if amount > 0 and method not in PAYMENT_METHODS:
            errors["paymentMethod"] = "Select cash, UPI, card, bank transfer, or other"
        try:
            paid_at = int(payload.get("paidAt", self._now()))
            if paid_at < 0 or paid_at > self._now() + 86400:
                raise ValueError
        except (TypeError, ValueError):
            paid_at = self._now()
            errors["paidAt"] = "Payment date is invalid"
        try:
            note = _clean_note(payload.get("note"))
        except ValueError as error:
            note = None
            errors["note"] = str(error)
        if errors:
            raise AdminSoftwareValidationError(errors)
        return amount, method if amount > 0 else "cash", paid_at, note

    def record_payment(
        self,
        membership_id: str,
        payload: Mapping[str, object],
        *,
        actor_admin_user_id: str,
        idempotency_key: object = None,
    ) -> dict[str, object]:
        amount, method, paid_at, note = self._validated_payment(payload)
        key = _clean_idempotency_key(idempotency_key)
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            payment = self._record_payment_connection(
                connection,
                membership_id,
                amount_paise=amount,
                method=method,
                paid_at=paid_at,
                note=note,
                actor_admin_user_id=actor_admin_user_id,
                idempotency_key=key,
            )
            membership = connection.execute("SELECT * FROM memberships WHERE id=?", (membership_id,)).fetchone()
            summary = self._payment_summary(connection, membership)
            connection.commit()
        return {"payment": payment, "summary": summary}

    def create_customer_bundle(
        self,
        payload: Mapping[str, object],
        *,
        actor_admin_user_id: str,
    ) -> dict[str, object]:
        errors: dict[str, str] = {}
        try:
            name = _clean_name(payload.get("displayName", payload.get("name")))
        except ValueError as error:
            name = ""
            errors["displayName"] = str(error)
        try:
            phone = normalize_phone(str(payload.get("phone", "")))
        except ValueError:
            phone = ""
            errors["phone"] = "Use an international mobile number such as +919876543210"
        try:
            person_type = _clean_person_type(payload.get("personType"))
        except ValueError as error:
            person_type = "member"
            errors["personType"] = str(error)
        try:
            note = _clean_note(payload.get("note"))
        except ValueError as error:
            note = None
            errors["note"] = str(error)
        now = self._now()
        plan_id = str(payload.get("planId", "")).strip()
        designation = None
        joined_at = None
        customer_status = "active"
        if person_type == "member":
            if not plan_id:
                errors["planId"] = "Membership plan is required"
        else:
            customer_status = str(payload.get("status", "active")).strip().casefold()
            if customer_status not in CUSTOMER_STATUSES:
                errors["status"] = "Status must be active or disabled"
            try:
                designation = _clean_designation(payload.get("designation"))
            except ValueError as error:
                errors["designation"] = str(error)
            try:
                joined_at = _validated_joined_at(payload.get("joinedAt", now), now=now)
            except ValueError as error:
                errors["joinedAt"] = str(error)
        if errors:
            raise AdminSoftwareValidationError(errors)
        if person_type == "member":
            payment_payload = dict(payload)
            payment_payload["note"] = None
            amount, method, paid_at, _payment_note = self._validated_payment(payment_payload, allow_zero=True)
        else:
            try:
                requested_amount = int(payload.get("amountPaidPaise", payload.get("amountPaise", 0)) or 0)
            except (TypeError, ValueError) as error:
                raise AdminSoftwareValidationError({"amountPaidPaise": "Staff records cannot have payments"}) from error
            if plan_id or requested_amount:
                raise AdminSoftwareValidationError({"personType": "Staff records cannot have plans or payments"})
            amount, method, paid_at = 0, "cash", now
        customer_id = uuid4().hex
        try:
            with self.database.session() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO customers(id,status,display_name,phone_e164,phone_verified,created_at,updated_at,"
                    "created_by_admin_user_id,person_type,joined_at,staff_designation,admin_note) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (customer_id, customer_status, name, phone, 0,
                     now, now, actor_admin_user_id, person_type, joined_at, designation, note),
                )
                connection.execute(
                    "INSERT INTO customer_profiles(customer_id,updated_at) VALUES (?,?)",
                    (customer_id, now),
                )
                membership = None
                payment = None
                summary = None
                if person_type == "member":
                    membership = self.membership_service._create_membership_connection(
                        connection,
                        customer_id,
                        plan_id,
                        actor_admin_user_id=actor_admin_user_id,
                        starts_at=payload.get("startsAt"),
                        source="admin_manual",
                    )
                    connection.execute(
                        "UPDATE customers SET joined_at=?,updated_at=? WHERE id=?",
                        (int(membership["startsAt"]), now, customer_id),
                    )
                    if amount > 0:
                        payment = self._record_payment_connection(
                            connection,
                            str(membership["id"]),
                            amount_paise=amount,
                            method=method,
                            paid_at=paid_at,
                            note=note,
                            actor_admin_user_id=actor_admin_user_id,
                        )
                    membership_row = connection.execute(
                        "SELECT * FROM memberships WHERE id=?", (membership["id"],)
                    ).fetchone()
                    summary = self._payment_summary(connection, membership_row)
                self.admin_service._audit(
                    connection,
                    actor_admin_user_id,
                    "customer_created",
                    target_type="customer",
                    target_id=customer_id,
                    metadata={"personType": person_type, "initialMembership": person_type == "member"},
                )
                row = self._customer_row(connection, customer_id)
                connection.commit()
        except sqlite3.IntegrityError as error:
            if "phone" in str(error).casefold() or "uq_customers_owner_managed_phone" in str(error):
                raise AdminSoftwareConflict("A person with this mobile number already exists") from error
            raise
        return {
            "customer": self._safe_customer(row),
            "membership": membership,
            "payment": payment,
            "paymentSummary": summary,
        }

    def update_customer(
        self,
        customer_id: str,
        payload: Mapping[str, object],
        *,
        actor_admin_user_id: str,
    ) -> dict[str, object]:
        unexpected = sorted(set(payload) - {"displayName", "phone", "status", "designation", "joinedAt", "note"})
        if unexpected:
            raise AdminSoftwareValidationError({field: "Unexpected field" for field in unexpected})
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._customer_row(connection, customer_id)
            name = current["display_name"]
            phone = current["phone_e164"]
            status = current["status"]
            designation = current["staff_designation"]
            joined_at = current["joined_at"]
            note = current["admin_note"]
            if "displayName" in payload:
                try:
                    name = _clean_name(payload["displayName"])
                except ValueError as error:
                    raise AdminSoftwareValidationError({"displayName": str(error)}) from error
            phone_changed = False
            if "phone" in payload:
                try:
                    phone = normalize_phone(str(payload["phone"]))
                except ValueError as error:
                    raise AdminSoftwareValidationError(
                        {"phone": "Use an international mobile number such as +919876543210"}
                    ) from error
                phone_changed = phone != current["phone_e164"]
            if "status" in payload:
                status = str(payload["status"]).strip().casefold()
                if status not in CUSTOMER_STATUSES:
                    raise AdminSoftwareValidationError({"status": "Status must be active or disabled"})
            if "note" in payload:
                try:
                    note = _clean_note(payload["note"])
                except ValueError as error:
                    raise AdminSoftwareValidationError({"note": str(error)}) from error
            if current["person_type"] == "staff":
                if "designation" in payload:
                    try:
                        designation = _clean_designation(payload["designation"])
                    except ValueError as error:
                        raise AdminSoftwareValidationError({"designation": str(error)}) from error
                if "joinedAt" in payload:
                    try:
                        joined_at = _validated_joined_at(payload["joinedAt"], now=self._now())
                    except ValueError as error:
                        raise AdminSoftwareValidationError({"joinedAt": str(error)}) from error
            elif "designation" in payload or "joinedAt" in payload:
                raise AdminSoftwareValidationError({
                    field: "This field is only available for staff"
                    for field in ("designation", "joinedAt") if field in payload
                })
            try:
                connection.execute(
                    "UPDATE customers SET display_name=?,phone_e164=?,phone_verified=?,status=?,staff_designation=?,"
                    "joined_at=?,admin_note=?,updated_at=? WHERE id=?",
                    (name, phone, 0 if phone_changed else current["phone_verified"], status, designation,
                     joined_at, note, self._now(), customer_id),
                )
            except sqlite3.IntegrityError as error:
                raise AdminSoftwareConflict("A person with this mobile number already exists") from error
            if current["person_type"] == "member" and (phone_changed or status == "disabled"):
                reason = "admin_phone_changed" if phone_changed else "admin_disabled"
                connection.execute(
                    "UPDATE customer_sessions SET revoked_at=?,revoke_reason=? "
                    "WHERE customer_id=? AND revoked_at IS NULL",
                    (self._now(), reason, customer_id),
                )
            self.admin_service._audit(
                connection,
                actor_admin_user_id,
                "customer_updated",
                target_type="customer",
                target_id=customer_id,
                metadata={"fields": sorted(payload)},
            )
            row = self._customer_row(connection, customer_id)
            connection.commit()
        return self._safe_customer(row)

    def list_payments(
        self,
        *,
        customer_id: str | None = None,
        membership_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        clauses = ["p.status='recorded'"]
        params: list[object] = []
        if customer_id:
            clauses.append("m.customer_id=?")
            params.append(customer_id)
        if membership_id:
            clauses.append("p.membership_id=?")
            params.append(membership_id)
        params.append(_bounded_limit(limit))
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT p.*,m.customer_id,m.membership_number,c.display_name FROM membership_payments p "
                "JOIN memberships m ON m.id=p.membership_id JOIN customers c ON c.id=m.customer_id "
                f"WHERE {' AND '.join(clauses)} ORDER BY p.paid_at DESC,p.created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [
            {
                "id": row["id"],
                "membershipId": row["membership_id"],
                "membershipNumber": row["membership_number"],
                "customerId": row["customer_id"],
                "customerName": row["display_name"],
                "amountPaise": int(row["amount_paise"]),
                "currency": row["currency"],
                "method": row["method"],
                "note": row["note"],
                "paidAt": int(row["paid_at"]),
                "status": row["status"],
            }
            for row in rows
        ]

    def customer_detail(self, customer_id: str) -> dict[str, object]:
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            customer = self._customer_row(connection, customer_id)
            if customer["person_type"] == "staff":
                connection.commit()
                return {"customer": self._safe_customer(customer)}
            self.membership_service._reconcile_connection(connection, customer_id=customer_id)
            memberships = connection.execute(
                "SELECT * FROM memberships WHERE customer_id=? ORDER BY starts_at DESC,created_at DESC",
                (customer_id,),
            ).fetchall()
            reminders = connection.execute(
                "SELECT id,membership_id,state,trigger_days,created_at,updated_at "
                "FROM notification_reminders WHERE customer_id=? ORDER BY created_at DESC LIMIT 20",
                (customer_id,),
            ).fetchall()
            items = [self._membership_payload(connection, row) for row in memberships]
            connection.commit()
        current = next((item for item in items if item["status"] == "active"), None)
        upcoming = next((item for item in reversed(items) if item["status"] == "scheduled"), None)
        history = [item for item in items if item["status"] in {"expired", "cancelled"}]
        return {
            "customer": self._safe_customer(customer),
            "membership": {"current": current, "upcoming": upcoming, "history": history, "all": items},
            "payments": self.list_payments(customer_id=customer_id, limit=100),
            "notifications": [
                {
                    "id": row["id"],
                    "membershipId": row["membership_id"],
                    "state": row["state"],
                    "triggerDays": int(row["trigger_days"]),
                    "createdAt": int(row["created_at"]),
                    "suppressedAt": int(row["updated_at"]) if row["state"] == "suppressed" else None,
                }
                for row in reminders
            ],
        }

    def list_customers(
        self,
        *,
        query: str = "",
        customer_status: str = "",
        membership_status: str = "",
        plan_id: str = "",
        person_type: str = "",
        limit: int = 200,
    ) -> list[dict[str, object]]:
        needle = query.strip().casefold()[:100]
        if customer_status and customer_status not in CUSTOMER_STATUSES:
            raise AdminSoftwareValidationError({"status": "Invalid customer status filter"})
        allowed_membership = {"", "active", "scheduled", "expired", "cancelled", "none"}
        if membership_status not in allowed_membership:
            raise AdminSoftwareValidationError({"membershipStatus": "Invalid membership status filter"})
        if person_type and person_type not in PERSON_TYPES:
            raise AdminSoftwareValidationError({"personType": "Invalid person type filter"})
        membership_order = (
            "CASE status WHEN 'active' THEN 0 WHEN 'scheduled' THEN 1 "
            "WHEN 'expired' THEN 2 ELSE 3 END,ends_at DESC,created_at DESC,id"
        )
        pattern = f"%{needle}%"
        bounded_limit = _bounded_limit(limit, 200)
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self.membership_service._reconcile_connection(connection)
            rows = connection.execute(
                "SELECT c.id,c.status,c.display_name,c.email,c.phone_e164,c.phone_verified,c.person_type,c.joined_at,"
                "c.staff_designation,c.admin_note,c.created_at,c.last_login_at "
                "FROM customers c WHERE c.status!='deleted' AND (?='' OR c.status=?) AND (?='' OR c.person_type=?) "
                "AND (?='' OR lower(COALESCE(c.display_name,'')) LIKE ? OR COALESCE(c.phone_e164,'') LIKE ? "
                "OR lower(COALESCE(c.staff_designation,'')) LIKE ? OR EXISTS(SELECT 1 FROM memberships search_m "
                "WHERE search_m.customer_id=c.id AND lower(search_m.membership_number) LIKE ?)) "
                "AND (?='' OR (c.person_type='member' AND COALESCE((SELECT m.status FROM memberships m WHERE m.customer_id=c.id "
                f"ORDER BY {membership_order} LIMIT 1),'none')=?)) "
                "AND (?='' OR (c.person_type='member' AND (SELECT m.plan_id FROM memberships m WHERE m.customer_id=c.id "
                f"ORDER BY {membership_order} LIMIT 1)=?)) "
                "ORDER BY c.display_name COLLATE NOCASE,c.id LIMIT ?",
                (
                    customer_status, customer_status, person_type, person_type, needle, pattern, pattern, pattern, pattern,
                    membership_status, membership_status, plan_id, plan_id, bounded_limit,
                ),
            ).fetchall()
            customer_ids = [str(row["id"]) for row in rows]
            selected_memberships: dict[str, object] = {}
            payment_totals: dict[str, int] = {}
            if customer_ids:
                placeholders = ",".join("?" for _ in customer_ids)
                membership_rows = connection.execute(
                    f"SELECT * FROM memberships WHERE customer_id IN ({placeholders}) "
                    f"ORDER BY customer_id,{membership_order}",
                    customer_ids,
                ).fetchall()
                for membership in membership_rows:
                    selected_memberships.setdefault(str(membership["customer_id"]), membership)
                membership_ids = [str(row["id"]) for row in selected_memberships.values()]
                if membership_ids:
                    membership_placeholders = ",".join("?" for _ in membership_ids)
                    totals = connection.execute(
                        "SELECT membership_id,COALESCE(SUM(amount_paise),0) AS recorded_paise "
                        f"FROM membership_payments WHERE status='recorded' AND membership_id IN ({membership_placeholders}) "
                        "GROUP BY membership_id",
                        membership_ids,
                    ).fetchall()
                    payment_totals = {str(item["membership_id"]): int(item["recorded_paise"]) for item in totals}
            result: list[dict[str, object]] = []
            now = self._now()
            for row in rows:
                item = self._safe_customer(row)
                membership = selected_memberships.get(str(row["id"])) if row["person_type"] == "member" else None
                if membership is None:
                    item["membership"] = None
                else:
                    membership_item = self.membership_service._safe_membership(membership, now=now)
                    membership_item["payment"] = self._payment_summary_from_recorded(
                        membership, payment_totals.get(str(membership["id"]), 0)
                    )
                    item["membership"] = membership_item
                result.append(item)
            connection.commit()
        return result

    def fees(
        self,
        *,
        query: str = "",
        pending_only: bool = False,
        balance: str = "",
        limit: int = 300,
    ) -> dict[str, object]:
        needle = query.strip().casefold()[:100]
        pattern = f"%{needle}%"
        balance_filter = balance.strip().casefold()
        if pending_only and not balance_filter:
            balance_filter = "pending"
        if balance_filter not in {"", "pending", "paid"}:
            raise AdminSoftwareValidationError({"balance": "Invalid fee balance filter"})
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self.membership_service._reconcile_connection(connection)
            memberships = connection.execute(
                "WITH fee_rows AS ("
                "SELECT m.*,c.display_name,c.phone_e164,"
                "COALESCE(SUM(CASE WHEN p.status='recorded' THEN p.amount_paise ELSE 0 END),0) AS recorded_paise,"
                "CASE WHEN m.source='payment' AND m.payment_reference IS NOT NULL THEN 0 "
                "ELSE MAX(0,m.plan_price_paise_snapshot-COALESCE(SUM(CASE WHEN p.status='recorded' THEN p.amount_paise ELSE 0 END),0)) END AS pending_paise "
                "FROM memberships m JOIN customers c ON c.id=m.customer_id "
                "LEFT JOIN membership_payments p ON p.membership_id=m.id "
                "WHERE c.status!='deleted' AND c.person_type='member' AND m.status!='cancelled' "
                "AND (?='' OR lower(COALESCE(c.display_name,'')) LIKE ? OR COALESCE(c.phone_e164,'') LIKE ? "
                "OR lower(m.membership_number) LIKE ?) "
                "GROUP BY m.id) "
                "SELECT fee_rows.*,COALESCE(SUM(pending_paise) OVER (),0) AS total_pending_paise "
                "FROM fee_rows WHERE (?='' OR (?='pending' AND pending_paise>0) OR (?='paid' AND pending_paise=0)) "
                "ORDER BY pending_paise DESC,ends_at ASC,id LIMIT ?",
                (needle, pattern, pattern, pattern, balance_filter, balance_filter, balance_filter,
                 _bounded_limit(limit, 300)),
            ).fetchall()
            rows: list[dict[str, object]] = []
            pending_total = int(memberships[0]["total_pending_paise"]) if memberships else 0
            now = self._now()
            for membership in memberships:
                summary = self._payment_summary_from_recorded(membership, int(membership["recorded_paise"]))
                item = self.membership_service._safe_membership(membership, now=now)
                item["payment"] = summary
                rows.append({
                    "customerId": membership["customer_id"],
                    "customerName": membership["display_name"],
                    "phone": membership["phone_e164"],
                    "membership": item,
                })
            connection.commit()
        return {"pendingFeesTotalPaise": pending_total, "rows": rows}

    def renew_membership(
        self,
        customer_id: str,
        payload: Mapping[str, object],
        *,
        actor_admin_user_id: str,
        idempotency_key: object = None,
    ) -> dict[str, object]:
        plan_id = str(payload.get("planId", "")).strip()
        if not plan_id:
            raise AdminSoftwareValidationError({"planId": "Membership plan is required"})
        amount, method, paid_at, note = self._validated_payment(payload, allow_zero=True)
        key = _clean_idempotency_key(idempotency_key)
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            customer = self._customer_row(connection, customer_id)
            if customer["person_type"] != "member":
                raise AdminSoftwareConflict("Staff records cannot have memberships")
            if key:
                existing = connection.execute(
                    "SELECT * FROM memberships WHERE created_by_admin_user_id=? AND admin_idempotency_key=?",
                    (actor_admin_user_id, key),
                ).fetchone()
                if existing is not None:
                    if existing["customer_id"] != customer_id or existing["plan_id"] != plan_id:
                        raise AdminSoftwareConflict("Idempotency key was already used for a different renewal")
                    if payload.get("startsAt") not in (None, ""):
                        try:
                            requested_start = int(payload["startsAt"])
                        except (TypeError, ValueError) as error:
                            raise AdminSoftwareValidationError({"startsAt": "Start time must be a Unix timestamp"}) from error
                        if int(existing["starts_at"]) != requested_start:
                            raise AdminSoftwareConflict("Idempotency key was already used for a different renewal")
                    existing_payment = connection.execute(
                        "SELECT * FROM membership_payments WHERE recorded_by_admin_user_id=? AND idempotency_key=?",
                        (actor_admin_user_id, key),
                    ).fetchone()
                    if amount > 0:
                        if (
                            existing_payment is None
                            or existing_payment["membership_id"] != existing["id"]
                            or int(existing_payment["amount_paise"]) != amount
                            or existing_payment["method"] != method
                            or existing_payment["note"] != note
                        ):
                            raise AdminSoftwareConflict("Idempotency key was already used for a different renewal")
                    elif existing_payment is not None:
                        raise AdminSoftwareConflict("Idempotency key was already used for a different renewal")
                    membership = self.membership_service._safe_membership(existing, now=self._now())
                    payment = self._safe_payment(existing_payment) if existing_payment is not None else None
                    summary = self._payment_summary(connection, existing)
                    connection.commit()
                    return {"membership": membership, "payment": payment, "paymentSummary": summary}
            membership = self.membership_service._create_membership_connection(
                connection,
                customer_id,
                plan_id,
                actor_admin_user_id=actor_admin_user_id,
                starts_at=payload.get("startsAt"),
                source="admin_manual",
                admin_idempotency_key=key,
            )
            payment = None
            if amount > 0:
                payment = self._record_payment_connection(
                    connection,
                    str(membership["id"]),
                    amount_paise=amount,
                    method=method,
                    paid_at=paid_at,
                    note=note,
                    actor_admin_user_id=actor_admin_user_id,
                    idempotency_key=key,
                )
            now = self._now()
            connection.execute(
                "UPDATE notification_reminders SET state='suppressed',updated_at=? "
                "WHERE customer_id=? AND state='pending' AND membership_id IN ("
                "SELECT id FROM memberships WHERE customer_id=? AND id!=? AND ends_at<=?)",
                (now, customer_id, customer_id, membership["id"], int(membership["startsAt"])),
            )
            self.admin_service._audit(
                connection,
                actor_admin_user_id,
                "membership_renewed",
                target_type="membership",
                target_id=str(membership["id"]),
                metadata={"customerId": customer_id, "planId": plan_id},
            )
            membership_row = connection.execute("SELECT * FROM memberships WHERE id=?", (membership["id"],)).fetchone()
            summary = self._payment_summary(connection, membership_row)
            connection.commit()
        return {"membership": membership, "payment": payment, "paymentSummary": summary}

    def dashboard(self) -> dict[str, object]:
        now = self._now()
        day = 86400
        current = datetime.fromtimestamp(now, tz=INDIA_TIMEZONE)
        day_start = int(current.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        month_start = int(current.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self.membership_service._reconcile_connection(connection)
            total_customers = int(connection.execute(
                "SELECT COUNT(*) FROM customers WHERE status!='deleted' AND person_type='member'"
            ).fetchone()[0])
            total_staff = int(connection.execute(
                "SELECT COUNT(*) FROM customers WHERE status!='deleted' AND person_type='staff'"
            ).fetchone()[0])
            active_members = int(connection.execute(
                "SELECT COUNT(DISTINCT customer_id) FROM memberships WHERE status='active'"
            ).fetchone()[0])
            expiring_soon = int(connection.execute(
                "SELECT COUNT(*) FROM memberships WHERE status='active' AND ends_at>? AND ends_at<=?",
                (now, now + 7 * day),
            ).fetchone()[0])
            expired_members = int(connection.execute(
                "SELECT COUNT(*) FROM customers c WHERE c.status!='deleted' AND c.person_type='member' "
                "AND EXISTS(SELECT 1 FROM memberships e WHERE e.customer_id=c.id AND e.status='expired') "
                "AND NOT EXISTS(SELECT 1 FROM memberships l WHERE l.customer_id=c.id AND l.status IN ('active','scheduled'))"
            ).fetchone()[0])
            new_this_month = int(connection.execute(
                "SELECT COUNT(*) FROM customers WHERE status!='deleted' AND person_type='member' AND joined_at>=?",
                (month_start,),
            ).fetchone()[0])
            manual_today = int(connection.execute(
                "SELECT COALESCE(SUM(amount_paise),0) FROM membership_payments "
                "WHERE status='recorded' AND paid_at>=?",
                (day_start,),
            ).fetchone()[0])
            manual_month = int(connection.execute(
                "SELECT COALESCE(SUM(amount_paise),0) FROM membership_payments "
                "WHERE status='recorded' AND paid_at>=?",
                (month_start,),
            ).fetchone()[0])
            gateway_today = int(connection.execute(
                "SELECT COALESCE(SUM(amount_paise),0) FROM payment_intents "
                "WHERE status='paid' AND paid_at>=?",
                (day_start,),
            ).fetchone()[0])
            gateway_month = int(connection.execute(
                "SELECT COALESCE(SUM(amount_paise),0) FROM payment_intents "
                "WHERE status='paid' AND paid_at>=?",
                (month_start,),
            ).fetchone()[0])
            pending_total = 0
            pending_rows = []
            pending_source_rows = connection.execute(
                "SELECT m.*,c.display_name,COALESCE(SUM(CASE WHEN p.status='recorded' THEN p.amount_paise ELSE 0 END),0) "
                "AS recorded_paise FROM memberships m JOIN customers c ON c.id=m.customer_id "
                "LEFT JOIN membership_payments p ON p.membership_id=m.id "
                "WHERE c.status!='deleted' AND c.person_type='member' AND m.status!='cancelled' GROUP BY m.id"
            ).fetchall()
            for row in pending_source_rows:
                summary = self._payment_summary_from_recorded(row, int(row["recorded_paise"]))
                if summary["pendingPaise"] > 0:
                    pending_total += summary["pendingPaise"]
                    pending_rows.append({
                        "customerId": row["customer_id"],
                        "customerName": row["display_name"],
                        "membershipId": row["id"],
                        "membershipNumber": row["membership_number"],
                        "planName": row["plan_name_snapshot"],
                        "endsAt": int(row["ends_at"]),
                        **summary,
                    })
            expiry_rows = connection.execute(
                "SELECT m.*,c.display_name,c.phone_e164 FROM memberships m JOIN customers c ON c.id=m.customer_id "
                "WHERE c.status!='deleted' AND c.person_type='member' AND m.status='active' "
                "AND m.ends_at>=? AND m.ends_at<? ORDER BY m.ends_at ASC",
                (day_start, day_start + 8 * day),
            ).fetchall()
            expired_rows = connection.execute(
                "SELECT m.*,c.display_name,c.phone_e164 FROM memberships m JOIN customers c ON c.id=m.customer_id "
                "WHERE c.status!='deleted' AND c.person_type='member' AND m.status='expired' "
                "AND NOT EXISTS(SELECT 1 FROM memberships live WHERE live.customer_id=m.customer_id AND live.status IN ('active','scheduled')) "
                "AND m.ends_at=(SELECT MAX(old.ends_at) FROM memberships old WHERE old.customer_id=m.customer_id AND old.status='expired') "
                "ORDER BY m.ends_at DESC LIMIT 50"
            ).fetchall()
            connection.commit()
        expiry = {"expired": [], "today": [], "tomorrow": [], "threeDays": [], "sevenDays": []}
        for row in expired_rows:
            expiry["expired"].append({
                "customerId": row["customer_id"],
                "customerName": row["display_name"],
                "phone": row["phone_e164"],
                "membershipId": row["id"],
                "membershipNumber": row["membership_number"],
                "planName": row["plan_name_snapshot"],
                "endsAt": int(row["ends_at"]),
                "status": "expired",
            })
        for row in expiry_rows:
            ends_at = int(row["ends_at"])
            if ends_at < day_start + day:
                key = "today"
            elif ends_at < day_start + 2 * day:
                key = "tomorrow"
            elif ends_at < day_start + 4 * day:
                key = "threeDays"
            else:
                key = "sevenDays"
            expiry[key].append({
                "customerId": row["customer_id"],
                "customerName": row["display_name"],
                "phone": row["phone_e164"],
                "membershipId": row["id"],
                "membershipNumber": row["membership_number"],
                "planName": row["plan_name_snapshot"],
                "endsAt": int(row["ends_at"]),
                "status": row["status"],
            })
        pending_rows.sort(key=lambda item: int(item["pendingPaise"]), reverse=True)
        recent_customers = self.list_customers(person_type="member", limit=8)
        return {
            "stats": {
                "totalCustomers": total_customers,
                "totalStaff": total_staff,
                "activeMembers": active_members,
                "expiringSoon": expiring_soon,
                "expiredMembers": expired_members,
                "pendingFeesTotalPaise": pending_total,
                "newCustomersThisMonth": new_this_month,
                "paymentsReceivedTodayPaise": manual_today + gateway_today,
                "paymentsReceivedThisMonthPaise": manual_month + gateway_month,
            },
            "expiring": expiry,
            "pendingFees": pending_rows[:12],
            "recentPayments": self.list_payments(limit=8),
            "recentCustomers": recent_customers[:8],
        }

    def list_memberships(
        self,
        *,
        status: str = "",
        plan_id: str = "",
        limit: int = 300,
    ) -> list[dict[str, object]]:
        if status and status not in {"scheduled", "active", "expired", "cancelled"}:
            raise AdminSoftwareValidationError({"status": "Invalid membership status"})
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self.membership_service._reconcile_connection(connection)
            rows = connection.execute(
                "SELECT m.*,c.display_name,c.phone_e164,COALESCE(SUM(CASE WHEN p.status='recorded' THEN p.amount_paise ELSE 0 END),0) "
                "AS recorded_paise FROM memberships m "
                "JOIN customers c ON c.id=m.customer_id "
                "LEFT JOIN membership_payments p ON p.membership_id=m.id "
                "WHERE c.status!='deleted' AND c.person_type='member' "
                "AND (?='' OR m.status=?) AND (?='' OR m.plan_id=?) "
                "GROUP BY m.id ORDER BY m.ends_at ASC LIMIT ?",
                (status, status, plan_id, plan_id, _bounded_limit(limit, 300)),
            ).fetchall()
            result = []
            now = self._now()
            for row in rows:
                membership = self.membership_service._safe_membership(row, now=now)
                membership["payment"] = self._payment_summary_from_recorded(row, int(row["recorded_paise"]))
                result.append({
                    "customer": {"id": row["customer_id"], "displayName": row["display_name"], "phone": row["phone_e164"]},
                    "membership": membership,
                })
            connection.commit()
        return result
