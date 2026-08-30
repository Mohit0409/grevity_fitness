from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import smtplib

from .config import Settings
from .notification import (
    NotificationConflict,
    NotificationRecipientUnavailable,
    NotificationService,
)


IST = timezone(timedelta(hours=5, minutes=30))


class DeliveryAdapterError(Exception):
    def __init__(self, code: str = "provider_error") -> None:
        super().__init__(code)
        self.code = code


class DeliveryAdapter(Protocol):
    channel: str

    def send(self, *, recipient: str, subject: str, body: str, context: dict[str, object] | None = None) -> str | None:
        ...


class SMTPEmailAdapter:
    channel = "email"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, *, recipient: str, subject: str, body: str, context: dict[str, object] | None = None) -> str | None:
        if not self.settings.smtp_configured:
            raise DeliveryAdapterError("smtp_not_configured")
        message_id = make_msgid(domain=None)
        message = EmailMessage()
        message["From"] = self.settings.email_from
        message["To"] = recipient
        message["Subject"] = subject
        message["Message-ID"] = message_id
        message.set_content(body)
        try:
            if self.settings.smtp_security == "ssl":
                client = smtplib.SMTP_SSL(self.settings.smtp_host, self.settings.smtp_port, timeout=15)
            else:
                client = smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15)
            with client:
                client.ehlo()
                if self.settings.smtp_security == "starttls":
                    client.starttls()
                    client.ehlo()
                client.login(self.settings.smtp_username, self.settings.smtp_password)
                client.send_message(message)
        except (OSError, smtplib.SMTPException):
            raise DeliveryAdapterError("smtp_delivery_failed") from None
        return message_id


class SMSDeliveryAdapter:
    """Provider boundary for an externally selected SMS API.

    Gravity deliberately does not guess a commercial SMS vendor. The injected
    sender is responsible for the provider-specific HTTPS call and must return
    only a safe provider message identifier.
    """

    channel = "sms"

    def __init__(self, sender: Callable[[str, str], str | None]) -> None:
        self.sender = sender

    def send(self, *, recipient: str, subject: str, body: str, context: dict[str, object] | None = None) -> str | None:
        try:
            return self.sender(recipient, body)
        except DeliveryAdapterError:
            raise
        except Exception:
            raise DeliveryAdapterError("sms_delivery_failed") from None


class WhatsAppDeliveryAdapter:
    """Provider boundary for an externally selected WhatsApp Business API."""

    channel = "whatsapp"

    def __init__(self, sender: Callable[[str, str], str | None]) -> None:
        self.sender = sender

    def send(self, *, recipient: str, subject: str, body: str, context: dict[str, object] | None = None) -> str | None:
        try:
            return self.sender(recipient, body)
        except DeliveryAdapterError:
            raise
        except Exception:
            raise DeliveryAdapterError("whatsapp_delivery_failed") from None


def _post_json(url: str, *, headers: dict[str, str], payload: dict[str, object], failure_code: str) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read(65536)
    except HTTPError as error:
        raise DeliveryAdapterError(f"{failure_code}_http_{error.code}") from None
    except (URLError, OSError, TimeoutError):
        raise DeliveryAdapterError(f"{failure_code}_network") from None
    try:
        result = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, ValueError):
        raise DeliveryAdapterError(f"{failure_code}_invalid_response") from None
    if not isinstance(result, dict):
        raise DeliveryAdapterError(f"{failure_code}_invalid_response")
    return result


def _normalized_phone(value: str) -> str:
    return value.strip().replace(" ", "").lstrip("+")


def _provider_values(context: dict[str, object]) -> dict[str, str]:
    payload = dict(context.get("payload") or {})
    ends_at = int(payload.get("endsAt") or 0)
    expiry = (
        datetime.fromtimestamp(ends_at, tz=IST).strftime("%d %b %Y")
        if ends_at > 0
        else "the recorded end date"
    )
    days = int(context.get("triggerDays") or 0)
    timing = "expired today" if days == 0 else f"expires in {days} day{'s' if days != 1 else ''}"
    return {
        "name": str(context.get("displayName") or "Member")[:80],
        "plan": str(payload.get("planName") or "membership")[:80],
        "timing": timing[:80],
        "expiry": expiry[:80],
        "number": str(payload.get("membershipNumber") or "-")[:80],
    }


class MetaWhatsAppAdapter:
    channel = "whatsapp"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, *, recipient: str, subject: str, body: str, context: dict[str, object] | None = None) -> str | None:
        if context is None or not self.settings.whatsapp_credentials_configured:
            raise DeliveryAdapterError("whatsapp_not_configured")
        role = str(context.get("recipientRole") or "customer")
        template = self.settings.whatsapp_owner_template if role == "owner" else self.settings.whatsapp_customer_template
        values = _provider_values(context)
        parameters = [
            {"type": "text", "text": values[key]}
            for key in ("name", "plan", "timing", "expiry", "number")
        ]
        payload = {
            "messaging_product": "whatsapp",
            "to": _normalized_phone(recipient),
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": self.settings.whatsapp_template_language},
                "components": [{"type": "body", "parameters": parameters}],
            },
        }
        result = _post_json(
            f"https://graph.facebook.com/{self.settings.whatsapp_graph_version}/{self.settings.whatsapp_phone_number_id}/messages",
            headers={"Authorization": f"Bearer {self.settings.whatsapp_access_token}", "Content-Type": "application/json"},
            payload=payload,
            failure_code="whatsapp",
        )
        messages = result.get("messages")
        if not isinstance(messages, list) or not messages or not isinstance(messages[0], dict):
            raise DeliveryAdapterError("whatsapp_provider_rejected")
        message_id = str(messages[0].get("id") or "")
        if not message_id:
            raise DeliveryAdapterError("whatsapp_invalid_response")
        return message_id


