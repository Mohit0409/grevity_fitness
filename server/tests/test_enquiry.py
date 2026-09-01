from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from http.cookies import SimpleCookie
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json
import unittest

from server.gravity.admin import AdminForbidden, AdminService, AdminSessionIdentity
from server.gravity.config import Settings
from server.gravity.database import Database
from server.gravity.enquiry import (
    EnquiryConflict,
    EnquiryRateLimitExceeded,
    EnquiryService,
    EnquiryValidationError,
)
from server.gravity.http import create_server


ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "phase-recovery-enquiry-secret-key-long-enough"
FIXED_NOW = 1_788_000_000


class MutableClock:
    def __init__(self, value: int = FIXED_NOW) -> None:
        self.value = value

    def __call__(self) -> float:
        return float(self.value)


def valid_payload(**changes):
    payload = {
        "type": "trial_visit",
        "name": "Aarav Sharma",
        "phone": "79995 26112",
        "email": "aarav@example.com",
        "preferredDate": "2026-09-01",
        "preferredTime": "morning",
        "message": "I would like to visit.",
        "website": "",
    }
    payload.update(changes)
    return payload


class EnquiryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        runtime = Path(self.temporary.name)
        self.settings = Settings.load(
            root_dir=ROOT,
            environ={
                "SECRET_KEY": TEST_SECRET,
                "GRAVITY_DATA_DIR": str(runtime / "data"),
                "GRAVITY_LOG_DIR": str(runtime / "logs"),
                "GRAVITY_BACKUP_DIR": str(runtime / "backups"),
                "APP_BASE_URL": "http://127.0.0.1:8787",
            },
        )
        self.settings.ensure_directories()
        self.database = Database(self.settings.database_path, self.settings.migrations_dir)
        self.database.migrate()
        self.clock = MutableClock()
        self.admin = AdminService(self.database, self.settings, clock=self.clock)
        self.service = EnquiryService(self.database, self.settings, self.admin, clock=self.clock)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_verified_plans_are_active_without_invented_descriptions(self):
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT name,price_paise,duration_months,status,description FROM membership_plans ORDER BY sort_order"
            ).fetchall()
        self.assertEqual(
            [(row["name"], row["price_paise"]) for row in rows],
            [("1 Month", 120000), ("3 Months", 300000), ("1 Year", 1000000)],
        )
        self.assertTrue(all(row["status"] == "active" for row in rows))
        self.assertEqual([row["duration_months"] for row in rows], [1, 3, 12])
        self.assertTrue(all(row["description"] is None for row in rows))

    def test_csrf_creation_idempotency_and_no_raw_ip_storage(self):
        issue = self.service.issue_csrf()
        self.service.verify_csrf(issue.token, issue.token)
        created, replayed = self.service.create(
            valid_payload(), idempotency_key="fixed-key-1234567890", remote_addr="203.0.113.44", request_id="request-one"
        )
        self.assertFalse(replayed)
        self.assertRegex(created["reference"], r"^GF-\d{6}-[A-F0-9]{6}$")
        repeated, replayed = self.service.create(
            valid_payload(), idempotency_key="fixed-key-1234567890", remote_addr="203.0.113.44", request_id="request-two"
        )
        self.assertTrue(replayed)
        self.assertEqual(repeated["reference"], created["reference"])
        with self.assertRaises(EnquiryConflict):
            self.service.create(
                valid_payload(name="Different Name"), idempotency_key="fixed-key-1234567890",
                remote_addr="203.0.113.44", request_id="request-three",
            )
        with self.database.session() as connection:
            raw = json.dumps([dict(row) for row in connection.execute("SELECT * FROM public_enquiry_rate_limits")])
        self.assertNotIn("203.0.113.44", raw)

    def test_validation_date_bounds_honeypot_and_rate_limits(self):
        with self.assertRaises(EnquiryValidationError) as context:
            self.service.create(
                valid_payload(phone="123", preferredDate="2030-01-01", website="spam.example"),
                idempotency_key="invalid-payload-key-1", remote_addr="198.51.100.2", request_id="bad",
            )
        self.assertEqual(set(context.exception.fields), {"phone", "preferredDate", "request"})
        for index in range(4):
            self.service.create(
                valid_payload(name=f"Visitor {chr(65 + index)}"),
                idempotency_key=f"contact-rate-key-{index:02d}", remote_addr=f"198.51.100.{20 + index}",
                request_id=f"rate-{index}",
            )
        with self.assertRaises(EnquiryRateLimitExceeded):
            self.service.create(
                valid_payload(name="Visitor Z"), idempotency_key="contact-rate-key-99",
                remote_addr="198.51.100.99", request_id="rate-blocked",
            )

    def test_admin_owner_and_reception_manage_trainer_is_denied(self):
        created, _ = self.service.create(
            valid_payload(), idempotency_key="admin-list-key-123", remote_addr="127.0.0.1", request_id="received"
        )
        owner = self.admin.bootstrap_owner("owner", "Gravity!Owner123")
        owner_session = AdminSessionIdentity("session", str(owner.admin["id"]), "csrf", owner.admin)
        reception = self.admin.create_admin(owner_session, "frontdesk", "Gravity!Desk123", "reception")
        trainer = self.admin.create_admin(owner_session, "coach", "Gravity!Coach123", "trainer")
        reception_session = AdminSessionIdentity("desk", str(reception.admin["id"]), "csrf", reception.admin)
        trainer_session = AdminSessionIdentity("coach", str(trainer.admin["id"]), "csrf", trainer.admin)
        rows = self.service.list_admin(reception_session, status="new")
        self.assertEqual(rows[0]["reference"], created["reference"])
        updated = self.service.set_status(
            reception_session, str(rows[0]["id"]), "contacted", request_id="status"
        )
        self.assertEqual(updated["status"], "contacted")
        detailed = self.service.add_note(
            reception_session, str(rows[0]["id"]), "Called; awaiting confirmation.", request_id="note"
        )
        self.assertEqual(detailed["notes"][0]["note"], "Called; awaiting confirmation.")
        with self.assertRaises(AdminForbidden):
            self.service.list_admin(trainer_session)

    def test_expired_enquiry_pii_and_children_are_purged(self):
        self.service.create(
            valid_payload(), idempotency_key="retention-test-key-1234",
            remote_addr="192.0.2.10", request_id="retention-create",
        )
        with self.database.session() as connection:
            enquiry_id = connection.execute("SELECT id FROM public_enquiries").fetchone()["id"]
            connection.execute(
                "UPDATE public_enquiries SET retention_expires_at=? WHERE id=?",
                (FIXED_NOW - 1, enquiry_id),
            )
        self.assertEqual(self.service.purge_expired(), 1)
        with self.database.session() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM public_enquiries").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM public_enquiry_events").fetchone()[0], 0)


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
            data_dir=runtime / "data", log_dir=runtime / "logs", backup_dir=runtime / "backups",
            database_path=runtime / "data" / "gravity.sqlite3", host="127.0.0.1", port=0,
        )
        server = create_server(settings)
        base = f"http://127.0.0.1:{server.server_port}"
        server.settings = replace(server.settings, app_base_url=base)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server, base
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def exchange(base, path, *, method="GET", body=None, headers=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(base + path, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        response = urlopen(request, timeout=5)
        return response.status, response.headers, json.loads(response.read() or b"{}")
    except HTTPError as error:
        return error.code, error.headers, json.loads(error.read() or b"{}")


class EnquiryHttpTests(unittest.TestCase):
    def test_public_contract_requires_origin_csrf_and_is_idempotent(self):
        with running_server() as (_server, base):
            status, headers, payload = exchange(base, "/api/enquiries/token")
            self.assertEqual(status, 200)
            cookies = SimpleCookie()
            cookies.load(headers.get("Set-Cookie"))
            token = payload["csrfToken"]
            common = {
                "Origin": base,
                "Cookie": f"gravity_enquiry_csrf={cookies['gravity_enquiry_csrf'].value}",
                "X-Enquiry-CSRF-Token": token,
                "Idempotency-Key": "http-enquiry-key-1234",
            }
            status, _, payload = exchange(base, "/api/enquiries", method="POST", body=valid_payload(), headers=common)
            self.assertEqual(status, 201)
            self.assertEqual(payload["enquiry"]["status"], "received")
            status, _, payload = exchange(base, "/api/enquiries", method="POST", body=valid_payload(), headers=common)
            self.assertEqual(status, 200)
            self.assertTrue(payload["enquiry"]["replayed"])
            bad_origin = dict(common, Origin="https://evil.example", **{"Idempotency-Key": "http-enquiry-key-9999"})
            status, _, payload = exchange(base, "/api/enquiries", method="POST", body=valid_payload(), headers=bad_origin)
            self.assertEqual((status, payload), (403, {"error": "invalid_origin"}))
            missing_csrf = {"Origin": base, "Idempotency-Key": "http-enquiry-key-7777"}
            status, _, payload = exchange(base, "/api/enquiries", method="POST", body=valid_payload(), headers=missing_csrf)
            self.assertEqual((status, payload), (403, {"error": "forbidden"}))

    def test_admin_enquiry_list_requires_authenticated_rbac(self):
        with running_server() as (_server, base):
            status, _, payload = exchange(base, "/api/admin/enquiries")
            self.assertEqual((status, payload), (401, {"error": "admin_unauthenticated"}))


if __name__ == "__main__":
    unittest.main()
