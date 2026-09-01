from __future__ import annotations

from dataclasses import dataclass
from hashlib import scrypt, sha256
from hmac import compare_digest, new as hmac_new
from typing import Callable, Mapping
from urllib.parse import quote
from uuid import uuid4
import base64
import json
import re
import secrets
import sqlite3
import struct
import time

from cryptography.fernet import Fernet, InvalidToken

from .config import Settings
from .database import Database


ADMIN_ROLES = ("owner", "admin", "trainer", "reception")
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset({"*"}),
    "admin": frozenset({
        "dashboard.view", "members.read", "members.manage", "memberships.manage",
        "membership_plans.manage", "payments.read", "payments.record", "notifications.manage", "diet.manage",
        "progress.manage", "content.manage", "attendance.view", "biometric.manage", "audit.read", "system.readiness",
        "enquiries.read", "enquiries.manage",
    }),
    "trainer": frozenset({"dashboard.view", "members.read", "attendance.view", "diet.manage", "progress.manage"}),
    "reception": frozenset({
        "dashboard.view", "members.read", "members.manage",
        "memberships.manage", "payments.read", "payments.record", "attendance.view",
        "enquiries.read", "enquiries.manage",
    }),
}
USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.@+-]{2,63}$")
RECOVERY_PATTERN = re.compile(r"^[A-Fa-f0-9]{12}$")
PASSWORD_MAX = 256
MAX_ACTIVE_ADMIN_SESSIONS = 3


class AdminError(Exception):
    pass


class AdminUnavailable(AdminError):
    pass


class AdminInvalidCredentials(AdminError):
    pass


class AdminChallengeExpired(AdminError):
    pass


class AdminInvalidSecondFactor(AdminError):
    pass


class AdminSessionInvalid(AdminError):
    pass


class AdminCsrfInvalid(AdminError):
    pass


class AdminForbidden(AdminError):
    pass


class AdminConflict(AdminError):
    pass


class AdminValidationError(AdminError):
    def __init__(self, fields: Mapping[str, str]) -> None:
        super().__init__("Admin validation failed")
        self.fields = dict(fields)


