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
            app_base_url="https://gravity.example",
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

    def test_explicit_environment_does_not_inherit_dotenv(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".env").write_text(
                "GRAVITY_ENV=production\nAPP_BASE_URL=https://prod.example\n",
                encoding="utf-8",
            )
            settings = Settings.load(root_dir=root, environ={"SECRET_KEY": "test-secret"})
            self.assertEqual(settings.environment, "development")
            self.assertEqual(settings.app_base_url, "http://127.0.0.1:8787")

    def test_migrations_are_idempotent_and_database_is_healthy(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "gravity.sqlite3"
            database = Database(path, ROOT / "server" / "migrations")
            self.assertEqual(database.migrate(), ["001", "002", "003", "004", "005", "006", "007", "008"])
            self.assertEqual(database.migrate(), [])
            self.assertEqual(database.health(), {"database": "ok", "migrations": "8"})
            with closing(sqlite3.connect(path)) as connection:
                versions = connection.execute("SELECT version FROM schema_migrations").fetchall()
                self.assertEqual(versions, [("001",), ("002",), ("003",), ("004",), ("005",), ("006",), ("007",), ("008",)])

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
                ("/", b"Make your next rep"),
                ("/pages/trainers.html", b"Start with your goal"),
                ("/pages/gallery.html", b"Current posts, from the source"),
                ("/account", b"Your member space"),
                ("/admin", b"Control Room"),
                ("/trainers", b"Start with your goal"),
                ("/coaching", b"Start with your goal"),
                ("/gallery", b"Current posts, from the source"),
                ("/privacy", b"REQUIRES_OPERATOR_LEGAL_REVIEW"),
                ("/favicon.ico", b"Gravity Fitness GF mark"),
                ("/css/style.css", b"--lime"),
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
            self.assertNotIn("googletagmanager.com", headers["Content-Security-Policy"])
            self.assertNotIn("google-analytics.com", headers["Content-Security-Policy"])
            self.assertEqual(headers["Referrer-Policy"], "strict-origin-when-cross-origin")
            self.assertEqual(headers["Server"], "GravityFitness")
            self.assertTrue(headers["X-Request-ID"])

    def test_unknown_api_and_admin_paths_do_not_fall_through_to_static(self):
        with running_server() as (base, _settings):
            for path in ("/api/nope", "/api/admin/users", "/admin/index.html", "/admin/private"):
                status, _headers, body = fetch(base, path)
                self.assertEqual(status, 404)
                self.assertEqual(json.loads(body), {"error": "not_found"})

    def test_membership_catalog_is_public_but_member_and_admin_data_are_private(self):
        with running_server() as (base, _settings):
            status, _headers, body = fetch(base, "/api/membership/plans")
            self.assertEqual(status, 200)
            plans = json.loads(body)["plans"]
            self.assertEqual(
                [(plan["name"], plan["pricePaise"], plan["durationMonths"], plan["description"]) for plan in plans],
                [("Basic", 99900, 1, None), ("Pro", 149900, 1, None), ("Elite", 249900, 1, None)],
            )
            status, _headers, body = fetch(base, "/api/me/membership")
            self.assertEqual(status, 401)
            self.assertEqual(json.loads(body), {"error": "unauthenticated"})
            status, _headers, body = fetch(base, "/api/admin/membership/plans")
            self.assertEqual(status, 401)
            self.assertEqual(json.loads(body), {"error": "admin_unauthenticated"})
            status, _headers, body = fetch(base, "/api/payment/config")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["enabled"], False)
            status, _headers, body = fetch(base, "/api/me/payments")
            self.assertEqual(status, 401)
            self.assertEqual(json.loads(body), {"error": "unauthenticated"})

    def test_public_page_has_no_static_payment_links_or_client_invoice_generator(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("RAZORPAY_LINKS", html)
        self.assertNotIn("rzp.io/l/", html)
        self.assertNotIn("jsPDF", html)
        self.assertNotIn("IGST @ 18%", html)

    def test_homepage_has_no_legacy_loader_or_athlete_runtime(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("loader", html.casefold())
        self.assertNotIn("athlete", html.casefold())
        self.assertNotIn("gsap", html.casefold())
        self.assertIn('/js/enquiry-form.js', html)

    def test_coaching_ui_contract_is_wired(self):
        with running_server() as (base, _settings):
            status, _headers, admin = fetch(base, "/admin")
            self.assertEqual(status, 200)
            for marker in (b'id="coachingView"', b'id="dietTemplateForm"', b'id="dietVersionForm"', b'/js/admin-coaching.js'):
                self.assertIn(marker, admin)
            status, _headers, account = fetch(base, "/account")
            self.assertEqual(status, 200)
            self.assertIn(b'/js/account-coaching.js', account)

    def test_readiness_ui_contract_is_wired(self):
        with running_server() as (base, _settings):
            status, _headers, admin = fetch(base, "/admin")
            self.assertEqual(status, 200)
            for marker in (
                b'data-view="readiness"', b'id="readinessView"', b'id="readinessSummary"',
                b'id="readinessBody"', b'id="refreshReadiness"', b'/js/admin-readiness.js',
            ):
                self.assertIn(marker, admin)
            status, _headers, body = fetch(base, "/js/admin-readiness.js")
            self.assertEqual(status, 200)
            self.assertIn(b'/api/admin/readiness', body)
            self.assertIn(b'system.readiness', body)

    def test_crawl_files_use_configured_public_origin(self):
        with running_server() as (base, _settings):
            status, headers, body = fetch(base, "/robots.txt")
            self.assertEqual(status, 200)
            self.assertTrue(headers["Content-Type"].startswith("text/plain"))
            robots = body.decode("utf-8")
            self.assertIn("Disallow: /account", robots)
            self.assertIn("Disallow: /admin", robots)
            self.assertIn("Disallow: /api/", robots)
            self.assertIn("Sitemap: https://gravity.example/sitemap.xml", robots)

            status, headers, body = fetch(base, "/sitemap.xml")
            self.assertEqual(status, 200)
            self.assertTrue(headers["Content-Type"].startswith("application/xml"))
            sitemap = body.decode("utf-8")
            for url in ("https://gravity.example/", "https://gravity.example/coaching", "https://gravity.example/gallery", "https://gravity.example/privacy"):
                self.assertIn(f"<loc>{url}</loc>", sitemap)
            self.assertNotIn("/account</loc>", sitemap)
            self.assertNotIn("/admin</loc>", sitemap)

            status, headers, body = fetch(base, "/site.webmanifest")
            self.assertEqual(status, 200)
            self.assertTrue(headers["Content-Type"].startswith("application/manifest+json"))
            self.assertEqual(json.loads(body)["name"], "Gravity Fitness Neemuch")

    def test_public_truth_and_accessibility_guards(self):
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        trainers = (ROOT / "web" / "pages" / "trainers.html").read_text(encoding="utf-8")
        gallery = (ROOT / "web" / "pages" / "gallery.html").read_text(encoding="utf-8")
        privacy = (ROOT / "web" / "pages" / "privacy.html").read_text(encoding="utf-8")
        public_plans = (ROOT / "web" / "js" / "public-membership.js").read_text(encoding="utf-8")
        enquiry_form = (ROOT / "web" / "js" / "enquiry-form.js").read_text(encoding="utf-8")
        combined = "\n".join((index, trainers, gallery, privacy, public_plans, enquiry_form))

        forbidden = (
            "Neemuch's #1", "4.9/5", "2,000+", "100+ Member",
            "First Month FREE", "IGFIT", "aggregateRating",
            '"priceRange"', '"ratingValue"', "Daily Calories", "Recommended Plan",
            "Underweight", "Overweight", "Obese", "G-QCV4MEH4R4",
            "hello@gravityfitness.in", "919876543210", "step-invoice",
            "downloadInvoicePDF", "jsPDF",
        )
        for marker in forbidden:
            self.assertNotIn(marker, combined, marker)

        for page in (index, trainers, gallery, privacy):
            self.assertIn('class="skip-link"', page)
            self.assertIn('id="main-content"', page)
        self.assertIn('/api/membership/plans', public_plans)
        self.assertIn('textContent', public_plans)
        self.assertIn('/api/enquiries/token', enquiry_form)
        self.assertIn('/api/enquiries', enquiry_form)
        self.assertNotIn('onclick=', combined)
        self.assertNotIn('href="#"', combined)
        self.assertIn('₹999', index)
        self.assertIn('₹1,499', index)
        self.assertIn('₹2,499', index)
        self.assertIn('REQUIRES_OPERATOR_LEGAL_REVIEW', privacy)

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
