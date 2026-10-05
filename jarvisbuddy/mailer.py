"""Sending email. Jarvis always reads the email back and waits for a "yes" before calling send()."""

from __future__ import annotations

import re
import smtplib
from email.message import EmailMessage

from .config import Config

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")


def spoken_to_email(text: str) -> str | None:
    """Turn "sri dot b at gmail dot com" (how speech recognition hears it) into an address."""
    t = text.lower().strip()
    t = re.sub(r"\s+at the rate\s+|\s+at\s+", "@", t)
    t = re.sub(r"\s*\bdot\b\s*", ".", t)
    t = re.sub(r"\s*\b(underscore)\b\s*", "_", t)
    t = re.sub(r"\s*\b(dash|hyphen)\b\s*", "-", t)
    t = t.replace(" ", "")
    return t if EMAIL_RE.match(t) else None


def subject_from(body: str) -> str:
    words = body.split()
    subject = " ".join(words[:7]) + ("..." if len(words) > 7 else "")
    return subject[:1].upper() + subject[1:]


class Mailer:
    def __init__(self, config: Config) -> None:
        self.config = config

    @property
    def ready(self) -> bool:
        return self.config.email_enabled

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.config.email_address
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(f"{body}\n\nSent by voice with {self.config.assistant_name}.")
        with smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port, timeout=20) as smtp:
            smtp.login(self.config.email_address, self.config.email_password)
            smtp.send_message(msg)
