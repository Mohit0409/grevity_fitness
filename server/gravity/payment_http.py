from __future__ import annotations

from http import HTTPStatus
from urllib.parse import parse_qs, urlsplit
from typing import Any

from .auth import InvalidCsrf
from .payment import (
    PaymentConflict,
    PaymentNotFound,
    PaymentUnavailable,
    PaymentValidationError,
    PaymentVerificationError,
)

PAYMENT_JSON_LIMIT = 16_384
WEBHOOK_BODY_LIMIT = 262_144


def _json(handler: Any, status: HTTPStatus, payload: dict[str, object], request_id: str, send_body: bool) -> HTTPStatus:
    handler._json_response(status, payload, request_id=request_id, send_body=send_body)
    return status


def _session(handler: Any, request_id: str, send_body: bool):
    return handler._require_session(request_id, send_body)


def _mutation_session(handler: Any, request_id: str, send_body: bool):
    if not handler._same_origin():
        return None, _json(handler, HTTPStatus.FORBIDDEN, {"error": "invalid_origin"}, request_id, send_body)
    session, failure = _session(handler, request_id, send_body)
    if session is None:
        return None, failure
    handler._require_csrf(session)
    return session, None


def _error(handler: Any, error: Exception, request_id: str, send_body: bool) -> HTTPStatus:
    if isinstance(error, PaymentUnavailable):
        return _json(handler, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "payment_unavailable"}, request_id, send_body)
    if isinstance(error, PaymentNotFound):
        return _json(handler, HTTPStatus.NOT_FOUND, {"error": "payment_not_found"}, request_id, send_body)
    if isinstance(error, PaymentConflict):
        return _json(handler, HTTPStatus.CONFLICT, {"error": "payment_conflict"}, request_id, send_body)
    if isinstance(error, PaymentValidationError):
        return _json(
            handler,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            {"error": "payment_validation", "fields": error.fields},
            request_id,
            send_body,
        )
    if isinstance(error, PaymentVerificationError):
        return _json(handler, HTTPStatus.BAD_REQUEST, {"error": "payment_verification_failed"}, request_id, send_body)
    if isinstance(error, InvalidCsrf):
        return _json(handler, HTTPStatus.FORBIDDEN, {"error": "invalid_csrf"}, request_id, send_body)
    raise error


