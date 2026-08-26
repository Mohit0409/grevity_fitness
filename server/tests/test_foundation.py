from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json
import logging
import sqlite3
import unittest

from server.gravity.config import Settings
from server.gravity.database import Database
from server.gravity.http import _safe_path_for_log, create_server
from server.gravity.logging_config import JsonFormatter


ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def running_server():
    with TemporaryDirectory() as temporary:
        runtime = Path(temporary)
        base = Settings.load(root_dir=ROOT, environ={"GRAVITY_PORT": "0", "GRAVITY_LOG_LEVEL": "CRITICAL"})
        settings = replace(
            base,
            data_dir=runtime / "data",
            log_dir=runtime / "logs",
            backup_dir=runtime / "backups",
            database_path=runtime / "data" / "gravity.sqlite3",
            host="127.0.0.1",
            port=0,
        )
        server = create_server(settings)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", settings
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def fetch(base: str, path: str, *, method: str = "GET", data: bytes | None = None):
    request = Request(base + path, method=method, data=data)
    try:
        response = urlopen(request, timeout=5)
        return response.status, dict(response.headers), response.read()
    except HTTPError as error:
        return error.code, dict(error.headers), error.read()


class DatabaseTests(unittest.TestCase):
    def test_migrations_are_idempotent_and_database_is_healthy(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "gravity.sqlite3"
            database = Database(path, ROOT / "server" / "migrations")
            self.assertEqual(database.migrate(), ["001"])
            self.assertEqual(database.migrate(), [])
            self.assertEqual(database.health(), {"database": "ok", "migrations": "1"})
            with closing(sqlite3.connect(path)) as connection:
                versions = connection.execute("SELECT version FROM schema_migrations").fetchall()
                self.assertEqual(versions, [("001",)])

    def test_changed_applied_migration_is_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            migrations = root / "migrations"
            migrations.mkdir()
            migration = migrations / "001_test.sql"
            migration.write_text("CREATE TABLE sample(id INTEGER PRIMARY KEY);", encoding="utf-8")
            database = Database(root / "db.sqlite3", migrations)
            database.migrate()
            migration.write_text("CREATE TABLE changed(id INTEGER PRIMARY KEY);", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "changed on disk"):
                database.migrate()


class HttpFoundationTests(unittest.TestCase):
    def test_health_is_safe_and_healthy(self):
        with running_server() as (base, _settings):
            status, headers, body = fetch(base, "/api/health")
            self.assertEqual(status, 200)
            self.assertEqual(
                json.loads(body),
                {"status": "ok", "service": "Gravity Fitness", "database": "ok"},
            )
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertNotIn("path", body.decode())

    def test_static_site_and_subpages_are_served(self):
        with running_server() as (base, _settings):
            for path, marker in (
                ("/", b"Transform Your Body"),
                ("/pages/trainers.html", b"Meet Your Coaches"),
                ("/pages/gallery.html", b"Inside Gravity"),
                ("/css/style.css", b"GRAVITY FITNESS"),
            ):
                status, _headers, body = fetch(base, path)
                self.assertEqual(status, 200, path)
                self.assertIn(marker, body, path)

    def test_only_public_allowlisted_files_are_exposed(self):
        with running_server() as (base, _settings):
            for path in (
                "/.env",
                "/.env.example",
                "/firebase.json",
                "/pyproject.toml",
                "/server/gravity/config.py",
                "/hydro-buddy-desktop/package-lock.json",
                "/assets/models/realistic-athlete.fbx",
                "/%2e%2e/firebase.json",
                "/pages/%2e%2e/%2e%2e/.env",
            ):
                status, _headers, body = fetch(base, path)
                self.assertEqual(status, 404, path)
                self.assertEqual(json.loads(body), {"error": "not_found"})

    def test_security_headers_are_present_without_server_version_leak(self):
        with running_server() as (base, _settings):
            status, headers, _body = fetch(base, "/")
            self.assertEqual(status, 200)
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(headers["X-Frame-Options"], "DENY")
            self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
            self.assertEqual(headers["Referrer-Policy"], "strict-origin-when-cross-origin")
            self.assertEqual(headers["Server"], "GravityFitness")
            self.assertTrue(headers["X-Request-ID"])

    def test_unknown_api_and_admin_paths_do_not_fall_through_to_static(self):
        with running_server() as (base, _settings):
            for path in ("/api/nope", "/api/admin/users", "/admin", "/admin/index.html"):
                status, _headers, body = fetch(base, path)
                self.assertEqual(status, 404)
                self.assertEqual(json.loads(body), {"error": "not_found"})

    def test_head_returns_content_length_without_body(self):
        with running_server() as (base, _settings):
            status, headers, body = fetch(base, "/", method="HEAD")
            self.assertEqual(status, 200)
            self.assertGreater(int(headers["Content-Length"]), 1000)
            self.assertEqual(body, b"")

    def test_unknown_posts_are_bounded_and_never_reach_static_files(self):
        with running_server() as (base, _settings):
            status, _headers, body = fetch(base, "/firebase.json", method="POST", data=b"{}")
            self.assertEqual(status, 404)
            self.assertEqual(json.loads(body), {"error": "not_found"})

            status, _headers, body = fetch(
                base,
                "/api/future",
                method="POST",
                data=b"x" * 1_048_577,
            )
            self.assertEqual(status, 413)
            self.assertEqual(json.loads(body), {"error": "request_too_large"})

    def test_port_collision_is_rejected(self):
        with running_server() as (base, settings):
            occupied_port = int(base.rsplit(":", 1)[1])
            with self.assertRaises(OSError):
                create_server(replace(settings, port=occupied_port))


class LoggingSafetyTests(unittest.TestCase):
    def test_sensitive_event_fields_and_query_tokens_are_redacted(self):
        record = logging.LogRecord("gravity.test", logging.INFO, __file__, 1, "event", (), None)
        record.event_data = {"token": "secret-value", "safe": "visible"}
        payload = json.loads(JsonFormatter().format(record))
        self.assertEqual(payload["token"], "[REDACTED]")
        self.assertEqual(payload["safe"], "visible")
        self.assertEqual(
            _safe_path_for_log("/callback?code=secret&state=public"),
            "/callback?code=[REDACTED]&state=public",
        )


if __name__ == "__main__":
    unittest.main()
