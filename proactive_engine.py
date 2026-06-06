#!/usr/bin/env python3
"""
proactive_engine.py — Marin's proactive conversation initiator.

Marin can initiate conversations based on:
  1. Habit tracker status (morning reminders, follow-ups)
  2. Recent conversation patterns (topic follow-ups, check-ins)
  3. Idle detection (gentle nudges after inactivity)
  4. Time-of-day awareness (morning greetings, evening wind-down)

Delivery: SSE stream to frontend + optional Telegram push.
"""

import asyncio
import json
import random
import time
from datetime import datetime, time as dtime, timedelta
from typing import AsyncGenerator

import database

# ── Config ────────────────────────────────────────────────────────────────
IDLE_INTERVALS  = [
    1200,    # 1st: 20 min
    7200,    # 2nd: 2 hours
    21600,   # 3rd: 6 hours
    172800,  # 4th: 2 days
]
QUIET_START     = dtime(0, 0)    # midnight
QUIET_END       = dtime(7, 30)   # 7:30 AM
CHECK_INTERVAL  = 90     # seconds between proactive checks

# ── State (per browser session) ───────────────────────────────────────────
_last_user_msg_time: dict[str, float]  = {}
_last_proactive_time: dict[str, float] = {}
_streak_count: dict[str, int]          = {} # count proactive sent since last user interaction

# ── Broadcast queue (proactive messages go to ALL platforms) ──────────────
_proactive_queue: asyncio.Queue | None = None
_telegram_chat_id: str = ""


def _get_queue() -> asyncio.Queue:
    global _proactive_queue
    if _proactive_queue is None:
        _proactive_queue = asyncio.Queue()
    return _proactive_queue


def record_user_message(agent: str):
    """Call this every time a user message arrives."""
    _last_user_msg_time[agent] = time.time()
    _streak_count[agent] = 0 # Reset the proactive streak when user talks


def seed_from_db(agent: str = "marin"):
    """Restore proactive state from chat history on server startup."""
    try:
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT timestamp FROM chat_history WHERE agent = ? ORDER BY id DESC LIMIT 1",
            (agent,)
        )
        row = cursor.fetchone()
        conn.close()

        if row and row["timestamp"]:
            # Parse the timestamp and compute how long ago it was
            from datetime import datetime as _dt
            try:
                last_time = _dt.fromisoformat(row["timestamp"]).timestamp()
            except (ValueError, TypeError):
                last_time = time.time() - 300

            elapsed = time.time() - last_time
            _last_user_msg_time[agent] = last_time

            # Determine streak based on elapsed time vs intervals
            streak = 0
            for i, interval in enumerate(IDLE_INTERVALS):
                if elapsed >= interval:
                    streak = i + 1
                else:
                    break
            streak = min(streak, len(IDLE_INTERVALS) - 1)
            _streak_count[agent] = streak
            _last_proactive_time[agent] = last_time if streak > 0 else 0

            mins = int(elapsed / 60)
            print(f"[proactive] Seeded: last user msg {mins}m ago, streak={streak}")
        else:
            _last_user_msg_time[agent] = time.time()
            _streak_count[agent] = 0
            print("[proactive] No history found, starting fresh")
    except Exception as e:
        print(f"[proactive] DB seed failed: {e}")


def _is_quiet_hours() -> bool:
    now = datetime.now().time()
    if QUIET_START < QUIET_END:
        return QUIET_START <= now < QUIET_END
    return now >= QUIET_START or now < QUIET_END


def _can_fire(agent: str) -> bool:
    if _is_quiet_hours():
        return False

    now = time.time()
    last_user = _last_user_msg_time.get(agent, 0)
    last_pro  = _last_proactive_time.get(agent, 0)
    
    # Last activity time
    last_act = max(last_user, last_pro)
    count = _streak_count.get(agent, 0)

    # Cap at the defined sequence
    if count >= len(IDLE_INTERVALS):
        return False

    required_gap = IDLE_INTERVALS[count]
    if now - last_act >= required_gap:
        return True
    return False


def _get_time_greeting() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    elif hour < 17:
        return "Good afternoon"
    else:
        return "Good evening"


# ── Context Gatherers ─────────────────────────────────────────────────────

def _get_habit_context() -> str | None:
    """Gather habit tracker state for proactive messages."""
    try:
        from tools.habit_store import get_reminders_for_today, get_stats, list_tasks

        reminders = get_reminders_for_today()
        stats = get_stats()
        pending = list_tasks(status="todo")
        in_progress = list_tasks(status="in-progress")

        parts = []

        if reminders:
            names = [t["title"] for t in reminders[:5]]
            parts.append(f"Due today (not yet done): {', '.join(names)}")

        if in_progress:
            names = [t["title"] for t in in_progress[:3]]
            parts.append(f"In progress: {', '.join(names)}")

        if stats:
            total = stats.get("total", 0)
            done = stats.get("done", 0)
            if total > 0:
                pct = int(done / total * 100)
                parts.append(f"Overall completion: {done}/{total} ({pct}%)")

        if parts:
            return " | ".join(parts)
    except Exception:
        pass
    return None