def _webhook(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    signatures = handler.headers.get_all("X-Razorpay-Signature", [])
    event_ids = handler.headers.get_all("X-Razorpay-Event-Id", [])
    if len(signatures) != 1 or len(event_ids) != 1:
        return _json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_webhook"}, request_id, send_body)
    raw = handler._raw_body(maximum=WEBHOOK_BODY_LIMIT, content_type="application/json")
    result = handler.server.payment_service.process_webhook(raw, signatures[0], event_ids[0])
    return _json(handler, HTTPStatus.OK, {"received": True, **result}, request_id, send_body)


def _customer_payments(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    if handler.command in {"GET", "HEAD"}:
        session, failure = _session(handler, request_id, send_body)
        if session is None:
            return failure
        raw_limit = parse_qs(urlsplit(handler.path).query).get("limit", ["50"])[0]
        return _json(
            handler,
            HTTPStatus.OK,
            {"payments": handler.server.payment_service.list_customer_payments(session.customer_id, raw_limit)},
            request_id,
            send_body,
        )
    session, failure = _mutation_session(handler, request_id, send_body)
    if session is None:
        return failure
    payload = handler._json_body(maximum=PAYMENT_JSON_LIMIT)
    intent = handler.server.payment_service.create_intent(session.customer_id, str(payload.get("planId", "")))
    return _json(handler, HTTPStatus.CREATED, {"payment": intent}, request_id, send_body)


def _verify_checkout(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _mutation_session(handler, request_id, send_body)
    if session is None:
        return failure
    payload = handler._json_body(maximum=PAYMENT_JSON_LIMIT)
    result = handler.server.payment_service.verify_checkout(
        session.customer_id,
        str(payload.get("intentId", "")),
        razorpay_order_id=str(payload.get("razorpayOrderId", "")),
        razorpay_payment_id=str(payload.get("razorpayPaymentId", "")),
        razorpay_signature=str(payload.get("razorpaySignature", "")),
    )
    return _json(handler, HTTPStatus.OK, result, request_id, send_body)


def _customer_payment(handler: Any, intent_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _session(handler, request_id, send_body)
    if session is None:
        return failure
    payment = handler.server.payment_service.get_intent(session.customer_id, intent_id)
    return _json(handler, HTTPStatus.OK, {"payment": payment}, request_id, send_body)


def _customer_invoices(handler: Any, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _session(handler, request_id, send_body)
    if session is None:
        return failure
    raw_limit = parse_qs(urlsplit(handler.path).query).get("limit", ["50"])[0]
    invoices = handler.server.payment_service.list_customer_invoices(session.customer_id, raw_limit)
    return _json(handler, HTTPStatus.OK, {"invoices": invoices}, request_id, send_body)


def _customer_invoice(handler: Any, invoice_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _session(handler, request_id, send_body)
    if session is None:
        return failure
    invoice = handler.server.payment_service.get_customer_invoice(session.customer_id, invoice_id)
    return _json(handler, HTTPStatus.OK, {"invoice": invoice}, request_id, send_body)


def _receipt(handler: Any, invoice_id: str, request_id: str, send_body: bool) -> HTTPStatus:
    session, failure = _session(handler, request_id, send_body)
    if session is None:
        return failure
    invoice = handler.server.payment_service.get_customer_invoice(session.customer_id, invoice_id)
    payment = handler.server.payment_service.get_intent(session.customer_id, str(invoice["paymentIntentId"]))
    if payment.get("status") != "paid":
        raise PaymentConflict("Payment receipt is not available for an unsettled payment")
    amount = int(invoice["amountPaise"]) / 100
    text = (
        "GRAVITY FITNESS — VERIFIED PAYMENT RECEIPT\n"
        "NOT A TAX INVOICE\n\n"
        f"Receipt reference: {invoice['documentNumber']}\n"
        f"Plan: {invoice['planName']}\n"
        f"Amount paid: {invoice['currency']} {amount:.2f}\n"
        f"Payment provider: {payment['provider']}\n"
        f"Payment status: {payment['status']}\n"
        f"Membership reference: {invoice['membershipId']}\n\n"
        "Tax invoice issuance is pending verified Gravity business/GST identity.\n"
    )
    data = text.encode("utf-8")
    handler.send_response(HTTPStatus.OK)
    handler._security_headers(request_id)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Disposition", f'attachment; filename="Gravity-Payment-Receipt-{invoice["documentNumber"]}.txt"')
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    if send_body:
        handler.wfile.write(data)
    return HTTPStatus.OK


def handle_payment_request(handler: Any, path: str, request_id: str, send_body: bool) -> HTTPStatus | None:
    try:
        if path == "/api/payment/config":
            if handler.command in {"GET", "HEAD"}:
                return _json(handler, HTTPStatus.OK, handler.server.payment_service.public_config(), request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD"}, request_id, send_body)
        if path == "/api/payments/razorpay/webhook":
            if handler.command == "POST":
                return _webhook(handler, request_id, send_body)
            return handler._method_not_allowed({"POST"}, request_id, send_body)
        if path == "/api/me/payments":
            if handler.command in {"GET", "HEAD", "POST"}:
                return _customer_payments(handler, request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD", "POST"}, request_id, send_body)
        if path == "/api/me/payments/verify":
            if handler.command == "POST":
                return _verify_checkout(handler, request_id, send_body)
            return handler._method_not_allowed({"POST"}, request_id, send_body)
        if path == "/api/me/invoices":
            if handler.command in {"GET", "HEAD"}:
                return _customer_invoices(handler, request_id, send_body)
            return handler._method_not_allowed({"GET", "HEAD"}, request_id, send_body)
        if path.startswith("/api/me/payments/"):
            intent_id = path.removeprefix("/api/me/payments/").strip("/")
            if intent_id and "/" not in intent_id:
                if handler.command in {"GET", "HEAD"}:
                    return _customer_payment(handler, intent_id, request_id, send_body)
                return handler._method_not_allowed({"GET", "HEAD"}, request_id, send_body)
        if path.startswith("/api/me/invoices/"):
            suffix = path.removeprefix("/api/me/invoices/").strip("/")
            if suffix.endswith("/receipt"):
                invoice_id = suffix.removesuffix("/receipt").strip("/")
                if invoice_id and "/" not in invoice_id:
                    if handler.command in {"GET", "HEAD"}:
                        return _receipt(handler, invoice_id, request_id, send_body)
                    return handler._method_not_allowed({"GET", "HEAD"}, request_id, send_body)
            if suffix and "/" not in suffix:
                if handler.command in {"GET", "HEAD"}:
                    return _customer_invoice(handler, suffix, request_id, send_body)
                return handler._method_not_allowed({"GET", "HEAD"}, request_id, send_body)
        return None
    except (
        PaymentUnavailable,
        PaymentNotFound,
        PaymentConflict,
        PaymentValidationError,
        PaymentVerificationError,
        InvalidCsrf,
    ) as error:
        return _error(handler, error, request_id, send_body)
