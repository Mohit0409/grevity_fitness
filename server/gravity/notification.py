from __future__ import annotations

from typing import Callable
from uuid import uuid4
import json
import re
import time

from .database import Database
from .membership import MembershipService


CHANNELS = (("email", "email"), ("sms", "phone"), ("whatsapp", "phone"))
ERROR_CODE_PATTERN = re.compile(r"^[a-zA-Z0-9_.:-]{1,80}$")


class NotificationError(Exception):
    pass


class NotificationNotFound(NotificationError):
    pass


class NotificationConflict(NotificationError):
    pass


class NotificationValidationError(NotificationError):
    pass


def _days(value: object) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError) as error:
        raise NotificationValidationError("Reminder days must be an integer") from error
    if not 1 <= days <= 90:
        raise NotificationValidationError("Reminder days must be between 1 and 90")
    return days


class NotificationService:
    def __init__(
        self,
        database: Database,
        membership_service: MembershipService,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.database = database
        self.membership_service = membership_service
        self.clock = clock or time.time

    def _now(self) -> int:
        return int(self.clock())

    @staticmethod
    def provider_blockers() -> dict[str, str]:
        return {
            "email": "BLOCKED_EXTERNAL_CONFIG",
            "sms": "BLOCKED_EXTERNAL_CONFIG",
            "whatsapp": "BLOCKED_EXTERNAL_CONFIG",
        }

    def _has_renewal(self, connection, customer_id: str, membership_id: str, ends_at: int) -> bool:
        row = connection.execute(
            "SELECT 1 FROM memberships WHERE customer_id=? AND id<>? "
            "AND status='scheduled' AND starts_at<=? LIMIT 1",
            (customer_id, membership_id, ends_at),
        ).fetchone()
        return row is not None

    def _delivery_rows(self, connection, reminder_id: str):
        return connection.execute(
            "SELECT * FROM notification_deliveries WHERE reminder_id=? ORDER BY channel",
            (reminder_id,),
        ).fetchall()

    def _safe_delivery(self, row) -> dict[str, object]:
        return {
            "id": row["id"],
            "channel": row["channel"],
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

    def _create_deliveries(self, connection, reminder_id: str, customer: dict[str, object]) -> None:
        now = self._now()
        for channel, recipient_ref in CHANNELS:
            value = customer.get(recipient_ref)
            status = "blocked_external_config" if value else "missing_recipient"
            connection.execute(
                "INSERT OR IGNORE INTO notification_deliveries("
                "id,reminder_id,channel,recipient_ref,status,attempt_count,created_at,updated_at"
                ") VALUES (?,?,?,?,?,?,?,?)",
                (uuid4().hex, reminder_id, channel, recipient_ref, status, 0, now, now),
            )

    def scan_expiring(self, days_before: object = 7) -> dict[str, int]:
        days = _days(days_before)
        candidates = self.membership_service.expiring_within(days)
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
                    self._create_deliveries(connection, reminder_id, dict(item.get("customer") or {}))
                else:
                    deduped += 1
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
        suppressed = 0
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT r.id,r.customer_id,r.membership_id,m.status,m.ends_at "
                "FROM notification_reminders r JOIN memberships m ON m.id=r.membership_id "
                "WHERE r.state='pending'"
            ).fetchall()
            for row in rows:
                should_suppress = row["status"] != "active" or self._has_renewal(
                    connection,
                    str(row["customer_id"]),
                    str(row["membership_id"]),
                    int(row["ends_at"]),
                )
                if should_suppress:
                    connection.execute(
                        "UPDATE notification_reminders SET state='suppressed',updated_at=? "
                        "WHERE id=? AND state='pending'",
                        (now, row["id"]),
                    )
                    suppressed += 1
            connection.commit()
        return suppressed

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
            for row in rows:
                item = self._safe_reminder(row, self._delivery_rows(connection, str(row["id"])))
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
        result: list[dict[str, object]] = []
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT * FROM notification_reminders WHERE customer_id=? "
                "ORDER BY created_at DESC LIMIT ?",
                (customer_id, bounded),
            ).fetchall()
            for row in rows:
                result.append(self._safe_reminder(row, self._delivery_rows(connection, str(row["id"]))))
        return result

    def queue_delivery(self, delivery_id: str) -> dict[str, object]:
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

    def due_deliveries(self, limit: int = 50) -> list[dict[str, object]]:
        now = self._now()
        bounded = min(max(int(limit), 1), 100)
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT d.* FROM notification_deliveries d "
                "JOIN notification_reminders r ON r.id=d.reminder_id "
                "WHERE r.state='pending' AND d.status IN ('queued','failed') "
                "AND (d.next_attempt_at IS NULL OR d.next_attempt_at<=?) "
                "ORDER BY COALESCE(d.next_attempt_at,d.created_at),d.created_at LIMIT ?",
                (now, bounded),
            ).fetchall()
        return [self._safe_delivery(row) for row in rows]

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
                "SELECT * FROM notification_deliveries WHERE id=?",
                (delivery_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise NotificationNotFound("Notification delivery not found")
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
                connection.execute(
                    "UPDATE notification_reminders SET state='completed',updated_at=? WHERE id=?",
                    (now, row["reminder_id"]),
                )
            else:
                delay = min(3600 * (2 ** max(0, attempts - 1)), 86400)
                connection.execute(
                    "UPDATE notification_deliveries SET status='failed',attempt_count=?,next_attempt_at=?,"
                    "last_error_code=?,updated_at=? WHERE id=?",
                    (attempts, now + delay, clean_error, now, delivery_id),
                )
            updated = connection.execute(
                "SELECT * FROM notification_deliveries WHERE id=?",
                (delivery_id,),
            ).fetchone()
            connection.commit()
        return self._safe_delivery(updated)
