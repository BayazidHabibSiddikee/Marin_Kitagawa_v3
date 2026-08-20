#!/usr/bin/env python3
"""
tools/telegram_tool.py — Agent-callable Telegram sender.
Reads credentials from env vars (TELEGRAM_BOT_TOKEN, TELEGRAM_USER_ID).
Falls back to database vault if env vars are empty.
"""

import json
import os
import urllib.parse
import urllib.request


def _get_credentials() -> tuple[str, str]:
    """Return (token, chat_id). Reads database vault first, then env vars."""
    token   = ""
    chat_id = ""

    # Primary: encrypted database (set via Command Center)
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from database import get_user_key
        token   = (get_user_key("USR-MASTER", "TELEGRAM_BOT_TOKEN") or "").strip()
        chat_id = (get_user_key("USR-MASTER", "TELEGRAM_CHAT_ID")   or "").strip()
    except Exception:
        pass

    # Fallback: env vars (legacy / .env file)
    if not token:
        token   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not chat_id:
        chat_id = os.getenv("TELEGRAM_USER_ID", os.getenv("TELEGRAM_CHAT_ID", "")).strip()

    return token, chat_id


def send(message: str, token: str = "", chat_id: str = "") -> dict:
    """
    Send a Telegram message. Returns {"ok": bool, "detail": str}.
    If token/chat_id are empty, reads from env or database.
    """
    if not token or not chat_id:
        token, chat_id = _get_credentials()

    if not token:
        return {"ok": False, "detail": "TELEGRAM_BOT_TOKEN not set. Configure it in Command Center → Telegram."}
    if not chat_id:
        return {"ok": False, "detail": "TELEGRAM_USER_ID (chat ID) not set. Configure it in Command Center → Telegram."}

    url  = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id":    chat_id,
        "text":       message,
        "parse_mode": "Markdown",
    }).encode()

    try:
        req      = urllib.request.Request(url, data=data, method="POST")
        response = urllib.request.urlopen(req, timeout=10)
        result   = json.loads(response.read())
        if result.get("ok"):
            return {"ok": True, "detail": f"Sent to chat {chat_id}."}
        return {"ok": False, "detail": f"Telegram API error: {result.get('description', result)}"}
    except Exception as e:
        return {"ok": False, "detail": f"Network error: {e}"}


if __name__ == "__main__":
    import sys
    msg = sys.argv[1] if len(sys.argv) > 1 else "Test message from Marin."
    result = send(msg)
    print(result)