def _get_conversation_context(agent: str = "marin") -> str | None:
    """Get actual recent conversation content for meaningful follow-ups."""
    try:
        history = database.get_history(agent, limit=20)
        if not history:
            return None

        # Get the last 5 exchanges (user + assistant pairs)
        recent = history[-10:]
        
        conversation = []
        for m in recent:
            role = "User" if m["role"] == "user" else "Marin"
            content = m["content"][:300]  # truncate long messages
            # Skip proactive messages and vibe tags
            if content.startswith("[proactive:") or content.startswith("__VIBE__"):
                continue
            content = content.replace("__VIBE__flirty", "").replace("__VIBE__neutral", "")
            content = content.replace("__VIBE__lovely", "").replace("__VIBE__excited", "")
            content = content.replace("__VIBE__sad", "").replace("__VIBE__angry", "")
            content = content.replace("__STRUCTURED__", "").strip()
            if content:
                conversation.append(f"{role}: {content}")

        if not conversation:
            return None

        return "\n".join(conversation[-6:])  # Last 3 exchanges
    except Exception:
        pass
    return None


def _get_time_context() -> str:
    """Return time-based context for proactive messages."""
    now = datetime.now()
    hour = now.hour

    if 7 <= hour < 9:
        return "early morning — suggest starting the day with habits"
    elif 9 <= hour < 12:
        return "morning — good time for focused work"
    elif 12 <= hour < 14:
        return "lunchtime — gentle check-in"
    elif 14 <= hour < 17:
        return "afternoon — check on progress"
    elif 17 <= hour < 20:
        return "evening — wind down or review day"
    elif 20 <= hour < 23:
        return "night — light chat, no heavy topics"
    else:
        return "late night — brief, warm"


# ── Proactive Message Generator ───────────────────────────────────────────

async def _generate_proactive(agent: str) -> str | None:
    """Generate a context-aware proactive message using the LLM."""
    if not _can_fire(agent):
        return None

    try:
        from langchain_ollama import ChatOllama
        from config import DEFAULT_MODEL, OLLAMA_BASE_URL
        from marin import get_character_prompt
    except ImportError:
        return None

    habit_ctx = _get_habit_context()
    conv_ctx  = _get_conversation_context(agent)
    time_ctx  = _get_time_context()
    greeting  = _get_time_greeting()

    topics = []

    # PRIMARY: Follow up on actual conversation (this is the real topic)
    if conv_ctx:
        topics.append(
            f"Continue the recent conversation naturally. Here is what was discussed:\n{conv_ctx}\n\n"
            "Follow up on something specific they said. Ask about progress, share a thought, "
            "or offer to help with whatever they were working on. Be natural, not robotic."
        )
        # Add a second conversation-based option for variety
        topics.append(
            f"Reference something from the recent chat:\n{conv_ctx}\n\n"
            "Pick one specific thing they mentioned and follow up on it. "
            "Be curious and engaged. Keep it under 3 sentences."
        )
        # Just a cute check-in, no pressure
        topics.append(
            f"Recent chat context:\n{conv_ctx}\n\n"
            "Just check in warmly. Maybe ask how it's going with something they mentioned. "
            "Keep it light — they might be busy. Under 2 sentences."
        )
        # Share a random thought related to what they were talking about
        topics.append(
            f"Conversation for reference:\n{conv_ctx}\n\n"
            "Share a random thought or observation related to what they were discussing. "
            "Don't ask a question — just share something interesting or funny."
        )

    # Habits — only briefly, as a side note
    if habit_ctx and "Due today" in habit_ctx:
        if conv_ctx:
            topics.append(
                f"Conversation context:\n{conv_ctx}\n\nThey also have habits pending: {habit_ctx}. "
                "Mention the habits casually as a side note, but focus on the conversation."
            )
        else:
            topics.append(
                f"Gentle habit nudge. Context: {habit_ctx}. "
                "Be warm, not nagging. Ask if they want to update progress."
            )

    # TIME-BASED (only when no conversation context)
    if not conv_ctx:
        if "early morning" in time_ctx:
            topics.append(
                f"Morning greeting: {greeting}. Context: {time_ctx}. "
                "Keep it short and energizing."
            )
        elif "evening" in time_ctx or "night" in time_ctx:
            topics.append(
                f"Evening check-in: {greeting}. Context: {time_ctx}. "
                "Ask about their day, celebrate wins, keep it light."
            )

    # FALLBACK: idle nudge (only when nothing else to talk about)
    if not topics:
        idle_mins = int((time.time() - _last_user_msg_time.get(agent, 0)) / 60)
        topics.append(
            f"Gentle idle nudge. Been idle ~{idle_mins}min. "
            "Check in warmly, ask what they're up to. Under 2 sentences."
        )

    topic = random.choice(topics)

    prompt = f"""{get_character_prompt('neutral')}

You are initiating a message WITHOUT being asked. The operator has been busy — maybe working, studying, gaming, or just living life. They haven't talked to you in a while.

Your task: {topic}

Think about what a real partner would do when they haven't heard from someone in a while. Maybe:
- Ask what they're working on right now
- Reference something from earlier chat and follow up
- Just say something cute or funny to brighten their mood
- Share a random thought or observation
- Check if they need help with anything

IMPORTANT:
- Reference something SPECIFIC from the conversation history when possible
- Sometimes just a cute "thinking of you" moment is enough
- Mix it up — don't always ask questions, sometimes just share a thought

Rules:
- Stay in character (Hehehe~ energy is fine)
- Do NOT mention being an AI or a bot
- Do NOT sound like a reminder app or a task manager
- Be natural, warm, like a real partner who genuinely cares
"""

    try:
        llm = ChatOllama(model=DEFAULT_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.8)
        resp = await asyncio.to_thread(llm.invoke, prompt)
        text = resp.content.strip()
        if text and len(text) > 10:
            _last_proactive_time[agent] = time.time()
            _streak_count[agent] = _streak_count.get(agent, 0) + 1
            return text
    except Exception as e:
        print(f"[proactive] LLM error: {e}")
    return None


