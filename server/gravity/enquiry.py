from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from typing import Callable, Mapping
from uuid import uuid4
import base64
import json
import re
import secrets
import sqlite3
import time

from .admin import AdminService, AdminSessionIdentity
from .config import Settings
from .database import Database


ENQUIRY_TYPES = frozenset({"trial_visit", "membership", "coaching", "general"})
ENQUIRY_STATUSES = frozenset({"new", "contacted", "confirmed", "closed"})
PREFERRED_TIMES = frozenset({"morning", "afternoon", "evening", "flexible"})
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
EMAIL_PATTERN = re.compile(r"^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,63}$")


class EnquiryError(Exception):
    pass


class EnquiryValidationError(EnquiryError):
    def __init__(self, fields: Mapping[str, str]) -> None:
        super().__init__("Enquiry validation failed")
        self.fields = dict(fields)


class EnquiryConflict(EnquiryError):
    pass


class EnquiryNotFound(EnquiryError):
    pass


class EnquiryCsrfInvalid(EnquiryError):
    pass


class EnquiryRateLimitExceeded(EnquiryError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Enquiry request rate exceeded")
        self.retry_after = max(1, int(retry_after))


@dataclass(frozen=True, slots=True)
class EnquiryCsrfIssue:
    token: str
    expires_at: int


class EnquiryService:
    CSRF_TTL_SECONDS = 30 * 60
    RETENTION_SECONDS = 180 * 24 * 60 * 60

    def __init__(
        self,
        database: Database,
        settings: Settings,
        admin_service: AdminService,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.database = database
        self.settings = settings
        self.admin_service = admin_service
        self.clock = clock
        configured = settings.secret_key.encode("utf-8")
        self._key = configured if len(configured) >= 32 else secrets.token_bytes(32)

    def _now(self) -> int:
        return int(self.clock())

    def purge_expired(self) -> int:
        """Delete enquiry PII after the declared retention window."""
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "DELETE FROM public_enquiries WHERE retention_expires_at <= ?",
                (now,),
            )
            connection.execute(
                "DELETE FROM public_enquiry_rate_limits "
                "WHERE window_started_at < ? AND COALESCE(blocked_until, 0) < ?",
                (now - self.RETENTION_SECONDS, now),
            )
            connection.commit()
        return max(0, int(cursor.rowcount))

    def _private_hash(self, scope: str, value: str) -> str:
        return hmac_new(self._key, f"{scope}\0{value}".encode("utf-8"), "sha256").hexdigest()

    @staticmethod
    def _b64encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def _b64decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    def issue_csrf(self) -> EnquiryCsrfIssue:
        now = self._now()
        payload = self._b64encode(
            json.dumps(
                {"iat": now, "nonce": secrets.token_urlsafe(18)},
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        signature = self._b64encode(hmac_new(self._key, f"enquiry-csrf\0{payload}".encode("ascii"), "sha256").digest())
        return EnquiryCsrfIssue(f"{payload}.{signature}", now + self.CSRF_TTL_SECONDS)

    def verify_csrf(self, supplied_header: str | None, cookie_token: str | None) -> None:
        if not supplied_header or not cookie_token or not compare_digest(supplied_header, cookie_token):
            raise EnquiryCsrfInvalid("Anonymous CSRF verification failed")
        try:
            payload, signature = supplied_header.split(".", 1)
            expected = self._b64encode(
                hmac_new(self._key, f"enquiry-csrf\0{payload}".encode("ascii"), "sha256").digest()
            )
            if not compare_digest(signature, expected):
                raise ValueError("signature")
            decoded = json.loads(self._b64decode(payload))
            issued_at = int(decoded["iat"])
            nonce = str(decoded["nonce"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeError) as error:
            raise EnquiryCsrfInvalid("Anonymous CSRF verification failed") from error
        now = self._now()
        if len(nonce) < 16 or issued_at > now + 30 or now - issued_at > self.CSRF_TTL_SECONDS:
            raise EnquiryCsrfInvalid("Anonymous CSRF verification failed")

    @staticmethod
    def _clean_text(value: object, *, maximum: int) -> str:
        if not isinstance(value, str):
            return ""
        return " ".join(value.strip().split())[: maximum + 1]

    @staticmethod
    def _clean_message(value: object) -> str:
        if not isinstance(value, str):
            return ""
        lines = [" ".join(line.split()) for line in value.replace("\r", "\n").split("\n")]
        return "\n".join(line for line in lines if line).strip()[:1001]

    @staticmethod
    def _normalize_phone(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) == 10 and digits[0] in "6789":
            return "+91" + digits
        if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
            return "+" + digits
        return None

    def _validate(self, payload: Mapping[str, object]) -> dict[str, object]:
        allowed = {
            "type", "name", "phone", "email", "planId", "preferredDate",
            "preferredTime", "message", "website",
        }
        errors: dict[str, str] = {}
        if any(key not in allowed for key in payload):
            errors["request"] = "The request contains unsupported fields"

        enquiry_type = self._clean_text(payload.get("type"), maximum=30).casefold()
        if enquiry_type not in ENQUIRY_TYPES:
            errors["type"] = "Choose a valid enquiry type"

        name = self._clean_text(payload.get("name"), maximum=80)
        if not 2 <= len(name) <= 80 or not any(character.isalpha() for character in name):
            errors["name"] = "Enter your name"

        phone = self._normalize_phone(payload.get("phone"))
        if phone is None:
            errors["phone"] = "Enter a valid Indian mobile number"

        email = self._clean_text(payload.get("email"), maximum=254).casefold()
        if email and (len(email) > 254 or not EMAIL_PATTERN.fullmatch(email)):
            errors["email"] = "Enter a valid email address"

        plan_id = self._clean_text(payload.get("planId"), maximum=80)
        if enquiry_type == "membership" and not plan_id:
            errors["planId"] = "Choose a membership plan"
        if plan_id:
            with self.database.session() as connection:
                exists = connection.execute(
                    "SELECT 1 FROM membership_plans WHERE id=? AND status='active'", (plan_id,)
                ).fetchone()
            if exists is None:
                errors["planId"] = "Choose a currently available membership plan"

        preferred_date = self._clean_text(payload.get("preferredDate"), maximum=10)
        parsed_date: date | None = None
        if preferred_date:
            try:
                parsed_date = date.fromisoformat(preferred_date)
            except ValueError:
                errors["preferredDate"] = "Choose a valid preferred date"
        today = datetime.fromtimestamp(self._now(), timezone.utc).date()
        if parsed_date and not today <= parsed_date <= today + timedelta(days=90):
            errors["preferredDate"] = "Choose a date within the next 90 days"
        if enquiry_type == "trial_visit" and not preferred_date:
            errors["preferredDate"] = "Choose a preferred visit date"

        preferred_time = self._clean_text(payload.get("preferredTime"), maximum=20).casefold()
        if preferred_time and preferred_time not in PREFERRED_TIMES:
            errors["preferredTime"] = "Choose a valid time preference"
        if enquiry_type == "trial_visit" and not preferred_time:
            errors["preferredTime"] = "Choose a preferred time"

        message = self._clean_message(payload.get("message"))
        if len(message) > 1000:
            errors["message"] = "Keep your message within 1000 characters"
        if enquiry_type == "general" and not message:
            errors["message"] = "Tell us how we can help"

        honeypot = self._clean_text(payload.get("website"), maximum=200)
        if honeypot:
            errors["request"] = "The request could not be accepted"
        if errors:
            raise EnquiryValidationError(errors)
        return {
            "type": enquiry_type,
            "name": name,
            "phone": phone,
            "email": email or None,
            "planId": plan_id or None,
            "preferredDate": preferred_date or None,
            "preferredTime": preferred_time or None,
            "message": message or None,
        }

    def _consume_bucket(
        self,
        connection: sqlite3.Connection,
        scope: str,
        key_hash: str,
        *,
        window: int,
        limit: int,
    ) -> None:
        now = self._now()
        row = connection.execute(
            "SELECT window_started_at,request_count,blocked_until FROM public_enquiry_rate_limits "
            "WHERE scope=? AND key_hash=?",
            (scope, key_hash),
        ).fetchone()
        if row and row["blocked_until"] and int(row["blocked_until"]) > now:
            raise EnquiryRateLimitExceeded(int(row["blocked_until"]) - now)
        window_started = int(row["window_started_at"]) if row else now
        count = int(row["request_count"]) if row else 0
        if now - window_started >= window:
            window_started, count = now, 0
        count += 1
        blocked_until = now + window if count > limit else None
        connection.execute(
            "INSERT INTO public_enquiry_rate_limits(scope,key_hash,window_started_at,request_count,blocked_until) "
            "VALUES(?,?,?,?,?) ON CONFLICT(scope,key_hash) DO UPDATE SET "
            "window_started_at=excluded.window_started_at,request_count=excluded.request_count,blocked_until=excluded.blocked_until",
            (scope, key_hash, window_started, count, blocked_until),
        )
        if blocked_until:
            raise EnquiryRateLimitExceeded(window)

    def create(
        self,
        payload: Mapping[str, object],
        *,
        idempotency_key: str,
        remote_addr: str,
        request_id: str,
    ) -> tuple[dict[str, object], bool]:
        if not IDEMPOTENCY_PATTERN.fullmatch(idempotency_key or ""):
            raise EnquiryValidationError({"request": "A valid idempotency key is required"})
        values = self._validate(payload)
        canonical = json.dumps(values, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
        fingerprint = sha256(canonical.encode("utf-8")).hexdigest()
        idempotency_hash = self._private_hash("idempotency", idempotency_key)
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                "SELECT reference,payload_fingerprint,created_at FROM public_enquiries WHERE idempotency_hash=?",
                (idempotency_hash,),
            ).fetchone()
            if prior:
                if not compare_digest(str(prior["payload_fingerprint"]), fingerprint):
                    connection.rollback()
                    raise EnquiryConflict("Idempotency key was already used for another request")
                connection.commit()
                return {
                    "reference": prior["reference"],
                    "status": "received",
                    "receivedAt": prior["created_at"],
                }, True

            self._consume_bucket(
                connection, "ip", self._private_hash("ip", remote_addr), window=15 * 60, limit=8
            )
            self._consume_bucket(
                connection, "contact", self._private_hash("phone", str(values["phone"])), window=60 * 60, limit=4
            )
            enquiry_id = uuid4().hex
            reference = f"GF-{datetime.fromtimestamp(now, timezone.utc):%Y%m}-{secrets.token_hex(3).upper()}"
            connection.execute(
                "INSERT INTO public_enquiries(id,reference,idempotency_hash,payload_fingerprint,enquiry_type,name,"
                "phone_e164,email,plan_id,preferred_date,preferred_time,message,status,source,created_at,updated_at,retention_expires_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    enquiry_id, reference, idempotency_hash, fingerprint, values["type"], values["name"],
                    values["phone"], values["email"], values["planId"], values["preferredDate"],
                    values["preferredTime"], values["message"], "new", "website", now, now,
                    now + self.RETENTION_SECONDS,
                ),
            )
            connection.execute(
                "INSERT INTO public_enquiry_events(enquiry_id,event_type,request_id,created_at) VALUES(?,?,?,?)",
                (enquiry_id, "received", request_id, now),
            )
            connection.commit()
        return {"reference": reference, "status": "received", "receivedAt": now}, False

    @staticmethod
    def _serialize(row: sqlite3.Row) -> dict[str, object]:
        return {
            "id": row["id"], "reference": row["reference"], "type": row["enquiry_type"],
            "name": row["name"], "phone": row["phone_e164"], "email": row["email"],
            "planId": row["plan_id"], "planName": row["plan_name"],
            "preferredDate": row["preferred_date"], "preferredTime": row["preferred_time"],
            "message": row["message"], "status": row["status"], "source": row["source"],
            "createdAt": row["created_at"], "updatedAt": row["updated_at"],
            "lastContactedAt": row["last_contacted_at"], "retentionExpiresAt": row["retention_expires_at"],
        }

    def list_admin(
        self,
        session: AdminSessionIdentity,
        *,
        status: str = "",
        enquiry_type: str = "",
        query: str = "",
        limit: int = 100,
    ) -> list[dict[str, object]]:
        self.admin_service.require_permission(session, "enquiries.read")
        if status and status not in ENQUIRY_STATUSES:
            raise EnquiryValidationError({"status": "Choose a valid status"})
        if enquiry_type and enquiry_type not in ENQUIRY_TYPES:
            raise EnquiryValidationError({"type": "Choose a valid enquiry type"})
        bounded = min(max(int(limit), 1), 200)
        needle = query.strip().casefold()[:100]
        pattern = f"%{needle}%"
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT e.*,p.name AS plan_name FROM public_enquiries e LEFT JOIN membership_plans p ON p.id=e.plan_id "
                "WHERE (?='' OR e.status=?) AND (?='' OR e.enquiry_type=?) AND "
                "(?='' OR lower(e.reference) LIKE ? OR lower(e.name) LIKE ? OR e.phone_e164 LIKE ? OR lower(COALESCE(e.email,'')) LIKE ?) "
                "ORDER BY e.created_at DESC,e.id DESC LIMIT ?",
                (status, status, enquiry_type, enquiry_type, needle, pattern, pattern, pattern, pattern, bounded),
            ).fetchall()
        return [self._serialize(row) for row in rows]

    def detail_admin(self, session: AdminSessionIdentity, enquiry_id: str) -> dict[str, object]:
        self.admin_service.require_permission(session, "enquiries.read")
        with self.database.session() as connection:
            row = connection.execute(
                "SELECT e.*,p.name AS plan_name FROM public_enquiries e LEFT JOIN membership_plans p ON p.id=e.plan_id WHERE e.id=?",
                (enquiry_id,),
            ).fetchone()
            if row is None:
                raise EnquiryNotFound("Enquiry not found")
            notes = connection.execute(
                "SELECT n.id,n.note,n.created_at,n.admin_user_id,a.username FROM public_enquiry_notes n "
                "JOIN admin_users a ON a.id=n.admin_user_id WHERE n.enquiry_id=? ORDER BY n.created_at ASC,n.id ASC",
                (enquiry_id,),
            ).fetchall()
            events = connection.execute(
                "SELECT event_type,from_status,to_status,created_at FROM public_enquiry_events WHERE enquiry_id=? ORDER BY id ASC",
                (enquiry_id,),
            ).fetchall()
        result = self._serialize(row)
        result["notes"] = [
            {"id": note["id"], "note": note["note"], "createdAt": note["created_at"], "adminUserId": note["admin_user_id"], "username": note["username"]}
            for note in notes
        ]
        result["events"] = [
            {"type": event["event_type"], "fromStatus": event["from_status"], "toStatus": event["to_status"], "createdAt": event["created_at"]}
            for event in events
        ]
        return result

    def set_status(
        self,
        session: AdminSessionIdentity,
        enquiry_id: str,
        status: object,
        *,
        request_id: str,
    ) -> dict[str, object]:
        self.admin_service.require_permission(session, "enquiries.manage")
        normalized = str(status or "").strip().casefold()
        if normalized not in ENQUIRY_STATUSES:
            raise EnquiryValidationError({"status": "Choose a valid status"})
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT status FROM public_enquiries WHERE id=?", (enquiry_id,)).fetchone()
            if row is None:
                connection.rollback()
                raise EnquiryNotFound("Enquiry not found")
            previous = str(row["status"])
            connection.execute(
                "UPDATE public_enquiries SET status=?,updated_at=?,last_contacted_at=CASE WHEN ?='contacted' THEN ? ELSE last_contacted_at END WHERE id=?",
                (normalized, now, normalized, now, enquiry_id),
            )
            connection.execute(
                "INSERT INTO public_enquiry_events(enquiry_id,admin_user_id,event_type,from_status,to_status,request_id,created_at) VALUES(?,?,?,?,?,?,?)",
                (enquiry_id, session.admin_user_id, "status_changed", previous, normalized, request_id, now),
            )
            self.admin_service._audit(
                connection, session.admin_user_id, "enquiry_status_changed",
                target_type="public_enquiry", target_id=enquiry_id,
                metadata={"fromStatus": previous, "toStatus": normalized, "requestId": request_id},
            )
            connection.commit()
        return self.detail_admin(session, enquiry_id)

    def add_note(
        self,
        session: AdminSessionIdentity,
        enquiry_id: str,
        note: object,
        *,
        request_id: str,
    ) -> dict[str, object]:
        self.admin_service.require_permission(session, "enquiries.manage")
        clean = self._clean_message(note)
        if not 2 <= len(clean) <= 1000:
            raise EnquiryValidationError({"note": "Enter a note between 2 and 1000 characters"})
        now = self._now()
        note_id = uuid4().hex
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            exists = connection.execute("SELECT 1 FROM public_enquiries WHERE id=?", (enquiry_id,)).fetchone()
            if exists is None:
                connection.rollback()
                raise EnquiryNotFound("Enquiry not found")
            connection.execute(
                "INSERT INTO public_enquiry_notes(id,enquiry_id,admin_user_id,note,created_at) VALUES(?,?,?,?,?)",
                (note_id, enquiry_id, session.admin_user_id, clean, now),
            )
            connection.execute(
                "INSERT INTO public_enquiry_events(enquiry_id,admin_user_id,event_type,request_id,created_at) VALUES(?,?,?,?,?)",
                (enquiry_id, session.admin_user_id, "note_added", request_id, now),
            )
            self.admin_service._audit(
                connection, session.admin_user_id, "enquiry_note_added",
                target_type="public_enquiry", target_id=enquiry_id,
                metadata={"requestId": request_id},
            )
            connection.commit()
        return self.detail_admin(session, enquiry_id)
