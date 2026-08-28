from __future__ import annotations

from email.utils import formatdate
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .admin import (
    AdminCsrfInvalid,
    AdminForbidden,
    AdminSessionInvalid,
)
from .enquiry import (
    EnquiryConflict,
    EnquiryCsrfInvalid,
    EnquiryNotFound,
    EnquiryRateLimitExceeded,
    EnquiryValidationError,
)


ENQUIRY_JSON_LIMIT = 16_384


def _json(
    handler: Any,
    status: HTTPStatus,
    payload: dict[str, object],
    request_id: str,
    send_body: bool,
    *,
    headers: list[tuple[str, str]] | None = None,
) -> HTTPStatus:
    handler._json_response(
        status,
        payload,
        request_id=request_id,
        send_body=send_body,
        headers=headers,
    )
    return status


def _csrf_cookie_header(handler: Any, token: str, expires_at: int) -> tuple[str, str]:
    now = int(handler.server.enquiry_service.clock())
    attributes = (
        f"Path=/; Max-Age={max(0, expires_at - now)}; "
        f"Expires={formatdate(expires_at, usegmt=True)}; SameSite=Strict"
    )
    if handler.server.settings.production and not handler._local_loopback_request():
        attributes += "; Secure"
    return "Set-Cookie", f"{handler.server.settings.enquiry_csrf_cookie_name}={token}; {attributes}"


