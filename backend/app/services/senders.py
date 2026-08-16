"""Outbound senders for the Notification Engine's Email and SMS channels.

Both senders degrade gracefully when unconfigured (no SMTP host / no Twilio
credentials): rather than raising or silently pretending to succeed, they
log the message and return a clear "not configured" failure so
`NotificationHistory` rows tell the truth about whether anything actually
went out. Set the corresponding settings (see app/core/config.py) to enable
real delivery.
"""

from __future__ import annotations

import base64
import logging
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    ok: bool
    error: str | None = None


class EmailSender:
    """Sends email over SMTP using app.core.config.settings."""

    def send(self, to_email: str, subject: str, body: str) -> SendResult:
        if not settings.smtp_host:
            logger.info("[email:unconfigured] to=%s subject=%s", to_email, subject)
            return SendResult(ok=False, error="SMTP is not configured (smtp_host is empty)")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.smtp_from_email
        message["To"] = to_email
        message.set_content(body)

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
                if settings.smtp_use_tls:
                    client.starttls()
                if settings.smtp_username:
                    client.login(settings.smtp_username, settings.smtp_password)
                client.send_message(message)
            return SendResult(ok=True)
        except Exception as exc:  # noqa: BLE001 - report any SMTP failure, don't crash dispatch
            logger.exception("Email send failed to=%s", to_email)
            return SendResult(ok=False, error=str(exc))


class SmsSender:
    """Sends SMS via Twilio's REST API.

    Uses plain `urllib` rather than the `twilio` SDK so the Notification
    Engine has no hard runtime dependency on a package that isn't in
    requirements.txt yet; swap this for `twilio.rest.Client` if/when that
    dependency is added.
    """

    TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"

    def send(self, to_phone: str, body: str) -> SendResult:
        if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number):
            logger.info("[sms:unconfigured] to=%s body=%s", to_phone, body)
            return SendResult(ok=False, error="Twilio is not configured (twilio_account_sid is empty)")

        url = f"{self.TWILIO_API_BASE}/Accounts/{settings.twilio_account_sid}/Messages.json"
        data = urllib.parse.urlencode(
            {"From": settings.twilio_from_number, "To": to_phone, "Body": body}
        ).encode()
        auth = base64.b64encode(
            f"{settings.twilio_account_sid}:{settings.twilio_auth_token}".encode()
        ).decode()
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if 200 <= response.status < 300:
                    return SendResult(ok=True)
                return SendResult(ok=False, error=f"Twilio returned HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            logger.exception("SMS send failed to=%s", to_phone)
            return SendResult(ok=False, error=f"Twilio HTTP {exc.code}: {exc.reason}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("SMS send failed to=%s", to_phone)
            return SendResult(ok=False, error=str(exc))


email_sender = EmailSender()
sms_sender = SmsSender()
