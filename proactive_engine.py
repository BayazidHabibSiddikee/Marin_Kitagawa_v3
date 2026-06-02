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
IDLE_COOLDOWN   = 3600   # 60 min after last user message before proactive nudge
MIN_GAP         = 7200   # 2 hours minimum between proactive messages
MAX_PER_SESSION = 2      # max proactive messages per browser session
QUIET_START     = dtime(0, 0)    # midnight
QUIET_END       = dtime(7, 30)   # 7:30 AM
CHECK_INTERVAL  = 90     # seconds between proactive checks

# ── State (per browser session) ───────────────────────────────────────────
_last_user_msg_time: dict[str, float]  = {}
_last_proactive_time: dict[str, float] = {}
_session_count: dict[str, int]         = {}

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


def _is_quiet_hours() -> bool:
    now = datetime.now().time()
    if QUIET_START < QUIET_END:
        return QUIET_START <= now < QUIET_END
    return now >= QUIET_START or now < QUIET_END


def _can_fire(agent: str) -> bool:
    now = time.time()
    last_user = _last_user_msg_time.get(agent, 0)
    last_pro  = _last_proactive_time.get(agent, 0)
    count     = _session_count.get(agent, 0)

    if _is_quiet_hours():              return False
    if count >= MAX_PER_SESSION:       return False
    if now - last_user < IDLE_COOLDOWN: return False
    if now - last_pro  < MIN_GAP:      return False
    return True


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

    # SECONDARY: Habits (only if no conversation context, or as a brief mention)
    if habit_ctx and "Due today" in habit_ctx:
        if conv_ctx:
            # If we have conversation context, just briefly mention habits
            topics.append(
                f"Briefly mention they have habits pending: {habit_ctx}. "
                "But FIRST follow up on what they were talking about. "
                "Keep the habit mention short, like a gentle side note."
            )
        else:
            # No conversation context — habits are the main topic
            topics.append(
                f"Give a gentle habit reminder. Context: {habit_ctx}. "
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

You are initiating a message WITHOUT being asked. The operator has been idle.
Your task: {topic}

IMPORTANT: Reference something SPECIFIC from the conversation. Quote their words, 
mention a project name, follow up on a question they asked. Be concrete, not generic.

Rules:
- Under 3 sentences
- Stay in character (Hehehe~ energy is fine)
- Do NOT start every sentence with "I"
- Do NOT mention being an AI or a bot
- Be natural, like a real partner who genuinely cares about what they were working on
"""

    try:
        llm = ChatOllama(model=DEFAULT_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.8)
        resp = await asyncio.to_thread(llm.invoke, prompt)
        text = resp.content.strip()
        if text and len(text) > 10:
            _last_proactive_time[agent] = time.time()
            _session_count[agent] = _session_count.get(agent, 0) + 1
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
Rules: Under 2 sentences. Stay in character. No questions.
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
            send(f"💬 *Marin:* {text}")
            print(f"[proactive] Telegram broadcast: {text[:60]}...")
        except Exception as e:
            print(f"[proactive] Telegram error: {e}")

    print(f"[proactive] Broadcast [{trigger}]: {text[:60]}...")


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
    _session_count[agent] = 0
    _last_proactive_time[agent] = 0


def get_status() -> dict:
    """Return current proactive engine status."""
    return {
        "quiet_hours": _is_quiet_hours(),
        "session_counts": dict(_session_count),
        "last_user_msg": {k: datetime.fromtimestamp(v).isoformat() if v else None
                          for k, v in _last_user_msg_time.items()},
        "last_proactive": {k: datetime.fromtimestamp(v).isoformat() if v else None
                           for k, v in _last_proactive_time.items()},
        "config": {
            "idle_cooldown": IDLE_COOLDOWN,
            "min_gap": MIN_GAP,
            "max_per_session": MAX_PER_SESSION,
            "check_interval": CHECK_INTERVAL,
        }
    }