class AdminRateLimitExceeded(AdminError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Admin rate limit exceeded")
        self.retry_after = max(1, retry_after)


@dataclass(frozen=True, slots=True)
class AdminChallengeIssue:
    challenge_token: str
    expires_at: int


@dataclass(frozen=True, slots=True)
class AdminSessionIdentity:
    session_id: str
    admin_user_id: str
    csrf_hash: str
    admin: dict[str, object]


@dataclass(frozen=True, slots=True)
class AdminSessionIssue:
    session_token: str
    csrf_token: str
    absolute_expires_at: int
    admin: dict[str, object]


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    admin: dict[str, object]
    totp_secret: str
    otpauth_uri: str
    recovery_codes: tuple[str, ...]


def _token_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _normalize_username(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid username")
    normalized = value.strip().casefold()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid username")
    return normalized


def _password_classes(password: str) -> int:
    return sum((
        any(ch.islower() for ch in password),
        any(ch.isupper() for ch in password),
        any(ch.isdigit() for ch in password),
        any(not ch.isalnum() for ch in password),
    ))


def _validate_password(password: object) -> str:
    if not isinstance(password, str) or not 12 <= len(password) <= PASSWORD_MAX:
        raise ValueError("Password must be 12-256 characters")
    if _password_classes(password) < 3:
        raise ValueError("Password must use at least three character classes")
    return password


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    work = scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${_b64(salt)}${_b64(work)}"


def _verify_password(encoded: str, password: str) -> bool:
    try:
        algorithm, n_raw, r_raw, p_raw, salt_raw, expected_raw = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        n, r, p = int(n_raw), int(r_raw), int(p_raw)
        if (n, r, p) != (16384, 8, 1):
            return False
        actual = scrypt(
            password.encode("utf-8"),
            salt=_b64decode(salt_raw),
            n=n, r=r, p=p, dklen=32,
        )
        return compare_digest(actual, _b64decode(expected_raw))
    except (ValueError, TypeError):
        return False


def _totp_code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret, casefold=True)
    digest = hmac_new(key, struct.pack(">Q", counter), "sha1").digest()
    offset = digest[-1] & 0x0F
    binary = int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF
    return f"{binary % 1_000_000:06d}"


class AdminService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.database = database
        self.settings = settings
        self.clock = clock
        digest = sha256(b"gravity-admin-totp\x00" + settings.secret_key.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    @property
    def configured(self) -> bool:
        return len(self.settings.secret_key.encode("utf-8")) >= 32

    def _now(self) -> int:
        return int(self.clock())

    def _private_hash(self, scope: str, value: str) -> str:
        return hmac_new(
            self.settings.secret_key.encode("utf-8"),
            f"{scope}\0{value}".encode("utf-8"),
            "sha256",
        ).hexdigest()

    def _safe_admin(self, row: sqlite3.Row) -> dict[str, object]:
        role = str(row["role"])
        permissions = ROLE_PERMISSIONS.get(role, frozenset())
        return {
            "id": row["id"],
            "username": row["username"],
            "role": role,
            "status": row["status"],
            "permissions": sorted(permissions),
            "totpEnabled": self.settings.admin_require_second_factor,
        }

    def bootstrap_required(self) -> bool:
        with self.database.session() as connection:
            row = connection.execute(
                "SELECT 1 FROM admin_users WHERE role='owner' AND status='active' LIMIT 1"
            ).fetchone()
        return row is None

    def _audit(
        self,
        connection: sqlite3.Connection,
        admin_user_id: str | None,
        action: str,
        *,
        target_type: str | None = None,
        target_id: str | None = None,
        result: str = "success",
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        safe_metadata = {
            str(key): value for key, value in (metadata or {}).items()
            if str(key).casefold() not in {
                "password", "token", "secret", "code", "csrf", "session",
                "authorization", "cookie",
            }
        }
        connection.execute(
            "INSERT INTO admin_audit_log(admin_user_id,action,target_type,target_id,result,"
            "metadata_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (
                admin_user_id, action, target_type, target_id, result,
                json.dumps(safe_metadata, separators=(",", ":"), sort_keys=True),
                self._now(),
            ),
        )

    def _consume_bucket(self, scope: str, key_hash: str, *, window: int, limit: int) -> None:
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT window_started_at,request_count,blocked_until FROM admin_rate_limits "
                "WHERE scope=? AND key_hash=?",
                (scope, key_hash),
            ).fetchone()
            if row and row["blocked_until"] and row["blocked_until"] > now:
                connection.commit()
                raise AdminRateLimitExceeded(row["blocked_until"] - now)
            if not row or now - row["window_started_at"] >= window:
                started_at, request_count = now, 1
            else:
                started_at, request_count = row["window_started_at"], row["request_count"] + 1
            blocked_until = now + window if request_count > limit else None
            connection.execute(
                "INSERT INTO admin_rate_limits(scope,key_hash,window_started_at,request_count,blocked_until,updated_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(scope,key_hash) DO UPDATE SET "
                "window_started_at=excluded.window_started_at,request_count=excluded.request_count,"
                "blocked_until=excluded.blocked_until,updated_at=excluded.updated_at",
                (scope, key_hash, started_at, request_count, blocked_until, now),
            )
            connection.execute("DELETE FROM admin_rate_limits WHERE updated_at<?", (now - 604800,))
            connection.commit()
            if blocked_until:
                raise AdminRateLimitExceeded(window)

    def _rate_limit_password(self, username: str, remote_addr: str) -> None:
        self._consume_bucket(
            "admin_password_account",
            self._private_hash("admin-account", username),
            window=900,
            limit=6,
        )
        self._consume_bucket(
            "admin_password_remote",
            self._private_hash("admin-remote", remote_addr),
            window=900,
            limit=12,
        )

    def _rate_limit_second_factor(self, admin_id: str, remote_addr: str) -> None:
        self._consume_bucket(
            "admin_second_factor_account",
            self._private_hash("admin-2fa-account", admin_id),
            window=600,
            limit=8,
        )
        self._consume_bucket(
            "admin_second_factor_remote",
            self._private_hash("admin-2fa-remote", remote_addr),
            window=600,
            limit=16,
        )

    def _create_admin_record(
        self,
        connection: sqlite3.Connection,
        *,
        username: str,
        password: str,
        role: str,
        actor_id: str | None,
    ) -> BootstrapResult:
        if role not in ADMIN_ROLES:
            raise ValueError("Invalid admin role")
        admin_id = uuid4().hex
        now = self._now()
        secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
        recovery_codes = tuple(secrets.token_hex(6).upper() for _ in range(8))
        encrypted_secret = self._fernet.encrypt(secret.encode("ascii")).decode("ascii")
        connection.execute(
            "INSERT INTO admin_users(id,username,password_hash,role,status,encrypted_totp_secret,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (admin_id, username, _hash_password(password), role, "active", encrypted_secret, now, now),
        )
        connection.executemany(
            "INSERT INTO admin_recovery_codes(id,admin_user_id,code_hash,created_at) VALUES(?,?,?,?)",
            [
                (
                    uuid4().hex,
                    admin_id,
                    self._private_hash("admin-recovery", f"{admin_id}\0{code}"),
                    now,
                )
                for code in recovery_codes
            ],
        )
        self._audit(
            connection,
            actor_id or admin_id,
            "admin_created",
            target_type="admin_user",
            target_id=admin_id,
            metadata={"role": role, "bootstrap": actor_id is None},
        )
        row = connection.execute("SELECT * FROM admin_users WHERE id=?", (admin_id,)).fetchone()
        label = quote(f"Gravity Fitness:{username}")
        issuer = quote("Gravity Fitness")
        uri = f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&digits=6&period=30"
        return BootstrapResult(
            admin=self._safe_admin(row),
            totp_secret=secret,
            otpauth_uri=uri,
            recovery_codes=recovery_codes,
        )

    def bootstrap_owner(self, username: object, password: object) -> BootstrapResult:
        if not self.configured:
            raise AdminUnavailable("Admin security is not configured")
        try:
            normalized = _normalize_username(username)
            valid_password = _validate_password(password)
        except ValueError as error:
            raise AdminValidationError({"credentials": str(error)}) from error
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT 1 FROM admin_users WHERE role='owner' LIMIT 1"
            ).fetchone()
            if existing:
                connection.rollback()
                raise AdminConflict("An owner already exists")
            try:
                result = self._create_admin_record(
                    connection,
                    username=normalized,
                    password=valid_password,
                    role="owner",
                    actor_id=None,
                )
                connection.commit()
                return result
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise AdminConflict("Administrator already exists") from error

    def create_admin(
        self,
        actor: AdminSessionIdentity,
        username: object,
        password: object,
        role: object,
    ) -> BootstrapResult:
        self.require_permission(actor, "admin.manage")
        if actor.admin.get("role") != "owner":
            raise AdminForbidden("Only the owner can create administrators")
        try:
            normalized = _normalize_username(username)
            valid_password = _validate_password(password)
            normalized_role = str(role).strip().casefold()
            if normalized_role not in ADMIN_ROLES:
                raise ValueError("Invalid admin role")
            if normalized_role == 'owner':
                raise ValueError('Owner role can only be created during initial bootstrap')
        except ValueError as error:
            raise AdminValidationError({"admin": str(error)}) from error
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                result = self._create_admin_record(
                    connection,
                    username=normalized,
                    password=valid_password,
                    role=normalized_role,
                    actor_id=actor.admin_user_id,
                )
                connection.commit()
                return result
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise AdminConflict("Administrator already exists") from error

    def begin_login(self, payload: Mapping[str, object], remote_addr: str) -> AdminChallengeIssue:
        if not self.configured:
            raise AdminUnavailable("Admin security is not configured")
        try:
            username = _normalize_username(payload.get("username"))
        except ValueError:
            username = "invalid"
        password = payload.get("password")
        candidate = password if isinstance(password, str) and len(password) <= PASSWORD_MAX else ""
        self._rate_limit_password(username, remote_addr)
        with self.database.session() as connection:
            row = connection.execute(
                "SELECT * FROM admin_users WHERE username=?",
                (username,),
            ).fetchone()
            encoded = row["password_hash"] if row is not None else _hash_password("Invalid!Password123")
            verified = _verify_password(str(encoded), candidate)
            valid = bool(row is not None and row["status"] == "active" and verified)
            if not valid:
                self._audit(
                    connection,
                    row["id"] if row is not None else None,
                    "admin_login_password",
                    target_type="admin_user",
                    target_id=row["id"] if row is not None else None,
                    result="failed",
                )
                raise AdminInvalidCredentials("Invalid administrator credentials")
            raw = secrets.token_urlsafe(48)
            now = self._now()
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE admin_login_challenges SET used_at=? WHERE admin_user_id=? AND used_at IS NULL",
                (now, row["id"]),
            )
            connection.execute(
                "INSERT INTO admin_login_challenges(id,admin_user_id,token_hash,created_at,expires_at) "
                "VALUES(?,?,?,?,?)",
                (uuid4().hex, row["id"], _token_hash(raw), now, now + 300),
            )
            self._audit(
                connection,
                row["id"],
                "admin_login_password",
                target_type="admin_user",
                target_id=row["id"],
                result="success",
            )
            connection.commit()
        return AdminChallengeIssue(challenge_token=raw, expires_at=now + 300)

    def _decrypt_totp_secret(self, encrypted: str) -> str:
        try:
            return self._fernet.decrypt(encrypted.encode("ascii")).decode("ascii")
        except (InvalidToken, UnicodeError, ValueError) as error:
            raise AdminUnavailable("Administrator second factor is unavailable") from error

    def verify_second_factor(
        self,
        challenge_token: str | None,
        code: object,
        *,
        remote_addr: str,
        user_agent: str,
        request_id: str,
    ) -> AdminSessionIssue:
        if not self.configured:
            raise AdminUnavailable("Admin security is not configured")
        require_second_factor = self.settings.admin_require_second_factor
        if not challenge_token or (require_second_factor and not isinstance(code, str)):
            raise AdminInvalidSecondFactor("Invalid administrator verification code")
        normalized_code = code.strip() if isinstance(code, str) else ""
        if require_second_factor and not (re.fullmatch(r"\d{6}", normalized_code) or RECOVERY_PATTERN.fullmatch(normalized_code)):
            raise AdminInvalidSecondFactor("Invalid administrator verification code")
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT c.*,u.username,u.role,u.status,u.encrypted_totp_secret,u.last_totp_counter "
                "FROM admin_login_challenges c JOIN admin_users u ON u.id=c.admin_user_id "
                "WHERE c.token_hash=?",
                (_token_hash(challenge_token),),
            ).fetchone()
            if row is None or row["used_at"] is not None or row["status"] != "active" or row["expires_at"] <= now:
                connection.rollback()
                raise AdminChallengeExpired("Administrator challenge expired")
            admin_id = str(row["admin_user_id"])
            connection.rollback()
            if require_second_factor:
                self._rate_limit_second_factor(admin_id, remote_addr)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT c.*,u.username,u.role,u.status,u.encrypted_totp_secret,u.last_totp_counter "
                "FROM admin_login_challenges c JOIN admin_users u ON u.id=c.admin_user_id "
                "WHERE c.token_hash=?",
                (_token_hash(challenge_token),),
            ).fetchone()
            if row is None or row["used_at"] is not None or row["status"] != "active" or row["expires_at"] <= now:
                connection.rollback()
                raise AdminChallengeExpired("Administrator challenge expired")

            verified = not require_second_factor
            accepted_counter: int | None = None
            recovery_id: str | None = None
            if require_second_factor and normalized_code.isdigit():
                secret = self._decrypt_totp_secret(str(row["encrypted_totp_secret"]))
                current_counter = now // 30
                for candidate_counter in range(current_counter - 1, current_counter + 2):
                    if compare_digest(_totp_code(secret, candidate_counter), normalized_code):
                        last_counter = row["last_totp_counter"]
                        if last_counter is None or candidate_counter > int(last_counter):
                            verified = True
                            accepted_counter = candidate_counter
                        break
            elif require_second_factor:
                recovery_hash = self._private_hash(
                    "admin-recovery",
                    f"{admin_id}\0{normalized_code.upper()}",
                )
                recovery = connection.execute(
                    "SELECT id FROM admin_recovery_codes WHERE admin_user_id=? AND code_hash=? AND used_at IS NULL",
                    (admin_id, recovery_hash),
                ).fetchone()
                if recovery is not None:
                    verified = True
                    recovery_id = str(recovery["id"])
            if not require_second_factor:
                self._audit(connection, admin_id, "admin_second_factor_skipped", target_type="admin_user", target_id=admin_id, metadata={"mode": "password_only"})
            elif not verified:
                self._audit(
                    connection,
                    admin_id,
                    "admin_second_factor",
                    target_type="admin_user",
                    target_id=admin_id,
                    result="failed",
                )
                connection.commit()
                raise AdminInvalidSecondFactor("Invalid administrator verification code")

            changed = connection.execute(
                "UPDATE admin_login_challenges SET used_at=? WHERE id=? AND used_at IS NULL",
                (now, row["id"]),
            ).rowcount
            if changed != 1:
                connection.rollback()
                raise AdminChallengeExpired("Administrator challenge expired")
            if accepted_counter is not None:
                connection.execute(
                    "UPDATE admin_users SET last_totp_counter=?,last_login_at=?,updated_at=? WHERE id=?",
                    (accepted_counter, now, now, admin_id),
                )
            else:
                connection.execute(
                    "UPDATE admin_users SET last_login_at=?,updated_at=? WHERE id=?",
                    (now, now, admin_id),
                )
            if recovery_id is not None:
                connection.execute(
                    "UPDATE admin_recovery_codes SET used_at=? WHERE id=? AND used_at IS NULL",
                    (now, recovery_id),
                )

            session_token = secrets.token_urlsafe(48)
            csrf_token = secrets.token_urlsafe(32)
            session_id = uuid4().hex
            absolute_expires_at = now + 28800
            idle_expires_at = now + 1800
            connection.execute(
                "INSERT INTO admin_sessions(id,admin_user_id,token_hash,csrf_hash,created_at,last_seen_at,"
                "idle_expires_at,absolute_expires_at,ip_hash,user_agent_hash) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    session_id,
                    admin_id,
                    _token_hash(session_token),
                    _token_hash(csrf_token),
                    now,
                    now,
                    idle_expires_at,
                    absolute_expires_at,
                    self._private_hash("admin-ip", remote_addr),
                    self._private_hash("admin-ua", user_agent[:1000]) if user_agent else None,
                ),
            )
            active_rows = connection.execute(
                "SELECT id FROM admin_sessions WHERE admin_user_id=? AND revoked_at IS NULL "
                "AND absolute_expires_at>? ORDER BY created_at DESC,id DESC",
                (admin_id, now),
            ).fetchall()
            for stale in active_rows[MAX_ACTIVE_ADMIN_SESSIONS:]:
                connection.execute(
                    "UPDATE admin_sessions SET revoked_at=?,revoke_reason='session_cap' WHERE id=?",
                    (now, stale["id"]),
                )
            self._audit(
                connection,
                admin_id,
                "admin_login",
                target_type="admin_session",
                target_id=session_id,
                metadata={"requestId": request_id},
            )
            admin_row = connection.execute("SELECT * FROM admin_users WHERE id=?", (admin_id,)).fetchone()
            connection.commit()
        return AdminSessionIssue(
            session_token=session_token,
            csrf_token=csrf_token,
            absolute_expires_at=absolute_expires_at,
            admin=self._safe_admin(admin_row),
        )

    def resolve_session(self, session_token: str | None) -> AdminSessionIdentity:
        if not session_token:
            raise AdminSessionInvalid("Administrator authentication required")
        now = self._now()
        with self.database.session() as connection:
            row = connection.execute(
                "SELECT s.*,u.username,u.role,u.status FROM admin_sessions s "
                "JOIN admin_users u ON u.id=s.admin_user_id WHERE s.token_hash=?",
                (_token_hash(session_token),),
            ).fetchone()
            if row is None or row["revoked_at"] is not None or row["status"] != "active":
                raise AdminSessionInvalid("Administrator authentication required")
            if row["absolute_expires_at"] <= now or row["idle_expires_at"] <= now:
                connection.execute(
                    "UPDATE admin_sessions SET revoked_at=?,revoke_reason='expired' WHERE id=?",
                    (now, row["id"]),
                )
                raise AdminSessionInvalid("Administrator session expired")
            refreshed_idle = min(int(row["absolute_expires_at"]), now + 1800)
            connection.execute(
                "UPDATE admin_sessions SET last_seen_at=?,idle_expires_at=? WHERE id=?",
                (now, refreshed_idle, row["id"]),
            )
            admin = {
                "id": row["admin_user_id"],
                "username": row["username"],
                "role": row["role"],
                "status": row["status"],
                "permissions": sorted(ROLE_PERMISSIONS.get(str(row["role"]), frozenset())),
                "totpEnabled": self.settings.admin_require_second_factor,
            }
            return AdminSessionIdentity(
                session_id=str(row["id"]),
                admin_user_id=str(row["admin_user_id"]),
                csrf_hash=str(row["csrf_hash"]),
                admin=admin,
            )

    def verify_csrf(
        self,
        session: AdminSessionIdentity,
        supplied_header: str | None,
        cookie_token: str | None,
    ) -> None:
        if (
            not supplied_header
            or not cookie_token
            or not compare_digest(supplied_header, cookie_token)
            or not compare_digest(_token_hash(supplied_header), session.csrf_hash)
        ):
            raise AdminCsrfInvalid("Administrator CSRF verification failed")

    @staticmethod
    def require_permission(session: AdminSessionIdentity, permission: str) -> None:
        role = str(session.admin.get("role", ""))
        permissions = ROLE_PERMISSIONS.get(role, frozenset())
        if "*" not in permissions and permission not in permissions:
            raise AdminForbidden("Administrator permission denied")

    def logout(
        self,
        session: AdminSessionIdentity,
        *,
        all_sessions: bool = False,
        request_id: str | None = None,
    ) -> None:
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if all_sessions:
                connection.execute(
                    "UPDATE admin_sessions SET revoked_at=?,revoke_reason='logout_all' "
                    "WHERE admin_user_id=? AND revoked_at IS NULL",
                    (now, session.admin_user_id),
                )
            else:
                connection.execute(
                    "UPDATE admin_sessions SET revoked_at=?,revoke_reason='logout' WHERE id=?",
                    (now, session.session_id),
                )
            self._audit(
                connection,
                session.admin_user_id,
                "admin_logout_all" if all_sessions else "admin_logout",
                target_type="admin_session",
                target_id=session.session_id,
                metadata={"requestId": request_id} if request_id else None,
            )
            connection.commit()

    def dashboard(self, session: AdminSessionIdentity) -> dict[str, object]:
        self.require_permission(session, "dashboard.view")
        with self.database.session() as connection:
            customer_rows = connection.execute(
                "SELECT status,COUNT(*) AS count FROM customers WHERE person_type='member' GROUP BY status"
            ).fetchall()
            admin_rows = connection.execute(
                "SELECT role,COUNT(*) AS count FROM admin_users WHERE status='active' GROUP BY role"
            ).fetchall()
            recent = connection.execute(
                "SELECT action,result,created_at FROM admin_audit_log ORDER BY id DESC LIMIT 8"
            ).fetchall()
        customers = {str(row["status"]): int(row["count"]) for row in customer_rows}
        admins = {str(row["role"]): int(row["count"]) for row in admin_rows}
        return {
            "customers": {
                "active": customers.get("active", 0),
                "disabled": customers.get("disabled", 0),
                "deleted": customers.get("deleted", 0),
                "total": sum(customers.values()),
            },
            "admins": admins,
            "recentAudit": [
                {"action": row["action"], "result": row["result"], "createdAt": row["created_at"]}
                for row in recent
            ],
        }

    def list_customers(self, session: AdminSessionIdentity, query: str = "") -> list[dict[str, object]]:
        self.require_permission(session, "members.read")
        needle = query.strip().casefold()[:100]
        pattern = f"%{needle}%"
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT id,status,display_name,email,phone_e164,created_at,last_login_at FROM customers "
                "WHERE person_type='member' AND (?='' OR lower(COALESCE(display_name,'')) LIKE ? OR lower(COALESCE(email,'')) LIKE ? "
                "OR COALESCE(phone_e164,'') LIKE ?) ORDER BY created_at DESC LIMIT 100",
                (needle, pattern, pattern, pattern),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "status": row["status"],
                "displayName": row["display_name"],
                "email": row["email"],
                "phone": row["phone_e164"],
                "createdAt": row["created_at"],
                "lastLoginAt": row["last_login_at"],
            }
            for row in rows
        ]

    def set_customer_status(
        self,
        session: AdminSessionIdentity,
        customer_id: str,
        status: str,
        *,
        request_id: str,
    ) -> dict[str, object]:
        self.require_permission(session, "members.manage")
        normalized = status.strip().casefold()
        if normalized not in {"active", "disabled"}:
            raise AdminValidationError({"status": "Status must be active or disabled"})
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                "UPDATE customers SET status=?,updated_at=? WHERE id=? AND status!='deleted' AND person_type='member'",
                (normalized, now, customer_id),
            ).rowcount
            if changed != 1:
                connection.rollback()
                raise AdminValidationError({"customer": "Customer not found"})
            if normalized == "disabled":
                connection.execute(
                    "UPDATE customer_sessions SET revoked_at=?,revoke_reason='admin_disabled' "
                    "WHERE customer_id=? AND revoked_at IS NULL",
                    (now, customer_id),
                )
            self._audit(
                connection,
                session.admin_user_id,
                "customer_status_changed",
                target_type="customer",
                target_id=customer_id,
                metadata={"status": normalized, "requestId": request_id},
            )
            connection.commit()
        return {"id": customer_id, "status": normalized}

    def list_admins(self, session: AdminSessionIdentity) -> list[dict[str, object]]:
        if session.admin.get("role") != "owner":
            raise AdminForbidden("Only the owner can manage administrators")
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT * FROM admin_users ORDER BY created_at ASC,id ASC"
            ).fetchall()
        return [self._safe_admin(row) for row in rows]

    def set_admin_status(
        self,
        session: AdminSessionIdentity,
        admin_id: str,
        status: str,
        *,
        request_id: str,
    ) -> dict[str, object]:
        if session.admin.get("role") != "owner":
            raise AdminForbidden("Only the owner can manage administrators")
        normalized = status.strip().casefold()
        if normalized not in {"active", "disabled"}:
            raise AdminValidationError({"status": "Status must be active or disabled"})
        if admin_id == session.admin_user_id and normalized == "disabled":
            raise AdminConflict("The active owner cannot disable their own account")
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            target = connection.execute(
                "SELECT * FROM admin_users WHERE id=?",
                (admin_id,),
            ).fetchone()
            if target is None:
                connection.rollback()
                raise AdminValidationError({"admin": "Administrator not found"})
            if target["role"] == "owner" and normalized == "disabled":
                owners = connection.execute(
                    "SELECT COUNT(*) FROM admin_users WHERE role='owner' AND status='active'"
                ).fetchone()[0]
                if owners <= 1:
                    connection.rollback()
                    raise AdminConflict("At least one active owner is required")
            connection.execute(
                "UPDATE admin_users SET status=?,updated_at=? WHERE id=?",
                (normalized, now, admin_id),
            )
            if normalized == "disabled":
                connection.execute(
                    "UPDATE admin_sessions SET revoked_at=?,revoke_reason='admin_disabled' "
                    "WHERE admin_user_id=? AND revoked_at IS NULL",
                    (now, admin_id),
                )
            self._audit(
                connection,
                session.admin_user_id,
                "admin_status_changed",
                target_type="admin_user",
                target_id=admin_id,
                metadata={"status": normalized, "requestId": request_id},
            )
            updated = connection.execute("SELECT * FROM admin_users WHERE id=?", (admin_id,)).fetchone()
            connection.commit()
        return self._safe_admin(updated)

    def audit_log(self, session: AdminSessionIdentity, limit: int = 100) -> list[dict[str, object]]:
        self.require_permission(session, "audit.read")
        bounded = min(max(int(limit), 1), 200)
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT l.id,l.admin_user_id,u.username,l.action,l.target_type,l.target_id,l.result,"
                "l.metadata_json,l.created_at FROM admin_audit_log l "
                "LEFT JOIN admin_users u ON u.id=l.admin_user_id ORDER BY l.id DESC LIMIT ?",
                (bounded,),
            ).fetchall()
        result: list[dict[str, object]] = []
        for row in rows:
            try:
                metadata = json.loads(row["metadata_json"])
            except (TypeError, json.JSONDecodeError):
                metadata = {}
            result.append({
                "id": row["id"],
                "adminUserId": row["admin_user_id"],
                "username": row["username"],
                "action": row["action"],
                "targetType": row["target_type"],
                "targetId": row["target_id"],
                "result": row["result"],
                "metadata": metadata if isinstance(metadata, dict) else {},
                "createdAt": row["created_at"],
            })
        return result
