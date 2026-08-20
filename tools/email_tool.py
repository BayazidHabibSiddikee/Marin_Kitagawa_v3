#!/usr/bin/env python3
"""
tools/email_tool.py — Agent-callable Gmail sender (SMTP, no interactive prompts).
Reads credentials from env vars (GMAIL_ADDRESS, GMAIL_APP_PASSWORD).
Falls back to database vault if env vars are empty.
"""

import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def _get_credentials() -> tuple[str, str]:
    """Return (sender_address, app_password). Reads encrypted DB first, then env as fallback."""
    sender   = ""
    password = ""

    # Primary: encrypted database vault (set via Command Center)
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from database import get_user_key
        sender   = (get_user_key("USR-MASTER", "GMAIL_ADDRESS")      or "").strip()
        password = (get_user_key("USR-MASTER", "GMAIL_APP_PASSWORD") or "").strip()
    except Exception:
        pass

    # Fallback: env vars (legacy / .env file)
    if not sender:
        sender   = os.getenv("GMAIL_ADDRESS",     os.getenv("EMAIL_SENDER",   "")).strip()
    if not password:
        password = os.getenv("GMAIL_APP_PASSWORD", os.getenv("EMAIL_PASSWORD", "")).strip()

    return sender, password


def send_email(
    to: str,
    subject: str,
    body: str,
    sender: str = "",
    password: str = "",
) -> dict:
    """
    Send a plain-text email via Gmail SMTP.
    Returns {"ok": bool, "detail": str}.
    If sender/password are empty, reads from env or database.
    """
    if not sender or not password:
        sender, password = _get_credentials()

    if not sender:
        return {
            "ok": False,
            "detail": "GMAIL_ADDRESS not set. Configure it in Command Center → Email."
        }
    if not password:
        return {
            "ok": False,
            "detail": "GMAIL_APP_PASSWORD not set. Generate one at myaccount.google.com → Security → App Passwords."
        }
    if not to or "@" not in to:
        return {"ok": False, "detail": f"Invalid recipient address: '{to}'"}

    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = sender
        msg["To"]      = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, to, msg.as_string())

        return {"ok": True, "detail": f"Email sent to {to}."}
    except smtplib.SMTPAuthenticationError:
        return {
            "ok": False,
            "detail": "Gmail authentication failed. Make sure you're using an App Password, not your regular password."
        }
    except Exception as e:
        return {"ok": False, "detail": f"Failed to send email: {e}"}


if __name__ == "__main__":
    # Quick test: python email_tool.py to@example.com "Subject" "Body"
    args = sys.argv[1:]
    if len(args) < 3:
        print("Usage: python email_tool.py <to> <subject> <body>")
        sys.exit(1)
    result = send_email(to=args[0], subject=args[1], body=args[2])
    print(result)
