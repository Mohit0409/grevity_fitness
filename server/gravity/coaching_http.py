from __future__ import annotations

from http import HTTPStatus
from typing import Any

from .admin import AdminCsrfInvalid, AdminForbidden
from .admin_http import _authenticated, _error_response, _json, _require_csrf, _same_origin
from .coaching import CoachingConflict, CoachingNotFound, CoachingValidationError


COACHING_JSON_LIMIT = 32_768


def _coaching_error(handler: Any, error: Exception, request_id: str, send_body: bool) -> HTTPStatus:
    if isinstance(error, CoachingNotFound):
        return _json(handler, HTTPStatus.NOT_FOUND, {"error": "coaching_not_found"}, request_id, send_body)
    if isinstance(error, CoachingConflict):
        return _json(handler, HTTPStatus.CONFLICT, {"error": "coaching_conflict"}, request_id, send_body)
    if isinstance(error, CoachingValidationError):
        return _json(
            handler, HTTPStatus.UNPROCESSABLE_ENTITY,
            {"error": "coaching_validation", "fields": error.fields},
            request_id, send_body,
        )
    if isinstance(error, (AdminCsrfInvalid, AdminForbidden)):
        return _error_response(handler, error, request_id, send_body)
    raise error


def _customer_summary(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = handler._require_session(request_id, send_body)
    if session is None:
        return failure
    summary = handler.server.coaching_service.customer_summary(session.customer_id)
    return _json(handler, HTTPStatus.OK, {"coaching": summary}, request_id, send_body)


def _admin_session(
    handler: Any,
    permission: str,
    request_id: str,
    send_body: bool,
    *,
    mutation: bool = False,
):
    if mutation:
        origin_failure = _same_origin(handler, request_id, send_body)
        if origin_failure is not None:
            return None, origin_failure
    session, failure = _authenticated(handler, request_id, send_body)
    if session is None:
        return None, failure
    handler.server.admin_service.require_permission(session, permission)
    if mutation:
        _require_csrf(handler, session)
    return session, None


def _member_summary(handler: Any, customer_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _admin_session(handler, "progress.manage", request_id, send_body)
    if session is None:
        return failure
    handler.server.admin_service.require_permission(session, "diet.manage")
    summary = handler.server.coaching_service.customer_summary(customer_id)
    return _json(handler, HTTPStatus.OK, {"coaching": summary}, request_id, send_body)


def _measurement(handler: Any, customer_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _admin_session(
        handler, "progress.manage", request_id, send_body, mutation=True,
    )
    if session is None:
        return failure
    payload = handler._json_body(maximum=COACHING_JSON_LIMIT)
    item = handler.server.coaching_service.add_measurement(
        customer_id,
        str(payload.get("metricKey", "")),
        payload.get("value"),
        measured_at=payload.get("measuredAt"),
        actor_admin_user_id=session.admin["id"],
    )
    return _json(handler, HTTPStatus.CREATED, {"measurement": item}, request_id, send_body)


def _goal(handler: Any, customer_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _admin_session(
        handler, "progress.manage", request_id, send_body, mutation=True,
    )
    if session is None:
        return failure
    payload = handler._json_body(maximum=COACHING_JSON_LIMIT)
    item = handler.server.coaching_service.set_goal(
        customer_id,
        str(payload.get("metricKey", "")),
        payload.get("targetValue"),
        target_at=payload.get("targetAt"),
        actor_admin_user_id=session.admin["id"],
    )
    return _json(handler, HTTPStatus.CREATED, {"goal": item}, request_id, send_body)


def _complete_goal(
    handler: Any, customer_id: str, goal_id: str, request_id: str, send_body: bool,
) -> HTTPStatus:
    session, failure = _admin_session(
        handler, "progress.manage", request_id, send_body, mutation=True,
    )
    if session is None:
        return failure
    handler._require_empty_body()
    item = handler.server.coaching_service.complete_goal(
        customer_id, goal_id, actor_admin_user_id=session.admin["id"],
    )
    return _json(handler, HTTPStatus.OK, {"goal": item}, request_id, send_body)


def _diet_templates(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _admin_session(handler, "diet.manage", request_id, send_body)
    if session is None:
        return failure
    if handler.command in {"GET", "HEAD"}:
        rows = handler.server.coaching_service.list_diet_templates()
        return _json(handler, HTTPStatus.OK, {"templates": rows}, request_id, send_body)
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=COACHING_JSON_LIMIT)
    item = handler.server.coaching_service.create_diet_template(
        payload.get("code"), payload.get("name"), payload.get("description"),
        actor_admin_user_id=session.admin["id"],
    )
    return _json(handler, HTTPStatus.CREATED, {"template": item}, request_id, send_body)


def _diet_template_status(
    handler: Any, template_id: str, request_id: str, send_body: bool,
) -> HTTPStatus:
    session, failure = _admin_session(
        handler, "diet.manage", request_id, send_body, mutation=True,
    )
    if session is None:
        return failure
    payload = handler._json_body(maximum=COACHING_JSON_LIMIT)
    item = handler.server.coaching_service.set_template_status(
        template_id, str(payload.get("status", "")), actor_admin_user_id=session.admin["id"],
    )
    return _json(handler, HTTPStatus.OK, {"template": item}, request_id, send_body)


def _diet_versions(
    handler: Any, template_id: str, request_id: str, send_body: bool,
) -> HTTPStatus:
    session, failure = _admin_session(handler, "diet.manage", request_id, send_body)
    if session is None:
        return failure
    if handler.command in {"GET", "HEAD"}:
        rows = handler.server.coaching_service.list_diet_versions(template_id)
        return _json(handler, HTTPStatus.OK, {"versions": rows}, request_id, send_body)
    origin_failure = _same_origin(handler, request_id, send_body)
    if origin_failure is not None:
        return origin_failure
    _require_csrf(handler, session)
    payload = handler._json_body(maximum=COACHING_JSON_LIMIT)
    item = handler.server.coaching_service.create_diet_version(
        template_id, payload.get("title"), payload.get("content"),
        actor_admin_user_id=session.admin["id"],
    )
    return _json(handler, HTTPStatus.CREATED, {"version": item}, request_id, send_body)


def _assign_diet(handler: Any, customer_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _admin_session(
        handler, "diet.manage", request_id, send_body, mutation=True,
    )
    if session is None:
        return failure
    payload = handler._json_body(maximum=COACHING_JSON_LIMIT)
    item = handler.server.coaching_service.assign_diet(
        customer_id, str(payload.get("versionId", "")), note=payload.get("note"),
        actor_admin_user_id=session.admin["id"],
    )
    return _json(handler, HTTPStatus.CREATED, {"assignment": item}, request_id, send_body)


def _end_diet(
    handler: Any, customer_id: str, assignment_id: str, request_id: str, send_body: bool,
) -> HTTPStatus:
    session, failure = _admin_session(
        handler, "diet.manage", request_id, send_body, mutation=True,
    )
    if session is None:
        return failure
    handler._require_empty_body()
    item = handler.server.coaching_service.end_diet_assignment(
        customer_id, assignment_id, actor_admin_user_id=session.admin["id"],
    )
    return _json(handler, HTTPStatus.OK, {"assignment": item}, request_id, send_body)


def handle_coaching_request(
    handler: Any, path: str, request_id: str, send_body: bool,
) -> HTTPStatus | None:
    try:
        if path == "/api/me/coaching":
            if handler.command in {"GET", "HEAD"}:
                return _customer_summary(handler, request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD"}, request_id, send_body)
        if path == "/api/admin/coaching/diets":
            if handler.command in {"GET", "HEAD", "POST"}:
                return _diet_templates(handler, request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD", "POST"}, request_id, send_body)
        if path.startswith("/api/admin/coaching/diets/"):
            suffix = path.removeprefix("/api/admin/coaching/diets/").strip("/")
            if suffix.endswith("/versions"):
                template_id = suffix.removesuffix("/versions").strip("/")
                if template_id and "/" not in template_id:
                    if handler.command in {"GET", "HEAD", "POST"}:
                        return _diet_versions(handler, template_id, request_id, send_body)
                    return handler._method_not_allowed({"GET", "HEAD", "POST"}, request_id, send_body)
            if suffix and "/" not in suffix:
                if handler.command == "PATCH":
                    return _diet_template_status(handler, suffix, request_id, send_body)
                return handler._method_not_allowed({"PATCH"}, request_id, send_body)
        prefix = "/api/admin/coaching/members/"
        if path.startswith(prefix):
            suffix = path.removeprefix(prefix).strip("/")
            parts = suffix.split("/") if suffix else []
            if len(parts) == 1 and handler.command in {"GET", "HEAD"}:
                return _member_summary(handler, parts[0], request_id, send_body)
            if len(parts) == 2 and parts[1] == "measurements" and handler.command == "POST":
                return _measurement(handler, parts[0], request_id, send_body)
            if len(parts) == 2 and parts[1] == "goals" and handler.command == "POST":
                return _goal(handler, parts[0], request_id, send_body)
            if len(parts) == 4 and parts[1] == "goals" and parts[3] == "complete" and handler.command == "POST":
                return _complete_goal(handler, parts[0], parts[2], request_id, send_body)
            if len(parts) == 2 and parts[1] == "diet" and handler.command == "POST":
                return _assign_diet(handler, parts[0], request_id, send_body)
            if len(parts) == 4 and parts[1] == "diet" and parts[3] == "end" and handler.command == "POST":
                return _end_diet(handler, parts[0], parts[2], request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD", "POST"}, request_id, send_body)
        return None
    except (CoachingNotFound, CoachingConflict, CoachingValidationError, AdminCsrfInvalid, AdminForbidden) as error:
        return _coaching_error(handler, error, request_id, send_body)
