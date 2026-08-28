from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Callable, Protocol
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

    def send(self, *, recipient: str, subject: str, body: str) -> str | None:
        ...


class SMTPEmailAdapter:
    channel = "email"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, *, recipient: str, subject: str, body: str) -> str | None:
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

    def send(self, *, recipient: str, subject: str, body: str) -> str | None:
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

    def send(self, *, recipient: str, subject: str, body: str) -> str | None:
        try:
            return self.sender(recipient, body)
        except DeliveryAdapterError:
            raise
        except Exception:
            raise DeliveryAdapterError("whatsapp_delivery_failed") from None


class NotificationDispatcher:
    def __init__(self, service: NotificationService, adapters: dict[str, DeliveryAdapter] | None = None) -> None:
        self.service = service
        self.adapters = dict(adapters or {})

    @classmethod
    def from_settings(cls, service: NotificationService, settings: Settings) -> "NotificationDispatcher":
        adapters: dict[str, DeliveryAdapter] = {}
        if settings.smtp_configured:
            adapters["email"] = SMTPEmailAdapter(settings)
        # SMS and WhatsApp are intentionally not guessed here. Their settings
        # remain readiness signals until an operator selects a concrete provider.
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
