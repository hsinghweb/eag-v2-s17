import os
import smtplib
from email.message import EmailMessage
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _get_gmail_config() -> tuple[Optional[str], Optional[str], Optional[str]]:
    user = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_APP_PASSWORD") or os.getenv("GMAIL_PASSWORD")
    recipient = os.getenv("GMAIL_TO") or user
    return user, password, recipient


def send_gmail(subject: str, body: str) -> bool:
    user, password, recipient = _get_gmail_config()
    if not user or not password or not recipient:
        return False

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
    return True
