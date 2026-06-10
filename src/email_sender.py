"""SMTP helper for sending alert emails through Gmail."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any


def send_email(config: dict[str, Any], subject: str, body: str) -> None:
    """Send a plain-text email to all configured recipients."""
    notification_config = config.get("notifications", {})
    sender = str(notification_config.get("sender_email") or "").strip()
    recipients = [
        str(recipient).strip()
        for recipient in notification_config.get("recipients", [])
        if str(recipient).strip()
    ]
    smtp_host = notification_config.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(notification_config.get("smtp_port", 587))
    smtp_tls_mode = str(
        notification_config.get(
            "smtp_tls_mode", "ssl" if smtp_port == 465 else "starttls"
        )
    ).lower()
    password_env = notification_config.get("gmail_app_password_env", "GMAIL_APP_PASSWORD")
    app_password = (os.getenv(password_env) or "").replace(" ", "").strip()

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

    try:
        if smtp_tls_mode == "ssl":
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as smtp:
                smtp.login(sender, app_password)
                smtp.send_message(message)
            return

        if smtp_tls_mode == "starttls":
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(sender, app_password)
                smtp.send_message(message)
            return
    except smtplib.SMTPAuthenticationError as exc:
        raise PermissionError(
            "Gmail rejected the SMTP login. Confirm the sender address is the "
            "same account that created the App Password, rotate the Gmail App "
            "Password if needed, and sign in to the Gmail account in a browser "
            "if Google requires an account security check."
        ) from exc
    except OSError as exc:
        raise ConnectionError(
            f"Could not connect to SMTP server {smtp_host}:{smtp_port} "
            f"using {smtp_tls_mode}. If port 587 is blocked on this server, "
            "set notifications.smtp_port to 465 and smtp_tls_mode to ssl."
        ) from exc

    raise ValueError(
        "Invalid notifications.smtp_tls_mode; expected 'ssl' or 'starttls'"
    )
