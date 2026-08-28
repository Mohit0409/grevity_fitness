from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from urllib.error import HTTPError
import io
import json
import unittest

from server.gravity.canary import firebase_canary, razorpay_canary, run_provider_canaries
from server.gravity.config import Settings
from server.gravity.firebase_auth import FirebaseAdminVerifier, FirebaseUnavailable


ROOT = Path(__file__).resolve().parents[2]


class FakeResponse:
    def __init__(self, payload: object, status: int = 200) -> None:
        self.body = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, maximum: int = -1) -> bytes:
        return self.body if maximum < 0 else self.body[:maximum]


class ProviderCanaryTests(unittest.TestCase):
    def production_settings(self, service_account: Path) -> Settings:
        return Settings.load(root_dir=ROOT, environ={
            "GRAVITY_ENV": "production",
            "APP_BASE_URL": "https://gravity.example",
            "SECRET_KEY": "x" * 40,
            "FIREBASE_PROJECT_ID": "gravity-authe",
            "FIREBASE_WEB_API_KEY": "api-key",
            "FIREBASE_AUTH_DOMAIN": "gravity.example",
            "FIREBASE_APP_ID": "app-id",
            "FIREBASE_SERVICE_ACCOUNT_PATH": str(service_account.resolve()),
            "RAZORPAY_MODE": "live",
            "RAZORPAY_KEY_ID": "rzp_live_example",
            "RAZORPAY_KEY_SECRET": "secret-example-value",
            "RAZORPAY_WEBHOOK_SECRET": "webhook-example-value",
        })

    def test_canaries_block_before_production_configuration(self):
        settings = Settings.load(root_dir=ROOT, environ={"SECRET_KEY": "x" * 40})
        report = run_provider_canaries(settings)
        self.assertFalse(report["ok"])
        self.assertEqual(report["firebase"]["status"], "blocked")
        self.assertEqual(report["razorpay"], {
            "ok": True, "status": "skipped", "code": "razorpay_disabled",
        })

    def test_firebase_probe_is_read_only_and_secret_safe(self):
        with TemporaryDirectory() as temporary:
            service_account = Path(temporary) / "service.json"
            service_account.write_text("{}", encoding="utf-8")
            settings = self.production_settings(service_account)
            called = []
            result = firebase_canary(settings, probe=lambda: called.append(True))
            self.assertEqual(called, [True])
            self.assertEqual(result, {"ok": True, "status": "passed", "code": None})
    def test_firebase_admin_probe_uses_list_users_without_returning_user_data(self):
        settings = Settings.load(root_dir=ROOT, environ={"SECRET_KEY": "x" * 40})
        verifier = FirebaseAdminVerifier(settings)
        fake_app = object()
        with mock.patch.object(verifier, "_get_app", return_value=fake_app), \
             mock.patch("firebase_admin.auth.list_users") as list_users:
            verifier.probe()
        list_users.assert_called_once_with(max_results=1, app=fake_app)

    def test_razorpay_canary_is_read_only_collection_fetch(self):
        with TemporaryDirectory() as temporary:
            service_account = Path(temporary) / "service.json"
            service_account.write_text("{}", encoding="utf-8")
            settings = self.production_settings(service_account)
            captured = {}

            def opener(request, timeout=0):
                captured["method"] = request.get_method()
                captured["url"] = request.full_url
                captured["authorization"] = request.headers.get("Authorization")
                captured["timeout"] = timeout
                return FakeResponse({"entity": "collection", "count": 0, "items": []})

            result = razorpay_canary(settings, opener=opener)
            self.assertTrue(result["ok"])
            self.assertEqual(captured["method"], "GET")
            self.assertIn("/v1/orders?count=1", captured["url"])
            self.assertTrue(str(captured["authorization"]).startswith("Basic "))
            self.assertNotIn(settings.razorpay_key_secret, json.dumps(result))
    def test_razorpay_failure_returns_only_safe_code(self):
        with TemporaryDirectory() as temporary:
            service_account = Path(temporary) / "service.json"
            service_account.write_text("{}", encoding="utf-8")
            settings = self.production_settings(service_account)

            def opener(request, timeout=0):
                raise HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b"secret provider body"))

            result = razorpay_canary(settings, opener=opener)
            encoded = json.dumps(result)
            self.assertEqual(result["code"], "razorpay_http_401")
            self.assertNotIn("secret provider body", encoded)
            self.assertNotIn(settings.razorpay_key_secret, encoded)


if __name__ == "__main__":
    unittest.main()