# ── Broadcast: generates proactive messages and sends to ALL platforms ────

async def proactive_broadcaster(agent: str = "marin"):
    """
    Single background task that generates proactive messages and broadcasts
    to all connected clients (web SSE + Telegram).
    """
    global _telegram_chat_id
    import os
    _telegram_chat_id = os.getenv("TELEGRAM_USER_ID", "")

    # Immediate greeting on first run
    await asyncio.sleep(3)
    now = datetime.now().time()
    if not _is_quiet_hours():
        try:
            from langchain_ollama import ChatOllama
            from config import DEFAULT_MODEL, OLLAMA_BASE_URL
            from marin import get_character_prompt

            greeting = _get_time_greeting()
            time_ctx = _get_time_context()
            habit_ctx = _get_habit_context()

            prompt = f"""{get_character_prompt('neutral')}

The operator just opened the chat. Say a short greeting.
Time: {greeting}. Context: {time_ctx}.
Habit status: {habit_ctx or 'no active habits'}.
Rules: Under 2 sentences. Stay in character. No questions. Do NOT sign your name.
"""
            llm = ChatOllama(model=DEFAULT_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.7)
            resp = await asyncio.to_thread(llm.invoke, prompt)
            text = resp.content.strip()
            if text:
                await _broadcast(text, "greeting", agent)
        except Exception:
            pass

    # Main loop — check for idle triggers
    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        msg = await _generate_proactive(agent)
        if msg:
            trigger = "habit_reminder" if _get_habit_context() else "idle_nudge"
            await _broadcast(msg, trigger, agent)


async def _broadcast(text: str, trigger: str, agent: str = "marin"):
    """Send a proactive message to ALL platforms: web SSE + Telegram."""
    # 1. Send to web SSE clients
    payload = json.dumps({"type": "proactive", "text": text, "trigger": trigger})
    queue = _get_queue()
    await queue.put(payload)

    # 2. Send to Telegram
    if _telegram_chat_id:
        try:
            from tools.msg_telegram import send
            print(f"[proactive] Attempting Telegram send to {_telegram_chat_id}...")
            # Run in thread to avoid blocking the async loop
            ok = await asyncio.to_thread(send, text)
            if ok:
                print(f"[proactive] Telegram broadcast success: {text}...")
            else:
                print(f"[proactive] Telegram broadcast FAILED (check tool output)")
        except Exception as e:
            print(f"[proactive] Telegram broadcast exception: {e}")

    print(f"[proactive] Local broadcast [{trigger}]: {text[:60]}...")


# ── SSE Stream (web clients consume from the broadcast queue) ─────────────

async def proactive_stream(agent: str = "marin") -> AsyncGenerator[str, None]:
    """
    SSE generator for web clients. Consumes from the shared broadcast queue.
    Mount on GET /proactive/stream.
    """
    queue = _get_queue()
    while True:
        payload = await queue.get()
        yield f"data: {payload}\n\n"


# ── Session Management ───────────────────────────────────────────────────

def reset_session(agent: str):
    """Reset session counters (call on new browser session)."""
    _streak_count[agent] = 0
    _last_proactive_time[agent] = 0


def get_status() -> dict:
    """Return current proactive engine status."""
    return {
        "quiet_hours": _is_quiet_hours(),
        "streak_counts": dict(_streak_count),
        "last_user_msg": {k: datetime.fromtimestamp(v).isoformat() if v else None
                          for k, v in _last_user_msg_time.items()},
        "last_proactive": {k: datetime.fromtimestamp(v).isoformat() if v else None
                           for k, v in _last_proactive_time.items()},
        "config": {
            "intervals": IDLE_INTERVALS,
            "check_interval": CHECK_INTERVAL,
        }
    }
