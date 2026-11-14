"""Sending verification codes by email (SMTP, standard library only).

Used only when `email_verification = true` in auth.toml. The code, the address and
the SMTP password are never written to a log.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.auth.config import SmtpSettings

SUBJECTS = {
    "ar": "رمز التحقق من حساب KSU Agent",
    "en": "Your KSU Agent verification code",
}

BODIES = {
    "ar": (
        "رمز التحقق الخاص بك هو: {code}\n\n"
        "ينتهي الرمز خلال {minutes} دقائق. إذا لم تطلب إنشاء حساب في KSU Agent "
        "فتجاهل هذه الرسالة.\n\n"
        "KSU Agent — مشروع طلابي، وليس خدمة رسمية من جامعة الملك سعود."
    ),
    "en": (
        "Your verification code is: {code}\n\n"
        "It expires in {minutes} minutes. If you did not sign up for KSU Agent, "
        "ignore this email.\n\n"
        "KSU Agent — a student project, not an official KSU service."
    ),
}


class Mailer(Protocol):
    """Anything that can deliver a verification code."""

    def send_code(self, to: str, code: str, lang: str, minutes: int) -> None: ...


class SmtpMailer:
    """Sends the code through the SMTP account in .env (STARTTLS, or SSL on 465)."""

    def __init__(self, settings: SmtpSettings, timeout: float = 15.0):
        self.settings = settings
        self.timeout = timeout

    def send_code(self, to: str, code: str, lang: str, minutes: int) -> None:
        lang = lang if lang in SUBJECTS else "ar"
        message = EmailMessage()
        message["From"] = self.settings.sender
        message["To"] = to
        message["Subject"] = SUBJECTS[lang]
        message.set_content(BODIES[lang].format(code=code, minutes=minutes))

        smtp_class = smtplib.SMTP_SSL if self.settings.port == 465 else smtplib.SMTP
        with smtp_class(self.settings.host, self.settings.port, timeout=self.timeout) as smtp:
            if smtp_class is smtplib.SMTP:
                smtp.starttls()
            if self.settings.username:
                smtp.login(self.settings.username, self.settings.password)
            smtp.send_message(message)
