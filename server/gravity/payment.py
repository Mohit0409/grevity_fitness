from __future__ import annotations

from hashlib import sha256
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4
import base64
import hmac
import json
import re
import time

from .config import Settings
from .database import Database
from .membership import MembershipConflict, MembershipService


PROVIDER_ID = re.compile(r"^[A-Za-z0-9_\-]{6,100}$")
ERROR_CODE = re.compile(r"^[A-Za-z0-9_.:\-]{1,80}$")


class PaymentError(Exception):
    pass


class PaymentUnavailable(PaymentError):
    pass


class PaymentNotFound(PaymentError):
    pass
class PaymentConflict(PaymentError):
    pass


class PaymentValidationError(PaymentError):
    def __init__(self, fields: dict[str, str]):
        super().__init__("Payment validation failed")
        self.fields = fields


class PaymentVerificationError(PaymentError):
    pass


class OrderProvider(Protocol):
    @property
    def configured(self) -> bool: ...

    def create_order(
        self,
        *,
        amount_paise: int,
        currency: str,
        receipt: str,
        notes: dict[str, str],
    ) -> dict[str, object]: ...


class RazorpayProvider:
    endpoint = "https://api.razorpay.com/v1/orders"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
    @property
    def configured(self) -> bool:
        return self.settings.razorpay_checkout_configured

    def create_order(
        self,
        *,
        amount_paise: int,
        currency: str,
        receipt: str,
        notes: dict[str, str],
    ) -> dict[str, object]:
        if not self.configured:
            raise PaymentUnavailable("Razorpay checkout is not configured")
        payload = json.dumps({
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt,
            "notes": notes,
        }, separators=(",", ":")).encode("utf-8")
        token = base64.b64encode(
            f"{self.settings.razorpay_key_id}:{self.settings.razorpay_key_secret}".encode("utf-8")
        ).decode("ascii")
        request = Request(
            self.endpoint,
            data=payload,
            method="POST",
            headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                body = response.read()
        except HTTPError as error:
            raise PaymentUnavailable(f"Razorpay order creation failed: HTTP {error.code}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise PaymentUnavailable("Razorpay order creation failed") from error
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PaymentUnavailable("Razorpay returned an invalid order response") from error
        order_id = str(data.get("id", ""))
        if not PROVIDER_ID.fullmatch(order_id):
            raise PaymentUnavailable("Razorpay returned an invalid order id")
        if int(data.get("amount", -1)) != amount_paise or str(data.get("currency", "")) != currency:
            raise PaymentUnavailable("Razorpay order amount or currency mismatch")
        return data


class PaymentService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        membership_service: MembershipService,
        *,
        provider: OrderProvider | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.membership_service = membership_service
        self.provider = provider or RazorpayProvider(settings)
        self.clock = clock or time.time

    def _now(self) -> int:
        return int(self.clock())
    @property
    def checkout_configured(self) -> bool:
        return bool(self.provider.configured and self.settings.razorpay_key_secret)

    @property
    def webhook_configured(self) -> bool:
        return self.settings.razorpay_webhook_configured

    def public_config(self) -> dict[str, object]:
        return {
            "enabled": self.checkout_configured,
            "provider": "razorpay",
            "mode": self.settings.razorpay_mode,
            "keyId": self.settings.razorpay_key_id if self.checkout_configured else None,
        }

    def _safe_intent(self, row) -> dict[str, object]:
        return {
            "id": row["id"],
            "customerId": row["customer_id"],
            "planId": row["plan_id"],
            "planName": row["plan_name_snapshot"],
            "amountPaise": int(row["amount_paise"]),
            "currency": row["currency"],
            "durationMonths": int(row["duration_months_snapshot"]),
            "provider": row["provider"],
            "status": row["status"],
            "providerOrderId": row["provider_order_id"],
            "providerPaymentId": row["provider_payment_id"],
            "createdAt": int(row["created_at"]),
            "paidAt": row["paid_at"],
        }
    def _safe_invoice(self, row) -> dict[str, object] | None:
        if row is None:
            return None
        return {
            "id": row["id"],
            "documentNumber": row["document_number"],
            "paymentIntentId": row["payment_intent_id"],
            "membershipId": row["membership_id"],
            "status": row["status"],
            "planName": row["plan_name_snapshot"],
            "amountPaise": int(row["amount_paise"]),
            "currency": row["currency"],
            "issuedAt": row["issued_at"],
            "createdAt": int(row["created_at"]),
        }

    def _plan_and_customer(self, connection, customer_id: str, plan_id: str):
        customer = connection.execute(
            "SELECT id,status,display_name,email,phone_e164,person_type FROM customers WHERE id=?",
            (customer_id,),
        ).fetchone()
        if customer is None or customer["status"] != "active" or customer["person_type"] != "member":
            raise PaymentValidationError({"customer": "Active customer account is required"})
        plan = connection.execute(
            "SELECT * FROM membership_plans WHERE id=? AND status='active'",
            (plan_id,),
        ).fetchone()
        if plan is None:
            raise PaymentValidationError({"planId": "Active membership plan is required"})
        if int(plan["price_paise"]) <= 0:
            raise PaymentValidationError({"planId": "Paid checkout requires a positive plan price"})
        return customer, plan

    @staticmethod
    def _payload_hash(value: bytes | str) -> str:
        data = value if isinstance(value, bytes) else value.encode("utf-8")
        return sha256(data).hexdigest()
    def create_intent(self, customer_id: str, plan_id: str) -> dict[str, object]:
        if not self.checkout_configured:
            raise PaymentUnavailable("Razorpay checkout is not configured")
        now = self._now()
        intent_id = uuid4().hex
        receipt = f"GF-{intent_id[:24]}"
        with self.database.session() as connection:
            customer, plan = self._plan_and_customer(connection, customer_id, plan_id)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO payment_intents("
                "id,customer_id,plan_id,plan_name_snapshot,amount_paise,currency,duration_months_snapshot,"
                "provider,status,receipt_reference,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    intent_id, customer_id, plan_id, plan["name"], plan["price_paise"], plan["currency"],
                    plan["duration_months"], "razorpay", "creating", receipt, now, now,
                ),
            )
            connection.commit()
        try:
            order = self.provider.create_order(
                amount_paise=int(plan["price_paise"]),
                currency=str(plan["currency"]),
                receipt=receipt,
                notes={"gravity_intent_id": intent_id, "gravity_customer_id": customer_id},
            )
            provider_order_id = str(order.get("id", ""))
        except PaymentError as error:
            self._mark_failed(intent_id, "provider_order_failed")
            raise error
        if not PROVIDER_ID.fullmatch(provider_order_id):
            self._mark_failed(intent_id, "invalid_provider_order")
            raise PaymentUnavailable("Razorpay returned an invalid order id")
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE payment_intents SET status='created',provider_order_id=?,last_error_code=NULL,updated_at=? "
                "WHERE id=? AND status='creating'",
                (provider_order_id, now, intent_id),
            )
            connection.execute(
                "INSERT INTO payment_events(payment_intent_id,event_key,event_type,payload_sha256,created_at) "
                "VALUES (?,?,?,?,?)",
                (intent_id, f"order:{provider_order_id}", "order_created", self._payload_hash(provider_order_id), now),
            )
            row = connection.execute("SELECT * FROM payment_intents WHERE id=?", (intent_id,)).fetchone()
            connection.commit()
        result = self._safe_intent(row)
        result["checkout"] = {
            "keyId": self.settings.razorpay_key_id,
            "orderId": provider_order_id,
            "amountPaise": int(row["amount_paise"]),
            "currency": row["currency"],
        }
        return result

    def _mark_failed(self, intent_id: str, code: str) -> None:
        now = self._now()
        clean = code if ERROR_CODE.fullmatch(code) else "payment_error"
        with self.database.session() as connection:
            connection.execute(
                "UPDATE payment_intents SET status='failed',last_error_code=?,updated_at=? "
                "WHERE id=? AND status='creating'",
                (clean, now, intent_id),
            )

    def get_intent(self, customer_id: str, intent_id: str) -> dict[str, object]:
        with self.database.session() as connection:
            row = connection.execute(
                "SELECT * FROM payment_intents WHERE id=? AND customer_id=?",
                (intent_id, customer_id),
            ).fetchone()
        if row is None:
            raise PaymentNotFound("Payment intent not found")
        return self._safe_intent(row)
    def _intent_row(self, intent_id: str):
        with self.database.session() as connection:
            row = connection.execute("SELECT * FROM payment_intents WHERE id=?", (intent_id,)).fetchone()
        if row is None:
            raise PaymentNotFound("Payment intent not found")
        return row

    def _membership_for_payment(self, payment_id: str) -> dict[str, object] | None:
        with self.database.session() as connection:
            row = connection.execute(
                "SELECT * FROM memberships WHERE payment_reference=?",
                (payment_id,),
            ).fetchone()
        if row is None:
            return None
        return self.membership_service._safe_membership(row, now=self._now())

    def _invoice_for_intent(self, intent_id: str) -> dict[str, object] | None:
        with self.database.session() as connection:
            row = connection.execute(
                "SELECT * FROM invoice_records WHERE payment_intent_id=?",
                (intent_id,),
            ).fetchone()
        return self._safe_invoice(row)

    def _verify_checkout_signature(self, order_id: str, payment_id: str, signature: str) -> None:
        secret = self.settings.razorpay_key_secret
        if not secret:
            raise PaymentUnavailable("Razorpay checkout verification is not configured")
        expected = hmac.new(
            secret.encode("utf-8"),
            f"{order_id}|{payment_id}".encode("utf-8"),
            "sha256",
        ).hexdigest()
        if not hmac.compare_digest(expected, signature.lower()):
            raise PaymentVerificationError("Razorpay payment signature is invalid")
    def verify_checkout(
        self,
        customer_id: str,
        intent_id: str,
        *,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> dict[str, object]:
        if not all(PROVIDER_ID.fullmatch(value or "") for value in (razorpay_order_id, razorpay_payment_id)):
            raise PaymentValidationError({"provider": "Invalid Razorpay identifiers"})
        if not re.fullmatch(r"[A-Fa-f0-9]{64}", razorpay_signature or ""):
            raise PaymentValidationError({"signature": "Invalid Razorpay signature"})
        row = self._intent_row(intent_id)
        if row["customer_id"] != customer_id:
            raise PaymentNotFound("Payment intent not found")
        stored_order_id = str(row["provider_order_id"] or "")
        if row["status"] == "paid":
            if row["provider_payment_id"] != razorpay_payment_id:
                raise PaymentConflict("Payment intent is already settled")
            return {
                "payment": self._safe_intent(row),
                "membership": self._membership_for_payment(razorpay_payment_id),
                "invoice": self._invoice_for_intent(intent_id),
            }
        if row["status"] not in {"created", "failed"}:
            raise PaymentConflict("Payment intent is not payable")
        if razorpay_order_id != stored_order_id:
            raise PaymentVerificationError("Razorpay order does not match the server order")
        self._verify_checkout_signature(stored_order_id, razorpay_payment_id, razorpay_signature)
        return self._finalize_verified_payment(
            row,
            razorpay_payment_id,
            event_key=f"checkout:{razorpay_payment_id}",
            event_type="checkout_verified",
            payload_hash=self._payload_hash(f"{stored_order_id}|{razorpay_payment_id}"),
        )

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> None:
        secret = self.settings.razorpay_webhook_secret
        if not secret:
            raise PaymentUnavailable("Razorpay webhook verification is not configured")
        if not re.fullmatch(r"[A-Fa-f0-9]{64}", signature or ""):
            raise PaymentVerificationError("Razorpay webhook signature is invalid")
        expected = hmac.new(secret.encode("utf-8"), raw_body, "sha256").hexdigest()
        if not hmac.compare_digest(expected, signature.lower()):
            raise PaymentVerificationError("Razorpay webhook signature is invalid")

    def _record_webhook_event(
        self,
        *,
        event_id: str,
        event_type: str,
        payload_hash: str,
        intent_id: str | None,
    ) -> bool:
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT 1 FROM payment_events WHERE provider_event_id=?",
                (event_id,),
            ).fetchone()
            if existing:
                connection.commit()
                return False
            connection.execute(
                "INSERT INTO payment_events(payment_intent_id,event_key,event_type,provider_event_id,payload_sha256,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (intent_id, f"webhook:{event_id}", event_type, event_id, payload_hash, now),
            )
            connection.commit()
        return True
    def _ensure_membership(self, row, payment_id: str) -> dict[str, object]:
        membership = self._membership_for_payment(payment_id)
        if membership is not None:
            return membership
        try:
            return self.membership_service.create_membership(
                str(row["customer_id"]),
                str(row["plan_id"]),
                source="payment",
                payment_reference=payment_id,
            )
        except MembershipConflict as error:
            membership = self._membership_for_payment(payment_id)
            if membership is not None:
                return membership
            raise PaymentConflict("Payment verified but membership activation conflicted") from error

    def _finalize_verified_payment(
        self,
        row,
        payment_id: str,
        *,
        event_key: str,
        event_type: str,
        payload_hash: str,
        provider_event_id: str | None = None,
    ) -> dict[str, object]:
        membership = self._ensure_membership(row, payment_id)
        now = self._now()
        intent_id = str(row["id"])
        document_number = f"GFD-{intent_id[:12].upper()}"
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute("SELECT * FROM payment_intents WHERE id=?", (intent_id,)).fetchone()
            if current is None:
                connection.rollback()
                raise PaymentNotFound("Payment intent not found")
            if current["status"] == "paid":
                connection.commit()
                return {
                    "payment": self._safe_intent(current),
                    "membership": self._membership_for_payment(str(current["provider_payment_id"])),
                    "invoice": self._invoice_for_intent(intent_id),
                }
            if current["status"] not in {"created", "failed"}:
                connection.rollback()
                raise PaymentConflict("Payment intent is not payable")
            connection.execute(
                "UPDATE payment_intents SET status='paid',provider_payment_id=?,paid_at=?,updated_at=?,last_error_code=NULL WHERE id=?",
                (payment_id, now, now, intent_id),
            )
            connection.execute(
                "INSERT OR IGNORE INTO payment_events("
                "payment_intent_id,event_key,event_type,provider_event_id,payload_sha256,created_at"
                ") VALUES (?,?,?,?,?,?)",
                (intent_id, event_key, event_type, provider_event_id, payload_hash, now),
            )
            connection.execute(
                "INSERT OR IGNORE INTO invoice_records("
                "id,document_number,payment_intent_id,customer_id,membership_id,status,"
                "plan_name_snapshot,amount_paise,currency,seller_snapshot_json,customer_snapshot_json,"
                "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uuid4().hex,
                    document_number,
                    intent_id,
                    current["customer_id"],
                    membership["id"],
                    "pending_business_identity",
                    current["plan_name_snapshot"],
                    current["amount_paise"],
                    current["currency"],
                    "{}",
                    "{}",
                    now,
                    now,
                ),
            )
            paid = connection.execute("SELECT * FROM payment_intents WHERE id=?", (intent_id,)).fetchone()
            invoice = connection.execute(
                "SELECT * FROM invoice_records WHERE payment_intent_id=?",
                (intent_id,),
            ).fetchone()
            connection.commit()
        return {
            "payment": self._safe_intent(paid),
            "membership": membership,
            "invoice": self._safe_invoice(invoice),
        }
    def _webhook_seen(self, event_id: str) -> bool:
        with self.database.session() as connection:
            row = connection.execute(
                "SELECT 1 FROM payment_events WHERE provider_event_id=?",
                (event_id,),
            ).fetchone()
        return row is not None

    def _intent_by_order(self, order_id: str):
        with self.database.session() as connection:
            return connection.execute(
                "SELECT * FROM payment_intents WHERE provider_order_id=?",
                (order_id,),
            ).fetchone()

    def process_webhook(self, raw_body: bytes, signature: str, event_id: str) -> dict[str, object]:
        self.verify_webhook_signature(raw_body, signature)
        if not PROVIDER_ID.fullmatch(event_id or ""):
            raise PaymentValidationError({"eventId": "Invalid Razorpay event id"})
        if self._webhook_seen(event_id):
            return {"duplicate": True, "processed": False}
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PaymentValidationError({"payload": "Invalid Razorpay webhook payload"}) from error
        event_type = str(payload.get("event", ""))
        if not re.fullmatch(r"[a-z0-9_.-]{1,80}", event_type):
            raise PaymentValidationError({"event": "Invalid Razorpay event type"})
        payment_entity = (((payload.get("payload") or {}).get("payment") or {}).get("entity") or {})
        order_entity = (((payload.get("payload") or {}).get("order") or {}).get("entity") or {})
        order_id = str(payment_entity.get("order_id") or order_entity.get("id") or "")
        payment_id = str(payment_entity.get("id") or "")
        payload_hash = self._payload_hash(raw_body)
        intent = self._intent_by_order(order_id) if order_id else None
        intent_id = str(intent["id"]) if intent is not None else None
        if event_type not in {"payment.captured", "order.paid", "payment.failed"}:
            self._record_webhook_event(
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                intent_id=intent_id,
            )
            return {"duplicate": False, "processed": False, "ignored": True}
        if intent is None:
            self._record_webhook_event(
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                intent_id=None,
            )
            return {"duplicate": False, "processed": False, "ignored": True}
        if event_type == "payment.failed":
            now = self._now()
            with self.database.session() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE payment_intents SET status='failed',last_error_code='provider_payment_failed',updated_at=? "
                    "WHERE id=? AND status='created'",
                    (now, intent["id"]),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO payment_events(payment_intent_id,event_key,event_type,provider_event_id,payload_sha256,created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (intent["id"], f"webhook:{event_id}", event_type, event_id, payload_hash, now),
                )
                connection.commit()
            return {"duplicate": False, "processed": True, "status": "failed"}
        if not PROVIDER_ID.fullmatch(payment_id) or order_id != str(intent["provider_order_id"]):
            raise PaymentVerificationError("Razorpay webhook payment identifiers do not match the server order")
        try:
            amount = int(payment_entity.get("amount", -1))
        except (TypeError, ValueError) as error:
            raise PaymentVerificationError("Razorpay webhook amount is invalid") from error
        currency = str(payment_entity.get("currency", ""))
        if amount != int(intent["amount_paise"]) or currency != str(intent["currency"]):
            raise PaymentVerificationError("Razorpay webhook amount or currency mismatch")
        if intent["status"] == "paid":
            self._record_webhook_event(
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                intent_id=str(intent["id"]),
            )
            return {"duplicate": False, "processed": False, "status": "paid"}
        result = self._finalize_verified_payment(
            intent,
            payment_id,
            event_key=f"webhook:{event_id}",
            event_type=event_type,
            payload_hash=payload_hash,
            provider_event_id=event_id,
        )
        return {
            "duplicate": False,
            "processed": True,
            "status": "paid",
            "payment": result["payment"],
            "membership": result["membership"],
            "invoice": result["invoice"],
        }

    def list_customer_payments(self, customer_id: str, limit: int = 50) -> list[dict[str, object]]:
        try:
            bounded = max(1, min(int(limit), 100))
        except (TypeError, ValueError):
            bounded = 50
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT * FROM payment_intents WHERE customer_id=? ORDER BY created_at DESC,id DESC LIMIT ?",
                (customer_id, bounded),
            ).fetchall()
        return [self._safe_intent(row) for row in rows]

    def list_customer_invoices(self, customer_id: str, limit: int = 50) -> list[dict[str, object]]:
        try:
            bounded = max(1, min(int(limit), 100))
        except (TypeError, ValueError):
            bounded = 50
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT * FROM invoice_records WHERE customer_id=? ORDER BY created_at DESC,id DESC LIMIT ?",
                (customer_id, bounded),
            ).fetchall()
        return [self._safe_invoice(row) for row in rows if row is not None]

    def get_customer_invoice(self, customer_id: str, invoice_id: str) -> dict[str, object]:
        with self.database.session() as connection:
            row = connection.execute(
                "SELECT * FROM invoice_records WHERE id=? AND customer_id=?",
                (invoice_id, customer_id),
            ).fetchone()
        if row is None:
            raise PaymentNotFound("Invoice not found")
        return self._safe_invoice(row) or {}
