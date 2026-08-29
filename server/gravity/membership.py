from calendar import monthrange
from datetime import datetime, timezone
from math import ceil
from typing import Callable, Mapping
from uuid import uuid4
import json
import re
import sqlite3
import time

from .database import Database


PLAN_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,49}$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
PLAN_STATUSES = {"active", "inactive"}
LIVE_MEMBERSHIP_STATUSES = {"scheduled", "active"}


class MembershipError(Exception):
    pass


class MembershipNotFound(MembershipError):
    pass


class MembershipConflict(MembershipError):
    pass


class MembershipValidationError(MembershipError):
    def __init__(self, fields: Mapping[str, str]) -> None:
        super().__init__("Membership validation failed")
        self.fields = dict(fields)

def _add_months(timestamp: int, months: int) -> int:
    current = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    month_index = current.month - 1 + months
    year = current.year + month_index // 12
    month = month_index % 12 + 1
    day = min(current.day, monthrange(year, month)[1])
    return int(current.replace(year=year, month=month, day=day).timestamp())


def _clean_text(value: object, *, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError("Expected text")
    normalized = " ".join(value.strip().split())
    if not minimum <= len(normalized) <= maximum:
        raise ValueError("Invalid text length")
    return normalized


def _membership_number(now: int) -> str:
    stamp = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y%m%d")
    return f"GF-{stamp}-{uuid4().hex[:8].upper()}"


class MembershipService:
    def __init__(self, database: Database, *, clock: Callable[[], float] | None = None) -> None:
        self.database = database
        self.clock = clock or time.time

    def _now(self) -> int:
        return int(self.clock())
    def _safe_plan(self, row) -> dict[str, object]:
        return {
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "description": row["description"],
            "pricePaise": int(row["price_paise"]),
            "currency": row["currency"],
            "durationMonths": int(row["duration_months"]),
            "status": row["status"],
            "sortOrder": int(row["sort_order"]),
            "updatedAt": int(row["updated_at"]),
        }

    def _safe_membership(self, row, *, now: int | None = None) -> dict[str, object]:
        current = self._now() if now is None else now
        ends_at = int(row["ends_at"])
        remaining = max(0, ceil((ends_at - current) / 86400)) if row["status"] == "active" else 0
        return {
            "id": row["id"],
            "membershipNumber": row["membership_number"],
            "customerId": row["customer_id"],
            "planId": row["plan_id"],
            "planName": row["plan_name_snapshot"],
            "pricePaise": int(row["plan_price_paise_snapshot"]),
            "currency": row["currency_snapshot"],
            "durationMonths": int(row["duration_months_snapshot"]),
            "status": row["status"],
            "startsAt": int(row["starts_at"]),
            "endsAt": ends_at,
            "daysRemaining": remaining,
            "source": row["source"],
            "createdAt": int(row["created_at"]),
        }

    def _event(self, connection, membership_id: str, event_type: str, *, actor_admin_user_id: str | None, metadata: dict[str, object] | None = None) -> None:
        connection.execute(
            "INSERT INTO membership_events(membership_id,event_type,actor_admin_user_id,metadata_json,created_at) VALUES (?,?,?,?,?)",
            (
                membership_id,
                event_type,
                actor_admin_user_id,
                json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True),
                self._now(),
            ),
        )

    def _plan_event(
        self,
        connection,
        plan_id: str,
        event_type: str,
        *,
        actor_admin_user_id: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        connection.execute(
            "INSERT INTO membership_plan_events(plan_id,event_type,actor_admin_user_id,metadata_json,created_at) "
            "VALUES (?,?,?,?,?)",
            (
                plan_id,
                event_type,
                actor_admin_user_id,
                json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True),
                self._now(),
            ),
        )

    def _reconcile_connection(self, connection, *, customer_id: str | None = None) -> None:
        now = self._now()
        customer_clause = " AND customer_id=?" if customer_id else ""
        customer_params: list[object] = [customer_id] if customer_id else []
        expired_rows = connection.execute(
            "SELECT id,status,starts_at,ends_at FROM memberships "
            "WHERE status IN ('scheduled','active') AND ends_at<=?" + customer_clause,
            [now, *customer_params],
        ).fetchall()
        activating_rows = connection.execute(
            "SELECT id,status,starts_at,ends_at FROM memberships "
            "WHERE status='scheduled' AND starts_at<=? AND ends_at>?" + customer_clause,
            [now, now, *customer_params],
        ).fetchall()
        for row, next_status, event_type in (
            *((row, "expired", "expired") for row in expired_rows),
            *((row, "active", "activated") for row in activating_rows),
        ):
            status = str(row["status"])
            cursor = connection.execute(
                "UPDATE memberships SET status=?,updated_at=? WHERE id=? AND status=?",
                (next_status, now, row["id"], status),
            )
            if cursor.rowcount != 1:
                continue
            self._event(
                connection,
                str(row["id"]),
                event_type,
                actor_admin_user_id=None,
                metadata={"automatic": True},
            )

    def reconcile(self, *, customer_id: str | None = None) -> None:
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._reconcile_connection(connection, customer_id=customer_id)
            connection.commit()

    def list_plans(self, *, active_only: bool = True) -> list[dict[str, object]]:
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT * FROM membership_plans WHERE (?=0 OR status='active') ORDER BY sort_order,name",
                (1 if active_only else 0,),
            ).fetchall()
        return [self._safe_plan(row) for row in rows]

    def _validated_plan_values(self, payload: Mapping[str, object], *, current=None) -> dict[str, object]:
        values: dict[str, object] = {
            "code": current["code"] if current is not None else "",
            "name": current["name"] if current is not None else "",
            "description": current["description"] if current is not None else None,
            "price_paise": int(current["price_paise"]) if current is not None else -1,
            "currency": current["currency"] if current is not None else "INR",
            "duration_months": int(current["duration_months"]) if current is not None else 0,
            "status": current["status"] if current is not None else "inactive",
            "sort_order": int(current["sort_order"]) if current is not None else 0,
        }
        errors: dict[str, str] = {}

        if current is None or "code" in payload:
            raw = str(payload.get("code", "")).strip().lower()
            if not PLAN_CODE_PATTERN.fullmatch(raw):
                errors["code"] = "Use 3-50 lowercase letters, numbers, or hyphens"
            else:
                values["code"] = raw
        if current is None or "name" in payload:
            try:
                values["name"] = _clean_text(payload.get("name"), minimum=2, maximum=80)
            except ValueError:
                errors["name"] = "Plan name must be 2-80 characters"
        if current is None or "description" in payload:
            raw_description = payload.get("description")
            if raw_description in {None, ""}:
                values["description"] = None
            else:
                try:
                    values["description"] = _clean_text(raw_description, minimum=1, maximum=500)
                except ValueError:
                    errors["description"] = "Description must be 1-500 characters"
        if current is None or "pricePaise" in payload:
            try:
                price = int(payload.get("pricePaise"))
                if price < 0:
                    raise ValueError
                values["price_paise"] = price
            except (TypeError, ValueError):
                errors["pricePaise"] = "Price must be a non-negative integer in paise"
        if current is None or "currency" in payload:
            currency = str(payload.get("currency", "INR")).strip().upper()
            if not CURRENCY_PATTERN.fullmatch(currency):
                errors["currency"] = "Currency must be a three-letter code"
            else:
                values["currency"] = currency
        if current is None or "durationMonths" in payload:
            try:
                duration = int(payload.get("durationMonths"))
                if not 1 <= duration <= 36:
                    raise ValueError
                values["duration_months"] = duration
            except (TypeError, ValueError):
                errors["durationMonths"] = "Duration must be 1-36 months"
        if current is None or "status" in payload:
            status = str(payload.get("status", "inactive")).strip().lower()
            if status not in PLAN_STATUSES:
                errors["status"] = "Status must be active or inactive"
            else:
                values["status"] = status
        if current is None or "sortOrder" in payload:
            try:
                values["sort_order"] = int(payload.get("sortOrder", 0))
            except (TypeError, ValueError):
                errors["sortOrder"] = "Sort order must be an integer"
        if errors:
            raise MembershipValidationError(errors)
        return values

    def create_plan(
        self,
        payload: Mapping[str, object],
        *,
        actor_admin_user_id: str,
    ) -> dict[str, object]:
        if not actor_admin_user_id:
            raise MembershipValidationError({"actor": "Administrator is required"})
        values = self._validated_plan_values(payload)
        now = self._now()
        plan_id = uuid4().hex
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO membership_plans(id,code,name,description,price_paise,currency,duration_months,status,sort_order,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        plan_id,
                        values["code"],
                        values["name"],
                        values["description"],
                        values["price_paise"],
                        values["currency"],
                        values["duration_months"],
                        values["status"],
                        values["sort_order"],
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise MembershipConflict("Membership plan code already exists") from error
            self._plan_event(
                connection,
                plan_id,
                "created",
                actor_admin_user_id=actor_admin_user_id,
                metadata={"status": values["status"]},
            )
            if values["status"] == "active":
                self._plan_event(
                    connection,
                    plan_id,
                    "activated",
                    actor_admin_user_id=actor_admin_user_id,
                )
            row = connection.execute("SELECT * FROM membership_plans WHERE id=?", (plan_id,)).fetchone()
            connection.commit()
        return self._safe_plan(row)

    def update_plan(
        self,
        plan_id: str,
        payload: Mapping[str, object],
        *,
        actor_admin_user_id: str,
    ) -> dict[str, object]:
        if not actor_admin_user_id:
            raise MembershipValidationError({"actor": "Administrator is required"})
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute("SELECT * FROM membership_plans WHERE id=?", (plan_id,)).fetchone()
            if current is None:
                connection.rollback()
                raise MembershipNotFound("Membership plan not found")
            values = self._validated_plan_values(payload, current=current)
            changes = {
                key: values[key]
                for key in values
                if values[key] != current[key]
            }
            if changes:
                try:
                    connection.execute(
                        "UPDATE membership_plans SET code=?,name=?,description=?,price_paise=?,currency=?,duration_months=?,status=?,sort_order=?,updated_at=? WHERE id=?",
                        (
                            values["code"], values["name"], values["description"], values["price_paise"],
                            values["currency"], values["duration_months"], values["status"],
                            values["sort_order"], self._now(), plan_id,
                        ),
                    )
                except sqlite3.IntegrityError as error:
                    connection.rollback()
                    raise MembershipConflict("Membership plan code already exists") from error
                self._plan_event(
                    connection,
                    plan_id,
                    "updated",
                    actor_admin_user_id=actor_admin_user_id,
                    metadata={"fields": sorted(changes)},
                )
                if current["status"] != values["status"]:
                    self._plan_event(
                        connection,
                        plan_id,
                        "activated" if values["status"] == "active" else "deactivated",
                        actor_admin_user_id=actor_admin_user_id,
                    )
            row = connection.execute("SELECT * FROM membership_plans WHERE id=?", (plan_id,)).fetchone()
            connection.commit()
        return self._safe_plan(row)

    def list_customer_memberships(self, customer_id: str) -> list[dict[str, object]]:
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._reconcile_connection(connection, customer_id=customer_id)
            rows = connection.execute(
                "SELECT * FROM memberships WHERE customer_id=? ORDER BY starts_at DESC,created_at DESC",
                (customer_id,),
            ).fetchall()
            connection.commit()
        now = self._now()
        return [self._safe_membership(row, now=now) for row in rows]

    def customer_summary(self, customer_id: str) -> dict[str, object]:
        memberships = self.list_customer_memberships(customer_id)
        current = next((item for item in memberships if item["status"] == "active"), None)
        upcoming = sorted(
            (item for item in memberships if item["status"] == "scheduled"),
            key=lambda item: int(item["startsAt"]),
        )
        history = [item for item in memberships if item["status"] in {"expired", "cancelled"}]
        return {
            "current": current,
            "upcoming": upcoming[0] if upcoming else None,
            "history": history,
        }

    def _plan_row(self, connection, plan_id: str):
        row = connection.execute(
            "SELECT * FROM membership_plans WHERE id=? AND status='active'",
            (plan_id,),
        ).fetchone()
        if row is None:
            raise MembershipNotFound("Membership plan not found")
        return row

    def _customer_exists(self, connection, customer_id: str) -> None:
        row = connection.execute(
            "SELECT status FROM customers WHERE id=?",
            (customer_id,),
        ).fetchone()
        if row is None or row["status"] == "deleted":
            raise MembershipNotFound("Customer not found")
        if row["status"] != "active":
            raise MembershipConflict("Customer account is not active")
    def _create_membership_connection(
        self,
        connection,
        customer_id: str,
        plan_id: str,
        *,
        actor_admin_user_id: str | None = None,
        starts_at: int | None = None,
        source: str = "admin_manual",
        payment_reference: str | None = None,
        admin_idempotency_key: str | None = None,
    ) -> dict[str, object]:
        now = self._now()
        if source not in {"admin_manual", "payment", "import"}:
            raise MembershipValidationError({"source": "Invalid membership source"})
        if source == "admin_manual" and not actor_admin_user_id:
            raise MembershipValidationError({"actor": "Administrator is required"})
        if source == "payment" and not payment_reference:
            raise MembershipValidationError({"paymentReference": "Verified payment reference is required"})
        self._reconcile_connection(connection, customer_id=customer_id)
        self._customer_exists(connection, customer_id)
        if payment_reference and connection.execute(
            "SELECT 1 FROM memberships WHERE payment_reference=? LIMIT 1", (payment_reference,)
        ).fetchone():
            raise MembershipConflict("Payment reference has already been used")
        plan = self._plan_row(connection, plan_id)
        live = connection.execute(
            "SELECT starts_at,ends_at FROM memberships WHERE customer_id=? "
            "AND status IN ('scheduled','active') ORDER BY ends_at DESC",
            (customer_id,),
        ).fetchall()
        if starts_at is None:
            start = max([now, *(int(row["ends_at"]) for row in live)])
        else:
            try:
                start = int(starts_at)
            except (TypeError, ValueError) as error:
                raise MembershipValidationError({"startsAt": "Start time must be a Unix timestamp"}) from error
            if start < now - 86400:
                raise MembershipValidationError({"startsAt": "Start time cannot be more than one day in the past"})
        end = _add_months(start, int(plan["duration_months"]))
        if connection.execute(
            "SELECT 1 FROM memberships WHERE customer_id=? AND status IN ('scheduled','active') "
            "AND starts_at < ? AND ends_at > ? LIMIT 1",
            (customer_id, end, start),
        ).fetchone():
            raise MembershipConflict("Membership period overlaps an existing live membership")
        membership_id = uuid4().hex
        status = "active" if start <= now < end else "scheduled"
        number = _membership_number(now)
        connection.execute(
            "INSERT INTO memberships(id,membership_number,customer_id,plan_id,plan_name_snapshot,"
            "plan_price_paise_snapshot,currency_snapshot,duration_months_snapshot,status,starts_at,"
            "ends_at,source,payment_reference,created_by_admin_user_id,admin_idempotency_key,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                membership_id, number, customer_id, plan["id"], plan["name"], plan["price_paise"],
                plan["currency"], plan["duration_months"], status, start, end, source,
                payment_reference, actor_admin_user_id, admin_idempotency_key, now, now,
            ),
        )
        self._event(
            connection,
            membership_id,
            "created",
            actor_admin_user_id=actor_admin_user_id,
            metadata={"source": source, "planId": plan["id"]},
        )
        if status == "active":
            self._event(
                connection,
                membership_id,
                "activated",
                actor_admin_user_id=actor_admin_user_id,
                metadata={"automatic": False},
            )
        row = connection.execute("SELECT * FROM memberships WHERE id=?", (membership_id,)).fetchone()
        return self._safe_membership(row, now=now)

    def create_membership(
        self,
        customer_id: str,
        plan_id: str,
        *,
        actor_admin_user_id: str | None = None,
        starts_at: int | None = None,
        source: str = "admin_manual",
        payment_reference: str | None = None,
        admin_idempotency_key: str | None = None,
    ) -> dict[str, object]:
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            membership = self._create_membership_connection(
                connection,
                customer_id,
                plan_id,
                actor_admin_user_id=actor_admin_user_id,
                starts_at=starts_at,
                source=source,
                payment_reference=payment_reference,
                admin_idempotency_key=admin_idempotency_key,
            )
            connection.commit()
        return membership

    def cancel_membership(
        self,
        membership_id: str,
        *,
        actor_admin_user_id: str,
        reason: object,
    ) -> dict[str, object]:
        try:
            clean_reason = _clean_text(reason, minimum=3, maximum=300)
        except ValueError:
            raise MembershipValidationError({"reason": "Cancellation reason must be 3-300 characters"})
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM memberships WHERE id=?",
                (membership_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise MembershipNotFound("Membership not found")
            if row["status"] not in LIVE_MEMBERSHIP_STATUSES:
                connection.rollback()
                raise MembershipConflict("Only scheduled or active memberships can be cancelled")
            connection.execute(
                "UPDATE memberships SET status='cancelled',cancellation_reason=?,cancelled_at=?,updated_at=? WHERE id=?",
                (clean_reason, now, now, membership_id),
            )
            self._event(
                connection,
                membership_id,
                "cancelled",
                actor_admin_user_id=actor_admin_user_id,
                metadata={"reason": clean_reason},
            )
            updated = connection.execute("SELECT * FROM memberships WHERE id=?", (membership_id,)).fetchone()
            connection.commit()
        return self._safe_membership(updated, now=now)
    def expiring_within(self, days: int = 7) -> list[dict[str, object]]:
        bounded = min(max(int(days), 1), 90)
        now = self._now()
        threshold = now + bounded * 86400
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._reconcile_connection(connection)
            rows = connection.execute(
                "SELECT m.*,c.display_name,c.email,c.phone_e164 FROM memberships m "
                "JOIN customers c ON c.id=m.customer_id WHERE m.status='active' "
                "AND m.ends_at>? AND m.ends_at<=? ORDER BY m.ends_at ASC",
                (now, threshold),
            ).fetchall()
            connection.commit()
        result: list[dict[str, object]] = []
        for row in rows:
            item = self._safe_membership(row, now=now)
            item["customer"] = {
                "displayName": row["display_name"],
                "email": row["email"],
                "phone": row["phone_e164"],
            }
            result.append(item)
        return result
