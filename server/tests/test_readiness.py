from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json
import time
import unittest

from server.gravity.admin import _totp_code
from server.gravity.config import Settings
from server.gravity.http import create_server
from server.gravity.readiness import ReadinessService


ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "phase-nine-readiness-secret-long-enough"


def request_json(base: str, path: str, *, headers=None):
    request = Request(base + path, headers=headers or {})
    try:
        response = urlopen(request, timeout=5)
        return response.status, json.loads(response.read() or b"{}")
    except HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")
@contextmanager
def running_server():
    with TemporaryDirectory() as temporary:
        runtime = Path(temporary)
        base = Settings.load(root_dir=ROOT, environ={
            "SECRET_KEY": TEST_SECRET,
            "GRAVITY_PORT": "0",
            "GRAVITY_LOG_LEVEL": "CRITICAL",
        })
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
        actual_base = f"http://127.0.0.1:{server.server_port}"
        server.settings = replace(server.settings, app_base_url=actual_base)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server, actual_base
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
def admin_issue(service, username: str, password: str, secret: str):
    challenge = service.begin_login({"username": username, "password": password}, "127.0.0.1")
    code = _totp_code(secret, int(time.time()) // 30)
    return service.verify_second_factor(
        challenge.challenge_token,
        code,
        remote_addr="127.0.0.1",
        user_agent="GravityReadinessTest/1.0",
        request_id="readiness-http",
    )


def admin_headers(server, issue):
    settings = server.settings
    cookie = (
        f"{settings.admin_session_cookie_name}={issue.session_token}; "
        f"{settings.admin_csrf_cookie_name}={issue.csrf_token}"
    )
    return {"Cookie": cookie}


class ReadinessServiceTests(unittest.TestCase):
    def test_report_is_secret_safe_and_provider_adapters_remain_blocked(self):
        secret_values = {
            "WHATSAPP_ACCESS_TOKEN": "wa-secret-value-123456789",
            "SMS_API_KEY": "sms-secret-value-123456789",
            "SMTP_PASSWORD": "smtp-secret-value-123456789",
            "RAZORPAY_KEY_SECRET": "rzp-secret-value-123456789",
        }
        settings = Settings.load(root_dir=ROOT, environ={
            "SECRET_KEY": TEST_SECRET,
            "WHATSAPP_PROVIDER": "meta",
            "WHATSAPP_PHONE_NUMBER_ID": "phone-id",
            "SMS_PROVIDER": "example-sms",
            "SMTP_HOST": "smtp.example.test",
            "SMTP_USERNAME": "mailer",
            "EMAIL_FROM": "gym@example.test",
            **secret_values,
        })
        report = ReadinessService(settings).report()
        encoded = json.dumps(report, sort_keys=True)
        for value in secret_values.values():
            self.assertNotIn(value, encoded)
        self.assertEqual(report["notifications"]["whatsapp"]["status"], "blocked_adapter_missing")
        self.assertEqual(report["notifications"]["sms"]["status"], "blocked_adapter_missing")
        self.assertEqual(report["notifications"]["email"]["status"], "ready")
        self.assertFalse(report["productionReady"])
        self.assertIn("production_mode", report["blockers"])
        self.assertIn("https_base_url", report["blockers"])
        self.assertIn("trusted_proxy_boundary", report["blockers"])
        self.assertIn("firebase_service_account_file", report["blockers"])
        self.assertIn("razorpay_live_mode", report["blockers"])

    def test_production_proxy_boundary_rejects_broad_trust(self):
        settings = Settings.load(root_dir=ROOT, environ={
            "GRAVITY_ENV": "production",
            "APP_BASE_URL": "https://gravity.example",
            "SECRET_KEY": "x" * 40,
            "GRAVITY_TRUST_PROXY": "true",
            "GRAVITY_TRUSTED_PROXY_CIDRS": "0.0.0.0/0",
        })
        report = ReadinessService(settings).report()
        self.assertFalse(report["runtime"]["trustedProxyBoundary"])
        self.assertIn("trusted_proxy_boundary", report["blockers"])

    def test_tax_invoice_gate_requires_explicit_enable_and_valid_gstin(self):
        base = {
            "SECRET_KEY": TEST_SECRET, "OWNER_PHONE": "+917999526112",
            "BUSINESS_NAME": "Gravity Fitness", "BUSINESS_ADDRESS": "Verified address",
        }
        disabled = Settings.load(root_dir=ROOT, environ={**base, "BUSINESS_GSTIN": "23ABCDE1234F1Z5"})
        self.assertFalse(disabled.tax_invoice_identity_configured)
        malformed = Settings.load(root_dir=ROOT, environ={**base, "BUSINESS_GSTIN": "not-a-gstin", "TAX_INVOICE_ENABLED": "true"})
        self.assertFalse(malformed.gstin_format_valid)
        self.assertFalse(malformed.tax_invoice_identity_configured)
        enabled = Settings.load(root_dir=ROOT, environ={**base, "BUSINESS_GSTIN": "23ABCDE1234F1Z5", "TAX_INVOICE_ENABLED": "true"})
        self.assertTrue(enabled.gstin_format_valid)
        self.assertTrue(enabled.tax_invoice_identity_configured)

    def test_complete_synthetic_production_identity_clears_critical_blockers(self):
        with TemporaryDirectory() as temporary:
            service_account = Path(temporary) / "service.json"
            service_account.write_text("{}", encoding="utf-8")
            settings = Settings.load(root_dir=ROOT, environ={
                "GRAVITY_ENV": "production", "APP_BASE_URL": "https://gravity.example",
                "GRAVITY_TRUST_PROXY": "true", "GRAVITY_TRUSTED_PROXY_CIDRS": "127.0.0.1/32",
                "SECRET_KEY": "x" * 40, "FIREBASE_PROJECT_ID": "gravity-authe",
                "FIREBASE_WEB_API_KEY": "api-key", "FIREBASE_AUTH_DOMAIN": "gravity.example",
                "FIREBASE_APP_ID": "app-id", "FIREBASE_SERVICE_ACCOUNT_PATH": str(service_account.resolve()),
                "RAZORPAY_MODE": "live", "RAZORPAY_KEY_ID": "rzp-key",
                "RAZORPAY_KEY_SECRET": "rzp-secret", "RAZORPAY_WEBHOOK_SECRET": "webhook-secret",
                "OWNER_PHONE": "+917999526112", "BUSINESS_NAME": "Gravity Fitness",
                "BUSINESS_ADDRESS": "Verified business address", "BUSINESS_GSTIN": "23ABCDE1234F1Z5",
                "TAX_INVOICE_ENABLED": "true",
            })
            report = ReadinessService(settings).report()
        self.assertTrue(report["productionReady"])
        self.assertEqual(report["blockers"], [])
        self.assertTrue(report["firebase"]["serviceAccountFilePresent"])
        self.assertTrue(report["razorpay"]["liveMode"])
        self.assertTrue(report["runtime"]["trustedProxyBoundary"])
        self.assertTrue(report["business"]["taxInvoiceIdentityConfigured"])


class ReadinessHttpTests(unittest.TestCase):
    def test_readiness_requires_owner_or_admin_permission(self):
        with running_server() as (server, base):
            status, payload = request_json(base, "/api/admin/readiness")
            self.assertEqual((status, payload), (401, {"error": "admin_unauthenticated"}))

            owner = server.admin_service.bootstrap_owner("owner", "Gravity!Owner123")
            issue = admin_issue(server.admin_service, "owner", "Gravity!Owner123", owner.totp_secret)
            status, payload = request_json(base, "/api/admin/readiness", headers=admin_headers(server, issue))
            self.assertEqual(status, 200)
            self.assertIn("readiness", payload)
            self.assertIn("firebase", payload["readiness"])

            owner_session = server.admin_service.resolve_session(issue.session_token)
            admin = server.admin_service.create_admin(owner_session, "opsadmin", "Gravity!Admin123", "admin")
            admin_login = admin_issue(server.admin_service, "opsadmin", "Gravity!Admin123", admin.totp_secret)
            status, _payload = request_json(base, "/api/admin/readiness", headers=admin_headers(server, admin_login))
            self.assertEqual(status, 200)

            for username, password, role in (
                ("trainer1", "Gravity!Trainer123", "trainer"),
                ("frontdesk", "Gravity!Desk123", "reception"),
            ):
                created = server.admin_service.create_admin(owner_session, username, password, role)
                login = admin_issue(server.admin_service, username, password, created.totp_secret)
                status, payload = request_json(base, "/api/admin/readiness", headers=admin_headers(server, login))
                self.assertEqual((status, payload), (403, {"error": "admin_forbidden"}))


if __name__ == "__main__":
    unittest.main()
