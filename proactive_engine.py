#!/usr/bin/env python3
"""
proactive_engine.py — Marin can initiate conversations unprompted.
Triggers: idle timeout, schedule, context events, page load.
Delivers via SSE to frontend.
"""

import asyncio
import json
import random
import time
from datetime import datetime, time as dtime
from typing import AsyncGenerator

# ── Config ────────────────────────────────────────────────────────────────
IDLE_COOLDOWN   = 600    # 10 min after last user msg before Marin can speak
MIN_GAP         = 600    # 10 min minimum between proactive messages
MAX_PER_SESSION = 3      # max proactive messages per session
QUIET_START     = dtime(0, 0)   # midnight
QUIET_END       = dtime(8, 0)   # 8am

# ── State ─────────────────────────────────────────────────────────────────
_last_user_msg_time: dict[str, float]  = {}
_last_proactive_time: dict[str, float] = {}
_session_count: dict[str, int]         = {}


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


async def _generate_proactive(agent: str) -> str | None:
    """Ask the LLM to produce an unprompted message."""
    if not _can_fire(agent):
        return None

    from langchain_ollama import ChatOllama
    from config import DEFAULT_MODEL, OLLAMA_BASE_URL
    from marin import get_character_prompt

    topics = [
        "check in warmly — you noticed the operator has been idle for a while",
        "share a small technical insight relevant to CNC, maths, or embedded systems",
 "give a gentle productivity nudge — ask if they want to start a focus session",
        "drop a quick market observation if something interesting is happening",
        "just say something playful and in-character — keep it under 2 sentences",
    ]
    topic = random.choice(topics)

    prompt = f"""{get_character_prompt('neutral')}

You are initiating a message WITHOUT being asked. The operator has been idle.
Your task: {topic}

Rules:
- Under 3 sentences
- No questions that need a long answer
- Stay in character (Hehehe~~ energy is fine)
- Do NOT start with "I" — vary your openers
- Do NOT mention being an AI or a bot
"""
    try:
        llm = ChatOllama(model=DEFAULT_MODEL, base_url=OLLAMA_BASE_URL)
        resp = await asyncio.to_thread(llm.invoke, prompt)
        text = resp.content.strip()
        if text:
            _last_proactive_time[agent] = time.time()
            _session_count[agent] = _session_count.get(agent, 0) + 1
            return text
    except Exception as e:
        print(f"[proactive] LLM error: {e}")
    return None


async def proactive_stream(agent: str) -> AsyncGenerator[str, None]:
    """
    SSE generator. Mount on GET /proactive/stream.
    Yields: data: {"type":"proactive","text":"..."}
    """
    CHECK_INTERVAL = 60  # check every 60s

    # Immediate greeting on first connection (page load trigger)
    now = datetime.now().time()
    if not _is_quiet_hours():
        from marin import get_character_prompt
        from config import DEFAULT_MODEL, OLLAMA_BASE_URL
        from langchain_ollama import ChatOllama

        hour = now.hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"

        try:
            llm = ChatOllama(model=DEFAULT_MODEL, base_url=OLLAMA_BASE_URL)
            prompt = f"""{get_character_prompt('neutral')}
Say a short greeting to the operator who just opened the chat. 
Greeting: {greeting}
Rules: Under 2 sentences. Stay in character. No questions.
"""
            resp = await asyncio.to_thread(llm.invoke, prompt)
            text = resp.content.strip()
            if text:
                payload = json.dumps({"type": "proactive", "text": text})
                yield f"data: {payload}\n\n"
        except Exception:
            pass

    # Main loop — check for idle triggers
    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        msg = await _generate_proactive(agent)
        if msg:
            payload = json.dumps({"type": "proactive", "text": msg})
            yield f"data: {payload}\n\n"


def reset_session(agent: str):
    """Reset session counters (call on new browser session)."""
    _session_count[agent] = 0
    _last_proactive_time[agent] = 0
