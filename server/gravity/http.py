from __future__ import annotations

from email.utils import formatdate
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address, ip_network
from pathlib import Path
from time import perf_counter
from typing import Callable
from urllib.parse import unquote, urlsplit
from uuid import uuid4
import json
import logging
import mimetypes

from .auth import (
    AccountDisabled,
    AuthService,
    AuthenticationError,
    AuthenticationUnavailable,
    IdentityConflict,
    InvalidCsrf,
    InvalidSession,
    ProfileValidationError,
    RateLimitExceeded,
    SessionIdentity,
    SessionIssue,
)
from .config import Settings
from .database import Database
from .firebase_auth import (
    FirebaseAccountDisabled,
    FirebaseAdminVerifier,
    FirebaseIdentityUnverified,
    FirebaseUnavailable,
    IdentityVerifier,
    InvalidFirebaseToken,
)


LOGGER = logging.getLogger("gravity.http")
PUBLIC_PREFIXES = {"assets", "css", "js", "pages"}
STATIC_ROUTE_ALIASES = {
    "/account": "pages/account.html",
    "/trainers": "pages/trainers.html",
    "/gallery": "pages/gallery.html",
}
SENSITIVE_QUERY_KEYS = {"access_token", "code", "id_token", "session", "token"}
MAX_REQUEST_BODY = 1_048_576
MAX_PROFILE_BODY = 16_384
AUTH_ROUTES: dict[str, set[str]] = {
    "/api/auth/config": {"GET", "HEAD"},
    "/api/auth/session": {"GET", "HEAD", "POST"},
    "/api/auth/logout": {"POST"},
    "/api/auth/logout-all": {"POST"},
    "/api/auth/link": {"POST"},
    "/api/me": {"GET", "HEAD", "PATCH"},
}


def _safe_path_for_log(raw_path: str) -> str:
    parsed = urlsplit(raw_path)
    if not parsed.query:
        return parsed.path
    pairs = []
    for part in parsed.query.split("&"):
        key, _separator, _value = part.partition("=")
        pairs.append(f"{key}=[REDACTED]" if key.lower() in SENSITIVE_QUERY_KEYS else part)
    return parsed.path + "?" + "&".join(pairs)


class GravityHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        settings: Settings,
        database: Database,
        auth_service: AuthService,
    ) -> None:
        super().__init__(address, handler)
        self.settings = settings
        self.database = database
        self.auth_service = auth_service


