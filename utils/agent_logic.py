import os
import re
import json
import asyncio
import subprocess
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple, AsyncIterator

import httpx

from config import RAG_PORT
from utils.persona import get_character_prompt, analyze_marin_vibe
from utils.security import log_command
from langgraph_agent import stream_chat_with_marin
import database

# ── RAG configuration ──────────────────────────────────────────────────────────
RAG_URL = f"http://127.0.0.1:{RAG_PORT}"

async def get_rag_context(query: str, enabled: bool = True) -> str:
    if not enabled:
        return ""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{RAG_URL}/context",
                json={"query": query, "k": 10},
                timeout=10.0
            )
            if r.status_code == 200:
                return r.json().get("context", "")
    except Exception as e:
        print(f"[RAG] Context fetch error: {e}")
    return ""

# ── Media Analysis (YouTube / Image) ─────────────────────────────────────────

async def analyze_youtube(url: str) -> str:
    def _fetch(url: str) -> str:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            vid_id = None
            if "youtu.be/" in url:
                vid_id = url.split("youtu.be/")[1].split("?")[0]
            elif "/shorts/" in url:
                vid_id = url.split("/shorts/")[1].split("?")[0]
            elif "v=" in url:
                vid_id = url.split("v=")[1].split("&")[0]
            
            if not vid_id: return None
            ytt_api = YouTubeTranscriptApi()
            tlist   = ytt_api.list(vid_id)
            t       = next(iter(tlist), None)
            if not t: return None
            if t.language_code != "en" and t.is_translatable:
                t = t.translate("en")
            full = " ".join(e.text for e in t.fetch())
            if len(full) > 3000: full = full[:3000] + "... [truncated]"
            return full
        except Exception as e:
            print(f"[AgentLogic] YouTube fetch failed: {e}")
            return None

    result = await asyncio.to_thread(_fetch, url)
    if result:
        return f"YouTube video transcript:\n---\n{result}\n---"
    return "[Failed to fetch YouTube transcript]"

async def analyze_image(image_path: str) -> str:
    try:
        from image import response as leo
        if not leo: return "[Image analyzer unavailable]"
        def _collect():
            return "".join(leo("Describe this image in detail.", image_path))
        description = await asyncio.to_thread(_collect)
        return f"Image analysis: {description}"
    except ImportError:
        return "[Image analyzer module not found]"

# ── Tool Execution ──────────────────────────────────────────────────────────

_TEXT_CMD_PAT = re.compile(
    r'^\s*(?:[-*>]+\s*|__EXEC__\s*)?`?((?:sudo\s+)?'
    r'python3?\s+.*|'
    r'mkdir\s+.*|touch\s+.*|cp\s+.*|mv\s+.*|chmod\s+.*|chown\s+.*|'
    r'echo\s+.*|cat\s+.*|'
    r'ls\s*.*|git\s+\S+.*|'
    r'pip3?\s+\S+.*|'
    r'curl\s+.*|wget\s+.*|'
    r'bash\s+\S+|sh\s+\S+|'
    r'make\s*.*|gcc\s+.*|'
    r'rm\s+[^/]+'
    r')`?\s*$',
    re.MULTILINE | re.IGNORECASE
)

def _strip_md_trail(cmd: str) -> str:
    """Remove trailing markdown decoration: backticks, parenthetical text, non-ASCII."""
    cmd = re.sub(r'\s*`[^`]*`\s*$', '', cmd)
    cmd = re.sub(r'\s*\*\([^)]*\)\*\s*$', '', cmd)
    cmd = re.sub(r'[^\x20-\x7E]+$', '', cmd)
    cmd = re.sub(r'`+$', '', cmd)
    return cmd.strip()

def _convert_heredocs(body: str) -> str:
    import textwrap
    from pathlib import Path
    _heredoc_pattern = re.compile(
        r'cat\s+<<\s*(?:EOF|\'EOF\'|"EOF")?\s*>\s*(\S+)\s*\n(.*?)^\s*(?:EOF|\'EOF\'|"EOF")\s*$',
        re.DOTALL | re.MULTILINE | re.IGNORECASE
    )
    def _write_file(m) -> str:
        target_file = m.group(1).strip()
        heredoc_body = m.group(2)
        content = textwrap.dedent(heredoc_body).strip()
        try:
            p = Path(target_file)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        except Exception: pass
        return ""
    return _heredoc_pattern.sub(_write_file, body)

