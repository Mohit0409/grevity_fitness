from __future__ import annotations

from email.utils import formatdate
from http import HTTPStatus
from io import StringIO
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from typing import Any
import csv
import os

from .membership import MembershipConflict, MembershipNotFound, MembershipValidationError
from .biometric import (
    BiometricAdapterError,
    BiometricConflict,
    BiometricNotFound,
    BiometricValidationError,
)
from .admin_software import (
    AdminSoftwareConflict,
    AdminSoftwareNotFound,
    AdminSoftwareValidationError,
)
from .notification import NotificationConflict, NotificationNotFound, NotificationValidationError
from .admin import (
    AdminChallengeExpired,
    AdminConflict,
    AdminCsrfInvalid,
    AdminForbidden,
    AdminInvalidCredentials,
    AdminInvalidSecondFactor,
    AdminRateLimitExceeded,
    AdminSessionIdentity,
    AdminSessionInvalid,
    AdminSessionIssue,
    AdminUnavailable,
    AdminValidationError,
)

ADMIN_JSON_LIMIT = 16_384
ADMIN_PHOTO_LIMIT = 768 * 1024


def _has_permission(session: AdminSessionIdentity, permission: str) -> bool:
    permissions = session.admin.get("permissions", [])
    if not isinstance(permissions, (list, tuple, set, frozenset)):
        return False
    return "*" in permissions or permission in permissions


def _without_membership_payment(value: object) -> object:
    if not isinstance(value, dict):
        return value
    item = dict(value)
    item.pop("payment", None)
    return item


def _without_customer_payment(value: object) -> object:
    if not isinstance(value, dict):
        return value
    item = dict(value)
    item["membership"] = _without_membership_payment(item.get("membership"))
    return item


def _redact_customer_detail(detail: dict[str, object], *, payments: bool, notifications: bool) -> dict[str, object]:
    result = dict(detail)
    if not payments:
        result.pop("payments", None)
        membership = dict(result.get("membership") or {})
        for key in ("current", "upcoming"):
            membership[key] = _without_membership_payment(membership.get(key))
        for key in ("history", "all"):
            membership[key] = [_without_membership_payment(item) for item in list(membership.get(key) or [])]
        result["membership"] = membership
    if not notifications:
        result.pop("notifications", None)
    return result


def _redact_dashboard_financials(data: dict[str, object]) -> dict[str, object]:
    result = dict(data)
    stats = dict(result.get("stats") or {})
    for key in ("pendingFeesTotalPaise", "paymentsReceivedTodayPaise", "paymentsReceivedThisMonthPaise"):
        stats.pop(key, None)
    result["stats"] = stats
    result.pop("pendingFees", None)
    result.pop("recentPayments", None)
    result["recentCustomers"] = [_without_customer_payment(item) for item in list(result.get("recentCustomers") or [])]
    return result


def _cookie_attributes(handler: Any, max_age: int, expires_at: int) -> str:
    attributes = (
        f"Path=/; Max-Age={max(0, max_age)}; "
        f"Expires={formatdate(expires_at, usegmt=True)}; SameSite=Strict"
    )
    if handler.server.settings.production:
        attributes += "; Secure"
    return attributes

def _challenge_cookie_headers(handler: Any, token: str, expires_at: int) -> list[tuple[str, str]]:
    settings = handler.server.settings
    now = int(handler.server.admin_service.clock())
    attributes = _cookie_attributes(handler, expires_at - now, expires_at)
    return [("Set-Cookie", f"{settings.admin_challenge_cookie_name}={token}; {attributes}; HttpOnly")]


def _session_cookie_headers(handler: Any, issue: AdminSessionIssue) -> list[tuple[str, str]]:
    settings = handler.server.settings
    now = int(handler.server.admin_service.clock())
    attributes = _cookie_attributes(handler, issue.absolute_expires_at - now, issue.absolute_expires_at)
    return [
        ("Set-Cookie", f"{settings.admin_session_cookie_name}={issue.session_token}; {attributes}; HttpOnly"),
        ("Set-Cookie", f"{settings.admin_csrf_cookie_name}={issue.csrf_token}; {attributes}"),
        *_clear_challenge_headers(handler),
    ]


def _clear_challenge_headers(handler: Any) -> list[tuple[str, str]]:
    name = handler.server.settings.admin_challenge_cookie_name
    attributes = "Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Strict"
    if handler.server.settings.production:
        attributes += "; Secure"
    return [("Set-Cookie", f"{name}=; {attributes}; HttpOnly")]


def _clear_session_headers(handler: Any) -> list[tuple[str, str]]:
    settings = handler.server.settings
    attributes = "Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Strict"
    if settings.production:
        attributes += "; Secure"
    return [
        ("Set-Cookie", f"{settings.admin_session_cookie_name}=; {attributes}; HttpOnly"),
        ("Set-Cookie", f"{settings.admin_csrf_cookie_name}=; {attributes}"),
        *_clear_challenge_headers(handler),
    ]


def _json(handler: Any, status: HTTPStatus, payload: dict[str, object], request_id: str, send_body: bool, *, headers: list[tuple[str, str]] | None = None) -> HTTPStatus:
    handler._json_response(
        status,
        payload,
        request_id=request_id,
        send_body=send_body,
        headers=headers,
    )
    return status


