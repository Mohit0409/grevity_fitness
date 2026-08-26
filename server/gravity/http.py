from __future__ import annotations

from email.utils import formatdate
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter
from urllib.parse import unquote, urlsplit
from uuid import uuid4
import json
import logging
import mimetypes

from .config import Settings
from .database import Database


LOGGER = logging.getLogger("gravity.http")
PUBLIC_PREFIXES = {"assets", "css", "js", "pages"}
SENSITIVE_QUERY_KEYS = {"access_token", "code", "id_token", "session", "token"}
MAX_REQUEST_BODY = 1_048_576


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

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], settings: Settings):
        super().__init__(address, handler)
        self.settings = settings
        self.database = Database(settings.database_path, settings.migrations_dir)


class GravityRequestHandler(BaseHTTPRequestHandler):
    server: GravityHTTPServer
    server_version = "GravityFitness"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def version_string(self) -> str:
        return "GravityFitness"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        self._dispatch(send_body=True)

    def do_HEAD(self) -> None:
        self._dispatch(send_body=False)

    def do_POST(self) -> None:
        started = perf_counter()
        request_id = uuid4().hex
        status: int | HTTPStatus = HTTPStatus.NOT_FOUND
        try:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                status = HTTPStatus.BAD_REQUEST
                self._json_response(status, {"error": "invalid_request"}, request_id=request_id)
                return
            if content_length < 0:
                status = HTTPStatus.BAD_REQUEST
                self._json_response(status, {"error": "invalid_request"}, request_id=request_id)
                return
            if content_length > MAX_REQUEST_BODY:
                status = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
                self._json_response(status, {"error": "request_too_large"}, request_id=request_id)
                return
            if content_length:
                self.rfile.read(content_length)
            self._json_response(status, {"error": "not_found"}, request_id=request_id)
        finally:
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
                        "remote": self.client_address[0],
                    }
                },
            )

    def _dispatch(self, *, send_body: bool) -> None:
        started = perf_counter()
        request_id = uuid4().hex
        status: int | HTTPStatus = HTTPStatus.INTERNAL_SERVER_ERROR
        try:
            path = urlsplit(self.path).path
            if path == "/api/health":
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
            if path.startswith("/api/") or path == "/admin" or path.startswith("/admin/"):
                status = HTTPStatus.NOT_FOUND
                self._json_response(status, {"error": "not_found"}, request_id=request_id, send_body=send_body)
                return
            status = self._static_response(path, request_id=request_id, send_body=send_body)
        except (BrokenPipeError, ConnectionResetError):
            status = 499
        except Exception:
            LOGGER.exception("request_failed", extra={"event_data": {"request_id": request_id}})
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            self._json_response(status, {"error": "internal_error"}, request_id=request_id, send_body=send_body)
        finally:
            LOGGER.info(
                "request_completed",
                extra={
                    "event_data": {
                        "request_id": request_id,
                        "method": self.command,
                        "path": _safe_path_for_log(self.path),
                        "status": int(status),
                        "duration_ms": round((perf_counter() - started) * 1000, 2),
                        "remote": self.client_address[0],
                    }
                },
            )

    def _static_response(self, raw_path: str, *, request_id: str, send_body: bool) -> HTTPStatus:
        try:
            decoded = unquote(raw_path, errors="strict")
        except UnicodeDecodeError:
            return self._not_found(request_id, send_body)
        if "\x00" in decoded or "\\" in decoded:
            return self._not_found(request_id, send_body)
        relative = decoded.lstrip("/") or "index.html"
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
        self.send_header("Cache-Control", "no-cache" if candidate.name.endswith(".html") else "public, max-age=3600")
        self.end_headers()
        if send_body:
            self.wfile.write(data)
        return HTTPStatus.OK

    def _not_found(self, request_id: str, send_body: bool) -> HTTPStatus:
        self._json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"}, request_id=request_id, send_body=send_body)
        return HTTPStatus.NOT_FOUND

    def _json_response(
        self,
        status: HTTPStatus | int,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
        send_body: bool = True,
    ) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(int(status))
        self._security_headers(request_id or uuid4().hex)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def _security_headers(self, request_id: str) -> None:
        self.send_header("X-Request-ID", request_id)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://www.googletagmanager.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://www.google-analytics.com https://*.google-analytics.com; "
            "frame-src https://www.google.com; "
            "form-action 'self' https://wa.me; upgrade-insecure-requests",
        )
        if self.server.settings.production and self.server.settings.app_base_url.startswith("https://"):
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")


def create_server(settings: Settings | None = None) -> GravityHTTPServer:
    configured = settings or Settings.load()
    configured.ensure_directories()
    database = Database(configured.database_path, configured.migrations_dir)
    database.migrate()
    server = GravityHTTPServer((configured.host, configured.port), GravityRequestHandler, configured)
    server.database = database
    return server
