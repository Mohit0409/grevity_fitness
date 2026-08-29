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
TEST_SECRET = "admin-software-http-secret-key-that-is-long-enough"


@contextmanager
def running_server():
    with TemporaryDirectory() as temporary:
        runtime = Path(temporary)
        base = Settings.load(
            root_dir=ROOT,
            environ={"SECRET_KEY": TEST_SECRET, "GRAVITY_PORT": "0", "GRAVITY_LOG_LEVEL": "CRITICAL"},
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
        raw = response.read()
        return response.status, json.loads(raw or b"{}")
    except HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def admin_issue(service, username, password, secret):
    challenge = service.begin_login({"username": username, "password": password}, "127.0.0.1")
    code = _totp_code(secret, int(time.time()) // 30)
    return service.verify_second_factor(
        challenge.challenge_token,
        code,
        remote_addr="127.0.0.1",
        user_agent="GravityAdminSoftwareHttpTest/1.0",
        request_id="admin-software-http",
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


def prepare_owner(server, base):
    owner = server.admin_service.bootstrap_owner("owner", "Gravity!Owner123")
    for plan_id in ("plan-basic-monthly", "plan-pro-monthly", "plan-elite-monthly"):
        server.membership_service.update_plan(
            plan_id, {"status": "active"}, actor_admin_user_id=owner.admin["id"]
        )
    issue = admin_issue(server.admin_service, "owner", "Gravity!Owner123", owner.totp_secret)
    return issue, admin_headers(server, issue, base)


def customer_payload(phone="+919876543210", paid=30000):
    return {
        "displayName": "Rahul Sharma",
        "phone": phone,
        "planId": "plan-basic-monthly",
        "amountPaidPaise": paid,
        "paymentMethod": "cash",
    }


class AdminSoftwareHttpTests(unittest.TestCase):
    def test_owner_customer_payment_fees_and_renewal_workflow(self):
        with running_server() as (server, base):
            status, payload = request_json(base, "/api/admin/customers")
            self.assertEqual((status, payload), (401, {"error": "admin_unauthenticated"}))
            _issue, headers = prepare_owner(server, base)
            status, created = request_json(
                base, "/api/admin/customers", method="POST", body=customer_payload(), headers=headers
            )
            self.assertEqual(status, 201)
            customer_id = created["customer"]["id"]
            membership_id = created["membership"]["id"]
            self.assertEqual(created["paymentSummary"]["pendingPaise"], 69900)

            status, detail = request_json(base, f"/api/admin/customers/{customer_id}", headers=headers)
            self.assertEqual(status, 200)
            self.assertEqual(detail["customer"]["displayName"], "Rahul Sharma")
            self.assertEqual(detail["membership"]["current"]["id"], membership_id)

            payment_headers = {**headers, "Idempotency-Key": "payment-http-key-0001"}
            status, payment = request_json(
                base, f"/api/admin/memberships/{membership_id}/payments", method="POST",
                body={"amountPaise": 20000, "method": "upi"}, headers=payment_headers,
            )
            self.assertEqual(status, 201)
            self.assertEqual(payment["summary"]["pendingPaise"], 49900)
            status, payment_replay = request_json(
                base, f"/api/admin/memberships/{membership_id}/payments", method="POST",
                body={"amountPaise": 20000, "method": "upi"}, headers=payment_headers,
            )
            self.assertEqual(status, 201)
            self.assertEqual(payment_replay["payment"]["id"], payment["payment"]["id"])
            self.assertEqual(payment_replay["summary"]["pendingPaise"], 49900)
            status, fees = request_json(base, "/api/admin/fees?pendingOnly=1", headers=headers)
            self.assertEqual(status, 200)
            self.assertEqual(fees["pendingFeesTotalPaise"], 49900)
            self.assertEqual(len(fees["rows"]), 1)

            renewal_headers = {**headers, "Idempotency-Key": "renewal-http-key-0001"}
            renewal_body = {
                "planId": "plan-pro-monthly",
                "amountPaidPaise": 50000,
                "paymentMethod": "cash",
            }
            status, renewed = request_json(
                base, f"/api/admin/customers/{customer_id}/renew", method="POST",
                body=renewal_body,
                headers=renewal_headers,
            )
            self.assertEqual(status, 201)
            self.assertEqual(renewed["membership"]["status"], "scheduled")
            status, renewed_replay = request_json(
                base, f"/api/admin/customers/{customer_id}/renew", method="POST",
                body=renewal_body, headers=renewal_headers,
            )
            self.assertEqual(status, 201)
            self.assertEqual(renewed_replay["membership"]["id"], renewed["membership"]["id"])
            status, memberships = request_json(base, "/api/admin/memberships", headers=headers)
            self.assertEqual(status, 200)
            self.assertEqual(len(memberships["memberships"]), 2)
            status, dashboard = request_json(base, "/api/admin/dashboard", headers=headers)
            self.assertEqual(status, 200)
            self.assertEqual(dashboard["stats"]["totalCustomers"], 1)
            self.assertEqual(dashboard["stats"]["activeMembers"], 1)

    def test_mutations_require_origin_csrf_and_duplicate_phone_is_conflict(self):
        with running_server() as (server, base):
            issue, headers = prepare_owner(server, base)
            no_origin = admin_headers(server, issue, base, include_origin=False)
            status, payload = request_json(
                base, "/api/admin/customers", method="POST", body=customer_payload(), headers=no_origin
            )
            self.assertEqual((status, payload), (403, {"error": "invalid_origin"}))

            no_csrf = admin_headers(server, issue, base, include_csrf=False)
            status, payload = request_json(
                base, "/api/admin/customers", method="POST", body=customer_payload(), headers=no_csrf
            )
            self.assertEqual((status, payload), (403, {"error": "admin_forbidden"}))

            status, _created = request_json(
                base, "/api/admin/customers", method="POST", body=customer_payload(), headers=headers
            )
            self.assertEqual(status, 201)
            status, duplicate = request_json(
                base, "/api/admin/customers", method="POST", body=customer_payload(), headers=headers
            )
            self.assertEqual(status, 409)
            self.assertEqual(duplicate["error"], "admin_software_conflict")

    def test_reception_operates_customers_but_trainer_cannot_mutate(self):
        with running_server() as (server, base):
            owner_issue, owner_headers = prepare_owner(server, base)
            owner_session = server.admin_service.resolve_session(owner_issue.session_token)
            reception = server.admin_service.create_admin(
                owner_session, "frontdesk", "Gravity!Desk123", "reception"
            )
            trainer = server.admin_service.create_admin(
                owner_session, "trainer1", "Gravity!Train123", "trainer"
            )
            desk_issue = admin_issue(
                server.admin_service, "frontdesk", "Gravity!Desk123", reception.totp_secret
            )
            desk_headers = admin_headers(server, desk_issue, base)
            status, created = request_json(
                base, "/api/admin/customers", method="POST",
                body=customer_payload(phone="+919876500001"), headers=desk_headers,
            )
            self.assertEqual(status, 201)

            trainer_issue = admin_issue(
                server.admin_service, "trainer1", "Gravity!Train123", trainer.totp_secret
            )
            trainer_headers = admin_headers(server, trainer_issue, base)
            status, listed = request_json(base, "/api/admin/customers", headers=trainer_headers)
            self.assertEqual(status, 200)
            self.assertEqual(len(listed["customers"]), 1)
            status, denied = request_json(
                base, "/api/admin/customers", method="POST",
                body=customer_payload(phone="+919876500002"), headers=trainer_headers,
            )
            self.assertEqual((status, denied), (403, {"error": "admin_forbidden"}))
            membership_id = created["membership"]["id"]
            status, denied = request_json(
                base, f"/api/admin/memberships/{membership_id}/payments", method="POST",
                body={"amountPaise": 100, "method": "cash"}, headers=trainer_headers,
            )
            self.assertEqual((status, denied), (403, {"error": "admin_forbidden"}))

    def test_invalid_customer_and_payment_inputs_fail_closed(self):
        with running_server() as (server, base):
            _issue, headers = prepare_owner(server, base)
            status, invalid = request_json(
                base, "/api/admin/customers", method="POST",
                body={"displayName": "R", "phone": "123", "planId": "missing"}, headers=headers,
            )
            self.assertEqual(status, 422)
            self.assertEqual(invalid["error"], "admin_software_validation")

            status, created = request_json(
                base, "/api/admin/customers", method="POST",
                body=customer_payload(phone="+919876500099", paid=0), headers=headers,
            )
            self.assertEqual(status, 201)
            membership_id = created["membership"]["id"]
            invalid_key_headers = {**headers, "Idempotency-Key": "short"}
            status, invalid = request_json(
                base, f"/api/admin/memberships/{membership_id}/payments", method="POST",
                body={"amountPaise": 100, "method": "cash"}, headers=invalid_key_headers,
            )
            self.assertEqual(status, 422)
            self.assertEqual(invalid["error"], "admin_software_validation")
            self.assertIn("idempotencyKey", invalid["fields"])


if __name__ == "__main__":
    unittest.main()
