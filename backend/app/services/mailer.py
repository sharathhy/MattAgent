"""Outgoing email for the sales agent's offers, from the owner's own address.

Two ways to send, both configured only through environment variables:

* the Brevo HTTPS API (``MATT_BREVO_API_KEY``), which works on Render's free plan, where
  outbound SMTP ports are blocked;
* plain SMTP with STARTTLS (``MATT_SMTP_*``, e.g. Gmail with an app password) on hosts
  that allow it.

Every message carries a one-click ``List-Unsubscribe`` header, as Gmail and Yahoo require.
"""

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import httpx

from app.core.config import Settings
from app.core.net import ipv4_transport

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


class MailError(Exception):
    pass


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    body: str
    unsubscribe_url: str


def sender(settings: Settings) -> str | None:
    return settings.mail_from or settings.smtp_username


def channel(settings: Settings) -> str | None:
    """Which way email goes out, or None when sending is not set up."""
    if sender(settings) is None:
        return None
    if settings.brevo_api_key:
        return "brevo"
    if settings.smtp_host and settings.smtp_username and settings.smtp_password:
        return "smtp"
    return None


def _headers(mail: Mail) -> dict[str, str]:
    return {
        "List-Unsubscribe": f"<{mail.unsubscribe_url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


def _brevo(settings: Settings, name: str, address: str, mail: Mail) -> None:
    payload = {
        "sender": {"name": name, "email": address},
        "to": [{"email": mail.to}],
        "replyTo": {"email": address},
        "subject": mail.subject,
        "textContent": mail.body,
        "headers": _headers(mail),
    }
    try:
        with httpx.Client(transport=ipv4_transport(), timeout=20) as client:
            res = client.post(BREVO_URL, json=payload,
                              headers={"api-key": settings.brevo_api_key or ""})  # fmt: skip
    except httpx.HTTPError as exc:
        raise MailError(f"Brevo could not be reached: {exc}") from exc
    if res.status_code >= 300:
        raise MailError(f"Brevo refused the email ({res.status_code}): {res.text[:300]}")


def _smtp(settings: Settings, name: str, address: str, mail: Mail) -> None:
    msg = EmailMessage()
    msg["From"] = formataddr((name, address))
    msg["To"] = mail.to
    msg["Subject"] = mail.subject
    msg["Message-ID"] = make_msgid(domain=address.rsplit("@", 1)[-1])
    for key, value in _headers(mail).items():
        msg[key] = value
    msg.set_content(mail.body)
    host, port = settings.smtp_host or "", settings.smtp_port
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20,
                                  context=ssl.create_default_context()) as smtp:  # fmt: skip
                smtp.login(settings.smtp_username or "", settings.smtp_password or "")
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(settings.smtp_username or "", settings.smtp_password or "")
                smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailError(f"SMTP sending failed: {exc}") from exc


def send(settings: Settings, mail: Mail) -> str:
    """Send one email; returns the channel used. Raises MailError on any failure."""
    way, address = channel(settings), sender(settings)
    if way is None or address is None:
        raise MailError("Email sending is not set up")
    name = settings.upi_payee_name
    if way == "brevo":
        _brevo(settings, name, address, mail)
    else:
        _smtp(settings, name, address, mail)
    return way
