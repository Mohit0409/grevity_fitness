from __future__ import annotations

from typing import Callable
from uuid import uuid4
import json
import re
import time

from .config import Settings
from .database import Database
from .membership import MembershipService


DELIVERY_TARGETS = (
    ("customer", "email", "email"),
    ("customer", "sms", "phone"),
    ("customer", "whatsapp", "phone"),
    ("owner", "email", "email"),
    ("owner", "sms", "phone"),
    ("owner", "whatsapp", "whatsapp"),
)
TERMINAL_DELIVERY_STATUSES = {"sent", "missing_recipient"}
ERROR_CODE_PATTERN = re.compile(r"^[a-zA-Z0-9_.:-]{1,80}$")


class NotificationError(Exception):
    pass


class NotificationNotFound(NotificationError):
    pass


class NotificationConflict(NotificationError):
    pass


class NotificationRecipientUnavailable(NotificationConflict):
    pass


class NotificationValidationError(NotificationError):
    pass


def _days(value: object) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError) as error:
        raise NotificationValidationError("Reminder days must be an integer") from error
    if not 0 <= days <= 90:
        raise NotificationValidationError("Reminder days must be between 0 and 90")
    return days


class NotificationService:
    def __init__(
        self,
        database: Database,
        membership_service: MembershipService,
        settings: Settings | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.database = database
        self.membership_service = membership_service
        self.settings = settings
        self.clock = clock or time.time

    def _now(self) -> int:
        return int(self.clock())

    def provider_blockers(self) -> dict[str, str]:
        settings = self.settings
        if settings is None:
            return {"email": "BLOCKED_EXTERNAL_CONFIG", "sms": "BLOCKED_EXTERNAL_CONFIG", "whatsapp": "BLOCKED_EXTERNAL_CONFIG"}
        return {
            "email": "READY" if settings.smtp_configured else "BLOCKED_EXTERNAL_CONFIG",
            "sms": "BLOCKED_ADAPTER_MISSING" if settings.sms_credentials_configured else "BLOCKED_EXTERNAL_CONFIG",
            "whatsapp": "BLOCKED_ADAPTER_MISSING" if settings.whatsapp_credentials_configured else "BLOCKED_EXTERNAL_CONFIG",
        }

    def _has_renewal(self, connection, customer_id: str, membership_id: str, ends_at: int) -> bool:
        row = connection.execute(
            "SELECT 1 FROM memberships WHERE customer_id=? AND id<>? "
            "AND status IN ('scheduled','active') AND starts_at<=? AND ends_at>? LIMIT 1",
            (customer_id, membership_id, ends_at, ends_at),
        ).fetchone()
        return row is not None

    def _delivery_rows(self, connection, reminder_id: str, *, recipient_role: str | None = None):
        if recipient_role is None:
            return connection.execute(
                "SELECT * FROM notification_deliveries WHERE reminder_id=? ORDER BY recipient_role,channel",
                (reminder_id,),
            ).fetchall()
        return connection.execute(
            "SELECT * FROM notification_deliveries WHERE reminder_id=? AND recipient_role=? ORDER BY channel",
            (reminder_id, recipient_role),
        ).fetchall()

    def _safe_delivery(self, row) -> dict[str, object]:
        return {
            "id": row["id"],
            "channel": row["channel"],
            "recipientRole": row["recipient_role"],
            "recipientRef": row["recipient_ref"],
            "status": row["status"],
            "attemptCount": int(row["attempt_count"]),
            "nextAttemptAt": row["next_attempt_at"],
            "lastErrorCode": row["last_error_code"],
            "sentAt": row["sent_at"],
        }

    def _safe_reminder(self, row, deliveries) -> dict[str, object]:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            payload = {}
        return {
            "id": row["id"],
            "eventType": row["event_type"],
            "customerId": row["customer_id"],
            "membershipId": row["membership_id"],
            "triggerDays": int(row["trigger_days"]),
            "triggerAt": int(row["trigger_at"]),
            "state": row["state"],
            "payload": payload,
            "createdAt": int(row["created_at"]),
            "deliveries": [self._safe_delivery(item) for item in deliveries],
        }

    def _owner_recipient(self, channel: str) -> str | None:
        settings = self.settings
        if settings is None:
            return None
        if channel == "email":
            return settings.owner_email or None
        if channel == "sms":
            return settings.owner_phone or None
        if channel == "whatsapp":
            return settings.owner_whatsapp or None
        return None

    def _initial_recipient(self, recipient_role: str, channel: str, customer: dict[str, object]) -> str | None:
        if recipient_role == "owner":
            return self._owner_recipient(channel)
        if channel == "email":
            return str(customer.get("email") or "") or None
        return str(customer.get("phone") or "") or None

    def _create_deliveries(self, connection, reminder_id: str, customer: dict[str, object]) -> None:
        now = self._now()
        for recipient_role, channel, recipient_ref in DELIVERY_TARGETS:
            recipient = self._initial_recipient(recipient_role, channel, customer)
            status = "blocked_external_config" if recipient else "missing_recipient"
            connection.execute(
                "INSERT OR IGNORE INTO notification_deliveries("
                "id,reminder_id,channel,recipient_role,recipient_ref,status,attempt_count,created_at,updated_at"
                ") VALUES (?,?,?,?,?,?,?,?,?)",
                (uuid4().hex, reminder_id, channel, recipient_role, recipient_ref, status, 0, now, now),
            )

    def _expiry_day_candidates(self) -> list[dict[str, object]]:
        self.membership_service.reconcile()
        now = self._now()
        lower_bound = now - 86400
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT m.*,c.display_name,c.email,c.phone_e164 FROM memberships m "
                "JOIN customers c ON c.id=m.customer_id "
                "WHERE m.status='expired' AND m.ends_at<=? AND m.ends_at>? ORDER BY m.ends_at ASC",
                (now, lower_bound),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "membershipNumber": row["membership_number"],
                "customerId": row["customer_id"],
                "planName": row["plan_name_snapshot"],
                "endsAt": int(row["ends_at"]),
                "daysRemaining": 0,
                "customer": {
                    "displayName": row["display_name"],
                    "email": row["email"],
                    "phone": row["phone_e164"],
                },
            }
            for row in rows
        ]

    def _candidates_for_window(self, days: int) -> list[dict[str, object]]:
        if days == 0:
            return self._expiry_day_candidates()
        lower_exclusive = {7: 3, 3: 1, 1: 0}.get(days, max(days - 1, 0))
        return [
            item
            for item in self.membership_service.expiring_within(days)
            if lower_exclusive < int(item.get("daysRemaining") or 0) <= days
        ]

    def scan_expiring(self, days_before: object = 7) -> dict[str, int]:
        days = _days(days_before)
        candidates = self._candidates_for_window(days)
        now = self._now()
        created = 0
        deduped = 0
        suppressed_renewed = 0
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for item in candidates:
                customer_id = str(item["customerId"])
                membership_id = str(item["id"])
                ends_at = int(item["endsAt"])
                if self._has_renewal(connection, customer_id, membership_id, ends_at):
                    suppressed_renewed += 1
                    continue
                dedupe_key = f"membership_expiry:{membership_id}:{days}"
                reminder_id = uuid4().hex
                payload = {
                    "planName": item.get("planName"),
                    "membershipNumber": item.get("membershipNumber"),
                    "endsAt": ends_at,
                    "daysRemaining": item.get("daysRemaining"),
                }
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO notification_reminders("
                    "id,dedupe_key,event_type,customer_id,membership_id,trigger_days,trigger_at,state,payload_json,created_at,updated_at"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        reminder_id, dedupe_key, "membership_expiry", customer_id, membership_id,
                        days, ends_at - days * 86400, "pending",
                        json.dumps(payload, separators=(",", ":"), sort_keys=True), now, now,
                    ),
                )
                if cursor.rowcount == 1:
                    created += 1
                else:
                    deduped += 1
                    existing = connection.execute(
                        "SELECT id FROM notification_reminders WHERE dedupe_key=?",
                        (dedupe_key,),
                    ).fetchone()
                    if existing is not None:
                        reminder_id = str(existing["id"])
                self._create_deliveries(connection, reminder_id, dict(item.get("customer") or {}))
            connection.commit()
        return {
            "daysBefore": days,
            "scanned": len(candidates),
            "created": created,
            "deduped": deduped,
            "suppressedRenewed": suppressed_renewed,
        }

    def reconcile(self) -> int:
        self.membership_service.reconcile()
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            invalid = connection.execute(
                "UPDATE notification_reminders SET state='suppressed',updated_at=? "
                "WHERE state='pending' AND id IN ("
                "SELECT r.id FROM notification_reminders r "
                "JOIN memberships m ON m.id=r.membership_id "
                "JOIN customers c ON c.id=r.customer_id "
                "WHERE r.state='pending' AND ("
                "NOT (m.status='active' OR (r.trigger_days=0 AND m.status='expired')) "
                "OR c.status!='active'"
                ")"
                ")",
                (now,),
            )
            renewed = connection.execute(
                "UPDATE notification_reminders SET state='suppressed',updated_at=? "
                "WHERE state='pending' AND id IN ("
                "SELECT DISTINCT r.id FROM notification_reminders r "
                "JOIN memberships m ON m.id=r.membership_id "
                "JOIN memberships renewal ON renewal.customer_id=r.customer_id "
                "AND renewal.id<>r.membership_id "
                "AND renewal.status IN ('scheduled','active') "
                "AND renewal.starts_at<=m.ends_at AND renewal.ends_at>m.ends_at "
                "WHERE r.state='pending'"
                ")",
                (now,),
            )
            suppressed = max(0, int(invalid.rowcount or 0)) + max(0, int(renewed.rowcount or 0))
            connection.commit()
        return suppressed

    @staticmethod
    def _batched_deliveries(connection, reminder_ids: list[str], *, recipient_role: str | None = None):
        grouped: dict[str, list[object]] = {reminder_id: [] for reminder_id in reminder_ids}
        if not reminder_ids:
            return grouped
        placeholders = ",".join("?" for _ in reminder_ids)
        params: list[object] = list(reminder_ids)
        role_clause = ""
        if recipient_role is not None:
            role_clause = " AND recipient_role=?"
            params.append(recipient_role)
        rows = connection.execute(
            f"SELECT * FROM notification_deliveries WHERE reminder_id IN ({placeholders})"
            f"{role_clause} ORDER BY reminder_id,recipient_role,channel",
            params,
        ).fetchall()
        for row in rows:
            grouped.setdefault(str(row["reminder_id"]), []).append(row)
        return grouped

    def list_admin(self, limit: int = 100) -> list[dict[str, object]]:
        self.reconcile()
        bounded = min(max(int(limit), 1), 200)
        result: list[dict[str, object]] = []
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT r.*,c.display_name,c.email,c.phone_e164 FROM notification_reminders r "
                "JOIN customers c ON c.id=r.customer_id ORDER BY r.created_at DESC LIMIT ?",
                (bounded,),
            ).fetchall()
            reminder_ids = [str(row["id"]) for row in rows]
            deliveries = self._batched_deliveries(connection, reminder_ids)
            for row in rows:
                item = self._safe_reminder(row, deliveries.get(str(row["id"]), []))
                item["customer"] = {
                    "displayName": row["display_name"],
                    "emailAvailable": bool(row["email"]),
                    "phoneAvailable": bool(row["phone_e164"]),
                }
                result.append(item)
        return result

    def list_customer(self, customer_id: str, limit: int = 50) -> list[dict[str, object]]:
        self.reconcile()
        bounded = min(max(int(limit), 1), 100)
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT * FROM notification_reminders WHERE customer_id=? "
                "ORDER BY created_at DESC LIMIT ?",
                (customer_id, bounded),
            ).fetchall()
            reminder_ids = [str(row["id"]) for row in rows]
            deliveries = self._batched_deliveries(connection, reminder_ids, recipient_role="customer")
            return [
                self._safe_reminder(row, deliveries.get(str(row["id"]), []))
                for row in rows
            ]

    def queue_delivery(self, delivery_id: str) -> dict[str, object]:
        self.reconcile()
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT d.*,r.state AS reminder_state FROM notification_deliveries d "
                "JOIN notification_reminders r ON r.id=d.reminder_id WHERE d.id=?",
                (delivery_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise NotificationNotFound("Notification delivery not found")
            if row["reminder_state"] != "pending":
                connection.rollback()
                raise NotificationConflict("Reminder is no longer pending")
            if row["status"] == "missing_recipient":
                connection.rollback()
                raise NotificationConflict("Recipient is unavailable")
            if row["status"] == "sent":
                connection.rollback()
                raise NotificationConflict("Delivery was already sent")
            connection.execute(
                "UPDATE notification_deliveries SET status='queued',next_attempt_at=?,last_error_code=NULL,updated_at=? WHERE id=?",
                (now, now, delivery_id),
            )
            updated = connection.execute(
                "SELECT * FROM notification_deliveries WHERE id=?",
                (delivery_id,),
            ).fetchone()
            connection.commit()
        return self._safe_delivery(updated)

    def _recipient_for_values(
        self,
        *,
        recipient_role: str,
        channel: str,
        customer_status: str,
        email: str | None,
        phone: str | None,
    ) -> str | None:
        if customer_status != "active":
            return None
        if recipient_role == "owner":
            return self._owner_recipient(channel)
        if channel == "email":
            return email or None
        return phone or None

    def activate_channels(self, channels: set[str]) -> int:
        self.reconcile()
        allowed = {channel for channel in channels if channel in {"email", "sms", "whatsapp"}}
        if not allowed:
            return 0
        now = self._now()
        changed = 0
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for channel in sorted(allowed):
                rows = connection.execute(
                    "SELECT d.*,c.status AS customer_status,c.email,c.phone_e164 "
                    "FROM notification_deliveries d JOIN notification_reminders r ON r.id=d.reminder_id "
                    "JOIN customers c ON c.id=r.customer_id "
                    "WHERE r.state='pending' AND d.channel=? "
                    "AND d.status IN ('blocked_external_config','missing_recipient')",
                    (channel,),
                ).fetchall()
                for row in rows:
                    recipient = self._recipient_for_values(
                        recipient_role=str(row["recipient_role"]),
                        channel=channel,
                        customer_status=str(row["customer_status"]),
                        email=row["email"],
                        phone=row["phone_e164"],
                    )
                    new_status = "queued" if recipient else "missing_recipient"
                    next_attempt = now if recipient else None
                    if row["status"] != new_status or row["next_attempt_at"] != next_attempt:
                        connection.execute(
                            "UPDATE notification_deliveries SET status=?,next_attempt_at=?,updated_at=? WHERE id=?",
                            (new_status, next_attempt, now, row["id"]),
                        )
                        changed += 1
            connection.commit()
        return changed

    def delivery_context(self, delivery_id: str) -> dict[str, object]:
        with self.database.session() as connection:
            row = connection.execute(
                "SELECT d.*,r.state AS reminder_state,r.trigger_days,r.trigger_at,r.payload_json,"
                "c.status AS customer_status,c.display_name,c.email,c.phone_e164 "
                "FROM notification_deliveries d JOIN notification_reminders r ON r.id=d.reminder_id "
                "JOIN customers c ON c.id=r.customer_id WHERE d.id=?",
                (delivery_id,),
            ).fetchone()
        if row is None:
            raise NotificationNotFound("Notification delivery not found")
        if row["reminder_state"] != "pending":
            raise NotificationConflict("Reminder is no longer pending")
        recipient = self._recipient_for_values(
            recipient_role=str(row["recipient_role"]),
            channel=str(row["channel"]),
            customer_status=str(row["customer_status"]),
            email=row["email"],
            phone=row["phone_e164"],
        )
        if not recipient:
            raise NotificationRecipientUnavailable("Recipient is unavailable")
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            payload = {}
        return {
            "id": row["id"],
            "channel": row["channel"],
            "recipientRole": row["recipient_role"],
            "recipient": recipient,
            "displayName": row["display_name"],
            "emailAvailable": bool(row["email"]),
            "phoneAvailable": bool(row["phone_e164"]),
            "triggerDays": int(row["trigger_days"]),
            "triggerAt": int(row["trigger_at"]),
            "payload": payload,
        }

    def mark_missing_recipient(self, delivery_id: str) -> dict[str, object]:
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM notification_deliveries WHERE id=?",
                (delivery_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise NotificationNotFound("Notification delivery not found")
            if row["status"] == "sent":
                connection.rollback()
                raise NotificationConflict("Delivery was already sent")
            connection.execute(
                "UPDATE notification_deliveries SET status='missing_recipient',next_attempt_at=NULL,"
                "last_error_code=NULL,updated_at=? WHERE id=?",
                (now, delivery_id),
            )
            self._refresh_reminder_state(connection, str(row["reminder_id"]), now)
            updated = connection.execute(
                "SELECT * FROM notification_deliveries WHERE id=?",
                (delivery_id,),
            ).fetchone()
            connection.commit()
        return self._safe_delivery(updated)

    def due_deliveries(self, limit: int = 50) -> list[dict[str, object]]:
        self.reconcile()
        now = self._now()
        bounded = min(max(int(limit), 1), 100)
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT d.* FROM notification_deliveries d "
                "JOIN notification_reminders r ON r.id=d.reminder_id "
                "WHERE r.state='pending' AND r.trigger_at<=? AND d.status IN ('queued','failed') "
                "AND (d.next_attempt_at IS NULL OR d.next_attempt_at<=?) "
                "ORDER BY COALESCE(d.next_attempt_at,d.created_at),d.created_at LIMIT ?",
                (now, now, bounded),
            ).fetchall()
        return [self._safe_delivery(row) for row in rows]

    def _refresh_reminder_state(self, connection, reminder_id: str, now: int) -> None:
        reminder = connection.execute(
            "SELECT state FROM notification_reminders WHERE id=?",
            (reminder_id,),
        ).fetchone()
        if reminder is None or reminder["state"] != "pending":
            return
        statuses = [
            str(row["status"])
            for row in connection.execute(
                "SELECT status FROM notification_deliveries WHERE reminder_id=?",
                (reminder_id,),
            ).fetchall()
        ]
        if statuses and all(status in TERMINAL_DELIVERY_STATUSES for status in statuses):
            connection.execute(
                "UPDATE notification_reminders SET state='completed',updated_at=? WHERE id=?",
                (now, reminder_id),
            )

    def record_delivery_attempt(
        self,
        delivery_id: str,
        *,
        success: bool,
        provider_message_id: str | None = None,
        error_code: str | None = None,
    ) -> dict[str, object]:
        now = self._now()
        clean_error = None
        if not success:
            clean_error = error_code if error_code and ERROR_CODE_PATTERN.fullmatch(error_code) else "provider_error"
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT d.*,r.state AS reminder_state FROM notification_deliveries d "
                "JOIN notification_reminders r ON r.id=d.reminder_id WHERE d.id=?",
                (delivery_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise NotificationNotFound("Notification delivery not found")
            if row["reminder_state"] != "pending":
                connection.rollback()
                raise NotificationConflict("Reminder is no longer pending")
            if row["status"] == "sent":
                connection.rollback()
                raise NotificationConflict("Delivery was already sent")
            attempts = int(row["attempt_count"]) + 1
            if success:
                connection.execute(
                    "UPDATE notification_deliveries SET status='sent',attempt_count=?,next_attempt_at=NULL,"
                    "last_error_code=NULL,provider_message_id=?,sent_at=?,updated_at=? WHERE id=?",
                    (attempts, provider_message_id, now, now, delivery_id),
                )
            else:
                delay = min(3600 * (2 ** max(0, attempts - 1)), 86400)
                connection.execute(
                    "UPDATE notification_deliveries SET status='failed',attempt_count=?,next_attempt_at=?,"
                    "last_error_code=?,updated_at=? WHERE id=?",
                    (attempts, now + delay, clean_error, now, delivery_id),
                )
            self._refresh_reminder_state(connection, str(row["reminder_id"]), now)
            updated = connection.execute(
                "SELECT * FROM notification_deliveries WHERE id=?",
                (delivery_id,),
            ).fetchone()
            connection.commit()
        return self._safe_delivery(updated)