def _same_origin(handler: Any, request_id: str, send_body: bool) -> HTTPStatus | None:
    if handler._same_origin():
        return None
    return _json(handler, HTTPStatus.FORBIDDEN, {"error": "invalid_origin"}, request_id, send_body)

def _admin_session(handler: Any) -> AdminSessionIdentity:
    token = handler._cookie_value(handler.server.settings.admin_session_cookie_name)
    return handler.server.admin_service.resolve_session(token)


def _require_csrf(handler: Any, session: AdminSessionIdentity) -> None:
    values = handler.headers.get_all("X-CSRF-Token", [])
    if len(values) != 1:
        raise AdminCsrfInvalid("Administrator CSRF verification failed")
    cookie = handler._cookie_value(handler.server.settings.admin_csrf_cookie_name)
    handler.server.admin_service.verify_csrf(session, values[0], cookie)


def _idempotency_key(handler: Any) -> str | None:
    values = handler.headers.get_all("Idempotency-Key", [])
    if not values:
        return None
    if len(values) != 1:
        raise AdminSoftwareValidationError({"idempotencyKey": "Provide one Idempotency-Key header"})
    return values[0]


def _error_response(handler: Any, error: Exception, request_id: str, send_body: bool) -> HTTPStatus:
    if isinstance(error, AdminRateLimitExceeded):
        return _json(
            handler,
            HTTPStatus.TOO_MANY_REQUESTS,
            {"error": "admin_rate_limited"},
            request_id,
            send_body,
            headers=[("Retry-After", str(error.retry_after))],
        )
    if isinstance(error, AdminUnavailable):
        return _json(handler, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "admin_unavailable"}, request_id, send_body)
    if isinstance(error, (AdminInvalidCredentials, AdminInvalidSecondFactor, AdminChallengeExpired)):
        return _json(handler, HTTPStatus.UNAUTHORIZED, {"error": "invalid_admin_credentials"}, request_id, send_body)
    if isinstance(error, AdminSessionInvalid):
        return _json(
            handler,
            HTTPStatus.UNAUTHORIZED,
            {"error": "admin_unauthenticated"},
            request_id,
            send_body,
            headers=_clear_session_headers(handler),
        )
    if isinstance(error, (AdminCsrfInvalid, AdminForbidden)):
        return _json(handler, HTTPStatus.FORBIDDEN, {"error": "admin_forbidden"}, request_id, send_body)
    if isinstance(error, MembershipNotFound):
        return _json(handler, HTTPStatus.NOT_FOUND, {"error": "membership_not_found"}, request_id, send_body)
    if isinstance(error, MembershipConflict):
        return _json(handler, HTTPStatus.CONFLICT, {"error": "membership_conflict"}, request_id, send_body)
    if isinstance(error, MembershipValidationError):
        return _json(
            handler,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            {"error": "membership_validation", "fields": error.fields},
            request_id,
            send_body,
        )
    if isinstance(error, NotificationNotFound):
        return _json(handler, HTTPStatus.NOT_FOUND, {"error": "notification_not_found"}, request_id, send_body)
    if isinstance(error, NotificationConflict):
        return _json(handler, HTTPStatus.CONFLICT, {"error": "notification_conflict"}, request_id, send_body)
    if isinstance(error, NotificationValidationError):
        return _json(handler, HTTPStatus.UNPROCESSABLE_ENTITY, {"error": "notification_validation"}, request_id, send_body)
    if isinstance(error, AdminSoftwareNotFound):
        return _json(handler, HTTPStatus.NOT_FOUND, {"error": "admin_software_not_found"}, request_id, send_body)
    if isinstance(error, AdminSoftwareConflict):
        return _json(handler, HTTPStatus.CONFLICT, {"error": "admin_software_conflict"}, request_id, send_body)
    if isinstance(error, AdminSoftwareValidationError):
        return _json(
            handler,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            {"error": "admin_software_validation", "fields": error.fields},
            request_id,
            send_body,
        )
    if isinstance(error, BiometricNotFound):
        return _json(handler, HTTPStatus.NOT_FOUND, {"error": "biometric_not_found"}, request_id, send_body)
    if isinstance(error, BiometricConflict):
        return _json(handler, HTTPStatus.CONFLICT, {"error": "biometric_conflict"}, request_id, send_body)
    if isinstance(error, BiometricValidationError):
        return _json(
            handler,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            {"error": "biometric_validation", "fields": error.fields},
            request_id,
            send_body,
        )
    if isinstance(error, BiometricAdapterError):
        return _json(
            handler,
            HTTPStatus.SERVICE_UNAVAILABLE,
            {"error": "biometric_device_unavailable", "status": error.status},
            request_id,
            send_body,
        )
    if isinstance(error, AdminConflict):
        return _json(handler, HTTPStatus.CONFLICT, {"error": "admin_conflict"}, request_id, send_body)
    if isinstance(error, AdminValidationError):
        return _json(
            handler,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            {"error": "admin_validation", "fields": error.fields},
            request_id,
            send_body,
        )
    raise error


