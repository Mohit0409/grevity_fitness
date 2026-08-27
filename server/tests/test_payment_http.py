from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4
import hmac
import json
import time
import unittest

from server.gravity.config import Settings
from server.gravity.http import create_server

ROOT = Path(__file__).resolve().parents[2]
KEY_SECRET = "rzp_test_secret_for_http_tests"
WEBHOOK_SECRET = "rzp_webhook_secret_for_http_tests"
SESSION_TOKEN = "phase6-customer-session-token"
CSRF_TOKEN = "phase6-customer-csrf-token"


class FakeOrderProvider:
    configured = True
    def __init__(self):
        self.counter = 0
    def create_order(self, *, amount_paise, currency, receipt, notes):
        self.counter += 1
        return {"id": f"order_http_{self.counter:04d}", "amount": amount_paise, "currency": currency}


@contextmanager
def running_server():
    with TemporaryDirectory() as temporary:
        runtime = Path(temporary)
        base = Settings.load(
            root_dir=ROOT,
            environ={
                "SECRET_KEY": "phase-six-http-secret-long-enough",
                "GRAVITY_PORT": "0",
                "GRAVITY_LOG_LEVEL": "CRITICAL",
                "RAZORPAY_MODE": "test",
                "RAZORPAY_KEY_ID": "rzp_test_http_key",
                "RAZORPAY_KEY_SECRET": KEY_SECRET,
                "RAZORPAY_WEBHOOK_SECRET": WEBHOOK_SECRET,
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
        server.payment_service.provider = FakeOrderProvider()
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
            connection.execute("UPDATE membership_plans SET status='active' WHERE id='plan-basic-monthly'")
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


def request_json(base, path, *, method="GET", body=None, raw=None, headers=None):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode("utf-8"))
    merged = {"Accept": "application/json", **(headers or {})}
    if data is not None and "Content-Type" not in merged:
        merged["Content-Type"] = "application/json"
    request = Request(base + path, data=data, method=method, headers=merged)
    try:
        response = urlopen(request, timeout=5)
        return response.status, json.loads(response.read() or b"{}")
    except HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def request_bytes(base, path, *, method="GET", headers=None):
    request = Request(base + path, method=method, headers=headers or {})
    try:
        response = urlopen(request, timeout=5)
        return response.status, dict(response.headers), response.read()
    except HTTPError as error:
        return error.code, dict(error.headers), error.read()


def customer_headers(base, *, include_origin=True, include_csrf=True):
    headers = {"Cookie": f"gravity_session={SESSION_TOKEN}; gravity_csrf={CSRF_TOKEN}"}
    if include_origin:
        headers["Origin"] = base
    if include_csrf:
        headers["X-CSRF-Token"] = CSRF_TOKEN
    return headers


def checkout_signature(order_id, payment_id):
    return hmac.new(KEY_SECRET.encode(), f"{order_id}|{payment_id}".encode(), sha256).hexdigest()


def webhook_signature(raw):
    return hmac.new(WEBHOOK_SECRET.encode(), raw, sha256).hexdigest()


class PaymentHttpTests(unittest.TestCase):
    def test_payment_http_boundaries_and_server_owned_state(self):
        with running_server() as (server, base):
            status, config = request_json(base, "/api/payment/config")
            self.assertEqual(status, 200)
            self.assertTrue(config["enabled"])
            self.assertEqual(config["keyId"], "rzp_test_http_key")
            self.assertNotIn(KEY_SECRET, json.dumps(config))
            headers = customer_headers(base)
            no_origin = customer_headers(base, include_origin=False)
            status, payload = request_json(
                base, "/api/me/payments", method="POST",
                body={"planId": "plan-basic-monthly"}, headers=no_origin,
            )
            self.assertEqual((status, payload), (403, {"error": "invalid_origin"}))

            status, payload = request_json(
                base, "/api/me/payments", method="POST",
                body={"planId": "plan-basic-monthly", "amountPaise": 1}, headers=headers,
            )
            self.assertEqual(status, 201)
            payment = payload["payment"]
            self.assertEqual(payment["amountPaise"], 99900)
            self.assertEqual(payment["planName"], "Basic")
            self.assertEqual(payment["checkout"]["amountPaise"], 99900)
            order_id = payment["providerOrderId"]

            status, listing = request_json(base, "/api/me/payments", headers=headers)
            self.assertEqual(status, 200)
            self.assertEqual(listing["payments"][0]["id"], payment["id"])

            status, bad = request_json(
                base, "/api/me/payments/verify", method="POST",
                body={
                    "intentId": payment["id"], "razorpayOrderId": order_id,
                    "razorpayPaymentId": "pay_http_bad", "razorpaySignature": "0" * 64,
                }, headers=headers,
            )
            self.assertEqual((status, bad), (400, {"error": "payment_verification_failed"}))
            payment_id = "pay_http_0001"
            signature = checkout_signature(order_id, payment_id)
            status, settled = request_json(
                base, "/api/me/payments/verify", method="POST",
                body={
                    "intentId": payment["id"], "razorpayOrderId": order_id,
                    "razorpayPaymentId": payment_id, "razorpaySignature": signature,
                }, headers=headers,
            )
            self.assertEqual(status, 200)
            self.assertEqual(settled["payment"]["status"], "paid")
            self.assertEqual(settled["membership"]["source"], "payment")
            self.assertEqual(settled["invoice"]["status"], "pending_business_identity")

            status, invoices = request_json(base, "/api/me/invoices", headers=headers)
            self.assertEqual(status, 200)
            self.assertEqual(len(invoices["invoices"]), 1)
            invoice_id = invoices["invoices"][0]["id"]
            status, invoice = request_json(base, f"/api/me/invoices/{invoice_id}", headers=headers)
            self.assertEqual(status, 200)
            self.assertEqual(invoice["invoice"]["documentNumber"], settled["invoice"]["documentNumber"])
            status, receipt_headers, receipt = request_bytes(
                base, f"/api/me/invoices/{invoice_id}/receipt", headers=headers,
            )
            self.assertEqual(status, 200, receipt.decode("utf-8", errors="replace"))
            self.assertIn("attachment;", receipt_headers.get("Content-Disposition", ""))
            text = receipt.decode("utf-8")
            self.assertIn("VERIFIED PAYMENT RECEIPT", text)
            self.assertIn("NOT A TAX INVOICE", text)
            self.assertNotIn(KEY_SECRET, text)
            no_csrf = customer_headers(base, include_csrf=False)
            status, payload = request_json(
                base, "/api/me/payments", method="POST",
                body={"planId": "plan-basic-monthly"}, headers=no_csrf,
            )
            self.assertEqual((status, payload), (403, {"error": "invalid_csrf"}))

            status, payload = request_json(
                base, "/api/me/payments", method="POST",
                body={"planId": "plan-basic-monthly"}, headers=headers,
            )
            self.assertEqual(status, 201)
            webhook_payment = payload["payment"]
            webhook_payment_id = "pay_http_0002"
            raw = json.dumps({
                "event": "payment.captured",
                "payload": {"payment": {"entity": {
                    "id": webhook_payment_id,
                    "order_id": webhook_payment["providerOrderId"],
                    "amount": 99900,
                    "currency": "INR",
                }}},
            }, separators=(",", ":")).encode()
            webhook_headers = {
                "X-Razorpay-Signature": webhook_signature(raw),
                "X-Razorpay-Event-Id": "evt_http_0002",
                "Content-Type": "application/json",
            }
            status, webhook = request_json(
                base, "/api/payments/razorpay/webhook", method="POST",
                raw=raw, headers=webhook_headers,
            )
            self.assertEqual(status, 200)
            self.assertTrue(webhook["received"])
            self.assertTrue(webhook["processed"])
            self.assertEqual(webhook["status"], "paid")

            status, duplicate = request_json(
                base, "/api/payments/razorpay/webhook", method="POST",
                raw=raw, headers=webhook_headers,
            )
            self.assertEqual(status, 200)
            self.assertTrue(duplicate["duplicate"])
            self.assertFalse(duplicate["processed"])

            status, missing = request_json(
                base, "/api/payments/razorpay/webhook", method="POST", raw=raw,
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual((status, missing), (400, {"error": "invalid_webhook"}))

            status, unauth = request_json(base, "/api/me/payments")
            self.assertEqual((status, unauth), (401, {"error": "unauthenticated"}))


if __name__ == "__main__":
    unittest.main()
