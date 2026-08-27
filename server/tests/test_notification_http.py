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


ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "phase-five-notification-http-secret-long-enough"


@contextmanager
def running_server():
    with TemporaryDirectory() as temporary:
        runtime = Path(temporary)
        base_settings = Settings.load(
            root_dir=ROOT,
            environ={"SECRET_KEY": TEST_SECRET, "GRAVITY_PORT": "0", "GRAVITY_LOG_LEVEL": "CRITICAL"},
        )
        settings = replace(
            base_settings,
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
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def request_json(base, path, *, method="GET", body=None, headers=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    merged = {"Content-Type": "application/json", **(headers or {})}
    request = Request(base + path, data=data, method=method, headers=merged)
    try:
        response = urlopen(request, timeout=5)
        return response.status, json.loads(response.read() or b"{}")
    except HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def admin_issue(service, username, password, secret):
    challenge = service.begin_login({"username": username, "password": password}, "127.0.0.1")
    code = _totp_code(secret, int(time.time()) // 30)
    return service.verify_second_factor(
        challenge.challenge_token,
        code,
        remote_addr="127.0.0.1",
        user_agent="GravityNotificationHttpTest/1.0",
        request_id="notification-http",
    )


def admin_headers(server, issue, base, *, include_origin=True, include_csrf=True):
    settings = server.settings
    cookie = f"{settings.admin_session_cookie_name}={issue.session_token}; {settings.admin_csrf_cookie_name}={issue.csrf_token}"
    headers = {"Cookie": cookie}
    if include_origin:
        headers["Origin"] = base
    if include_csrf:
        headers["X-CSRF-Token"] = issue.csrf_token
    return headers


class NotificationHttpTests(unittest.TestCase):
    def test_notification_routes_require_auth_origin_and_csrf(self):
        with running_server() as (server, base):
            status, payload = request_json(base, "/api/me/notifications")
            self.assertEqual((status, payload), (401, {"error": "unauthenticated"}))
            status, payload = request_json(base, "/api/admin/notifications")
            self.assertEqual((status, payload), (401, {"error": "admin_unauthenticated"}))

            owner = server.admin_service.bootstrap_owner("owner", "Gravity!Owner123")
            issue = admin_issue(server.admin_service, "owner", "Gravity!Owner123", owner.totp_secret)
            headers = admin_headers(server, issue, base)
            status, payload = request_json(base, "/api/admin/notifications", headers=headers)
            self.assertEqual(status, 200)
            self.assertEqual(payload["notifications"], [])
            self.assertEqual(set(payload["providerBlockers"].values()), {"BLOCKED_EXTERNAL_CONFIG"})

            no_origin = admin_headers(server, issue, base, include_origin=False)
            status, payload = request_json(base, "/api/admin/notifications/scan", method="POST", body={"daysBefore": 7}, headers=no_origin)
            self.assertEqual((status, payload), (403, {"error": "invalid_origin"}))
            no_csrf = admin_headers(server, issue, base, include_csrf=False)
            status, payload = request_json(
                base, "/api/admin/notifications/scan", method="POST",
                body={"daysBefore": 7}, headers=no_csrf,
            )
            self.assertEqual((status, payload), (403, {"error": "admin_forbidden"}))

            status, payload = request_json(
                base, "/api/admin/notifications/scan", method="POST",
                body={"daysBefore": 7}, headers=headers,
            )
            self.assertEqual(status, 200)
            self.assertEqual(payload["scan"]["created"], 0)
            self.assertEqual(payload["scan"]["scanned"], 0)

            status, payload = request_json(
                base, "/api/admin/notifications/scan", method="POST",
                body={"daysBefore": 0}, headers=headers,
            )
            self.assertEqual((status, payload), (422, {"error": "notification_validation"}))
            owner_session = server.admin_service.resolve_session(issue.session_token)
            reception = server.admin_service.create_admin(
                owner_session, "frontdesk", "Gravity!Desk123", "reception"
            )
            desk_issue = admin_issue(
                server.admin_service, "frontdesk", "Gravity!Desk123", reception.totp_secret
            )
            desk_headers = admin_headers(server, desk_issue, base)
            status, payload = request_json(base, "/api/admin/notifications", headers=desk_headers)
            self.assertEqual((status, payload), (403, {"error": "admin_forbidden"}))
            status, payload = request_json(
                base, "/api/admin/notifications/scan", method="POST",
                body={"daysBefore": 7}, headers=desk_headers,
            )
            self.assertEqual((status, payload), (403, {"error": "admin_forbidden"}))

            status, payload = request_json(
                base, "/api/admin/notifications/send", method="POST", body={}, headers=headers,
            )
            self.assertEqual((status, payload), (404, {"error": "not_found"}))


if __name__ == "__main__":
    unittest.main()
