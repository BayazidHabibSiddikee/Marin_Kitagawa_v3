#!/usr/bin/env python3
"""
Simple Telegram Message Sender
"""

import os
import sys
import argparse
import urllib.request
import urllib.parse
import json

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

# ── Credentials from .env ──
DEFAULT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
DEFAULT_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def send(message: str, token: str = DEFAULT_TOKEN, chat_id: str = DEFAULT_CHAT_ID) -> bool:
    """
    Send a Telegram message.
    Returns True on success, False on failure.
    """
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
            print(f"✅ Sent: {message[:60]}{'...' if len(message) > 60 else ''}")
            return True
        else:
            print(f"❌ Telegram error: {result}")
            return False
    except Exception as e:
        print(f"❌ Failed to send: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send a Telegram message")
    parser.add_argument("message",           help="Message text to send")
    parser.add_argument("--token",  "-t",    default=DEFAULT_TOKEN,   help="Bot token")
    parser.add_argument("--chat",   "-c",    default=DEFAULT_CHAT_ID, help="Chat/User ID")
    args = parser.parse_args()

    ok = send(args.message, token=args.token, chat_id=args.chat)
    sys.exit(0 if ok else 1)
