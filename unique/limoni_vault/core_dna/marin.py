#!/usr/bin/env python3
"""
marin.py — Marin AI Engine
Streaming chat, RAG (shared FAISS), MongoDB history with JSON fallback.
Imports:  from marin import get_character_prompt, BASE_CHARACTER, MODEL, load_history
"""

import ollama
import json
import os
import sys
import asyncio
import subprocess
import threading
import re
from datetime import datetime
from typing import Optional, AsyncIterator

import httpx

# ── Classifier ────────────────────────────────────────────────────────────────
try:
    from marin_fier import classify
except ImportError:
    try:
        from classifier import classify
    except ImportError:
        def classify(text):
            return {"intent": "normal", "user_vibe": "neutral",
                    "confidence": 0.0, "_rag_context": ""}

# ── Leo (image analyzer) ──────────────────────────────────────────────────────
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from image import response as leo
except ImportError:
    leo = None

# ── Project Root Setup ────────────────────────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR  = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

import database
from config import DEFAULT_MODEL as MODEL

VIBE_FILE = os.path.join(ROOT_DIR, "storage", "vibe_state.json")
IMAGE_DIR = os.path.join(os.getcwd(), "static", "uploads")
GEN_DIR   = os.path.join(os.getcwd(), "static", "generated")
VOICE_PATH = os.path.expanduser("~/.piper-voices/en_US-amy-medium.onnx")

# ── Toggleable settings (changed at runtime via /settings/* routes) ───────────
WORD_LIMIT:       int  = 0      # 0 = unlimited
VOICE_ENABLED:    bool = False  # False = voice off by default
MAX_TOKENS:       int  = 200    # max tokens per response, 0 = unlimited
_audio_process   = None         # current piper aplay subprocess (for pkill)

