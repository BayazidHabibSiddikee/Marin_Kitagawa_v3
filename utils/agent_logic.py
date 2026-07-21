import asyncio
import re
import threading
from collections.abc import AsyncIterator
from typing import Any

import httpx

import database
from config import RAG_PORT
from utils.persona import analyze_marin_vibe, get_character_prompt
from utils.security import log_command

# ── RAG configuration ──────────────────────────────────────────────────────────
RAG_URL = f"http://127.0.0.1:{RAG_PORT}"

def fix_spacing(text: str) -> str:
    """Fix missing spaces between words from small models.
    '.' and ':' only split before an uppercase letter so decimals (3.14),
    domains (example.com), filenames (file.py) and 'Label:value' survive.
    """
    if not text:
        return text
    # 1. camelCase: wordWord -> word Word
    text = re.sub(r'([a-z,])([A-Z])', r'\1 \2', text)
    # 2. Punctuation: word,word -> word, word
    #    '.' and ':' only split before uppercase so decimals/URLs survive
    text = re.sub(r'([,!?;])([a-zA-Z])', r'\1 \2', text)
    text = re.sub(r'([.:])([A-Z])', r'\1 \2', text)
    # 3. Common glued words (aggressive for 0.5B models)
    glued = [
        (r'([iI])(don\'?t)', r'\1 \2'),
        (r'([iI])(can\'?t)', r'\1 \2'),
        (r'([iI])(am)', r'\1 \2'),
        (r'([iI])(\'m)', r'\1 \2'),
        (r'(but)(as)(an)', r'\1 \2 \3'),
        (r'(but)(an)', r'\1 \2'),
        (r'(is)(a)', r'\1 \2'),
        (r'(to)(you)', r'\1 \2'),
        (r'(for)(you)', r'\1 \2'),
        (r'(of)(the)', r'\1 \2'),
        (r'(in)(the)', r'\1 \2'),
        (r'(it)(is)', r'\1 \2'),
        (r'(and)(the)', r'\1 \2'),
        (r'(asan)', r'as an'),
        (r'(tobe)', r'to be'),
        (r'(witha)', r'with a'),
        (r'(operatewitha)', r'operate with a'),
        (r'(staticlist)', r'static list'),
        (r'(languagemodel)', r'language model'),
        (r'(im|I\'m)(sorry)', r"I'm \2"),
    ]
    for pattern, repl in glued:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    # 4. Final cleanup
    return re.sub(r'  +', ' ', text)

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
    r'make\s*.*|gcc\s+.*'
    r')`?\s*$',
    re.MULTILINE | re.IGNORECASE
)

MAX_CONCURRENT_COMMANDS = 3
_active_command_count = 0
_active_command_lock = threading.Lock()

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

    if not raw_cmds:
        return

    user_id = user["user_id"]

    from utils.command_runner import run_command

    def _run_task(cmd):
        global _active_command_count
        with _active_command_lock:
            _active_command_count += 1
        try:
            import shlex
            try:
                shlex.split(cmd)
                from safety import system_guard
                if not system_guard.is_authorized(user_id):
                    log_command(cmd, "blocked", "Password authorization required for terminal commands.", user_id=user_id)
                    return

                code, output = run_command(cmd, timeout=30)
                log_command(cmd, "done" if code == 0 else f"exit {code}", output, user_id=user_id)
            except Exception as e:
                log_command(cmd, "error", str(e), user_id=user_id)
        finally:
            with _active_command_lock:
                _active_command_count -= 1

    started = 0
    for cmd in raw_cmds:
        with _active_command_lock:
            if _active_command_count >= MAX_CONCURRENT_COMMANDS:
                log_command(cmd, "blocked", f"Too many concurrent commands (max {MAX_CONCURRENT_COMMANDS}).", user_id=user_id)
                continue
        threading.Thread(target=_run_task, args=(cmd,), daemon=True).start()
        started += 1

# ── Unified Preprocessor ─────────────────────────────────────────────────────

async def preprocess_input(user_input: str, image_path: str = None, rag_enabled: bool = False) -> dict[str, Any]:
    from marin_fier import classify

    classification = classify(user_input)

    rag_context = ""
    if rag_enabled:
        rag_context = await get_rag_context(user_input)

    # (YouTube transcript logic can be added here if needed)

    parts = []
    if rag_context:   parts.append(f"[KNOWLEDGE HUB - SYSTEM RETRIEVED CONTEXT]\n{rag_context}\n[END KNOWLEDGE HUB]")

    enriched_prompt = "\n\n".join(parts)

    return {
        "enriched_prompt": enriched_prompt,
        "classification": classification,
        "rag_context": rag_context
    }

# ── Control tags (YouTube, VRM director, projector) ─────────────────────────

_CONTROL_TAG_PATTERNS = [
    r'__YOUTUBE__[\w-]+',
    r'__DIRECTOR__[A-Za-z0-9+/=]+',
    r'__DANCE__',
    r'__STREAM__\S+',
    r'__BROWSER__\S+',
    r'__ANIM__\w+',
    r'__SEARCH__\S+',
    r'__PROJECTOR_OFF__',
]

def extract_control_tags(text: str) -> tuple[str, list[str]]:
    """Split control tags from speakable text. Tags are yielded separately to the UI."""
    if not text:
        return "", []
    tags: list[str] = []
    clean = text
    for pattern in _CONTROL_TAG_PATTERNS:
        for match in re.findall(pattern, clean):
            if match not in tags:
                tags.append(match)
            clean = clean.replace(match, "")
    # Strip LLM meta-instructions that leak from tool output
    clean = re.sub(r'\[video:[^\]]*\]', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\[mood:[^\]]*\]', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'You MUST include\b[^.]*\.?', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\s{2,}', ' ', clean).strip()
    return clean, tags