class GravityRequestHandler(BaseHTTPRequestHandler):
    server: GravityHTTPServer
    server_version = "GravityFitness"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(15)

    def version_string(self) -> str:
        return "GravityFitness"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        self._dispatch(send_body=True)

    def do_HEAD(self) -> None:
        self._dispatch(send_body=False)

    def do_POST(self) -> None:
        self._dispatch(send_body=True)

    def do_PATCH(self) -> None:
        self._dispatch(send_body=True)

    def do_PUT(self) -> None:
        self._dispatch(send_body=True)

    def do_DELETE(self) -> None:
        self._dispatch(send_body=True)

    def _dispatch(self, *, send_body: bool) -> None:
        started = perf_counter()
        request_id = uuid4().hex
        status: int | HTTPStatus = HTTPStatus.INTERNAL_SERVER_ERROR
        try:
            if self.command not in {"GET", "HEAD"}:
                try:
                    declared_length = self._content_length()
                    if declared_length > MAX_REQUEST_BODY:
                        self._drain_body(min(declared_length, MAX_REQUEST_BODY + 1))
                        status = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
                        self._json_response(
                            status,
                            {"error": "request_too_large"},
                            request_id=request_id,
                            send_body=send_body,
                        )
                        return
                except RequestError as error:
                    status = error.status
                    self._json_response(status, {"error": error.code}, request_id=request_id, send_body=send_body)
                    return
            path = urlsplit(self.path).path
            if path == "/api/health":
                if self.command not in {"GET", "HEAD"}:
                    status = self._method_not_allowed({"GET", "HEAD"}, request_id, send_body)
                    return
                health = self.server.database.health()
                healthy = health["database"] == "ok"
                status = HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE
                self._json_response(
                    status,
                    {
                        "status": "ok" if healthy else "error",
                        "service": "Gravity Fitness",
                        "database": health["database"],
                    },
                    request_id=request_id,
                    send_body=send_body,
                )
                return
            if path in AUTH_ROUTES:
                if self.command not in AUTH_ROUTES[path]:
                    status = self._method_not_allowed(AUTH_ROUTES[path], request_id, send_body)
                    return
                status = self._auth_response(path, request_id=request_id, send_body=send_body)
                return
            if path.startswith("/api/") or path == "/admin" or path.startswith("/admin/"):
                status = HTTPStatus.NOT_FOUND
                self._json_response(status, {"error": "not_found"}, request_id=request_id, send_body=send_body)
                return
            if self.command not in {"GET", "HEAD"}:
                status = self._discard_bounded_body(request_id=request_id, send_body=send_body)
                return
            status = self._static_response(path, request_id=request_id, send_body=send_body)
        except (BrokenPipeError, ConnectionResetError):
            status = 499
        except Exception:
            LOGGER.exception("request_failed", extra={"event_data": {"request_id": request_id}})
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            self._json_response(status, {"error": "internal_error"}, request_id=request_id, send_body=send_body)
        finally:
            if self.command not in {"GET", "HEAD"}:
                self.close_connection = True
            LOGGER.info(
                "request_completed",
                extra={
                    "event_data": {
                        "request_id": request_id,
                        "method": self.command,
                        "path": _safe_path_for_log(self.path),
                        "status": int(status),
                        "duration_ms": round((perf_counter() - started) * 1000, 2),
                    }
                },
            )

    def _auth_response(self, path: str, *, request_id: str, send_body: bool) -> HTTPStatus:
        if path == "/api/auth/config":
            return self._auth_config(request_id, send_body)
        if path == "/api/auth/session" and self.command in {"GET", "HEAD"}:
            return self._session_status(request_id, send_body)
        if path == "/api/auth/session" and self.command == "POST":
            return self._exchange_session(request_id, send_body)
        if path == "/api/me" and self.command in {"GET", "HEAD"}:
            session, failure_status = self._require_session(request_id, send_body)
            if not session:
                return failure_status
            self._json_response(
                HTTPStatus.OK,
                {"user": session.user},
                request_id=request_id,
                send_body=send_body,
            )
            return HTTPStatus.OK
        if path == "/api/me" and self.command == "PATCH":
            return self._update_profile(request_id, send_body)
        if path in {"/api/auth/logout", "/api/auth/logout-all"}:
            return self._logout(request_id, send_body, all_sessions=path.endswith("logout-all"))
        if path == "/api/auth/link":
            return self._link_identity(request_id, send_body)
        self._json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"}, request_id=request_id)
        return HTTPStatus.NOT_FOUND

    def _auth_config(self, request_id: str, send_body: bool) -> HTTPStatus:
        settings = self.server.settings
        enabled = settings.firebase_client_configured and self.server.auth_service.configured
        payload: dict[str, object] = {"enabled": enabled}
        if enabled:
            payload["firebase"] = {
                "apiKey": settings.firebase_web_api_key,
                "authDomain": settings.firebase_auth_domain,
                "projectId": settings.firebase_project_id,
                "appId": settings.firebase_app_id,
            }
            payload["providers"] = ["password", "google.com", "phone"]
        self._json_response(HTTPStatus.OK, payload, request_id=request_id, send_body=send_body)
        return HTTPStatus.OK

    def _session_status(self, request_id: str, send_body: bool) -> HTTPStatus:
        try:
            token = self._cookie_value(self.server.settings.session_cookie_name)
            session = self.server.auth_service.resolve_session(token)
            payload: dict[str, object] = {"authenticated": True, "user": session.user}
        except (InvalidSession, AccountDisabled):
            payload = {"authenticated": False}
        except RequestError as error:
            self._json_response(error.status, {"error": error.code}, request_id=request_id, send_body=send_body)
            return error.status
        self._json_response(HTTPStatus.OK, payload, request_id=request_id, send_body=send_body)
        return HTTPStatus.OK

    def _exchange_session(self, request_id: str, send_body: bool) -> HTTPStatus:
        if not self._same_origin():
            self._json_response(HTTPStatus.FORBIDDEN, {"error": "invalid_origin"}, request_id=request_id)
            return HTTPStatus.FORBIDDEN
        try:
            self._require_empty_body()
            id_token = self._bearer_token()
            issue = self.server.auth_service.exchange(
                id_token,
                remote_addr=self._client_ip(),
                user_agent=self.headers.get("User-Agent", "")[:1000],
                request_id=request_id,
                prior_session_token=self._cookie_value(self.server.settings.session_cookie_name),
            )
        except RateLimitExceeded as error:
            self._json_response(
                HTTPStatus.TOO_MANY_REQUESTS,
                {"error": "rate_limited"},
                request_id=request_id,
                headers=[("Retry-After", str(error.retry_after))],
            )
            return HTTPStatus.TOO_MANY_REQUESTS
        except (AuthenticationUnavailable, FirebaseUnavailable):
            self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "authentication_unavailable"},
                request_id=request_id,
            )
            return HTTPStatus.SERVICE_UNAVAILABLE
        except (FirebaseAccountDisabled, AccountDisabled):
            self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "account_disabled"},
                request_id=request_id,
            )
            return HTTPStatus.FORBIDDEN
        except IdentityConflict:
            self._json_response(
                HTTPStatus.CONFLICT,
                {"error": "account_link_required"},
                request_id=request_id,
            )
            return HTTPStatus.CONFLICT
        except (InvalidFirebaseToken, FirebaseIdentityUnverified, AuthenticationError, ValueError):
            self._json_response(
                HTTPStatus.UNAUTHORIZED,
                {"error": "invalid_credentials"},
                request_id=request_id,
            )
            return HTTPStatus.UNAUTHORIZED
        except RequestError as error:
            self._json_response(error.status, {"error": error.code}, request_id=request_id)
            return error.status
        self._json_response(
            HTTPStatus.OK,
            {"authenticated": True, "user": issue.user, "csrfToken": issue.csrf_token},
            request_id=request_id,
            send_body=send_body,
            headers=self._auth_cookie_headers(issue),
        )
        return HTTPStatus.OK

    def _update_profile(self, request_id: str, send_body: bool) -> HTTPStatus:
        if not self._same_origin():
            self._json_response(HTTPStatus.FORBIDDEN, {"error": "invalid_origin"}, request_id=request_id)
            return HTTPStatus.FORBIDDEN
        session, failure_status = self._require_session(request_id, send_body)
        if not session:
            return failure_status
        try:
            self._require_csrf(session)
            payload = self._json_body(maximum=MAX_PROFILE_BODY)
            user = self.server.auth_service.update_profile(session, payload, request_id=request_id)
        except InvalidCsrf:
            self._json_response(HTTPStatus.FORBIDDEN, {"error": "invalid_csrf"}, request_id=request_id)
            return HTTPStatus.FORBIDDEN
        except ProfileValidationError as error:
            self._json_response(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "invalid_profile", "fields": error.fields},
                request_id=request_id,
            )
            return HTTPStatus.UNPROCESSABLE_ENTITY
        except AccountDisabled:
            self._json_response(HTTPStatus.FORBIDDEN, {"error": "account_disabled"}, request_id=request_id)
            return HTTPStatus.FORBIDDEN
        except RequestError as error:
            self._json_response(error.status, {"error": error.code}, request_id=request_id)
            return error.status
        self._json_response(HTTPStatus.OK, {"user": user}, request_id=request_id, send_body=send_body)
        return HTTPStatus.OK

    def _link_identity(self, request_id: str, send_body: bool) -> HTTPStatus:
        if not self._same_origin():
            self._json_response(HTTPStatus.FORBIDDEN, {"error": "invalid_origin"}, request_id=request_id)
            return HTTPStatus.FORBIDDEN
        session, failure_status = self._require_session(request_id, send_body)
        if not session:
            return failure_status
        try:
            self._require_empty_body()
            self._require_csrf(session)
            id_token = self._bearer_token()
            current_token = self._cookie_value(self.server.settings.session_cookie_name)
            if not current_token:
                raise InvalidSession("Session is missing")
            issue = self.server.auth_service.link_identity(
                session,
                id_token,
                current_session_token=current_token,
                remote_addr=self._client_ip(),
                user_agent=self.headers.get("User-Agent", "")[:1000],
                request_id=request_id,
            )
        except RateLimitExceeded as error:
            self._json_response(
                HTTPStatus.TOO_MANY_REQUESTS,
                {"error": "rate_limited"},
                request_id=request_id,
                headers=[("Retry-After", str(error.retry_after))],
            )
            return HTTPStatus.TOO_MANY_REQUESTS
        except InvalidCsrf:
            self._json_response(HTTPStatus.FORBIDDEN, {"error": "invalid_csrf"}, request_id=request_id)
            return HTTPStatus.FORBIDDEN
        except (AuthenticationUnavailable, FirebaseUnavailable):
            self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "authentication_unavailable"},
                request_id=request_id,
            )
            return HTTPStatus.SERVICE_UNAVAILABLE
        except (FirebaseAccountDisabled, AccountDisabled):
            self._json_response(HTTPStatus.FORBIDDEN, {"error": "account_disabled"}, request_id=request_id)
            return HTTPStatus.FORBIDDEN
        except IdentityConflict:
            self._json_response(HTTPStatus.CONFLICT, {"error": "account_conflict"}, request_id=request_id)
            return HTTPStatus.CONFLICT
        except (InvalidFirebaseToken, FirebaseIdentityUnverified, AuthenticationError, ValueError):
            self._json_response(HTTPStatus.UNAUTHORIZED, {"error": "invalid_credentials"}, request_id=request_id)
            return HTTPStatus.UNAUTHORIZED
        except RequestError as error:
            self._json_response(error.status, {"error": error.code}, request_id=request_id)
            return error.status
        self._json_response(
            HTTPStatus.OK,
            {"authenticated": True, "user": issue.user, "csrfToken": issue.csrf_token},
            request_id=request_id,
            send_body=send_body,
            headers=self._auth_cookie_headers(issue),
        )
        return HTTPStatus.OK

    def _logout(self, request_id: str, send_body: bool, *, all_sessions: bool) -> HTTPStatus:
        if not self._same_origin():
            self._json_response(HTTPStatus.FORBIDDEN, {"error": "invalid_origin"}, request_id=request_id)
            return HTTPStatus.FORBIDDEN
        session, failure_status = self._require_session(request_id, send_body)
        if not session:
            return failure_status
        try:
            self._require_empty_body()
            self._require_csrf(session)
            self.server.auth_service.logout(session, request_id=request_id, all_sessions=all_sessions)
        except InvalidCsrf:
            self._json_response(HTTPStatus.FORBIDDEN, {"error": "invalid_csrf"}, request_id=request_id)
            return HTTPStatus.FORBIDDEN
        except RequestError as error:
            self._json_response(error.status, {"error": error.code}, request_id=request_id)
            return error.status
        self._json_response(
            HTTPStatus.OK,
            {"authenticated": False},
            request_id=request_id,
            send_body=send_body,
            headers=self._clear_auth_cookie_headers(),
        )
        return HTTPStatus.OK

    def _require_session(
        self, request_id: str, send_body: bool
    ) -> tuple[SessionIdentity | None, HTTPStatus]:
        try:
            token = self._cookie_value(self.server.settings.session_cookie_name)
            return self.server.auth_service.resolve_session(token), HTTPStatus.OK
        except AccountDisabled:
            self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "account_disabled"},
                request_id=request_id,
                send_body=send_body,
                headers=self._clear_auth_cookie_headers(),
            )
            return None, HTTPStatus.FORBIDDEN
        except InvalidSession:
            self._json_response(
                HTTPStatus.UNAUTHORIZED,
                {"error": "unauthenticated"},
                request_id=request_id,
                send_body=send_body,
                headers=self._clear_auth_cookie_headers(),
            )
            return None, HTTPStatus.UNAUTHORIZED
        except RequestError as error:
            self._json_response(
                error.status,
                {"error": error.code},
                request_id=request_id,
                send_body=send_body,
                headers=self._clear_auth_cookie_headers(),
            )
            return None, error.status

    def _require_csrf(self, session: SessionIdentity) -> None:
        header_values = self.headers.get_all("X-CSRF-Token", [])
        if len(header_values) != 1:
            raise InvalidCsrf("CSRF header is invalid")
        cookie_token = self._cookie_value(self.server.settings.csrf_cookie_name)
        self.server.auth_service.verify_csrf(session, header_values[0], cookie_token)

    def _same_origin(self) -> bool:
        origins = self.headers.get_all("Origin", [])
        if len(origins) != 1:
            return False
        expected = urlsplit(self.server.settings.app_base_url)
        actual = urlsplit(origins[0])
        return (
            actual.scheme in {"http", "https"}
            and actual.scheme == expected.scheme
            and actual.netloc == expected.netloc
            and not actual.path
            and not actual.query
            and not actual.fragment
        )

    def _bearer_token(self) -> str:
        values = self.headers.get_all("Authorization", [])
        if len(values) != 1 or len(values[0]) > 16_391 or not values[0].startswith("Bearer "):
            raise RequestError(HTTPStatus.UNAUTHORIZED, "invalid_credentials")
        token = values[0][7:]
        if not token or token != token.strip() or any(character.isspace() for character in token):
            raise RequestError(HTTPStatus.UNAUTHORIZED, "invalid_credentials")
        return token

    def _cookie_value(self, name: str) -> str | None:
        raw_values = self.headers.get_all("Cookie", [])
        if not raw_values:
            return None
        if len(raw_values) != 1 or len(raw_values[0]) > 8192:
            raise RequestError(HTTPStatus.BAD_REQUEST, "invalid_request")
        names = []
        for part in raw_values[0].split(";"):
            key, separator, _value = part.strip().partition("=")
            if separator:
                names.append(key)
        if len(names) != len(set(names)):
            raise RequestError(HTTPStatus.BAD_REQUEST, "invalid_request")
        cookie = SimpleCookie()
        try:
            cookie.load(raw_values[0])
        except Exception as error:
            raise RequestError(HTTPStatus.BAD_REQUEST, "invalid_request") from error
        morsel = cookie.get(name)
        return morsel.value if morsel else None

    def _client_ip(self) -> str:
        peer = ip_address(self.client_address[0])
        trusted = self.server.settings.trust_proxy and any(
            peer in ip_network(cidr, strict=False) for cidr in self.server.settings.trusted_proxy_cidrs
        )
        if trusted:
            forwarded_values = self.headers.get_all("X-Forwarded-For", [])
            if len(forwarded_values) == 1:
                first = forwarded_values[0].split(",", 1)[0].strip()
                try:
                    return ip_address(first).compressed
                except ValueError:
                    pass
        return peer.compressed

    def _require_empty_body(self) -> None:
        if self.headers.get("Transfer-Encoding"):
            raise RequestError(HTTPStatus.BAD_REQUEST, "invalid_request")
        length = self._content_length()
        if length:
            if length > MAX_REQUEST_BODY:
                self._drain_body(min(length, MAX_REQUEST_BODY + 1))
                raise RequestError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request_too_large")
            self._drain_body(length)
            raise RequestError(HTTPStatus.BAD_REQUEST, "invalid_request")

    def _json_body(self, *, maximum: int) -> dict[str, object]:
        if self.headers.get("Transfer-Encoding"):
            raise RequestError(HTTPStatus.BAD_REQUEST, "invalid_request")
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise RequestError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "unsupported_media_type")
        length = self._content_length()
        if length <= 0:
            raise RequestError(HTTPStatus.BAD_REQUEST, "invalid_request")
        if length > maximum:
            raise RequestError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request_too_large")
        try:
            payload = json.loads(self.rfile.read(length))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise RequestError(HTTPStatus.BAD_REQUEST, "invalid_json") from error
        if not isinstance(payload, dict):
            raise RequestError(HTTPStatus.BAD_REQUEST, "invalid_json")
        return payload

    def _content_length(self) -> int:
        values = self.headers.get_all("Content-Length", [])
        if not values:
            return 0
        if len(values) != 1:
            raise RequestError(HTTPStatus.BAD_REQUEST, "invalid_request")
        try:
            length = int(values[0])
        except ValueError as error:
            raise RequestError(HTTPStatus.BAD_REQUEST, "invalid_request") from error
        if length < 0:
            raise RequestError(HTTPStatus.BAD_REQUEST, "invalid_request")
        return length

    def _discard_bounded_body(self, *, request_id: str, send_body: bool) -> HTTPStatus:
        try:
            length = self._content_length()
            if length > MAX_REQUEST_BODY:
                self._drain_body(min(length, MAX_REQUEST_BODY + 1))
                self._json_response(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    {"error": "request_too_large"},
                    request_id=request_id,
                    send_body=send_body,
                )
                return HTTPStatus.REQUEST_ENTITY_TOO_LARGE
            if length:
                self._drain_body(length)
            self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found"},
                request_id=request_id,
                send_body=send_body,
            )
            return HTTPStatus.NOT_FOUND
        except RequestError as error:
            self._json_response(error.status, {"error": error.code}, request_id=request_id, send_body=send_body)
            return error.status

    def _drain_body(self, length: int) -> None:
        remaining = length
        while remaining:
            chunk = self.rfile.read(min(65_536, remaining))
            if not chunk:
                break
            remaining -= len(chunk)

    def _static_response(self, raw_path: str, *, request_id: str, send_body: bool) -> HTTPStatus:
        try:
            decoded = unquote(raw_path, errors="strict")
        except UnicodeDecodeError:
            return self._not_found(request_id, send_body)
        if "\x00" in decoded or "\\" in decoded:
            return self._not_found(request_id, send_body)
        route_key = decoded.rstrip("/") or "/"
        relative = STATIC_ROUTE_ALIASES.get(route_key, decoded.lstrip("/") or "index.html")
        parts = Path(relative).parts
        if any(part in {"", ".", ".."} or part.startswith(".") for part in parts):
            return self._not_found(request_id, send_body)
        if relative != "index.html" and parts[0] not in PUBLIC_PREFIXES:
            return self._not_found(request_id, send_body)
        candidate = (self.server.settings.web_dir / relative).resolve()
        try:
            candidate.relative_to(self.server.settings.web_dir)
        except ValueError:
            return self._not_found(request_id, send_body)
        if not candidate.is_file():
            return self._not_found(request_id, send_body)

        data = candidate.read_bytes()
        mime, _encoding = mimetypes.guess_type(candidate.name)
        if candidate.suffix == ".js":
            mime = "application/javascript"
        content_type = mime or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self._security_headers(request_id)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Last-Modified", formatdate(candidate.stat().st_mtime, usegmt=True))
        cache_control = (
            "no-cache"
            if candidate.name.endswith(".html") or not self.server.settings.production
            else "public, max-age=3600"
        )
        self.send_header("Cache-Control", cache_control)
        self.end_headers()
        if send_body:
            self.wfile.write(data)
        return HTTPStatus.OK

    def _not_found(self, request_id: str, send_body: bool) -> HTTPStatus:
        self._json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"}, request_id=request_id, send_body=send_body)
        return HTTPStatus.NOT_FOUND

    def _method_not_allowed(self, allowed: set[str], request_id: str, send_body: bool) -> HTTPStatus:
        self._json_response(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {"error": "method_not_allowed"},
            request_id=request_id,
            send_body=send_body,
            headers=[("Allow", ", ".join(sorted(allowed)))],
        )
        return HTTPStatus.METHOD_NOT_ALLOWED

    def _auth_cookie_headers(self, issue: SessionIssue) -> list[tuple[str, str]]:
        settings = self.server.settings
        max_age = max(0, issue.absolute_expires_at - int(self.server.auth_service.clock()))
        attributes = f"Path=/; Max-Age={max_age}; Expires={formatdate(issue.absolute_expires_at, usegmt=True)}; SameSite=Lax"
        if settings.production:
            attributes += "; Secure"
        return [
            ("Set-Cookie", f"{settings.session_cookie_name}={issue.session_token}; {attributes}; HttpOnly"),
            ("Set-Cookie", f"{settings.csrf_cookie_name}={issue.csrf_token}; {attributes}"),
        ]

    def _clear_auth_cookie_headers(self) -> list[tuple[str, str]]:
        settings = self.server.settings
        attributes = "Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax"
        if settings.production:
            attributes += "; Secure"
        return [
            ("Set-Cookie", f"{settings.session_cookie_name}=; {attributes}; HttpOnly"),
            ("Set-Cookie", f"{settings.csrf_cookie_name}=; {attributes}"),
        ]

    def _json_response(
        self,
        status: HTTPStatus | int,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
        send_body: bool = True,
        headers: list[tuple[str, str]] | None = None,
    ) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(int(status))
        self._security_headers(request_id or uuid4().hex)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for name, value in headers or []:
            self.send_header(name, value)
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def _security_headers(self, request_id: str) -> None:
        self.send_header("X-Request-ID", request_id)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://www.googletagmanager.com "
            "https://www.gstatic.com https://www.google.com https://recaptcha.net https://www.recaptcha.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://www.google-analytics.com https://*.google-analytics.com "
            "https://identitytoolkit.googleapis.com https://securetoken.googleapis.com; "
            "frame-src https://www.google.com https://recaptcha.net https://www.recaptcha.net https://*.firebaseapp.com; "
            "form-action 'self' https://wa.me; upgrade-insecure-requests",
        )
        if self.server.settings.production and self.server.settings.app_base_url.startswith("https://"):
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")


class RequestError(Exception):
    def __init__(self, status: HTTPStatus, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


def create_server(
    settings: Settings | None = None,
    *,
    verifier: IdentityVerifier | None = None,
    clock: Callable[[], float] | None = None,
) -> GravityHTTPServer:
    configured = settings or Settings.load()
    configured.ensure_directories()
    database = Database(configured.database_path, configured.migrations_dir)
    database.migrate()
    identity_verifier = verifier or FirebaseAdminVerifier(configured)
    auth_service = AuthService(database, configured, identity_verifier, **({"clock": clock} if clock else {}))
    return GravityHTTPServer(
        (configured.host, configured.port),
        GravityRequestHandler,
        configured,
        database,
        auth_service,
    )
