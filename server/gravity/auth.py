from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from typing import Callable, Mapping
from unicodedata import normalize as unicode_normalize
from uuid import uuid4
import json
import re
import secrets
import sqlite3
import time

from .config import Settings
from .database import Database
from .firebase_auth import IdentityVerifier, VerifiedFirebaseIdentity


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")
ALLOWED_PROFILE_FIELDS = {
    "displayName",
    "dateOfBirth",
    "gender",
    "address",
    "emergencyContactName",
    "emergencyContactPhone",
    "healthNotes",
}
ALLOWED_GENDERS = {"female", "male", "non_binary", "prefer_not_to_say"}
MAX_ACTIVE_SESSIONS = 5


class AuthenticationError(Exception):
    pass


class AuthenticationUnavailable(AuthenticationError):
    pass


class InvalidSession(AuthenticationError):
    pass


class AccountDisabled(AuthenticationError):
    pass


class IdentityConflict(AuthenticationError):
    pass


class InvalidCsrf(AuthenticationError):
    pass


class ProfileValidationError(AuthenticationError):
    def __init__(self, fields: Mapping[str, str]) -> None:
        super().__init__("Profile validation failed")
        self.fields = dict(fields)


class RateLimitExceeded(AuthenticationError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Authentication rate limit exceeded")
        self.retry_after = max(1, retry_after)


@dataclass(frozen=True, slots=True)
class SessionIdentity:
    session_id: str
    customer_id: str
    csrf_hash: str
    user: dict[str, object]


@dataclass(frozen=True, slots=True)
class SessionIssue:
    session_token: str
    csrf_token: str
    absolute_expires_at: int
    user: dict[str, object]


def normalize_email(value: str) -> str:
    normalized = unicode_normalize("NFKC", value).strip().casefold()
    if len(normalized) > 254 or not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid email")
    return normalized


def normalize_phone(value: str) -> str:
    normalized = value.strip().replace(" ", "").replace("-", "")
    if not PHONE_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid E.164 phone number")
    return normalized


def _token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _clean_text(value: object, *, maximum: int, multiline: bool = False) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Must be text")
    cleaned = value.strip()
    if not cleaned:
        return None
    if "\x00" in cleaned or (not multiline and ("\r" in cleaned or "\n" in cleaned)):
        raise ValueError("Contains invalid characters")
    if len(cleaned) > maximum:
        raise ValueError("Too long")
    return cleaned


class AuthService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        verifier: IdentityVerifier,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.database = database
        self.settings = settings
        self.verifier = verifier
        self.clock = clock

    @property
    def configured(self) -> bool:
        return bool(self.verifier.configured and len(self.settings.secret_key.encode("utf-8")) >= 32)

    def _now(self) -> int:
        return int(self.clock())

    def _private_hash(self, scope: str, value: str) -> str:
        return hmac_new(
            self.settings.secret_key.encode("utf-8"),
            f"{scope}\0{value}".encode("utf-8"),
            "sha256",
        ).hexdigest()

    def _consume_bucket(self, scope: str, key_hash: str, *, window: int, limit: int) -> None:
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT window_started_at, request_count, blocked_until FROM auth_rate_limits "
                "WHERE scope = ? AND key_hash = ?",
                (scope, key_hash),
            ).fetchone()
            if row and row["blocked_until"] and row["blocked_until"] > now:
                connection.commit()
                raise RateLimitExceeded(row["blocked_until"] - now)
            if not row or now - row["window_started_at"] >= window:
                started_at, request_count = now, 1
            else:
                started_at, request_count = row["window_started_at"], row["request_count"] + 1
            blocked_until = now + window if request_count > limit else None
            connection.execute(
                "INSERT INTO auth_rate_limits(scope, key_hash, window_started_at, request_count, blocked_until, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(scope, key_hash) DO UPDATE SET "
                "window_started_at = excluded.window_started_at, request_count = excluded.request_count, "
                "blocked_until = excluded.blocked_until, updated_at = excluded.updated_at",
                (scope, key_hash, started_at, request_count, blocked_until, now),
            )
            connection.execute("DELETE FROM auth_rate_limits WHERE updated_at < ?", (now - 604_800,))
            connection.commit()
            if blocked_until:
                raise RateLimitExceeded(window)

    def _rate_limit_exchange(self, remote_addr: str) -> None:
        key_hash = self._private_hash("remote", remote_addr)
        self._consume_bucket("firebase_exchange_minute", key_hash, window=60, limit=5)
        self._consume_bucket("firebase_exchange_hour", key_hash, window=3600, limit=20)

    def _rate_limit_link(self, customer_id: str, remote_addr: str) -> None:
        key_hash = self._private_hash("link", f"{customer_id}\0{remote_addr}")
        self._consume_bucket("firebase_link_hour", key_hash, window=3600, limit=5)

    def exchange(
        self,
        id_token: str,
        *,
        remote_addr: str,
        user_agent: str,
        request_id: str,
        prior_session_token: str | None = None,
    ) -> SessionIssue:
        if not self.configured:
            raise AuthenticationUnavailable("Customer authentication is not configured")
        self._rate_limit_exchange(remote_addr)
        identity = self.verifier.verify(id_token)
        if identity.auth_time < self._now() - 600 or identity.auth_time > self._now() + 60:
            raise AuthenticationError("Firebase authentication is not recent")

        session_token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(32)
        now = self._now()
        customer_id = uuid4().hex
        session_id = uuid4().hex
        normalized_email = normalize_email(identity.email) if identity.email_verified and identity.email else None
        normalized_phone = normalize_phone(identity.phone_number) if identity.phone_number else None
        ip_hash = self._private_hash("ip", remote_addr)
        user_agent_hash = self._private_hash("ua", user_agent[:1000]) if user_agent else None

        try:
            with self.database.session() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT customer_id FROM firebase_identities WHERE project_id = ? AND firebase_uid = ?",
                    (identity.project_id, identity.uid),
                ).fetchone()
                created = existing is None
                if existing:
                    customer_id = existing["customer_id"]
                    self._validate_existing_customer(
                        connection,
                        customer_id,
                        normalized_email=normalized_email,
                        normalized_phone=normalized_phone,
                    )
                    self._update_existing_identity(connection, customer_id, identity, now)
                else:
                    self._assert_identity_available(connection, identity, normalized_email, normalized_phone)
                    connection.execute(
                        "INSERT INTO customers(id, display_name, email, normalized_email, email_verified, "
                        "phone_e164, phone_verified, photo_url, created_at, updated_at, last_login_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            customer_id,
                            identity.display_name,
                            identity.email if normalized_email else None,
                            normalized_email,
                            1 if normalized_email else 0,
                            normalized_phone,
                            1 if normalized_phone else 0,
                            identity.photo_url,
                            now,
                            now,
                            now,
                        ),
                    )
                    connection.execute(
                        "INSERT INTO customer_profiles(customer_id, updated_at) VALUES (?, ?)",
                        (customer_id, now),
                    )
                    connection.execute(
                        "INSERT INTO firebase_identities(project_id, firebase_uid, customer_id, "
                        "last_sign_in_provider, created_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            identity.project_id,
                            identity.uid,
                            customer_id,
                            identity.sign_in_provider,
                            now,
                            now,
                        ),
                    )
                    self._upsert_provider_identity(connection, identity, now)

                if prior_session_token:
                    connection.execute(
                        "UPDATE customer_sessions SET revoked_at = ?, revoke_reason = 'rotated' "
                        "WHERE token_hash = ? AND revoked_at IS NULL",
                        (now, _token_hash(prior_session_token)),
                    )
                absolute_expires_at = self._insert_session(
                    connection,
                    session_id=session_id,
                    customer_id=customer_id,
                    session_token=session_token,
                    csrf_token=csrf_token,
                    now=now,
                    ip_hash=ip_hash,
                    user_agent_hash=user_agent_hash,
                )
                connection.execute(
                    "UPDATE customers SET last_login_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, customer_id),
                )
                self._audit(
                    connection,
                    actor_id=customer_id,
                    action="customer_registered" if created else "customer_login",
                    request_id=request_id,
                    metadata={"provider": identity.sign_in_provider},
                )
                user = self._customer_payload(connection, customer_id)
                connection.commit()
        except sqlite3.IntegrityError as error:
            raise IdentityConflict("A verified identity already belongs to another account") from error

        return SessionIssue(
            session_token=session_token,
            csrf_token=csrf_token,
            absolute_expires_at=absolute_expires_at,
            user=user,
        )

    def link_identity(
        self,
        session: SessionIdentity,
        id_token: str,
        *,
        current_session_token: str,
        remote_addr: str,
        user_agent: str,
        request_id: str,
    ) -> SessionIssue:
        if not self.configured:
            raise AuthenticationUnavailable("Customer authentication is not configured")
        self._rate_limit_link(session.customer_id, remote_addr)
        identity = self.verifier.verify(id_token)
        if identity.auth_time < self._now() - 600 or identity.auth_time > self._now() + 60:
            raise AuthenticationError("Firebase authentication is not recent")
        normalized_email = normalize_email(identity.email) if identity.email_verified and identity.email else None
        normalized_phone = normalize_phone(identity.phone_number) if identity.phone_number else None
        session_token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(32)
        now = self._now()
        new_session_id = uuid4().hex
        try:
            with self.database.session() as connection:
                connection.execute("BEGIN IMMEDIATE")
                current = connection.execute(
                    "SELECT status, normalized_email, phone_e164 FROM customers WHERE id = ?",
                    (session.customer_id,),
                ).fetchone()
                if not current or current["status"] != "active":
                    raise AccountDisabled("Customer account is disabled")
                if normalized_email and current["normalized_email"] not in (None, normalized_email):
                    raise IdentityConflict("Verified email differs from the current account")
                if normalized_phone and current["phone_e164"] not in (None, normalized_phone):
                    raise IdentityConflict("Verified phone differs from the current account")
                self._validate_existing_customer(
                    connection,
                    session.customer_id,
                    normalized_email=normalized_email,
                    normalized_phone=normalized_phone,
                )
                uid_owner = connection.execute(
                    "SELECT customer_id FROM firebase_identities WHERE project_id = ? AND firebase_uid = ?",
                    (identity.project_id, identity.uid),
                ).fetchone()
                if uid_owner and uid_owner["customer_id"] != session.customer_id:
                    raise IdentityConflict("Firebase identity belongs to another account")
                provider_owner = connection.execute(
                    "SELECT firebase_uid FROM firebase_provider_identities "
                    "WHERE project_id = ? AND sign_in_provider = ? AND provider_subject = ?",
                    (identity.project_id, identity.sign_in_provider, identity.provider_subject),
                ).fetchone()
                if provider_owner and provider_owner["firebase_uid"] != identity.uid:
                    raise IdentityConflict("Provider identity belongs to another account")
                if not uid_owner:
                    connection.execute(
                        "INSERT INTO firebase_identities(project_id, firebase_uid, customer_id, "
                        "last_sign_in_provider, created_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            identity.project_id,
                            identity.uid,
                            session.customer_id,
                            identity.sign_in_provider,
                            now,
                            now,
                        ),
                    )
                self._update_existing_identity(connection, session.customer_id, identity, now)
                connection.execute(
                    "UPDATE customer_sessions SET revoked_at = ?, revoke_reason = 'identity_linked' "
                    "WHERE id = ? AND token_hash = ? AND revoked_at IS NULL",
                    (now, session.session_id, _token_hash(current_session_token)),
                )
                absolute_expires_at = self._insert_session(
                    connection,
                    session_id=new_session_id,
                    customer_id=session.customer_id,
                    session_token=session_token,
                    csrf_token=csrf_token,
                    now=now,
                    ip_hash=self._private_hash("ip", remote_addr),
                    user_agent_hash=self._private_hash("ua", user_agent[:1000]) if user_agent else None,
                )
                self._audit(
                    connection,
                    actor_id=session.customer_id,
                    action="customer_identity_linked",
                    request_id=request_id,
                    metadata={"provider": identity.sign_in_provider},
                )
                user = self._customer_payload(connection, session.customer_id)
                connection.commit()
        except sqlite3.IntegrityError as error:
            raise IdentityConflict("A verified identity already belongs to another account") from error
        return SessionIssue(
            session_token=session_token,
            csrf_token=csrf_token,
            absolute_expires_at=absolute_expires_at,
            user=user,
        )

    def _assert_identity_available(
        self,
        connection: sqlite3.Connection,
        identity: VerifiedFirebaseIdentity,
        normalized_email: str | None,
        normalized_phone: str | None,
    ) -> None:
        provider_owner = connection.execute(
            "SELECT firebase_uid FROM firebase_provider_identities "
            "WHERE project_id = ? AND sign_in_provider = ? AND provider_subject = ?",
            (identity.project_id, identity.sign_in_provider, identity.provider_subject),
        ).fetchone()
        if provider_owner:
            raise IdentityConflict("Provider identity already belongs to another account")
        if normalized_email and connection.execute(
            "SELECT 1 FROM customers WHERE normalized_email = ? AND email_verified = 1 AND status != 'deleted'",
            (normalized_email,),
        ).fetchone():
            raise IdentityConflict("Verified email already belongs to another account")
        if normalized_phone and connection.execute(
            "SELECT 1 FROM customers WHERE phone_e164 = ? AND phone_verified = 1 AND status != 'deleted'",
            (normalized_phone,),
        ).fetchone():
            raise IdentityConflict("Verified phone already belongs to another account")

    def _validate_existing_customer(
        self,
        connection: sqlite3.Connection,
        customer_id: str,
        *,
        normalized_email: str | None,
        normalized_phone: str | None,
    ) -> None:
        customer = connection.execute(
            "SELECT status FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        if not customer or customer["status"] != "active":
            raise AccountDisabled("Customer account is disabled")
        if normalized_email:
            owner = connection.execute(
                "SELECT id FROM customers WHERE normalized_email = ? AND email_verified = 1 "
                "AND status != 'deleted' AND id != ?",
                (normalized_email, customer_id),
            ).fetchone()
            if owner:
                raise IdentityConflict("Verified email already belongs to another account")
        if normalized_phone:
            owner = connection.execute(
                "SELECT id FROM customers WHERE phone_e164 = ? AND phone_verified = 1 "
                "AND status != 'deleted' AND id != ?",
                (normalized_phone, customer_id),
            ).fetchone()
            if owner:
                raise IdentityConflict("Verified phone already belongs to another account")

    def _update_existing_identity(
        self,
        connection: sqlite3.Connection,
        customer_id: str,
        identity: VerifiedFirebaseIdentity,
        now: int,
    ) -> None:
        normalized_email = normalize_email(identity.email) if identity.email_verified and identity.email else None
        normalized_phone = normalize_phone(identity.phone_number) if identity.phone_number else None
        self._upsert_provider_identity(connection, identity, now)
        connection.execute(
            "UPDATE firebase_identities SET last_sign_in_provider = ?, last_seen_at = ? "
            "WHERE project_id = ? AND firebase_uid = ?",
            (identity.sign_in_provider, now, identity.project_id, identity.uid),
        )
        connection.execute(
            "UPDATE customers SET "
            "display_name = COALESCE(display_name, ?), "
            "email = COALESCE(?, email), normalized_email = COALESCE(?, normalized_email), "
            "email_verified = CASE WHEN ? IS NOT NULL THEN 1 ELSE email_verified END, "
            "phone_e164 = COALESCE(?, phone_e164), "
            "phone_verified = CASE WHEN ? IS NOT NULL THEN 1 ELSE phone_verified END, "
            "photo_url = COALESCE(?, photo_url), updated_at = ? WHERE id = ?",
            (
                identity.display_name,
                identity.email if normalized_email else None,
                normalized_email,
                normalized_email,
                normalized_phone,
                normalized_phone,
                identity.photo_url,
                now,
                customer_id,
            ),
        )

    @staticmethod
    def _upsert_provider_identity(
        connection: sqlite3.Connection, identity: VerifiedFirebaseIdentity, now: int
    ) -> None:
        owner = connection.execute(
            "SELECT firebase_uid FROM firebase_provider_identities "
            "WHERE project_id = ? AND sign_in_provider = ? AND provider_subject = ?",
            (identity.project_id, identity.sign_in_provider, identity.provider_subject),
        ).fetchone()
        if owner and owner["firebase_uid"] != identity.uid:
            raise IdentityConflict("Provider identity belongs to another Firebase account")
        connection.execute(
            "INSERT INTO firebase_provider_identities(project_id, sign_in_provider, provider_subject, "
            "firebase_uid, created_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(project_id, sign_in_provider, provider_subject) DO UPDATE SET "
            "last_seen_at = excluded.last_seen_at",
            (
                identity.project_id,
                identity.sign_in_provider,
                identity.provider_subject,
                identity.uid,
                now,
                now,
            ),
        )

    def _insert_session(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        customer_id: str,
        session_token: str,
        csrf_token: str,
        now: int,
        ip_hash: str | None,
        user_agent_hash: str | None,
    ) -> int:
        idle_expires_at = now + self.settings.session_idle_seconds
        absolute_expires_at = now + self.settings.session_absolute_seconds
        connection.execute(
            "INSERT INTO customer_sessions(id, customer_id, token_hash, csrf_hash, created_at, "
            "last_seen_at, idle_expires_at, absolute_expires_at, ip_hash, user_agent_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                customer_id,
                _token_hash(session_token),
                _token_hash(csrf_token),
                now,
                now,
                idle_expires_at,
                absolute_expires_at,
                ip_hash,
                user_agent_hash,
            ),
        )
        stale = connection.execute(
            "SELECT id FROM customer_sessions WHERE customer_id = ? AND revoked_at IS NULL "
            "ORDER BY rowid DESC LIMIT -1 OFFSET ?",
            (customer_id, MAX_ACTIVE_SESSIONS),
        ).fetchall()
        if stale:
            connection.executemany(
                "UPDATE customer_sessions SET revoked_at = ?, revoke_reason = 'session_limit' WHERE id = ?",
                [(now, row["id"]) for row in stale],
            )
        return absolute_expires_at

    def resolve_session(self, session_token: str | None, *, touch: bool = True) -> SessionIdentity:
        if not session_token or len(session_token) > 256:
            raise InvalidSession("Session is missing")
        now = self._now()
        with self.database.session() as connection:
            row = connection.execute(
                "SELECT s.id AS session_id, s.customer_id, s.csrf_hash, s.last_seen_at, "
                "s.idle_expires_at, s.absolute_expires_at, s.revoked_at, c.status "
                "FROM customer_sessions s JOIN customers c ON c.id = s.customer_id "
                "WHERE s.token_hash = ?",
                (_token_hash(session_token),),
            ).fetchone()
            if not row or row["revoked_at"] is not None:
                raise InvalidSession("Session is invalid")
            if row["status"] != "active":
                connection.execute(
                    "UPDATE customer_sessions SET revoked_at = ?, revoke_reason = 'account_disabled' "
                    "WHERE id = ? AND revoked_at IS NULL",
                    (now, row["session_id"]),
                )
                raise AccountDisabled("Customer account is disabled")
            if now >= row["idle_expires_at"] or now >= row["absolute_expires_at"]:
                connection.execute(
                    "UPDATE customer_sessions SET revoked_at = ?, revoke_reason = 'expired' "
                    "WHERE id = ? AND revoked_at IS NULL",
                    (now, row["session_id"]),
                )
                raise InvalidSession("Session has expired")
            if touch and now - row["last_seen_at"] >= 60:
                connection.execute(
                    "UPDATE customer_sessions SET last_seen_at = ?, idle_expires_at = ? WHERE id = ?",
                    (
                        now,
                        min(now + self.settings.session_idle_seconds, row["absolute_expires_at"]),
                        row["session_id"],
                    ),
                )
            user = self._customer_payload(connection, row["customer_id"])
            return SessionIdentity(
                session_id=row["session_id"],
                customer_id=row["customer_id"],
                csrf_hash=row["csrf_hash"],
                user=user,
            )

    @staticmethod
    def verify_csrf(session: SessionIdentity, header_token: str | None, cookie_token: str | None) -> None:
        if not header_token or not cookie_token:
            raise InvalidCsrf("CSRF token is missing")
        if len(header_token) > 256 or not compare_digest(header_token, cookie_token):
            raise InvalidCsrf("CSRF token does not match")
        if not compare_digest(_token_hash(header_token), session.csrf_hash):
            raise InvalidCsrf("CSRF token is invalid")

    def logout(self, session: SessionIdentity, *, request_id: str, all_sessions: bool = False) -> None:
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if all_sessions:
                connection.execute(
                    "UPDATE customer_sessions SET revoked_at = ?, revoke_reason = 'logout_all' "
                    "WHERE customer_id = ? AND revoked_at IS NULL",
                    (now, session.customer_id),
                )
            else:
                connection.execute(
                    "UPDATE customer_sessions SET revoked_at = ?, revoke_reason = 'logout' "
                    "WHERE id = ? AND revoked_at IS NULL",
                    (now, session.session_id),
                )
            self._audit(
                connection,
                actor_id=session.customer_id,
                action="customer_logout_all" if all_sessions else "customer_logout",
                request_id=request_id,
            )
            connection.commit()

    def update_profile(
        self,
        session: SessionIdentity,
        payload: Mapping[str, object],
        *,
        request_id: str,
    ) -> dict[str, object]:
        unexpected = sorted(set(payload) - ALLOWED_PROFILE_FIELDS)
        if unexpected:
            raise ProfileValidationError({field: "Unexpected field" for field in unexpected})
        values, errors = self._validated_profile(payload)
        if errors:
            raise ProfileValidationError(errors)
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT display_name FROM customers WHERE id = ? AND status = 'active'",
                (session.customer_id,),
            ).fetchone()
            if not existing:
                raise AccountDisabled("Customer account is disabled")
            if "display_name" in values:
                connection.execute(
                    "UPDATE customers SET display_name = ?, updated_at = ? WHERE id = ?",
                    (values.pop("display_name"), now, session.customer_id),
                )
            if values:
                assignments = ", ".join(f"{column} = ?" for column in values)
                connection.execute(
                    f"UPDATE customer_profiles SET {assignments}, updated_at = ? WHERE customer_id = ?",
                    (*values.values(), now, session.customer_id),
                )
            display_name = connection.execute(
                "SELECT display_name FROM customers WHERE id = ?", (session.customer_id,)
            ).fetchone()["display_name"]
            if display_name:
                connection.execute(
                    "UPDATE customer_profiles SET completed_at = COALESCE(completed_at, ?) "
                    "WHERE customer_id = ?",
                    (now, session.customer_id),
                )
            self._audit(
                connection,
                actor_id=session.customer_id,
                action="customer_profile_updated",
                request_id=request_id,
                metadata={"fields": sorted(payload)},
            )
            user = self._customer_payload(connection, session.customer_id)
            connection.commit()
            return user

    def _validated_profile(
        self, payload: Mapping[str, object]
    ) -> tuple[dict[str, object], dict[str, str]]:
        values: dict[str, object] = {}
        errors: dict[str, str] = {}
        text_fields = {
            "displayName": ("display_name", 80, False),
            "address": ("address", 300, True),
            "emergencyContactName": ("emergency_contact_name", 80, False),
            "healthNotes": ("health_notes", 1000, True),
        }
        for external, (column, maximum, multiline) in text_fields.items():
            if external not in payload:
                continue
            try:
                value = _clean_text(payload[external], maximum=maximum, multiline=multiline)
                if external == "displayName" and (not value or len(value) < 2):
                    raise ValueError("Use at least two characters")
                values[column] = value
            except ValueError as error:
                errors[external] = str(error)
        if "gender" in payload:
            gender = payload["gender"]
            if gender in (None, ""):
                values["gender"] = None
            elif isinstance(gender, str) and gender in ALLOWED_GENDERS:
                values["gender"] = gender
            else:
                errors["gender"] = "Select a valid option"
        if "dateOfBirth" in payload:
            raw_date = payload["dateOfBirth"]
            if raw_date in (None, ""):
                values["date_of_birth"] = None
            elif isinstance(raw_date, str):
                try:
                    parsed = date.fromisoformat(raw_date)
                    today = date.today()
                    if parsed > today or parsed.year < today.year - 120:
                        raise ValueError
                    values["date_of_birth"] = parsed.isoformat()
                except ValueError:
                    errors["dateOfBirth"] = "Enter a valid date of birth"
            else:
                errors["dateOfBirth"] = "Enter a valid date of birth"
        if "emergencyContactPhone" in payload:
            raw_phone = payload["emergencyContactPhone"]
            if raw_phone in (None, ""):
                values["emergency_contact_phone"] = None
            elif isinstance(raw_phone, str):
                try:
                    values["emergency_contact_phone"] = normalize_phone(raw_phone)
                except ValueError:
                    errors["emergencyContactPhone"] = "Use an international number such as +919876543210"
            else:
                errors["emergencyContactPhone"] = "Enter a valid phone number"
        return values, errors

    @staticmethod
    def _customer_payload(connection: sqlite3.Connection, customer_id: str) -> dict[str, object]:
        row = connection.execute(
            "SELECT c.id, c.status, c.display_name, c.email, c.email_verified, c.phone_e164, "
            "c.phone_verified, c.photo_url, p.date_of_birth, p.gender, p.address, "
            "p.emergency_contact_name, p.emergency_contact_phone, p.health_notes, p.completed_at "
            "FROM customers c JOIN customer_profiles p ON p.customer_id = c.id WHERE c.id = ?",
            (customer_id,),
        ).fetchone()
        if not row:
            raise InvalidSession("Customer account is missing")
        providers = [
            provider_row["sign_in_provider"]
            for provider_row in connection.execute(
                "SELECT DISTINCT p.sign_in_provider "
                "FROM firebase_provider_identities p "
                "JOIN firebase_identities i ON i.project_id = p.project_id AND i.firebase_uid = p.firebase_uid "
                "WHERE i.customer_id = ? ORDER BY p.sign_in_provider",
                (customer_id,),
            ).fetchall()
        ]
        return {
            "id": row["id"],
            "status": row["status"],
            "displayName": row["display_name"],
            "email": row["email"],
            "emailVerified": bool(row["email_verified"]),
            "phone": row["phone_e164"],
            "phoneVerified": bool(row["phone_verified"]),
            "photoUrl": row["photo_url"],
            "providers": providers,
            "profileComplete": row["completed_at"] is not None,
            "profile": {
                "dateOfBirth": row["date_of_birth"],
                "gender": row["gender"],
                "address": row["address"],
                "emergencyContactName": row["emergency_contact_name"],
                "emergencyContactPhone": row["emergency_contact_phone"],
                "healthNotes": row["health_notes"],
            },
        }

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        *,
        actor_id: str,
        action: str,
        request_id: str,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        connection.execute(
            "INSERT INTO audit_logs(actor_type, actor_id, action, entity_type, entity_id, request_id, metadata_json) "
            "VALUES ('customer', ?, ?, 'customer', ?, ?, ?)",
            (
                actor_id,
                action,
                actor_id,
                request_id,
                json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True),
            ),
        )
