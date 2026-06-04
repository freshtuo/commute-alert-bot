"""SMTP helper for sending alert emails through Gmail."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any


def send_email(config: dict[str, Any], subject: str, body: str) -> None:
    """Send a plain-text email to all configured recipients."""
    notification_config = config.get("notifications", {})
    sender = notification_config.get("sender_email")
    recipients = notification_config.get("recipients", [])
    smtp_host = notification_config.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(notification_config.get("smtp_port", 587))
    password_env = notification_config.get("gmail_app_password_env", "GMAIL_APP_PASSWORD")
    app_password = os.getenv(password_env)

    if not sender:
        raise ValueError("Missing notifications.sender_email in config/config.yaml")
    if not recipients:
        raise ValueError("Missing notifications.recipients in config/config.yaml")
    if not app_password:
        raise ValueError(f"Missing required environment variable: {password_env}")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(body)

    # Gmail App Passwords work over standard STARTTLS SMTP.
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(sender, app_password)
        smtp.send_message(message)
