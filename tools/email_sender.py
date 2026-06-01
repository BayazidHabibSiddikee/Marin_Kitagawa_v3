#!/usr/bin/env python3
"""
email_sender.py — Send emails with .txt or .tex file attachments via Gmail SMTP.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# Gmail SMTP config
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "izuku.midoriya.genzi@gmail.com"
SENDER_PASSWORD = "ncnwcsffkcopitcb"  # app password (no spaces)


def send_email(
    to: str,
    subject: str,
    body: str = "",
    attachment_path: str = "",
) -> str:
    """
    Send an email. Optionally attach a .txt or .tex file.
    
    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain text body (used if no attachment, or as intro with attachment).
        attachment_path: Path to .txt or .tex file to attach.
    
    Returns:
        Status message string.
    """
    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = to
    msg["Subject"] = subject

    # Body
    final_body = body
    if attachment_path:
        fname = os.path.basename(attachment_path)
        if not body:
            final_body = f"Please find attached: {fname}"
        else:
            final_body = f"{body}\n\n---\nAttached: {fname}"

    msg.attach(MIMEText(final_body, "plain"))

    # Attachment
    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        filename = os.path.basename(attachment_path)
        part.add_header("Content-Disposition", f"attachment; filename={filename}")
        msg.attach(part)

    # Send
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, to, msg.as_string())
        att_info = f" + attachment {os.path.basename(attachment_path)}" if attachment_path else ""
        return f"Email sent to {to}{att_info}."
    except Exception as e:
        return f"Email failed: {e}"
