#!/usr/bin/env python3
"""
telegram_bot.py — Bidirectional Telegram bot for Marin.

Receives messages from Telegram, processes them through the same
marin_main() engine as the web UI, and sends responses back.

Usage:
    python telegram_bot.py              # run standalone
    python -m telegram_bot              # same

Designed to run as a background task alongside the FastAPI server,
or standalone for Telegram-only usage.
"""

import os
import sys
import json
import time
import asyncio
import urllib.request
import urllib.parse
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────
BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID     = os.getenv("TELEGRAM_USER_ID", "")
POLL_TIMEOUT = 20   # long-poll timeout (seconds)
POLL_INTERVAL = 1   # delay between polls
MAX_MSG_LEN = 4096  # Telegram message limit

# ── State ─────────────────────────────────────────────────────────────────
_last_update_id = 0
_processing = set()  # chat IDs currently being processed


def _api(method: str, data: dict = None) -> dict:
    """Call Telegram Bot API method."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method="POST")
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except Exception as e:
        print(f"[TG] API error: {e}")
        return {"ok": False, "error": str(e)}


def _send_text(chat_id: int, text: str):
    """Send a text message, splitting if too long."""
    # Telegram doesn't like Markdown without proper escaping, send plain
    for i in range(0, len(text), MAX_MSG_LEN):
        chunk = text[i:i + MAX_MSG_LEN]
        _api("sendMessage", {
            "chat_id": chat_id,
            "text": chunk,
        })


def _send_typing(chat_id: int):
    """Show typing indicator."""
    _api("sendChatAction", {"chat_id": chat_id, "action": "typing"})


def _process_message_sync(chat_id: int, user_text: str, user_name: str):
    """
    Process a message through marin_main() and send the response.
    Saves to shared database so web and Telegram share history.
    """
    if chat_id in _processing:
        _send_text(chat_id, "Still working on the last one~ Give me a sec!")
        return

    _processing.add(chat_id)
    try:
        print(f"[TG] {user_name} ({chat_id}): {user_text[:60]}...")

        # Save user message to shared DB
        import database
        database.save_message("marin", "user", f"[telegram] {user_text}")

        # Record for proactive engine
        from proactive_engine import record_user_message
        record_user_message("marin")

        # Build an async runner
        loop = asyncio.new_event_loop()
        try:
            async def _run():
                # Import here to avoid circular imports at module level
                from marin import main as marin_main
                from utils.shared_logic import MASTER_USER

                # Collect full response from streaming
                full_response = []
                async for chunk in marin_main(user_text, user=MASTER_USER):
                    if chunk and not chunk.startswith("__"):
                        full_response.append(chunk)

                return "".join(full_response)

            result = loop.run_until_complete(_run())
        finally:
            loop.close()

        if result:
            # Clean up any stray tags
            result = result.replace("__VIBE__flirty", "").replace("__VIBE__neutral", "")
            result = result.replace("__VIBE__lovely", "").replace("__VIBE__excited", "")
            result = result.replace("__VIBE__sad", "").replace("__VIBE__angry", "")
            result = result.replace("__VIBE__stressed", "").replace("__VIBE__focused", "")
            result = result.replace("__VIBE__playful", "").strip()

            if result:
                _send_text(chat_id, result)
                # Save assistant response to shared DB
                database.save_message("marin", "assistant", result)
                print(f"[TG] Replied to {user_name}: {result[:60]}...")
            else:
                _send_text(chat_id, "Hehehe~ I'm here! What's up?")
        else:
            _send_text(chat_id, "Hmm, my brain glitched for a sec. Try again?")

    except Exception as e:
        print(f"[TG] Error processing message: {e}")
        _send_text(chat_id, f"Oops, something went wrong: {str(e)[:100]}")
    finally:
        _processing.discard(chat_id)


async def _poll_loop():
    """Main polling loop — receives updates from Telegram."""
    global _last_update_id

    print(f"[TG] Bot starting... Token: {BOT_TOKEN[:10]}...")
    print(f"[TG] Allowed chat ID: {CHAT_ID}")

    # Verify bot is working
    me = _api("getMe")
    if not me.get("ok"):
        print(f"[TG] Failed to get bot info: {me}")
        return
    bot_name = me["result"].get("username", "unknown")
    print(f"[TG] Bot ready: @{bot_name}")

    while True:
        try:
            params = {"timeout": POLL_TIMEOUT}
            if _last_update_id:
                params["offset"] = _last_update_id + 1

            resp = _api("getUpdates", params)
            if not resp.get("ok"):
                print(f"[TG] getUpdates failed: {resp}")
                await asyncio.sleep(5)
                continue

            for update in resp.get("result", []):
                _last_update_id = max(_last_update_id, update["update_id"])
                msg = update.get("message")
                if not msg:
                    continue

                chat_id = msg["chat"]["id"]
                text = msg.get("text", "")
                user = msg.get("from", {})
                user_name = user.get("first_name", "User")

                # Only respond to allowed chat ID (or all if CHAT_ID is empty)
                if CHAT_ID and str(chat_id) != str(CHAT_ID):
                    print(f"[TG] Ignored message from unknown chat {chat_id}")
                    _send_text(chat_id, "Sorry, I only talk to my Operator! 💜")
                    continue

                if not text:
                    continue

                # Handle /start and /help
                if text.startswith("/start"):
                    _send_text(chat_id,
                        "Hehehe~ Hello! I'm Marin! 💜\n\n"
                        "You can chat with me here just like on the web.\n"
                        "I can help with:\n"
                        "• Study & learning\n"
                        "• Coding & debugging\n"
                        "• Math & plotting\n"
                        "• Habits & productivity\n"
                        "• Market info & news\n"
                        "• Or just casual chat~ Ummaaah! 🐸✨"
                    )
                    continue

                if text.startswith("/habits"):
                    try:
                        from tools.habit_store import get_reminders_for_today, list_tasks
                        reminders = get_reminders_for_today()
                        tasks = list_tasks(status="todo")
                        lines = ["📋 **HABITS**\n"]
                        if reminders:
                            lines.append("⏰ Due today:")
                            for t in reminders:
                                lines.append(f"  • {t['title']} [{t['priority']}]")
                        if tasks:
                            lines.append("\n📝 Todo:")
                            for t in tasks[:5]:
                                lines.append(f"  • {t['title']}")
                        if not reminders and not tasks:
                            lines.append("All clear! No pending habits.")
                        _send_text(chat_id, "\n".join(lines))
                    except Exception as e:
                        _send_text(chat_id, f"Habit check failed: {e}")
                    continue

                if text.startswith("/stats"):
                    try:
                        from tools.habit_store import get_stats
                        s = get_stats()
                        _send_text(chat_id,
                            f"📊 **STATS**\n"
                            f"Total: {s['total']} | Done: {s['done']} | "
                            f"Todo: {s['todo']} | In-progress: {s['in_progress']}"
                        )
                    except Exception as e:
                        _send_text(chat_id, f"Stats error: {e}")
                    continue

                if text.startswith("/status"):
                    from proactive_engine import get_status
                    st = get_status()
                    _send_text(chat_id,
                        f"🤖 **STATUS**\n"
                        f"Quiet hours: {st['quiet_hours']}\n"
                        f"Proactive msgs this session: {st['session_counts'].get('marin', 0)}"
                    )
                    continue

                # Process chat message in thread pool (non-blocking)
                loop = asyncio.get_event_loop()
                loop.run_in_executor(
                    None,
                    _process_message_sync,
                    chat_id, text, user_name
                )

        except Exception as e:
            print(f"[TG] Poll error: {e}")
            await asyncio.sleep(5)


def run_bot():
    """Entry point — run the polling loop."""
    if not BOT_TOKEN:
        print("[TG] No TELEGRAM_BOT_TOKEN set. Bot cannot start.")
        print("[TG] Set it in .env or as environment variable.")
        return

    asyncio.run(_poll_loop())


# ── Integration with FastAPI lifespan ─────────────────────────────────────

async def start_telegram_bot():
    """Start the bot as a background task (called from main.py lifespan)."""
    if not BOT_TOKEN:
        print("[TG] No TELEGRAM_BOT_TOKEN — Telegram bot disabled.")
        return

    print("[TG] Starting Telegram bot in background...")
    # Run in a separate thread so it doesn't block the event loop
    import threading
    thread = threading.Thread(target=_run_threaded, daemon=True)
    thread.start()


def _run_threaded():
    """Run the poll loop in a thread with its own event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_poll_loop())
    except Exception as e:
        print(f"[TG] Bot thread crashed: {e}")
    finally:
        loop.close()


if __name__ == "__main__":
    run_bot()
