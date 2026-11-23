"""Outgoing email: password-reset links, invitations and "you were added" notices.

Backends (``EMAIL_BACKEND``): ``smtp`` (any provider: SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD,
SMTP_SECURITY), ``console`` (nothing is sent; outside production the message is logged so a developer can follow a
link), ``memory`` (tests) and ``auto`` (smtp when SMTP_HOST is set, else console). Messages are plain text in the
recipient's language, so they render the same in every mail client.
"""
from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    text: str


OUTBOX: list[Message] = []  # the "memory" backend (tests)


def enabled() -> bool:
    return get_settings().email_enabled


def send(message: Message) -> bool:
    """Send one message. Never raises: a failed email is logged and reported as False."""
    s = get_settings()
    backend = s.effective_email_backend
    try:
        if backend == "memory":
            OUTBOX.append(message)
        elif backend == "smtp":
            _send_smtp(message)
        else:
            if s.environment == "production":
                log.warning("email_not_configured", to_domain=message.to.rsplit("@", 1)[-1], subject=message.subject)
            else:  # development: show the message so the link can be followed without a mail server
                log.info("email_console", to=message.to, subject=message.subject, text=message.text)
            return False
        log.info("email_sent", to_domain=message.to.rsplit("@", 1)[-1], subject=message.subject)
        return True
    except Exception as exc:  # noqa: BLE001 - mail must never break the request that triggered it
        log.error("email_failed", to_domain=message.to.rsplit("@", 1)[-1], error=type(exc).__name__)
        return False


def _send_smtp(message: Message) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.email_from, message.to, message.subject
    msg["Message-ID"] = make_msgid(domain=s.email_from.rsplit("@", 1)[-1].strip(">") or None)
    msg.set_content(message.text)
    password = s.smtp_password.get_secret_value() if s.smtp_password else None
    if s.smtp_security == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=15, context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15)
    with server:
        if s.smtp_security == "starttls":
            server.starttls(context=ssl.create_default_context())
        if s.smtp_username and password:
            server.login(s.smtp_username, password)
        server.send_message(msg)


# ------------------------------------------------------------------ messages
def _link(path: str, token: str) -> str:
    return f"{get_settings().app_base_url.rstrip('/')}/{path}?token={token}"


def password_reset(to: str, name: str, token: str, locale: str) -> Message:
    minutes = get_settings().password_reset_ttl_minutes
    link = _link("reset-password", token)
    if locale == "he":
        return Message(to, "איפוס סיסמה ל-InvoiceFlow", (
            f"שלום {name},\n\nהתקבלה בקשה לאיפוס הסיסמה שלך ב-InvoiceFlow. לבחירת סיסמה חדשה:\n{link}\n\n"
            f"הקישור תקף ל-{minutes} דקות ולשימוש אחד. בחירת סיסמה חדשה מנתקת את כל המכשירים המחוברים.\n"
            "אם לא ביקשת איפוס, אפשר להתעלם מההודעה; הסיסמה שלך לא תשתנה.\n"))
    return Message(to, "Reset your InvoiceFlow password", (
        f"Hello {name},\n\nWe received a request to reset your InvoiceFlow password. Choose a new one here:\n{link}\n\n"
        f"The link works once and expires in {minutes} minutes. Setting a new password signs out all your devices.\n"
        "If you did not ask for this, ignore this email; your password stays the same.\n"))


def invite(to: str, name: str, org_name: str, inviter: str, token: str, locale: str) -> Message:
    hours = get_settings().invite_ttl_hours
    link = _link("accept-invite", token)
    if locale == "he":
        return Message(to, f"הזמנה להצטרף ל-{org_name} ב-InvoiceFlow", (
            f"שלום {name},\n\n{inviter} הזמין/ה אותך להצטרף לצוות של {org_name} ב-InvoiceFlow.\n"
            f"לבחירת סיסמה וכניסה:\n{link}\n\nהקישור תקף ל-{hours} שעות ולשימוש אחד.\n"))
    return Message(to, f"You're invited to {org_name} on InvoiceFlow", (
        f"Hello {name},\n\n{inviter} invited you to join {org_name} on InvoiceFlow.\n"
        f"Choose your password and sign in here:\n{link}\n\nThe link works once and expires in {hours} hours.\n"))


def added_to_organization(to: str, name: str, org_name: str, inviter: str, locale: str) -> Message:
    url = get_settings().app_base_url.rstrip("/")
    if locale == "he":
        return Message(to, f"נוספת ל-{org_name} ב-InvoiceFlow", (
            f"שלום {name},\n\n{inviter} הוסיף/ה אותך לצוות של {org_name} ב-InvoiceFlow. "
            f"אפשר להיכנס עם הסיסמה הקיימת שלך ולעבור ביניהם מתפריט הארגון:\n{url}\n"))
    return Message(to, f"You were added to {org_name} on InvoiceFlow", (
        f"Hello {name},\n\n{inviter} added you to {org_name} on InvoiceFlow. Sign in with your existing password and "
        f"switch businesses from the organization menu:\n{url}\n"))


def two_factor_reset(to: str, name: str, org_name: str, admin: str, locale: str) -> Message:
    url = get_settings().app_base_url.rstrip("/")
    if locale == "he":
        return Message(to, "האימות הדו-שלבי שלך ב-InvoiceFlow אופס", (
            f"שלום {name},\n\n{admin}, מנהל/ת המערכת של {org_name}, כיבה/תה את האימות הדו-שלבי בחשבון שלך, "
            "וכל המכשירים המחוברים נותקו.\n"
            f"אפשר להיכנס עם הסיסמה שלך ולהגדיר אפליקציית אימות חדשה בהגדרות:\n{url}\n\n"
            "אם לא ביקשת זאת, פנה/י מיד למנהל/ת המערכת ושנה/י את הסיסמה.\n"))
    return Message(to, "Your InvoiceFlow two-factor sign-in was reset", (
        f"Hello {name},\n\n{admin}, an administrator of {org_name}, turned off two-factor sign-in on your account, "
        "and all your devices were signed out.\n"
        f"Sign in with your password and set up a new authenticator app in Settings:\n{url}\n\n"
        "If you did not ask for this, contact your administrator right away and change your password.\n"))