class MSG91SMSAdapter:
    channel = "sms"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, *, recipient: str, subject: str, body: str, context: dict[str, object] | None = None) -> str | None:
        if context is None or not self.settings.sms_credentials_configured:
            raise DeliveryAdapterError("sms_not_configured")
        role = str(context.get("recipientRole") or "customer")
        flow_id = self.settings.sms_owner_flow_id if role == "owner" else self.settings.sms_customer_flow_id
        values = _provider_values(context)
        payload = {
            "flow_id": flow_id,
            "sender": self.settings.sms_sender_id,
            "recipients": [{
                "mobiles": _normalized_phone(recipient),
                "name": values["name"],
                "expiry": values["expiry"],
            }],
        }
        result = _post_json(
            "https://control.msg91.com/api/v5/flow",
            headers={"authkey": self.settings.sms_api_key, "Content-Type": "application/json", "Accept": "application/json"},
            payload=payload,
            failure_code="sms",
        )
        response_type = str(result.get("type") or "").lower()
        if response_type and response_type != "success":
            raise DeliveryAdapterError("sms_provider_rejected")
        message_id = str(result.get("message") or result.get("request_id") or result.get("requestId") or "")
        if not message_id:
            raise DeliveryAdapterError("sms_invalid_response")
        return message_id


class NotificationDispatcher:
    def __init__(self, service: NotificationService, adapters: dict[str, DeliveryAdapter] | None = None) -> None:
        self.service = service
        self.adapters = dict(adapters or {})

    @classmethod
    def from_settings(cls, service: NotificationService, settings: Settings) -> "NotificationDispatcher":
        adapters: dict[str, DeliveryAdapter] = {}
        if settings.smtp_configured:
            adapters["email"] = SMTPEmailAdapter(settings)
        if settings.sms_credentials_configured and settings.sms_adapter_supported:
            adapters["sms"] = MSG91SMSAdapter(settings)
        if settings.whatsapp_credentials_configured and settings.whatsapp_adapter_supported:
            adapters["whatsapp"] = MetaWhatsAppAdapter(settings)
        return cls(service, adapters)

    @staticmethod
    def _expiry_text(payload: dict[str, object]) -> str:
        ends_at = int(payload.get("endsAt") or 0)
        if ends_at <= 0:
            return "the recorded membership end time"
        return datetime.fromtimestamp(ends_at, tz=IST).strftime("%d %b %Y, %I:%M %p IST")

    @classmethod
    def _message(cls, context: dict[str, object]) -> tuple[str, str]:
        payload = dict(context.get("payload") or {})
        name = str(context.get("displayName") or "Member")
        plan = str(payload.get("planName") or "membership")
        number = str(payload.get("membershipNumber") or "")
        days = int(context.get("triggerDays") or 0)
        expiry = cls._expiry_text(payload)
        role = str(context.get("recipientRole") or "customer")

        if role == "owner":
            subject = "Gravity Fitness member expiry alert"
            timing = "expired today" if days == 0 else f"reaches the {days}-day expiry reminder window"
            body = (
                "Gravity Fitness membership expiry alert.\n\n"
                f"Member: {name}\n"
                f"Plan: {plan}\n"
                f"Status: {timing}.\n"
                f"Expiry: {expiry}.\n"
                f"Verified email available: {'yes' if context.get('emailAvailable') else 'no'}.\n"
                f"Verified phone available: {'yes' if context.get('phoneAvailable') else 'no'}.\n"
            )
            if number:
                body += f"Membership number: {number}.\n"
            body += "Review the member record in the Gravity admin portal before following up.\n"
            return subject, body

        subject = "Gravity Fitness membership expiry reminder"
        timing = "has expired today" if days == 0 else f"will expire in {days} day{'s' if days != 1 else ''}"
        body = (
            f"Hello {name},\n\n"
            f"Your Gravity Fitness {plan} membership {timing}.\n"
            f"Expiry: {expiry}.\n"
        )
        if number:
            body += f"Membership number: {number}.\n"
        body += "Please check your Gravity account or contact the gym for current renewal options.\n"
        return subject, body

    def process_due(self, limit: int = 50) -> dict[str, int]:
        self.service.activate_channels(set(self.adapters))
        deliveries = self.service.due_deliveries(limit)
        sent = failed = skipped = 0
        for item in deliveries:
            delivery_id = str(item["id"])
            adapter = self.adapters.get(str(item["channel"]))
            if adapter is None:
                skipped += 1
                continue
            try:
                context = self.service.delivery_context(delivery_id)
                subject, body = self._message(context)
                provider_id = adapter.send(
                    recipient=str(context["recipient"]),
                    subject=subject,
                    body=body,
                    context=context,
                )
                self.service.record_delivery_attempt(
                    delivery_id,
                    success=True,
                    provider_message_id=provider_id,
                )
                sent += 1
            except NotificationRecipientUnavailable:
                self.service.mark_missing_recipient(delivery_id)
                skipped += 1
            except NotificationConflict:
                skipped += 1
            except DeliveryAdapterError as error:
                self.service.record_delivery_attempt(delivery_id, success=False, error_code=error.code)
                failed += 1
            except Exception:
                self.service.record_delivery_attempt(delivery_id, success=False, error_code="provider_error")
                failed += 1
        return {"attempted": sent + failed, "sent": sent, "failed": failed, "skipped": skipped}
