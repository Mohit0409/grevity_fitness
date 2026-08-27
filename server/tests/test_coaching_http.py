from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4
import json
import time
import unittest

from server.gravity.admin import _totp_code
from server.gravity.config import Settings
from server.gravity.http import create_server

ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "phase-seven-coaching-http-secret-long-enough"
SESSION_TOKEN = "phase7-customer-session-token"
CSRF_TOKEN = "phase7-customer-csrf-token"

@contextmanager
def running_server():
    with TemporaryDirectory() as temporary:
        runtime = Path(temporary)
        base = Settings.load(
            root_dir=ROOT,
            environ={
                "SECRET_KEY": TEST_SECRET,
                "GRAVITY_PORT": "0",
                "GRAVITY_LOG_LEVEL": "CRITICAL",
            },
        )
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
        now = int(time.time())
        with server.database.session() as connection:
            connection.execute(
                "INSERT INTO customers(id,status,display_name,created_at,updated_at) VALUES (?,?,?,?,?)",
                ("customer-http", "active", "HTTP Customer", now, now),
            )
            connection.execute(
                "INSERT INTO customer_profiles(customer_id,updated_at) VALUES (?,?)",
                ("customer-http", now),
            )
            server.auth_service._insert_session(
                connection,
                session_id=uuid4().hex,
                customer_id="customer-http",
                session_token=SESSION_TOKEN,
                csrf_token=CSRF_TOKEN,
                now=now,
                ip_hash=None,
                user_agent_hash=None,
            )
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
    merged = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        merged.setdefault("Content-Type", "application/json")
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
        user_agent="GravityCoachingHttpTest/1.0",
        request_id="coaching-http",
    )

def admin_headers(server, issue, base, *, include_origin=True, include_csrf=True):
    settings = server.settings
    cookie = (
        f"{settings.admin_session_cookie_name}={issue.session_token}; "
        f"{settings.admin_csrf_cookie_name}={issue.csrf_token}"
    )
    headers = {"Cookie": cookie}
    if include_origin:
        headers["Origin"] = base
    if include_csrf:
        headers["X-CSRF-Token"] = issue.csrf_token
    return headers


def customer_headers(server):
    settings = server.settings
    return {
        "Cookie": (
            f"{settings.session_cookie_name}={SESSION_TOKEN}; "
            f"{settings.csrf_cookie_name}={CSRF_TOKEN}"
        )
    }


class CoachingHttpTests(unittest.TestCase):
    def test_customer_read_only_and_staff_rbac_boundaries(self):
        with running_server() as (server, base):
            status, payload = request_json(base, "/api/me/coaching")
            self.assertEqual((status, payload), (401, {"error": "unauthenticated"}))
            status, payload = request_json(
                base, "/api/admin/coaching/members/customer-http"
            )
            self.assertEqual((status, payload), (401, {"error": "admin_unauthenticated"}))

            owner = server.admin_service.bootstrap_owner("owner", "Gravity!Owner123")
            owner_issue = admin_issue(
                server.admin_service, "owner", "Gravity!Owner123", owner.totp_secret
            )
            owner_session = server.admin_service.resolve_session(owner_issue.session_token)
            trainer = server.admin_service.create_admin(
                owner_session, "coach", "Gravity!Coach123", "trainer"
            )
            reception = server.admin_service.create_admin(
                owner_session, "frontdesk", "Gravity!Desk123", "reception"
            )
            trainer_issue = admin_issue(
                server.admin_service, "coach", "Gravity!Coach123", trainer.totp_secret
            )
            desk_issue = admin_issue(
                server.admin_service, "frontdesk", "Gravity!Desk123", reception.totp_secret
            )
            trainer_headers = admin_headers(server, trainer_issue, base)
            desk_headers = admin_headers(server, desk_issue, base)
            no_origin = admin_headers(server, trainer_issue, base, include_origin=False)
            status, payload = request_json(
                base,
                "/api/admin/coaching/members/customer-http/measurements",
                method="POST",
                body={"metricKey": "weight_kg", "value": 82.4},
                headers=no_origin,
            )
            self.assertEqual((status, payload), (403, {"error": "invalid_origin"}))

            no_csrf = admin_headers(server, trainer_issue, base, include_csrf=False)
            status, payload = request_json(
                base,
                "/api/admin/coaching/members/customer-http/measurements",
                method="POST",
                body={"metricKey": "weight_kg", "value": 82.4},
                headers=no_csrf,
            )
            self.assertEqual((status, payload), (403, {"error": "admin_forbidden"}))

            status, payload = request_json(
                base,
                "/api/admin/coaching/members/customer-http/measurements",
                method="POST",
                body={"metricKey": "weight_kg", "value": 82.4},
                headers=trainer_headers,
            )
            self.assertEqual(status, 201)
            self.assertEqual(payload["measurement"]["metricKey"], "weight_kg")
            status, payload = request_json(
                base,
                "/api/admin/coaching/members/customer-http/goals",
                method="POST",
                body={"metricKey": "weight_kg", "targetValue": 78},
                headers=trainer_headers,
            )
            self.assertEqual(status, 201)
            goal_id = payload["goal"]["id"]

            status, payload = request_json(
                base, "/api/admin/coaching/diets", method="POST",
                body={
                    "code": "balanced-indian",
                    "name": "Balanced Indian",
                    "description": "General fitness meal structure",
                },
                headers=trainer_headers,
            )
            self.assertEqual(status, 201)
            template_id = payload["template"]["id"]
            status, payload = request_json(
                base, f"/api/admin/coaching/diets/{template_id}/versions", method="POST",
                body={
                    "title": "Balanced Indian v1",
                    "content": {
                        "dietType": "vegetarian",
                        "meals": [{"name": "Breakfast", "items": ["Poha with vegetables", "Curd"]}],
                        "notes": ["Adjust portions with your coach."],
                    },
                },
                headers=trainer_headers,
            )
            self.assertEqual(status, 201)
            version_id = payload["version"]["id"]
            status, payload = request_json(
                base, f"/api/admin/coaching/diets/{template_id}", method="PATCH",
                body={"status": "active"}, headers=trainer_headers,
            )
            self.assertEqual(status, 200)
            status, payload = request_json(
                base, "/api/admin/coaching/members/customer-http/diet", method="POST",
                body={"versionId": version_id, "note": "Initial coaching plan"},
                headers=trainer_headers,
            )
            self.assertEqual(status, 201)

            status, payload = request_json(
                base, "/api/admin/coaching/members/customer-http",
                headers=desk_headers,
            )
            self.assertEqual((status, payload), (403, {"error": "admin_forbidden"}))

            member_headers = customer_headers(server)
            status, payload = request_json(base, "/api/me/coaching", headers=member_headers)
            self.assertEqual(status, 200)
            coaching = payload["coaching"]
            self.assertEqual(coaching["latestMeasurements"]["weight_kg"]["value"], 82.4)
            self.assertEqual(coaching["goals"][0]["id"], goal_id)
            self.assertEqual(coaching["currentDiet"]["plan"]["version"], 1)
            self.assertIn("not medical advice", coaching["currentDiet"]["plan"]["disclaimer"].lower())

            status, payload = request_json(
                base, "/api/me/coaching", method="POST", body={}, headers=member_headers,
            )
            self.assertEqual((status, payload), (405, {"error": "method_not_allowed"}))


if __name__ == "__main__":
    unittest.main()