def _public_token(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    handler._require_empty_body()
    issue = handler.server.enquiry_service.issue_csrf()
    return _json(
        handler,
        HTTPStatus.OK,
        {"csrfToken": issue.token, "expiresAt": issue.expires_at},
        request_id,
        send_body,
        headers=[_csrf_cookie_header(handler, issue.token, issue.expires_at)],
    )


def _public_create(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    if not handler._same_origin():
        return _json(handler, HTTPStatus.FORBIDDEN, {"error": "invalid_origin"}, request_id, send_body)
    csrf_headers = handler.headers.get_all("X-Enquiry-CSRF-Token", [])
    if len(csrf_headers) != 1:
        raise EnquiryCsrfInvalid("Anonymous CSRF verification failed")
    handler.server.enquiry_service.verify_csrf(
        csrf_headers[0],
        handler._cookie_value(handler.server.settings.enquiry_csrf_cookie_name),
    )
    idempotency_headers = handler.headers.get_all("Idempotency-Key", [])
    if len(idempotency_headers) != 1:
        raise EnquiryValidationError({"request": "A valid idempotency key is required"})
    payload = handler._json_body(maximum=ENQUIRY_JSON_LIMIT)
    result, replayed = handler.server.enquiry_service.create(
        payload,
        idempotency_key=idempotency_headers[0],
        remote_addr=handler._client_ip(),
        request_id=request_id,
    )
    result["replayed"] = replayed
    return _json(handler, HTTPStatus.OK if replayed else HTTPStatus.CREATED, {"enquiry": result}, request_id, send_body)


def _admin_session(handler: Any):
    token = handler._cookie_value(handler.server.settings.admin_session_cookie_name)
    return handler.server.admin_service.resolve_session(token)


def _require_admin_mutation(handler: Any, session: Any) -> None:
    if not handler._same_origin():
        raise AdminCsrfInvalid("Administrator origin verification failed")
    values = handler.headers.get_all("X-CSRF-Token", [])
    if len(values) != 1:
        raise AdminCsrfInvalid("Administrator CSRF verification failed")
    cookie = handler._cookie_value(handler.server.settings.admin_csrf_cookie_name)
    handler.server.admin_service.verify_csrf(session, values[0], cookie)


def _admin_list(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session = _admin_session(handler)
    query = parse_qs(urlsplit(handler.path).query, keep_blank_values=True)
    try:
        limit = int(query.get("limit", ["100"])[0])
    except ValueError:
        limit = 100
    rows = handler.server.enquiry_service.list_admin(
        session,
        status=query.get("status", [""])[0].strip().casefold(),
        enquiry_type=query.get("type", [""])[0].strip().casefold(),
        query=query.get("q", [""])[0],
        limit=limit,
    )
    return _json(handler, HTTPStatus.OK, {"enquiries": rows}, request_id, send_body)


def _admin_detail(handler: Any, enquiry_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    session = _admin_session(handler)
    result = handler.server.enquiry_service.detail_admin(session, enquiry_id)
    return _json(handler, HTTPStatus.OK, {"enquiry": result}, request_id, send_body)


def _admin_status(handler: Any, enquiry_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    session = _admin_session(handler)
    _require_admin_mutation(handler, session)
    payload = handler._json_body(maximum=ENQUIRY_JSON_LIMIT)
    result = handler.server.enquiry_service.set_status(
        session, enquiry_id, payload.get("status"), request_id=request_id
    )
    return _json(handler, HTTPStatus.OK, {"enquiry": result}, request_id, send_body)


def _admin_note(handler: Any, enquiry_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    session = _admin_session(handler)
    _require_admin_mutation(handler, session)
    payload = handler._json_body(maximum=ENQUIRY_JSON_LIMIT)
    result = handler.server.enquiry_service.add_note(
        session, enquiry_id, payload.get("note"), request_id=request_id
    )
    return _json(handler, HTTPStatus.CREATED, {"enquiry": result}, request_id, send_body)


def _error_response(handler: Any, error: Exception, request_id: str, send_body: bool) -> HTTPStatus:
    if isinstance(error, EnquiryValidationError):
        return _json(
            handler,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            {"error": "enquiry_validation", "fields": error.fields},
            request_id,
            send_body,
        )
    if isinstance(error, EnquiryConflict):
        return _json(handler, HTTPStatus.CONFLICT, {"error": "enquiry_conflict"}, request_id, send_body)
    if isinstance(error, EnquiryNotFound):
        return _json(handler, HTTPStatus.NOT_FOUND, {"error": "enquiry_not_found"}, request_id, send_body)
    if isinstance(error, EnquiryRateLimitExceeded):
        return _json(
            handler,
            HTTPStatus.TOO_MANY_REQUESTS,
            {"error": "enquiry_rate_limited"},
            request_id,
            send_body,
            headers=[("Retry-After", str(error.retry_after))],
        )
    if isinstance(error, (EnquiryCsrfInvalid, AdminCsrfInvalid, AdminForbidden)):
        return _json(handler, HTTPStatus.FORBIDDEN, {"error": "forbidden"}, request_id, send_body)
    if isinstance(error, AdminSessionInvalid):
        return _json(handler, HTTPStatus.UNAUTHORIZED, {"error": "admin_unauthenticated"}, request_id, send_body)
    raise error


def handle_enquiry_request(
    handler: Any,
    path: str,
    request_id: str,
    send_body: bool,
) -> HTTPStatus | None:
    try:
        if path == "/api/enquiries/token":
            if handler.command in {"GET", "HEAD"}:
                return _public_token(handler, request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD"}, request_id, send_body)
        if path == "/api/enquiries":
            if handler.command == "POST":
                return _public_create(handler, request_id, send_body)
            return handler._method_not_allowed({"POST"}, request_id, send_body)
        if path == "/api/admin/enquiries":
            if handler.command in {"GET", "HEAD"}:
                return _admin_list(handler, request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD"}, request_id, send_body)
        prefix = "/api/admin/enquiries/"
        if path.startswith(prefix):
            suffix = path.removeprefix(prefix).strip("/")
            parts = suffix.split("/") if suffix else []
            if len(parts) == 1:
                if handler.command in {"GET", "HEAD"}:
                    return _admin_detail(handler, parts[0], request_id, send_body)
                return handler._method_not_allowed({"GET", "HEAD"}, request_id, send_body)
            if len(parts) == 2 and parts[1] == "status":
                if handler.command == "PATCH":
                    return _admin_status(handler, parts[0], request_id, send_body)
                return handler._method_not_allowed({"PATCH"}, request_id, send_body)
            if len(parts) == 2 and parts[1] == "notes":
                if handler.command == "POST":
                    return _admin_note(handler, parts[0], request_id, send_body)
                return handler._method_not_allowed({"POST"}, request_id, send_body)
        return None
    except (
        EnquiryValidationError,
        EnquiryConflict,
        EnquiryNotFound,
        EnquiryRateLimitExceeded,
        EnquiryCsrfInvalid,
        AdminSessionInvalid,
        AdminCsrfInvalid,
        AdminForbidden,
    ) as error:
        return _error_response(handler, error, request_id, send_body)