async def stream_marin_chat(
    prompt: str,
    user: dict,
    session_id: str = "default",
    image_path: str = None
) -> AsyncIterator[str]:
    """
    Two-System Pipeline:
    1. Fast Classification (Regex)
    2. Path A: Instant Persona Response (direct to user)
    3. Path B: Background Tool Execution (if needed, result via /api/pending)
    """
    user_id = user["user_id"]
    is_owner = (user["role"] == "owner")

    # 1. Fast Intent Detection
    from langgraph_agent import get_llm, log_agent
    from marin_fier import classify
    log_agent(f"AgentLogic: Classifying prompt: {prompt[:50]}...")
    cls = classify(prompt)
    intent = cls["intent"]
    user_vibe = cls.get("user_vibe", "neutral")
    log_agent(f"AgentLogic: Detected intent '{intent}' with confidence {cls['confidence']:.2f}")

    # Tool detection — broad keywords covering real user requests
    TOOL_KEYWORDS = [
        "download", "search", "find", "get me", "fetch", "grab",
        "book", "pdf", "paper", "textbook", "ebook",
        "analyze", "stock", "crypto", "bitcoin", "news", "weather",
        "alarm", "timer", "screenshot", "batch", "convert",
        "habit", "trade", "buy", "sell", "install", "update",
        "play", "open", "launch", "run", "execute", "command",
        "ls", "list", "read", "file", "write", "check", "system",
    ]
    p_lower = prompt.lower()
    needs_tools = any(kw in p_lower for kw in TOOL_KEYWORDS) or (intent != "chat" and cls["confidence"] > 0.8)

    # ── HYBRID EXECUTION: Inline for high-confidence tools ──
    tool_result = None
    tool_tags: list[str] = []
    inline_complete = False

    if intent != "chat" and cls["confidence"] >= 0.9 and needs_tools:
        from marin_fier import execute_tool
        raw_tool_result = await execute_tool(intent, cls.get("params", {}), user_id)
        if raw_tool_result is not None:
            tool_result, tool_tags = extract_control_tags(raw_tool_result)
            inline_complete = True
            needs_tools = False
            # Push YouTube/VRM tags immediately so TV + avatar react without waiting for LLM
            for tag in tool_tags:
                yield tag

    # 2. INSTANT PERSONA RESPONSE
    from config import PERSONA_MODEL

    persona_llm = get_llm(PERSONA_MODEL)
    theme = "evil" if is_owner else "standard"
    user_name = database.get_state("USER_NAME") or "Limon"
    system = get_character_prompt(user_vibe, theme=theme, user_name=user_name)

    # Make Persona aware of what it is doing
    context_instruction = "\nIMPORTANT: ALWAYS use proper spaces. Do NOT glom words."
    if tool_result:
        context_instruction += (
            f"\n[SYSTEM: Tool {intent} completed. Speakable result:\n{tool_result}\n"
            "Say ONE short natural line about this (1-2 sentences). "
            "Do NOT repeat system instructions or mention tags/commands.]"
        )
    elif needs_tools:
        context_instruction += (
            f"\n[SYSTEM: The user has requested a task that requires your tools ({intent}). "
            "DO NOT say you cannot do it. Tell the user you are handling it right now and will deliver the result shortly. "
            "Be confident and in-character. Keep it under 2 sentences.]"
        )

    history = database.get_history("marin", limit=10, user_id=user_id, session_id=session_id)

    full_response = ""

    fast_msgs = [
        {"role": "system", "content": system + context_instruction},
        *[{"role": m["role"], "content": m["content"]} for m in history],
        {"role": "user", "content": prompt}
    ]

    # Optional: Voice trigger for the response
    import marin
    if getattr(marin, "VOICE_ENABLED", False):
        yield "__TALK_ON__"

    try:
        async for chunk in persona_llm.astream(fast_msgs):
            if chunk.content:
                full_response += chunk.content
                yield chunk.content
    except Exception as e:
        print(f"[AgentLogic] Streaming error: {e}")
        if not full_response:
            yield "Sorry, I hit a snag. Please try again~"
        return

    if full_response:
        database.save_message("marin", "user", prompt, user_id=user_id, session_id=session_id)
        database.save_message("marin", "assistant", full_response, user_id=user_id, session_id=session_id)
        vibe = analyze_marin_vibe(full_response)
        yield f"__VIBE__{vibe}"

        # ── Director Script: timed action sequence for VRM playback ──────────
        try:
            from director_engine import make_director_tag, vibe_to_emotion
            # Always derive emotion from Marin's OWN response (not the user's input)
            # This ensures VRM reflects what Marin is saying/feeling, not what user said
            director_emotion = vibe_to_emotion(vibe)
            director_tag = make_director_tag(full_response, director_emotion)
            yield director_tag
        except Exception as _de:
            pass  # Director is non-critical — never break the stream

    # 3. Path B: BACKGROUND TOOL EXECUTION
    # Trigger if: keywords matched OR Marin's response shows she refused/deferred a tool task
    REFUSAL_PATTERNS = ["i cannot", "i can't", "i don't have the ability", "i'm unable", "cannot download", "cannot access"]
    response_implies_tool = any(p in full_response.lower() for p in REFUSAL_PATTERNS)

    if not inline_complete and (needs_tools or response_implies_tool):
        from langgraph_agent import run_background_tools
        asyncio.create_task(run_background_tools(prompt, history, user_id, user["role"], user_vibe, session_id))