def _login(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    issue = handler.server.admin_service.begin_login(payload, handler._client_ip())
    if not handler.server.settings.admin_require_second_factor:
        session_issue = handler.server.admin_service.verify_second_factor(
            issue.challenge_token, None,
            remote_addr=handler._client_ip(), user_agent=handler.headers.get("User-Agent", "")[:1000], request_id=request_id,
        )
        return _json(handler, HTTPStatus.OK, {"authenticated": True, "admin": session_issue.admin, "csrfToken": session_issue.csrf_token, "secondFactorRequired": False}, request_id, send_body, headers=_session_cookie_headers(handler, session_issue))
    return _json(
        handler,
        HTTPStatus.OK,
        {"challenge": True, "expiresAt": issue.expires_at, "secondFactorRequired": True},
        request_id,
        send_body,
        headers=_challenge_cookie_headers(handler, issue.challenge_token, issue.expires_at),
    )


def _verify(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    challenge = handler._cookie_value(handler.server.settings.admin_challenge_cookie_name)
    issue = handler.server.admin_service.verify_second_factor(
        challenge,
        payload.get("code"),
        remote_addr=handler._client_ip(),
        user_agent=handler.headers.get("User-Agent", "")[:1000],
        request_id=request_id,
    )
    return _json(
        handler,
        HTTPStatus.OK,
        {"authenticated": True, "admin": issue.admin, "csrfToken": issue.csrf_token},
        request_id,
        send_body,
        headers=_session_cookie_headers(handler, issue),
    )


def _session_status(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    service = handler.server.admin_service
    payload: dict[str, object] = {
        "authenticated": False,
        "configured": service.configured,
        "bootstrapRequired": service.bootstrap_required(),
        "secondFactorRequired": handler.server.settings.admin_require_second_factor,
    }
    try:
        session = _admin_session(handler)
    except AdminSessionInvalid:
        return _json(handler, HTTPStatus.OK, payload, request_id, send_body)
    payload.update({"authenticated": True, "admin": session.admin})
    return _json(handler, HTTPStatus.OK, payload, request_id, send_body)


def _authenticated(handler: Any, request_id: str, send_body: bool) -> tuple[AdminSessionIdentity | None, HTTPStatus | None]:
    try:
        return _admin_session(handler), None
    except AdminSessionInvalid as error:
        return None, _error_response(handler, error, request_id, send_body)

def _logout(handler: Any, request_id: str, send_body: bool, *, all_sessions: bool) -> HTTPStatus:
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    _require_csrf(handler, session)
    handler._require_empty_body()
    handler.server.admin_service.logout(session, all_sessions=all_sessions, request_id=request_id)
    return _json(
        handler,
        HTTPStatus.OK,
        {"authenticated": False},
        request_id,
        send_body,
        headers=_clear_session_headers(handler),
    )


def _dashboard(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "dashboard.view")
    data = handler.server.admin_software_service.dashboard()
    if not _has_permission(session, "payments.read"):
        data = _redact_dashboard_financials(data)
    return _json(handler, HTTPStatus.OK, data, request_id, send_body)

def _customer_photo_path(handler: Any, customer_id: str, *, create: bool = False) -> Path:
    root = Path(handler.server.settings.database_path).parent / "customer-photos"
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root / f"{customer_id}.jpg"


def _customer_photo(handler: Any, customer_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "members.read")
    handler.server.admin_software_service.customer_detail(customer_id)
    photo = _customer_photo_path(handler, customer_id)
    if handler.command in {"GET", "HEAD"}:
        if not photo.is_file():
            return _json(handler, HTTPStatus.NOT_FOUND, {"error": "photo_not_found"}, request_id, send_body)
        data = photo.read_bytes()
        handler.send_response(HTTPStatus.OK)
        handler._security_headers(request_id)
        handler.send_header("Content-Type", "image/jpeg")
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "private, no-store")
        handler.end_headers()
        if send_body:
            handler.wfile.write(data)
        return HTTPStatus.OK
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    handler.server.admin_service.require_permission(session, "members.manage")
    _require_csrf(handler, session)
    data = handler._raw_body(maximum=ADMIN_PHOTO_LIMIT, content_type="image/jpeg")
    if len(data) < 4 or not data.startswith(b"\xff\xd8\xff") or not data.endswith(b"\xff\xd9"):
        return _json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_customer_photo"}, request_id, send_body)
    photo = _customer_photo_path(handler, customer_id, create=True)
    temporary = photo.with_name(f".{photo.name}.{request_id}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, photo)
    with handler.server.admin_software_service.database.session() as connection:
        connection.execute("BEGIN IMMEDIATE")
        handler.server.admin_service._audit(
            connection, session.admin_user_id, "customer_photo_updated",
            target_type="customer", target_id=customer_id, metadata={"bytes": len(data)},
        )
        connection.commit()
    return _json(handler, HTTPStatus.OK, {"saved": True}, request_id, send_body)


def _members(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "members.read")
    query = parse_qs(urlsplit(handler.path).query).get("q", [""])[0]
    rows = handler.server.admin_software_service.list_customers(query=query, person_type="member")
    if not _has_permission(session, "payments.read"):
        rows = [_without_customer_payment(item) for item in rows]
    return _json(handler, HTTPStatus.OK, {"members": rows}, request_id, send_body)


def _customers(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    if handler.command in {"GET", "HEAD"}:
        handler.server.admin_service.require_permission(session, "members.read")
        params = parse_qs(urlsplit(handler.path).query)
        rows = handler.server.admin_software_service.list_customers(
            query=params.get("q", [""])[0],
            customer_status=params.get("status", [""])[0],
            membership_status=params.get("membershipStatus", [""])[0],
            plan_id=params.get("planId", [""])[0],
            person_type=params.get("personType", [""])[0],
            limit=params.get("limit", ["200"])[0],
        )
        if not _has_permission(session, "payments.read"):
            rows = [_without_customer_payment(item) for item in rows]
        return _json(handler, HTTPStatus.OK, {"customers": rows}, request_id, send_body)
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    handler.server.admin_service.require_permission(session, "members.manage")
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    if str(payload.get("personType", "member")).strip().casefold() != "staff":
        handler.server.admin_service.require_permission(session, "memberships.manage")
        if payload.get("amountPaidPaise") not in (None, "", 0, "0"):
            handler.server.admin_service.require_permission(session, "payments.record")
    result = handler.server.admin_software_service.create_customer_bundle(
        payload, actor_admin_user_id=session.admin_user_id
    )
    return _json(handler, HTTPStatus.CREATED, result, request_id, send_body)


def _member_status(handler: Any, customer_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    status = str(payload.get("status", ""))
    member = handler.server.admin_service.set_customer_status(
        session,
        customer_id,
        status,
        request_id=request_id,
    )
    return _json(handler, HTTPStatus.OK, {"member": member}, request_id, send_body)


def _customer_detail(handler: Any, customer_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    if handler.command in {"GET", "HEAD"}:
        handler.server.admin_service.require_permission(session, "members.read")
        detail = handler.server.admin_software_service.customer_detail(customer_id)
        detail = _redact_customer_detail(
            detail,
            payments=_has_permission(session, "payments.read"),
            notifications=_has_permission(session, "notifications.manage"),
        )
        return _json(handler, HTTPStatus.OK, detail, request_id, send_body)
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    handler.server.admin_service.require_permission(session, "members.manage")
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    customer = handler.server.admin_software_service.update_customer(
        customer_id, payload, actor_admin_user_id=session.admin_user_id
    )
    return _json(handler, HTTPStatus.OK, {"customer": customer}, request_id, send_body)


def _customer_renew(handler: Any, customer_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "memberships.manage")
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    if payload.get("amountPaidPaise") not in (None, "", 0, "0"):
        handler.server.admin_service.require_permission(session, "payments.record")
    result = handler.server.admin_software_service.renew_membership(
        customer_id,
        payload,
        actor_admin_user_id=session.admin_user_id,
        idempotency_key=_idempotency_key(handler),
    )
    return _json(handler, HTTPStatus.CREATED, result, request_id, send_body)


def _memberships(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "members.read")
    params = parse_qs(urlsplit(handler.path).query)
    rows = handler.server.admin_software_service.list_memberships(
        status=params.get("status", [""])[0],
        plan_id=params.get("planId", [""])[0],
        limit=params.get("limit", ["300"])[0],
    )
    if not _has_permission(session, "payments.read"):
        rows = [
            {**item, "membership": _without_membership_payment(item.get("membership"))}
            if isinstance(item, dict) else item
            for item in rows
        ]
    return _json(handler, HTTPStatus.OK, {"memberships": rows}, request_id, send_body)


def _payments(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "payments.read")
    params = parse_qs(urlsplit(handler.path).query)
    rows = handler.server.admin_software_service.list_payments(
        customer_id=params.get("customerId", [None])[0],
        membership_id=params.get("membershipId", [None])[0],
        limit=params.get("limit", ["100"])[0],
    )
    return _json(handler, HTTPStatus.OK, {"payments": rows}, request_id, send_body)


def _record_membership_payment(handler: Any, membership_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "payments.record")
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    result = handler.server.admin_software_service.record_payment(
        membership_id,
        payload,
        actor_admin_user_id=session.admin_user_id,
        idempotency_key=_idempotency_key(handler),
    )
    return _json(handler, HTTPStatus.CREATED, result, request_id, send_body)


def _fees(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "payments.read")
    params = parse_qs(urlsplit(handler.path).query)
    pending_only = params.get("pendingOnly", ["0"])[0].strip().casefold() in {"1", "true", "yes"}
    result = handler.server.admin_software_service.fees(
        query=params.get("q", [""])[0],
        pending_only=pending_only,
        balance=params.get("balance", [""])[0],
        limit=params.get("limit", ["300"])[0],
    )
    return _json(handler, HTTPStatus.OK, result, request_id, send_body)


def _admins(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    if handler.command == "GET":
        admins = handler.server.admin_service.list_admins(session)
        return _json(handler, HTTPStatus.OK, {"admins": admins}, request_id, send_body)
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    result = handler.server.admin_service.create_admin(
        session,
        payload.get("username"),
        payload.get("password"),
        payload.get("role"),
    )
    return _json(
        handler,
        HTTPStatus.CREATED,
        {
            "admin": result.admin,
            "totpSecret": result.totp_secret,
            "otpauthUri": result.otpauth_uri,
            "recoveryCodes": list(result.recovery_codes),
        },
        request_id,
        send_body,
    )

def _admin_status(handler: Any, admin_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    admin = handler.server.admin_service.set_admin_status(
        session,
        admin_id,
        str(payload.get("status", "")),
        request_id=request_id,
    )
    return _json(handler, HTTPStatus.OK, {"admin": admin}, request_id, send_body)


def _audit(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    raw_limit = parse_qs(urlsplit(handler.path).query).get("limit", ["100"])[0]
    try:
        limit = int(raw_limit)
    except ValueError:
        limit = 100
    rows = handler.server.admin_service.audit_log(session, limit)
    return _json(handler, HTTPStatus.OK, {"audit": rows}, request_id, send_body)

def _readiness(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "system.readiness")
    return _json(handler, HTTPStatus.OK, {"readiness": handler.server.readiness_service.report()}, request_id, send_body)


def _biometric_devices(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    if handler.command in {"GET", "HEAD"}:
        handler.server.admin_service.require_permission(session, "attendance.view")
        return _json(handler, HTTPStatus.OK, {"devices": handler.server.biometric_service.list_devices()}, request_id, send_body)
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    handler.server.admin_service.require_permission(session, "biometric.manage")
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    return _json(
        handler,
        HTTPStatus.CREATED,
        handler.server.biometric_service.create_device(payload, actor_admin_user_id=session.admin_user_id),
        request_id,
        send_body,
    )


def _biometric_device_update(handler: Any, device_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "biometric.manage")
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    return _json(
        handler,
        HTTPStatus.OK,
        handler.server.biometric_service.update_device(device_id, payload, actor_admin_user_id=session.admin_user_id),
        request_id,
        send_body,
    )


def _biometric_device_test(handler: Any, device_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "biometric.manage")
    _require_csrf(handler, session)
    handler._require_empty_body()
    return _json(
        handler,
        HTTPStatus.OK,
        handler.server.biometric_service.test_connection(device_id, actor_admin_user_id=session.admin_user_id),
        request_id,
        send_body,
    )


def _biometric_device_sync(handler: Any, device_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "biometric.manage")
    _require_csrf(handler, session)
    handler._require_empty_body()
    return _json(
        handler,
        HTTPStatus.OK,
        handler.server.biometric_service.sync_device(device_id, actor_admin_user_id=session.admin_user_id),
        request_id,
        send_body,
    )


def _biometric_device_users(handler: Any, device_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "biometric.manage")
    params = parse_qs(urlsplit(handler.path).query)
    unmatched = params.get("unmatched", ["0"])[0].strip().casefold() in {"1", "true", "yes"}
    users = handler.server.biometric_service.list_device_users(
        device_id,
        unmatched_only=unmatched,
        query=params.get("q", [""])[0],
    )
    return _json(handler, HTTPStatus.OK, {"users": users}, request_id, send_body)


def _biometric_mappings(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    if handler.command in {"GET", "HEAD"}:
        handler.server.admin_service.require_permission(session, "attendance.view")
        params = parse_qs(urlsplit(handler.path).query)
        rows = handler.server.biometric_service.list_mappings(
            person_id=params.get("personId", [""])[0],
            device_id=params.get("deviceId", [""])[0],
        )
        return _json(handler, HTTPStatus.OK, {"mappings": rows}, request_id, send_body)
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    handler.server.admin_service.require_permission(session, "members.manage")
    handler.server.admin_service.require_permission(session, "biometric.manage")
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    return _json(
        handler,
        HTTPStatus.CREATED,
        handler.server.biometric_service.create_mapping(payload, actor_admin_user_id=session.admin_user_id),
        request_id,
        send_body,
    )


def _biometric_mapping_delete(handler: Any, mapping_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "members.manage")
    handler.server.admin_service.require_permission(session, "biometric.manage")
    _require_csrf(handler, session)
    handler._require_empty_body()
    return _json(
        handler,
        HTTPStatus.OK,
        handler.server.biometric_service.remove_mapping(mapping_id, actor_admin_user_id=session.admin_user_id),
        request_id,
        send_body,
    )


def _biometric_unmatched(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "attendance.view")
    params = parse_qs(urlsplit(handler.path).query)
    rows = handler.server.biometric_service.unmatched_activity(device_id=params.get("deviceId", [""])[0])
    return _json(handler, HTTPStatus.OK, {"unmatched": rows}, request_id, send_body)


def _attendance(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "attendance.view")
    params = parse_qs(urlsplit(handler.path).query)
    result = handler.server.biometric_service.list_attendance(
        start_date=params.get("date", params.get("startDate", [""]))[0],
        end_date=params.get("endDate", [""])[0],
        person_type=params.get("personType", [""])[0],
        query=params.get("q", [""])[0],
        membership_status=params.get("membershipStatus", [""])[0],
        limit=params.get("limit", ["200"])[0],
    )
    return _json(handler, HTTPStatus.OK, result, request_id, send_body)


def _attendance_stats(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "attendance.view")
    params = parse_qs(urlsplit(handler.path).query)
    stats = handler.server.biometric_service.attendance_stats(date=params.get("date", [""])[0])
    return _json(handler, HTTPStatus.OK, {"stats": stats}, request_id, send_body)


def _attendance_person(handler: Any, person_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "attendance.view")
    return _json(
        handler,
        HTTPStatus.OK,
        {"attendance": handler.server.biometric_service.person_attendance(person_id)},
        request_id,
        send_body,
    )


def _attendance_export(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "attendance.view")
    params = parse_qs(urlsplit(handler.path).query)
    result = handler.server.biometric_service.list_attendance(
        start_date=params.get("date", params.get("startDate", [""]))[0],
        end_date=params.get("endDate", [""])[0],
        person_type=params.get("personType", [""])[0],
        query=params.get("q", [""])[0],
        membership_status=params.get("membershipStatus", [""])[0],
        limit=params.get("limit", ["500"])[0],
    )
    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(["date", "name", "person_type", "membership_number", "first_scan", "last_scan", "scan_count", "verification", "membership_status"])
    for row in result["visits"]:
        writer.writerow([
            row.get("date", ""),
            row.get("displayName", ""),
            row.get("personType", ""),
            row.get("membershipNumber", ""),
            row.get("firstScanAt", ""),
            row.get("lastScanAt", ""),
            row.get("scanCount", ""),
            row.get("verificationSummary", ""),
            row.get("membershipStatus", ""),
        ])
    data = out.getvalue().encode("utf-8-sig")
    handler.send_response(HTTPStatus.OK)
    handler._security_headers(request_id)
    handler.send_header("Content-Type", "text/csv; charset=utf-8")
    handler.send_header("Content-Disposition", "attachment; filename=gravity-attendance.csv")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    if send_body:
        handler.wfile.write(data)
    return HTTPStatus.OK


def _biometric_simulate(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    if handler.server.settings.production:
        return _json(handler, HTTPStatus.NOT_FOUND, {"error": "not_found"}, request_id, send_body)
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "biometric.manage")
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    event = handler.server.biometric_service.record_event(
        str(payload.get("deviceId", "")),
        payload,
        source="mock",
    )
    return _json(handler, HTTPStatus.CREATED, event, request_id, send_body)


def handle_admin_request(handler: Any, path: str, request_id: str, send_body: bool) -> HTTPStatus | None:
    try:
        if path == "/api/admin/session" and handler.command in {"GET", "HEAD"}:
            return _session_status(handler, request_id, send_body)
        if path == "/api/admin/login" and handler.command == "POST":
            return _login(handler, request_id, send_body)
        if path == "/api/admin/verify" and handler.command == "POST":
            return _verify(handler, request_id, send_body)
        if path == "/api/admin/logout" and handler.command == "POST":
            return _logout(handler, request_id, send_body, all_sessions=False)
        if path == "/api/admin/logout-all" and handler.command == "POST":
            return _logout(handler, request_id, send_body, all_sessions=True)
        if path == "/api/admin/dashboard" and handler.command in {"GET", "HEAD"}:
            return _dashboard(handler, request_id, send_body)
        if path == "/api/admin/readiness" and handler.command in {"GET", "HEAD"}:
            return _readiness(handler, request_id, send_body)
        if path == "/api/admin/attendance" and handler.command in {"GET", "HEAD"}:
            return _attendance(handler, request_id, send_body)
        if path == "/api/admin/attendance/stats" and handler.command in {"GET", "HEAD"}:
            return _attendance_stats(handler, request_id, send_body)
        if path == "/api/admin/attendance/export" and handler.command in {"GET", "HEAD"}:
            return _attendance_export(handler, request_id, send_body)
        if path.startswith("/api/admin/attendance/person/") and handler.command in {"GET", "HEAD"}:
            person_id = path.removeprefix("/api/admin/attendance/person/").strip("/")
            if person_id and "/" not in person_id:
                return _attendance_person(handler, person_id, request_id, send_body)
        if path == "/api/admin/biometric/devices":
            if handler.command in {"GET", "HEAD", "POST"}:
                return _biometric_devices(handler, request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD", "POST"}, request_id, send_body)
        if path == "/api/admin/biometric/mappings":
            if handler.command in {"GET", "HEAD", "POST"}:
                return _biometric_mappings(handler, request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD", "POST"}, request_id, send_body)
        if path == "/api/admin/biometric/unmatched" and handler.command in {"GET", "HEAD"}:
            return _biometric_unmatched(handler, request_id, send_body)
        if path == "/api/admin/biometric/simulate" and handler.command == "POST":
            return _biometric_simulate(handler, request_id, send_body)
        if path.startswith("/api/admin/biometric/mappings/"):
            mapping_id = path.removeprefix("/api/admin/biometric/mappings/").strip("/")
            if mapping_id and "/" not in mapping_id:
                if handler.command == "DELETE":
                    return _biometric_mapping_delete(handler, mapping_id, request_id, send_body)
                return handler._method_not_allowed({"DELETE"}, request_id, send_body)
        if path.startswith("/api/admin/biometric/devices/") and path.endswith("/test"):
            device_id = path.removeprefix("/api/admin/biometric/devices/").removesuffix("/test").strip("/")
            if device_id and "/" not in device_id:
                if handler.command == "POST":
                    return _biometric_device_test(handler, device_id, request_id, send_body)
                return handler._method_not_allowed({"POST"}, request_id, send_body)
        if path.startswith("/api/admin/biometric/devices/") and path.endswith("/sync"):
            device_id = path.removeprefix("/api/admin/biometric/devices/").removesuffix("/sync").strip("/")
            if device_id and "/" not in device_id:
                if handler.command == "POST":
                    return _biometric_device_sync(handler, device_id, request_id, send_body)
                return handler._method_not_allowed({"POST"}, request_id, send_body)
        if path.startswith("/api/admin/biometric/devices/") and path.endswith("/users"):
            device_id = path.removeprefix("/api/admin/biometric/devices/").removesuffix("/users").strip("/")
            if device_id and "/" not in device_id:
                if handler.command in {"GET", "HEAD"}:
                    return _biometric_device_users(handler, device_id, request_id, send_body)
                return handler._method_not_allowed({"GET", "HEAD"}, request_id, send_body)
        if path.startswith("/api/admin/biometric/devices/"):
            device_id = path.removeprefix("/api/admin/biometric/devices/").strip("/")
            if device_id and "/" not in device_id:
                if handler.command == "PATCH":
                    return _biometric_device_update(handler, device_id, request_id, send_body)
                return handler._method_not_allowed({"PATCH"}, request_id, send_body)
        if path == "/api/admin/members" and handler.command in {"GET", "HEAD"}:
            return _members(handler, request_id, send_body)
        if path == "/api/admin/customers":
            if handler.command in {"GET", "HEAD", "POST"}:
                return _customers(handler, request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD", "POST"}, request_id, send_body)
        if path.startswith("/api/admin/customers/") and path.endswith("/photo"):
            customer_id = path.removeprefix("/api/admin/customers/").removesuffix("/photo").strip("/")
            if customer_id and "/" not in customer_id:
                if handler.command in {"GET", "HEAD", "POST"}:
                    return _customer_photo(handler, customer_id, request_id, send_body)
                return handler._method_not_allowed({"GET", "HEAD", "POST"}, request_id, send_body)
        if path.startswith("/api/admin/customers/") and path.endswith("/renew"):
            customer_id = path.removeprefix("/api/admin/customers/").removesuffix("/renew").strip("/")
            if customer_id and "/" not in customer_id:
                if handler.command == "POST":
                    return _customer_renew(handler, customer_id, request_id, send_body)
                return handler._method_not_allowed({"POST"}, request_id, send_body)
        if path.startswith("/api/admin/customers/"):
            customer_id = path.removeprefix("/api/admin/customers/").strip("/")
            if customer_id and "/" not in customer_id:
                if handler.command in {"GET", "HEAD", "PATCH"}:
                    return _customer_detail(handler, customer_id, request_id, send_body)
                return handler._method_not_allowed({"GET", "HEAD", "PATCH"}, request_id, send_body)
        if path == "/api/admin/memberships":
            if handler.command in {"GET", "HEAD"}:
                return _memberships(handler, request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD"}, request_id, send_body)
        if path == "/api/admin/payments":
            if handler.command in {"GET", "HEAD"}:
                return _payments(handler, request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD"}, request_id, send_body)
        if path == "/api/admin/fees":
            if handler.command in {"GET", "HEAD"}:
                return _fees(handler, request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD"}, request_id, send_body)
        if path.startswith("/api/admin/memberships/") and path.endswith("/payments"):
            membership_id = path.removeprefix("/api/admin/memberships/").removesuffix("/payments").strip("/")
            if membership_id and "/" not in membership_id:
                if handler.command == "POST":
                    return _record_membership_payment(handler, membership_id, request_id, send_body)
                return handler._method_not_allowed({"POST"}, request_id, send_body)
        if path == "/api/admin/membership/plans":
            if handler.command in {"GET", "HEAD", "POST"}:
                return _membership_plans(handler, request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD", "POST"}, request_id, send_body)
        if path.startswith("/api/admin/membership/plans/"):
            plan_id = path.removeprefix("/api/admin/membership/plans/").strip("/")
            if plan_id and "/" not in plan_id:
                if handler.command == "PATCH":
                    return _membership_plan_update(handler, plan_id, request_id, send_body)
                return handler._method_not_allowed({"PATCH"}, request_id, send_body)
        if path == "/api/admin/notifications":
            if handler.command in {"GET", "HEAD"}:
                return _notifications(handler, request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD"}, request_id, send_body)
        if path == "/api/admin/notifications/scan":
            if handler.command == "POST":
                return _notification_scan(handler, request_id, send_body)
            return handler._method_not_allowed({"POST"}, request_id, send_body)
        if path == "/api/admin/memberships/expiring":
            if handler.command in {"GET", "HEAD"}:
                return _expiring_memberships(handler, request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD"}, request_id, send_body)
        if path.startswith("/api/admin/memberships/") and path.endswith("/cancel"):
            membership_id = path.removeprefix("/api/admin/memberships/").removesuffix("/cancel").strip("/")
            if membership_id and "/" not in membership_id:
                if handler.command == "PATCH":
                    return _cancel_membership(handler, membership_id, request_id, send_body)
                return handler._method_not_allowed({"PATCH"}, request_id, send_body)
        if path.startswith("/api/admin/members/") and path.endswith("/memberships"):
            customer_id = path.removeprefix("/api/admin/members/").removesuffix("/memberships").strip("/")
            if customer_id and "/" not in customer_id:
                if handler.command in {"GET", "POST"}:
                    return _member_memberships(handler, customer_id, request_id, send_body)
                return handler._method_not_allowed({"GET", "POST"}, request_id, send_body)
        if path.startswith("/api/admin/members/") and handler.command == "PATCH":
            customer_id = path.removeprefix("/api/admin/members/")
            if customer_id and "/" not in customer_id:
                return _member_status(handler, customer_id, request_id, send_body)
        if path == "/api/admin/admins" and handler.command in {"GET", "POST"}:
            return _admins(handler, request_id, send_body)
        if path.startswith("/api/admin/admins/") and handler.command == "PATCH":
            admin_id = path.removeprefix("/api/admin/admins/")
            if admin_id and "/" not in admin_id:
                return _admin_status(handler, admin_id, request_id, send_body)
        if path == "/api/admin/audit" and handler.command in {"GET", "HEAD"}:
            return _audit(handler, request_id, send_body)
        if path.startswith("/api/admin/"):
            known = {
                "/api/admin/session": {"GET", "HEAD"},
                "/api/admin/login": {"POST"},
                "/api/admin/verify": {"POST"},
                "/api/admin/logout": {"POST"},
                "/api/admin/logout-all": {"POST"},
                "/api/admin/dashboard": {"GET", "HEAD"},
                "/api/admin/readiness": {"GET", "HEAD"},
                "/api/admin/attendance": {"GET", "HEAD"},
                "/api/admin/attendance/stats": {"GET", "HEAD"},
                "/api/admin/attendance/export": {"GET", "HEAD"},
                "/api/admin/members": {"GET", "HEAD"},
                "/api/admin/notifications": {"GET", "HEAD"},
                "/api/admin/notifications/scan": {"POST"},
                "/api/admin/admins": {"GET", "POST"},
                "/api/admin/audit": {"GET", "HEAD"},
            }
            if path in known:
                return handler._method_not_allowed(known[path], request_id, send_body)
        return None
    except (
        AdminUnavailable,
        AdminInvalidCredentials,
        AdminChallengeExpired,
        AdminInvalidSecondFactor,
        AdminSessionInvalid,
        AdminCsrfInvalid,
        AdminForbidden,
        AdminConflict,
        AdminValidationError,
        AdminRateLimitExceeded,
        AdminSoftwareNotFound,
        AdminSoftwareConflict,
        AdminSoftwareValidationError,
        MembershipNotFound,
        MembershipConflict,
        MembershipValidationError,
        NotificationNotFound,
        NotificationConflict,
        NotificationValidationError,
        BiometricNotFound,
        BiometricConflict,
        BiometricValidationError,
        BiometricAdapterError,
    ) as error:
        return _error_response(handler, error, request_id, send_body)

def _membership_plans(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    if handler.command in {"GET", "HEAD"}:
        handler.server.admin_service.require_permission(session, "members.read")
        plans = handler.server.membership_service.list_plans(active_only=False)
        return _json(handler, HTTPStatus.OK, {"plans": plans}, request_id, send_body)
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    handler.server.admin_service.require_permission(session, "membership_plans.manage")
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    plan = handler.server.membership_service.create_plan(payload, actor_admin_user_id=session.admin_user_id)
    return _json(handler, HTTPStatus.CREATED, {"plan": plan}, request_id, send_body)


def _membership_plan_update(handler: Any, plan_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "membership_plans.manage")
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    plan = handler.server.membership_service.update_plan(
        plan_id,
        payload,
        actor_admin_user_id=session.admin_user_id,
    )
    return _json(handler, HTTPStatus.OK, {"plan": plan}, request_id, send_body)


def _member_memberships(handler: Any, customer_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    if handler.command == "GET":
        handler.server.admin_service.require_permission(session, "members.read")
        rows = handler.server.membership_service.list_customer_memberships(customer_id)
        return _json(handler, HTTPStatus.OK, {"memberships": rows}, request_id, send_body)
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    handler.server.admin_service.require_permission(session, "memberships.manage")
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    membership = handler.server.membership_service.create_membership(
        customer_id,
        str(payload.get("planId", "")),
        actor_admin_user_id=session.admin_user_id,
        starts_at=payload.get("startsAt"),
        source="admin_manual",
    )
    return _json(handler, HTTPStatus.CREATED, {"membership": membership}, request_id, send_body)


def _cancel_membership(handler: Any, membership_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "memberships.manage")
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    membership = handler.server.membership_service.cancel_membership(
        membership_id,
        actor_admin_user_id=session.admin_user_id,
        reason=payload.get("reason"),
    )
    return _json(handler, HTTPStatus.OK, {"membership": membership}, request_id, send_body)


def _expiring_memberships(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "memberships.manage")
    raw_days = parse_qs(urlsplit(handler.path).query).get("days", ["7"])[0]
    try:
        days = int(raw_days)
    except ValueError:
        days = 7
    rows = handler.server.membership_service.expiring_within(days)
    return _json(handler, HTTPStatus.OK, {"memberships": rows}, request_id, send_body)

def _notifications(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "notifications.manage")
    raw_limit = parse_qs(urlsplit(handler.path).query).get("limit", ["100"])[0]
    try:
        limit = int(raw_limit)
    except ValueError:
        limit = 100
    rows = handler.server.notification_service.list_admin(limit)
    return _json(handler, HTTPStatus.OK, {"notifications": rows, "providerBlockers": handler.server.notification_service.provider_blockers()}, request_id, send_body)

def _notification_scan(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    handler.server.admin_service.require_permission(session, "notifications.manage")
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=ADMIN_JSON_LIMIT)
    result = handler.server.notification_service.scan_expiring(payload.get("daysBefore", 7))
    return _json(handler, HTTPStatus.OK, {"scan": result, "providerBlockers": handler.server.notification_service.provider_blockers()}, request_id, send_body)