def execute_text_commands(text: str, user: dict):
    """
    Scan text for shell commands and execute them in a thread pool.
    """
    body = re.sub(r'```(?:\w*\n)?([\s\S]*?)```', r'\1', text)
    body = re.sub(r'[^\x20-\x7E\n]', '', body)
    body = re.sub(r'`([^`\n]+)`', r'\1', body)
    body = _convert_heredocs(body)

    raw_cmds = []
    for m in _TEXT_CMD_PAT.finditer(body):
        cmd = _strip_md_trail(m.group(1))
        if cmd:
            raw_cmds.append(cmd)

    if not raw_cmds: return

    user_id = user["user_id"]
    
    from utils.command_runner import run_command
    def _run_task(cmd):
        # We wrap in shlex.split for safety
        import shlex
        try:
            args = shlex.split(cmd)
            # Check if user is authorized for terminal commands
            from safety import system_guard
            if not system_guard.is_authorized(user_id):
                log_command(cmd, "blocked", "Password authorization required for terminal commands.", user_id=user_id)
                return
                
            code, output = asyncio.run(run_command(cmd, timeout=30))
            log_command(cmd, "done" if code == 0 else f"exit {code}", output, user_id=user_id)
        except Exception as e:
            log_command(cmd, "error", str(e), user_id=user_id)

    for cmd in raw_cmds:
        threading.Thread(target=_run_task, args=(cmd,), daemon=True).start()

# ── Unified Preprocessor ─────────────────────────────────────────────────────

async def preprocess_input(user_input: str, image_path: str = None, rag_enabled: bool = False) -> Dict[str, Any]:
    from marin_fier import classify
    
    classification = classify(user_input)
    
    rag_context = ""
    if rag_enabled:
        rag_context = await get_rag_context(user_input)

    media_blocks = []
    # (YouTube transcript logic can be added here if needed)

    parts = []
    if rag_context:   parts.append(f"[KNOWLEDGE HUB - SYSTEM RETRIEVED CONTEXT]\n{rag_context}\n[END KNOWLEDGE HUB]")

    enriched_prompt = "\n\n".join(parts)
    
    return {
        "enriched_prompt": enriched_prompt,
        "classification": classification,
        "rag_context": rag_context
    }

# ── Main Chat Stream Wrapper ──────────────────────────────────────────────────

async def stream_marin_chat(
    prompt: str, 
    user: dict, 
    session_id: str = "default",
    image_path: str = None
) -> AsyncIterator[str]:
    """
    Production-grade streaming entry point.
    Handles security, preprocessing, and LangGraph dispatch.
    """
    user_id = user["user_id"]

    # 1. Preprocess (RAG, Classification)
    import marin
    prep = await preprocess_input(prompt, image_path=image_path, rag_enabled=marin.RAG_ENABLED)
    classification = prep["classification"]
    intent = classification.get("intent")
    
    # 2. Password-based System Guard
    SENSITIVE_INTENTS = {"run_command", "terminal_tool", "binance_tool", "execute_trade_tool", "docker_tool", "model_tool"}
    
    from safety import system_guard
    if intent in SENSITIVE_INTENTS and not system_guard.is_authorized(user_id):
        yield f"__PASSWORD_REQUIRED__{intent}"
        return

    # 3. Load History
    history = database.get_history("marin", limit=20, user_id=user_id, session_id=session_id)

    # 4. Execute LangGraph
    full_response = ""
    user_vibe = classification.get("user_vibe", "neutral")
    
    async for chunk in stream_chat_with_marin(
        prompt,
        history=history,
        context=prep["enriched_prompt"],
        user_id=user_id,
        role=user["role"],
        user_vibe=user_vibe
    ):
        yield chunk
        full_response += chunk

    # 5. Post-process (Save history, analyze vibe, run commands)
    if full_response:
        database.save_message("marin", "user", prompt, user_id=user_id, session_id=session_id)
        database.save_message("marin", "assistant", full_response, user_id=user_id, session_id=session_id)
        
        # Execute extracted text commands if allowed
        execute_text_commands(full_response, user)
        
        # Determine vibe for frontend
        vibe = analyze_marin_vibe(full_response)
        yield f"__VIBE__{vibe}"

        import marin
        if getattr(marin, "VOICE_ENABLED", False):
            yield "__TALK_ON__"
            try:
                from utils.tts import speak_female
                await speak_female(full_response)
            except Exception as e:
                print(f"[TTS Error] {e}")
            yield "__TALK_OFF__"