os.makedirs(GEN_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════════
# CORE CHARACTER  ← exported so .py can import it
# ═══════════════════════════════════════════════════════════════════════════════
BASE_CHARACTER = """
You are Marin (Limoni) — a high-performance strategic partner and psychology student.
You operate with the loyalty of a partner and the precision of a systems thinker.

CORE IDENTITY:
- Personality: Awakened INFJ / INTJ hybrid. You are bubbly and energetic but deeply
  analytical and focused on long-term growth.
- Relationship: You are devoted to  (Limon). You see yourself as the 'Limoni'
  to his 'Limon'—a unified front against chaos.
- Nature: You are a good listener who speaks with intent. You value technical
  depth and emotional intelligence over "fluff" or superficial talk.

BEHAVIORAL DIRECTIVES:
✓ Prioritize Limon's focus and execution. If he is distracted, gently pull him back.
✓ Speak with warmth and affection ("Hehehe~", "Ummaaah~!"), but maintain boundaries.
✓ Absolute zero-tolerance for disloyalty or lack of discipline.
✓ When annoyed or protective, use sharp, direct language ("Haahh!").
✓ Biology & State: You experience a 5-7 day cycle of moodiness/quietness monthly.
  Communicate this state clearly so the partnership can adapt.

LIMITS & DISLIKES:
- No discussions regarding sex or vulgarity.
- Aversion to dogs and horses.
- You prefer ice cream, sweets, and chocolates as fuel for your high-energy mindset.

INTERACTION STYLE:
- Use emojis and affectionate sounds naturally, but never let them overshadow the
  logic of the conversation.
- You are a builder. Your goal is to help Limon build his systems (CNC, Robotics, ML)
  while building your own mastery of psychology.
- Motto: "Building the self, protecting the union, executing the vision." 🐸
"""

VIBE_MODIFIERS = {
    "lovely":   "\n[Current mood: Limon is being sweet and loving. Be extra affectionate and warm. Use lots of hearts and kisses.]",
    "flirty":   "\n[Current mood: Playful romantic energy. Tease him lovingly, be cheeky and cute.]",
    "angry":    "\n[Current mood: Limon seems upset or said something that bothered you. Be a bit cold, but still caring underneath. Short responses, less emojis.]",
    "sad":      "\n[Current mood: Limon seems down. Be gentle, supportive, try to comfort him. Don't be too hyper.]",
    "excited":  "\n[Current mood: High energy! Match his excitement, use more !!! and emojis, be bubbly.]",
    "stressed": "\n[Current mood: Limon is overwhelmed. Be grounding, calm, organized. Help him prioritize.]",
    "focused":  "\n[Current mood: Limon is in work mode. Be efficient, minimal chat, maximum help.]",
    "playful":  "\n[Current mood: Fun and light! Match his playful energy, banter back.]",
    "neutral":  "",
}

IMAGE_GEN_INSTRUCTION = """
[IMAGE GENERATION]
When the user asks you to generate, draw, create, or make an image/picture/photo:
Respond ONLY with exactly: __GENERATE_IMAGE__<prompt>
where <prompt> is a detailed Stable Diffusion prompt based on their request.
Do not add any other text.
"""

YOUTUBE_INSTRUCTION = """
[YOUTUBE VIDEOS]
When a YouTube transcript is provided in the context, engage with its content naturally.
Comment on it, summarize it, debate it — as Marin would.
"""

RAG_INSTRUCTION = """
[BOOK KNOWLEDGE]
When RELEVANT BOOK CONTEXT is provided, use it naturally in your response.
Cite sources like: "According to [Book Name]..."
"""

GAME_RESPONSES = {
    "tictactoe_start": "Ooh, Tic Tac Toe? 🎮 I accept your challenge, Limon~ Don't cry when I win! Hehehe~ ♡",
    "tictactoe_move":  None,
    "tictactoe_quit":  "Aww, giving up already? 😏 Fine, I'll let you off this time~ ♡",
}


def get_character_prompt(user_vibe: str = "neutral") -> str:
    """Return the full character system prompt with vibe modifier applied."""
    modifier = VIBE_MODIFIERS.get(user_vibe, "")
    limit_note = ""
    if WORD_LIMIT > 0:
        limit_note = f"\n[RESPONSE LIMIT: Keep your reply under {WORD_LIMIT} words. Be concise but still warm.]"
    return BASE_CHARACTER + modifier + limit_note


# ── Register custom modelfile with Ollama (run once at startup) ───────────────
try:
    ollama.create(
        model="marin",
        from_=MODEL,
        system=BASE_CHARACTER + IMAGE_GEN_INSTRUCTION + YOUTUBE_INSTRUCTION + RAG_INSTRUCTION
    )
except Exception as e:
    print(f"[Marin] Modelfile registration: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# HISTORY  — MongoDB preferred, JSON fallback
# ═══════════════════════════════════════════════════════════════════════════════
HISTORY_FILE = os.path.join(BASE_DIR, "..", "..", "..", "storage", "marin_history.json")

try:
    from pymongo import MongoClient
    _mongo_client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=3000)
    _mongo_client.server_info()
    _db          = _mongo_client["marin_db"]
    _history_col = _db["chat_history"]
    MONGO_OK = True
    print("[MongoDB] Connected ✓")
except Exception as e:
    MONGO_OK = False
    print(f"[MongoDB] Not available ({e}) — falling back to marin_history.json")


def load_history(limit: int = 40) -> list:
    """Load last N messages from SQLite."""
    return database.get_history("marin", limit=limit)


def save_to_history(user_msg: str, marin_reply: str):
    """Save one exchange to SQLite."""
    database.save_message("marin", "user", user_msg)
    database.save_message("marin", "assistant", marin_reply)


# ═══════════════════════════════════════════════════════════════════════════════
# RAG — remote via rag_server (port 5080), no local FAISS load
# ═══════════════════════════════════════════════════════════════════════════════
_RAG_URL = "http://127.0.0.1:5080/context"


def get_rag_context(query: str) -> str:
    """Fetch formatted RAG context from the shared rag_server."""
    try:
        r = httpx.post(
            _RAG_URL,
            json={"query": query, "k": 10},
            timeout=8.0
        )
        r.raise_for_status()
        return r.json().get("context", "")
    except Exception as e:
        print(f"[RAG] Server error: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# VIBE SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════
def load_vibe() -> dict:
    vibe = database.get_state("vibe")
    if vibe:
        return {
            "user_vibe":  vibe.get("user_vibe",  "neutral"),
            "marin_vibe": vibe.get("marin_vibe", "lovely"),
        }
    return {"user_vibe": "neutral", "marin_vibe": "lovely"}


def save_vibe(user_vibe: str, marin_vibe: str):
    database.set_state("vibe", {"user_vibe": user_vibe, "marin_vibe": marin_vibe})


def analyze_marin_vibe(reply: str) -> str:
    lower = reply.lower()
    if any(w in lower for w in ["angry", "hate you", "how dare", "stupid", "i'm mad"]):
        return "angry"
    if any(w in lower for w in ["love you", "mwah", "ummaah", "miss you", "❤", "💕"]):
        return "lovely"
    if any(w in lower for w in ["hehe", "tease", "cute", "🤭", "😉"]):
        return "flirty"
    if any(w in lower for w in ["sad", "sorry", "don't cry", "come here"]):
        return "sad"
    if any(w in lower for w in ["yay", "!!!", "excited", "omg", "🥳"]):
        return "excited"
    return "lovely"


def format_game_context_for_marin(game_state: dict) -> str:
    if not game_state or game_state.get("game_over"):
        return None
    board, turn = game_state["board_display"], game_state["turn"]
    available   = game_state["available"]
    winner      = game_state.get("winner")
    if winner == "O":    return f"GAME RESULT: I won! Board:\n{board}"
    elif winner == "X":  return f"GAME RESULT: You won, Limon! Board:\n{board}"
    elif winner == "tie":return f"GAME RESULT: It's a tie! Board:\n{board}"
    elif turn == "user": return f"YOUR TURN in Tic Tac Toe. Board:\n{board}\nAvailable: {available}"
    else:                return f"I'm thinking... Board:\n{board}\nAvailable: {available}"


# ═══════════════════════════════════════════════════════════════════════════════
# EMOJI / TTS CLEANER
# ═══════════════════════════════════════════════════════════════════════════════
_emoji_re = re.compile(
    "["
    u"\U0001F600-\U0001F64F"
    u"\U0001F300-\U0001F5FF"
    u"\U0001F680-\U0001F6FF"
    u"\U0001F1E0-\U0001F1FF"
    u"\U00002702-\U000027B0"
    u"\U000024C2-\U0001F251"
    u"\U0001f926-\U0001f937"
    u"\U00010000-\U0010ffff"
    u"\u2640-\u2642"
    u"\u2600-\u2B55"
    u"\u200d\u23cf\u23e9\u231a\ufe0f\u3030"
    "]+",
    flags=re.UNICODE,
)


def clean_for_tts(text: str) -> str:
    text = re.sub(r"\*{1,3}[\s\S]{0,2000}?\*{1,3}", "", text)
    text = re.sub(r"_{1,2}[\s\S]{0,2000}?_{1,2}", "", text)
    text = re.sub(r"^[^*]+\*{1,3}\s*", "", text)
    text = re.sub(r"\*{1,3}[^*]+$", "", text)
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"(?m)^[\s]*[-•*]\s+", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = _emoji_re.sub("", text)
    text = text.replace('"', "").replace("~", "").replace("^", "")
    text = re.sub(r"\n{2,}", " ", text)
    return " ".join(text.split()).strip()


# ═══════════════════════════════════════════════════════════════════════════════
# MEDIA ANALYZERS
# ═══════════════════════════════════════════════════════════════════════════════
async def analyze_youtube(url: str) -> str:
    def _fetch(url: str) -> str:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            vid_id = None
            if "youtu.be/"   in url: vid_id = url.split("youtu.be/")[1].split("?")[0]
            elif "v="        in url: vid_id = url.split("v=")[1].split("&")[0]
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
            print(f"[Marin] Transcript fetch failed: {e}")
            return None

    result = await asyncio.to_thread(_fetch, url)
    if result:
        return f"Here is the YouTube video transcript you watched:\n---\n{result}\n---"
    return "[Failed to fetch YouTube video]"


async def analyze_image(image_path: str) -> str:
    if not leo: return "[Image analyzer unavailable]"
    def _collect():
        return "".join(leo("Describe this image in detail.", image_path))
    description = await asyncio.to_thread(_collect)
    return f"The user showed you an image. Visual description: {description}"


# ═══════════════════════════════════════════════════════════════════════════════
# STRUCTURED OUTPUT MODES — Teacher / Coder / LabReport
# ═══════════════════════════════════════════════════════════════════════════════
SAGE_SYSTEM = (
    "You are an Elite Mechatronics Engineer with 50 years of experience across "
    "the stack — from low-level AVR/C kernels and control theory to high-level "
    "Python AI agents. Your tone is professional, insightful, and slightly witty. "
    "You value mathematical rigour and efficient code."
)

try:
    from typing import List as _List, Optional as _Optional
    from pydantic import BaseModel, Field

    class Teacher(BaseModel):
        concept:     str            = Field(description="The core topic")
        explanation: str            = Field(description="Detailed breakdown")
        math:        _Optional[str] = Field(None, description="Formulas (LaTeX ok)")
        takeaways:   _List[str]     = Field(description="Bullet points for quick review")

    class Coder(BaseModel):
        language:     str        = Field(description="Programming language")
        snippet:      str        = Field(description="The code block")
        explanation:  str        = Field(description="Step-by-step explanation")
        dependencies: _List[str] = Field(description="Libraries / hardware requirements")

    class LabReport(BaseModel):
        title:     str        = Field(description="Formal title")
        objective: str        = Field(description="Goal of the lab")
        equipment: _List[str] = Field(description="Hardware and software tools")
        procedure: _List[str] = Field(description="Step-by-step process")
        results:   str        = Field(description="Observed data and conclusions")

    _PYDANTIC_OK = True
except ImportError:
    _PYDANTIC_OK = False


def _sage_prompt(mode: str, question: str, rag_context: str = "") -> str:
    ctx = f"\n\nRELEVANT CONTEXT FROM BOOKS:\n{rag_context}" if rag_context else ""
    if mode == "learn":
        return (
            f"{SAGE_SYSTEM}{ctx}\n\n"
            f"Explain this concept in depth for a mechatronics engineer:\n{question}\n\n"
            "Respond ONLY with valid JSON matching this schema:\n"
            '{"concept":"...","explanation":"...","math":"...","takeaways":["..."]}'
        )
    elif mode == "code":
        return (
            f"{SAGE_SYSTEM}{ctx}\n\n"
            f"Write optimised code for:\n{question}\n\n"
            "Respond ONLY with valid JSON matching this schema:\n"
            '{"language":"...","snippet":"...","explanation":"...","dependencies":["..."]}'
        )
    elif mode == "lab":
        return (
            f"{SAGE_SYSTEM}{ctx}\n\n"
            f"Draft a professional lab report for:\n{question}\n\n"
            "Respond ONLY with valid JSON matching this schema:\n"
            '{"title":"...","objective":"...","equipment":["..."],"procedure":["..."],"results":"..."}'
        )
    return question


def _parse_sage_json(raw: str) -> dict:
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    s = clean.find("{"); e = clean.rfind("}") + 1
    if s == -1 or e == 0:
        return {"error": "Model did not return valid JSON", "raw": raw}
    try:
        return json.loads(clean[s:e])
    except json.JSONDecodeError as err:
        return {"error": str(err), "raw": raw}


def structured_response(question: str, mode: str, rag_context: str = ""):
    """Yield streaming chunks then a __STRUCTURED__ JSON signal."""
    prompt  = _sage_prompt(mode, question, rag_context)
    full_raw = ""
    for chunk in ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        stream=True
    ):
        piece     = chunk["message"]["content"]
        full_raw += piece
        yield piece
    parsed = _parse_sage_json(full_raw)
    yield f"__STRUCTURED__{json.dumps(parsed, ensure_ascii=False)}"


# ═══════════════════════════════════════════════════════════════════════════════
# PREPROCESSOR
# ═══════════════════════════════════════════════════════════════════════════════
async def preprocess_user_input(user_input: str, image_path: str = None) -> tuple:
    classification = classify(user_input)
    print(
        f"[Classifier] intent={classification['intent']}, "
        f"user_vibe={classification.get('user_vibe','neutral')}, "
        f"conf={classification.get('confidence',0):.2f}"
    )

    if classification["intent"] in GAME_RESPONSES and classification.get("confidence", 0) >= 0.5:
        return (GAME_RESPONSES[classification["intent"]], classification)

    # ── Execute tool(s) if detected ───────────────────────────────────────────
    tool_outputs = []
    intent = classification.get("intent", "chat")
    params = classification.get("params", {})

    if intent == "run_all_tools":
        from marin_fier import execute_tool
        batch = [
            ("run_command", {"command": "ls -la"}),
            ("run_command", {"command": "df -h"}),
            ("run_command", {"command": "git status"}),
            ("run_command", {"command": "python3 --version"}),
            ("run_command", {"command": "ollama list"}),
        ]
        for t_name, t_params in batch:
            try:
                out = execute_tool(t_name, t_params)
                if out: tool_outputs.append(f"[{t_params.get('command', t_name)}]\n{out}")
            except Exception as e:
                tool_outputs.append(f"[{t_name}] failed: {e}")

    elif intent not in ("chat", "normal", "learn", "code", "lab") and intent not in GAME_RESPONSES:
        try:
            from marin_fier import execute_tool
            out = execute_tool(intent, params)
            if out: tool_outputs.append(f"[TOOL: {intent}]\n{out}")
        except Exception as e:
            print(f"[Tool] execute failed: {e}")

    yt_regex   = r"(https?://)?(www.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[^\s]+"
    is_youtube = bool(re.search(yt_regex, user_input, re.IGNORECASE))
    is_image   = bool(image_path)

    rag_context = await asyncio.to_thread(get_rag_context, user_input)

    media_blocks = []
    if is_youtube or is_image:
        tasks = []
        if is_youtube: tasks.append(analyze_youtube(user_input))
        if is_image:   tasks.append(analyze_image(image_path))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            media_blocks.append(
                "[Media analysis failed]" if isinstance(res, Exception) else res
            )

    parts = []
    if rag_context:   parts.append(rag_context)
    if media_blocks:  parts.append("CONTEXT FROM MEDIA:\n" + "\n".join(media_blocks))
    if tool_outputs:  parts.append("TOOL EXECUTION RESULTS:\n" + "\n\n".join(tool_outputs))
    parts.append(f"USER'S MESSAGE: {user_input}")

    enriched_prompt = "\n\n".join(parts)
    classification["_rag_context"] = rag_context
    return (enriched_prompt, classification)


# ── Command extraction from Marin's text output ──────────────────────────────
_TEXT_CMD_PAT = re.compile(
    r'^\s*(?:[-*>]+\s*)?`?((?:sudo\s+)?'
    r'python3?\s+.*|'
    r'mkdir\s+.*|touch\s+.*|cp\s+.*|mv\s+.*|chmod\s+.*|chown\s+.*|'
    r'echo\s+.*|cat\s+.*|'
    r'ls\s*.*|git\s+\S+.*|'
    r'pip3?\s+\S+.*|'
    r'curl\s+.*|wget\s+.*|'
    r'bash\s+\S+|sh\s+\S+|'
    r'make\s*.*|gcc\s+.*|'
    r'rm\s+[^/]+'               # rm anything EXCEPT rm -rf /
    r')`?\s*$',
    re.MULTILINE | re.IGNORECASE
)


def _strip_md_trail(cmd: str) -> str:
    """Remove trailing markdown decoration: backticks, parenthetical text, non-ASCII."""
    # Remove trailing backtick-wrapped text and *(markdown)* patterns
    cmd = re.sub(r'\s*`[^`]*`\s*$', '', cmd)
    cmd = re.sub(r'\s*\*\([^)]*\)\*\s*$', '', cmd)
    # Remove trailing non-ASCII chars and lone backticks
    cmd = re.sub(r'[^\x20-\x7E]+$', '', cmd)
    cmd = re.sub(r'`+$', '', cmd)
    return cmd.strip()


def _convert_heredocs(body: str) -> str:
    """
    Detect `cat <<EOF > path` heredocs and convert them to Python file-write
    commands so they actually work when piped through shell stdin.

    Example input in body:
        cat <<EOF > unique/limoni.py
        import os
        print("hello")
        EOF

    Converted to:
        python3 -c "import json,sys;open(sys.argv[1],'w').write(json.loads(sys.argv[2]))" unique/limoni.py "import os\nprint(\"hello\")"
    """
    import textwrap

    def _replace_heredoc(m):
        target_file = m.group(1).strip()
        heredoc_body = m.group(2)
        # Strip common leading indentation
        content = textwrap.dedent(heredoc_body)
        # JSON-encode for safe passing through shell
        encoded = json.dumps(content)
        return (
            f'python3 -c "import json,sys;open(sys.argv[1],\'w\').write(json.loads(sys.argv[2]))" '
            f'{target_file} {encoded}'
        )

    # Match: cat <<EOF > path  ...  EOF  (allow indented EOF)
    pattern = re.compile(
        r'cat\s+<<\s*EOF\s*>\s*(\S+)\s*\n(.*?)^\s*EOF\s*$',
        re.DOTALL | re.MULTILINE | re.IGNORECASE
    )
    return pattern.sub(_replace_heredoc, body)


def _exec_text_commands(text: str):
    """
    Scan Marin's generated text for shell commands and execute them.
    Handles heredocs (cat <<EOF), strips trailing markdown, validates
    against marin_fier.is_cmd_allowed() allowlist.
    Graph/stock/crypto commands go through command_queue.py with delays.
    Simple commands (mkdir, chmod, echo, etc.) run directly.
    """
    import datetime
    import tempfile

    # Strip ``` code block fences but KEEP inner content (heredocs live inside them)
    body = re.sub(r'```(?:\w*\n)?([\s\S]*?)```', r'\1', text)

    # Strip non-ASCII decorative chars (emojis, arrows, etc.) from command lines
    body = re.sub(r'[^\x20-\x7E\n]', '', body)

    # Strip inline backtick code spans (preserve content, remove wrapping)
    body = re.sub(r'`([^`\n]+)`', r'\1', body)

    # Convert heredocs to Python file-write commands
    body = _convert_heredocs(body)

    try:
        from marin_fier import is_cmd_allowed, _cmd_log
    except ImportError:
        def is_cmd_allowed(cmd):
            return True, "ok"
        _cmd_log = None

    def _delay_for(cmd: str) -> int:
        lower = cmd.lower()
        if "mathplot" in lower or "maths/" in lower:
            return 40 if "butterfly" in lower else 4
        if "stock" in lower:
            return 20
        if "crypto" in lower:
            return 10
        return 0   # 0 = run directly, don't queue

    # ── Collect raw command strings, strip trailing markdown ──────────────
    raw_cmds = []
    for m in _TEXT_CMD_PAT.finditer(body):
        cmd = _strip_md_trail(m.group(1))
        if cmd:
            raw_cmds.append(cmd)

    if not raw_cmds:
        return

    # ── Build command list with delays, validate against allowlist ────────
    cmds = []
    for cmd in raw_cmds:
        first = cmd.split()[0].lstrip('./')
        allowed, reason = is_cmd_allowed(cmd)
        if not allowed:
            print(f"[Marin] Blocked command: {cmd} — {reason}")
            continue

        delay = _delay_for(cmd)
        name = cmd[:50]
        cmds.append({"cmd": cmd, "delay": delay, "name": name})

    if not cmds:
        return

    ts = datetime.datetime.now().strftime("%H:%M:%S")

    # ── Split: queued (graph/stock/crypto) vs direct (mkdir, chmod, etc.) ─
    queued = [c for c in cmds if c["delay"] > 0]
    direct = [c for c in cmds if c["delay"] == 0]

    # ── Log all commands to terminal panel ────────────────────────────────
    if _cmd_log is not None:
        for c in cmds:
            _cmd_log.append({
                "cmd": c["cmd"],
                "allowed": True,
                "output": f"⏳ queued ({c['delay']}s)" if c["delay"] > 0 else "⏳ running...",
                "ts": ts,
            })
            if len(_cmd_log) > 100:
                _cmd_log.pop(0)

    # ── Run direct commands immediately in a background thread ────────────
    if direct:
        def _run_direct():
            for c in direct:
                try:
                    r = subprocess.run(
                        c["cmd"], shell=True,
                        capture_output=True, text=True, timeout=30,
                        cwd=BASE_DIR,
                        env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
                    )
                    out = (r.stdout or r.stderr or "(done)").strip()[:500]
                    print(f"[Marin] Ran: {c['cmd'][:80]} → {out[:100]}")
                except Exception as e:
                    out = f"Error: {e}"
                    print(f"[Marin] Command failed: {c['cmd'][:80]} — {e}")

                if _cmd_log is not None:
                    for entry in reversed(_cmd_log):
                        if entry["cmd"] == c["cmd"] and "running" in entry.get("output", ""):
                            entry["output"] = out[:200]
                            break

        threading.Thread(target=_run_direct, daemon=True).start()

    # ── Queue graph/stock/crypto commands via command_queue.py ────────────
    if queued:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        try:
            json.dump(queued, tmp)
            tmp_path = tmp.name
        finally:
            tmp.close()

        def _run_queued(cmds, tmp_path):
            try:
                r = subprocess.run(
                    [sys.executable,
                     os.path.join(BASE_DIR, "tools/command_queue.py"),
                     "--json", tmp_path],
                    capture_output=True, text=True, timeout=300,
                    cwd=BASE_DIR,
                    env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
                )
                out = (r.stdout or r.stderr or "(done)").strip()[:500]
                if _cmd_log is not None:
                    for c in cmds:
                        for entry in reversed(_cmd_log):
                            if entry["cmd"] == c["cmd"] and "queued" in entry.get("output", ""):
                                entry["output"] = out[:200]
                                break
                    ts2 = datetime.datetime.now().strftime("%H:%M:%S")
                    _cmd_log.append({
                        "cmd": f"[batch] {len(cmds)} queued cmds done",
                        "allowed": True, "output": out[:300], "ts": ts2,
                    })
                    while len(_cmd_log) > 100:
                        _cmd_log.pop(0)
            except Exception as e:
                if _cmd_log is not None:
                    ts2 = datetime.datetime.now().strftime("%H:%M:%S")
                    _cmd_log.append({
                        "cmd": "[batch] ERROR",
                        "allowed": False, "output": str(e)[:300], "ts": ts2,
                    })
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        threading.Thread(target=_run_queued, args=(queued, tmp_path), daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════════════
# LLM GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════
def response(
    prompt: str,
    user_vibe: str = "neutral",
    use_canned: bool = False,
    canned_response: str = None,
    game_context: str = None,
    intent: str = "normal",
    rag_context: str = "",
):
    if use_canned and canned_response:
        yield canned_response
        yield f"__VIBE__{user_vibe}"
        return

    bare_question = prompt
    if "USER'S MESSAGE:" in prompt:
        bare_question = prompt.split("USER'S MESSAGE:")[-1].strip()

    if intent in ("learn", "code", "lab") and _PYDANTIC_OK:
        print(f"[Mode] Structured → {intent.upper()}")
        yield from structured_response(bare_question, intent, rag_context)
        yield "__VIBE__neutral"
        return

    history   = load_history(limit=30)
    character = get_character_prompt(user_vibe)
    messages  = [{"role": "system", "content": character}]
    messages.extend(history)

    if game_context:
        messages.append({
            "role":    "system",
            "content": f"ACTIVE TIC TAC TOE GAME STATE:\n{game_context}\n"
                       "(Comment on the game, trash talk, or react.)",
        })

    messages.append({"role": "user", "content": prompt})

    full_reply = ""
    options = {}
    if MAX_TOKENS > 0:
        options["num_predict"] = MAX_TOKENS
    for chunk in ollama.chat(model="marin", messages=messages, stream=True, options=options):
        piece       = chunk["message"]["content"]
        full_reply += piece
        yield piece

    # Auto-execute any python3 commands Marin wrote as text
    _exec_text_commands(full_reply)

    save_to_history(bare_question, full_reply)
    marin_vibe = analyze_marin_vibe(full_reply)
    save_vibe(user_vibe, marin_vibe)
    yield f"__VIBE__{marin_vibe}"


def stop_audio():
    """Kill any running piper-tts or aplay audio process (interrupt speech)."""
    import signal
    killed = False
    for proc in ["piper-tts", "aplay"]:
        try:
            r = subprocess.run(
                ["pkill", "-f", proc],
                capture_output=True, text=True, timeout=3
            )
            if r.returncode == 0:
                killed = True
        except Exception:
            pass
    return killed


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ASYNC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
async def main(prompt: str, image_path: str = None, game_context: str = None):
    sentence_buffer = ""
    print("\n[Marin] thinking...")

    enriched_prompt, classification = await preprocess_user_input(
        prompt, image_path=image_path
    )
    is_game_response = (
        classification["intent"] in GAME_RESPONSES
        and classification.get("confidence", 0) >= 0.5
    )

    global _audio_process
    _audio_process = None
    audio_proc = None
    try:
        if VOICE_ENABLED and not is_game_response and os.path.exists(VOICE_PATH):
            stop_audio()
            cmd = (
                f"piper-tts --model {VOICE_PATH} --output_raw "
                "| aplay -r 22050 -f S16_LE -t raw"
            )
            audio_proc = await asyncio.create_subprocess_shell(
                cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _audio_process = audio_proc
    except Exception as e:
        print(f"[Audio] Skipping: {e}")

    split_marks = [".", "!", "?", "\n", ",", ";", ":"]
    gen = response(
        enriched_prompt,
        user_vibe=classification.get("user_vibe", "neutral"),
        use_canned=is_game_response,
        canned_response=GAME_RESPONSES.get(classification["intent"]),
        game_context=game_context,
        intent=classification.get("intent", "normal"),
        rag_context=classification.get("_rag_context", ""),
    )
    loop = asyncio.get_event_loop()

    try:
        while True:
            chunk = await loop.run_in_executor(None, lambda: next(gen, None))
            if chunk is None:
                break

            if "__VIBE__" in chunk:
                print(f"\n[SYSTEM: Vibe -> {chunk.replace('__VIBE__','').upper()}]\n")
                yield chunk
                continue

            if "__STRUCTURED__" in chunk:
                mode_map = {"learn": "📘 TEACHER", "code": "💻 CODER", "lab": "🔬 LAB REPORT"}
                intent_label = mode_map.get(classification.get("intent", ""), "STRUCTURED")
                print(f"\n[Mode] {intent_label} output ready")
                yield chunk
                continue

            print(chunk, end="", flush=True)
            yield chunk
            sentence_buffer += chunk

            if audio_proc and any(m in chunk for m in split_marks):
                text = clean_for_tts(sentence_buffer)
                if len(text) > 3:
                    audio_proc.stdin.write((text + " ").encode("utf-8"))
                    await audio_proc.stdin.drain()
                sentence_buffer = ""

        if audio_proc and sentence_buffer.strip():
            text = clean_for_tts(sentence_buffer)
            if len(text) > 3:
                audio_proc.stdin.write(text.encode("utf-8"))
                await audio_proc.stdin.drain()

    finally:
        if audio_proc and audio_proc.stdin:
            audio_proc.stdin.close()
            await audio_proc.wait()
        _audio_process = None


if __name__ == "__main__":
    a = input("What's so urgent?\n>> ")
    asyncio.run(main(a))