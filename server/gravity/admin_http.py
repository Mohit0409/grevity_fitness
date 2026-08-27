from __future__ import annotations

from email.utils import formatdate
from http import HTTPStatus
from urllib.parse import parse_qs, urlsplit
from typing import Any

from .membership import MembershipConflict, MembershipNotFound, MembershipValidationError
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
    return _json(
        handler,
        HTTPStatus.OK,
        {"challenge": True, "expiresAt": issue.expires_at},
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
    data = handler.server.admin_service.dashboard(session)
    return _json(handler, HTTPStatus.OK, data, request_id, send_body)

def _members(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return failure or HTTPStatus.UNAUTHORIZED
    query = parse_qs(urlsplit(handler.path).query).get("q", [""])[0]
    rows = handler.server.admin_service.list_customers(session, query)
    return _json(handler, HTTPStatus.OK, {"members": rows}, request_id, send_body)


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
        if path == "/api/admin/members" and handler.command in {"GET", "HEAD"}:
            return _members(handler, request_id, send_body)
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
                "/api/admin/members": {"GET", "HEAD"},
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
        MembershipNotFound,
        MembershipConflict,
        MembershipValidationError,
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
