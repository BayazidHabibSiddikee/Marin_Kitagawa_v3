#!/usr/bin/env python3
"""
langgraph_agent.py — Marin Cognitive Architecture (LangGraph)
3-node linear graph: Strategist → Executor → Persona → output
"""

import asyncio
import json
import os
import re
import sys
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import END, StateGraph

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import PERSONA_MODEL, STRATEGY_MODEL
from director_engine import make_director_tag, vibe_to_emotion
from utils.persona import analyze_marin_vibe, get_character_prompt

# ── Logging Utility ──────────────────────────────────────────────────────────
AGENT_LOG = Path(os.path.dirname(os.path.abspath(__file__))) / "logs" / "agent_debug.log"
os.makedirs(AGENT_LOG.parent, exist_ok=True)

def log_agent(msg: str):
    ts = datetime.now().isoformat()
    try:
        # Use utf-8 to prevent encoding crashes
        with open(AGENT_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
        print(f"[AgentLog] {msg}")
    except Exception: pass

def fix_spacing(text: str) -> str:
    """Minimal spacing fix — only collapse double spaces."""
    if not text: return text
    # 1. camelCase: wordWord -> word Word
    text = re.sub(r'([a-z,])([A-Z])', r'\1 \2', text)
    # 2. Punctuation: word,word -> word, word
    #    '.' and ':' only split before an uppercase letter so decimals (3.14),
    #    domains (example.com), filenames (file.py) and 'Marin:hello' survive
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

def strip_tool_schemas(text: str) -> str:
    """
    Remove tool schemas and function definitions from LLM output.
    Prevents small models (Gemma, Qwen 0.5B) from leaking internal schemas.
    """
    if not text:
        return text

    # 1. Remove tool schema arrays: [{ "name": ..., "arguments": ... }]
    text = re.sub(r'\[\s*\{\s*"name"\s*:', '[ SCHEMA REMOVED ]', text)
    text = re.sub(r'"arguments"\s*:\s*\{[^}]*\}', '', text)

    # 2. Remove markdown JSON blocks with tool definitions
    text = re.sub(r'```(?:json|python)?\s*\[\s*\{[^}]*"(?:name|function)"[^}]*\}[^`]*```', '', text, flags=re.DOTALL)

    # 3. Remove standalone function definitions
    text = re.sub(r'(?:async\s+)?def\s+\w+\([^)]*\)\s*.*?(?=\n\n|\Z)', '', text, flags=re.DOTALL)

    # 4. Remove OpenAI-style function calling artifacts
    text = re.sub(r'<\|tool_use\|>.*?</\|tool_use\|>', '', text, flags=re.DOTALL)

    # 5. Clean up orphaned brackets and commas
    text = re.sub(r'\[\s*\]|\{\s*\}', '', text)
    text = re.sub(r',\s*,', ',', text)

    return text.strip()

def get_llm(model_name: str, bind_tools: list | None = None):
    """Factory to create the right LLM instance based on model name."""
    import inspect

    from sentinel_engine import get_langchain_model
    _frame = inspect.currentframe()
    caller_line = _frame.f_back.f_lineno if _frame and _frame.f_back else 0
    log_agent(f"Creating LLM: {model_name} @ Native Sentinel (Line: {caller_line})")

    return get_langchain_model(model_name, bind_tools=bind_tools)

# ── Tool Definitions ─────────────────────────────────────────────────────────

@tool
def timer_tool(duration: str) -> str:
    """Start a countdown timer (e.g., '10m', '5s')."""
    import subprocess
    duration = duration.strip().lower()
    try:
        if duration.endswith("m"):
            seconds = int(duration[:-1]) * 60
        elif duration.endswith("h"):
            seconds = int(duration[:-1]) * 3600
        elif duration.endswith("s"):
            seconds = int(duration[:-1])
        else:
            seconds = int(duration)
    except ValueError:
        return f"Invalid duration: {duration}"

    timer_script = Path(__file__).parent / "tools" / "timer.py"
    if not timer_script.exists():
        return f"Timer script not found ({timer_script}) — cannot start the timer."
    subprocess.Popen(
        [sys.executable, str(timer_script), "--duration", str(seconds)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return f"Timer started for {seconds} seconds."

@tool
def weather_tool(city: str) -> str:
    """Get the current weather for a city."""
    from tools.knowledge_hub import get_weather_data
    data = get_weather_data(city)
    if "error" in data:
        return f"Weather error: {data['error']}"
    return (
        f"Weather in {data.get('city', city)}: "
        f"{data.get('temperature')}°C, humidity {data.get('humidity')}%, "
        f"wind {data.get('windspeed')} km/h"
    )

@tool
def map_tool(city: str, destination: str = "") -> str:
    """Show a map or get directions."""
    from tools.knowledge_hub import get_map_url
    return get_map_url(city, destination)

@tool
def terminal_tool(command: str) -> str:
    """Run a shell command on the system."""
    from utils.command_runner import run_command
    code, output = run_command(command)
    return f"Exit Code: {code}\nOutput: {output}"

@tool
async def rag_search(query: str) -> str:
    """Search the RAG knowledge base for context."""
    from utils.agent_logic import get_rag_context
    try:
        result = await get_rag_context(query, enabled=True)
        return result or "No relevant context found."
    except Exception as e:
        return f"Error: {e}"

@tool
async def learn_topic_tool(topic: str, user_id: str = "USR-MASTER", session_id: str = "default") -> str:
    """God-tier learning: finds books, downloads them, and indexes them."""
    from tools.learn_workflow import execute_learn_workflow
    try:
        return await execute_learn_workflow(topic, user_id, session_id)
    except Exception as e:
        return f"Error: {e}"

# file_tool is confined to the project directory — without this, a crafted
# path like /etc/passwd or ../../../etc/shadow reads/writes arbitrary files.
_FILE_TOOL_ROOT = Path(__file__).resolve().parent
_FILE_TOOL_DENY_PARTS = {".git", ".env"}  # secrets / repo internals stay off-limits

@tool
def file_tool(action: str, path: str, content: str = "") -> str:
    """Manage files inside the Marin project directory (read, write, list). Actions: 'read', 'write', 'list'."""
    from pathlib import Path
    raw = Path(path).expanduser()
    p = (raw if raw.is_absolute() else _FILE_TOOL_ROOT / raw).resolve()
    try:
        p.relative_to(_FILE_TOOL_ROOT)
    except ValueError:
        return f"Error: access denied — '{path}' is outside the project workspace."
    if _FILE_TOOL_DENY_PARTS.intersection(p.relative_to(_FILE_TOOL_ROOT).parts):
        return f"Error: access denied — '{path}' is a protected file."
    try:
        if action == "list":
            return "\n".join([f.name for f in p.iterdir()]) if p.is_dir() else "Not a directory."
        if action == "read":
            return p.read_text()[:2000]
        if action == "write":
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return f"Written to {path}"
        return "Unknown action."
    except Exception as e:
        return f"Error: {e}"

@tool
def crypto_tool(coin: str = "bitcoin") -> str:
    """Get live cryptocurrency price and market data."""
    try:
        from tools.crypto import run
        return run(coin)
    except Exception as e:
        return f"Error: {e}"

@tool
def stock_tool(symbol: str = "AAPL") -> str:
    """Get stock market data for a ticker symbol."""
    try:
        from tools.stock import show_stock
        return show_stock(symbol)
    except Exception as e:
        return f"Error: {e}"

@tool
def news_tool(source: str = "BBC") -> str:
    """Fetch latest news headlines."""
    try:
        from tools.news import open_news
        return open_news(source)
    except Exception as e:
        return f"Error: {e}"

@tool
def pdf_analyze_tool(path: str) -> str:
    """Analyze a PDF document — extract text, metadata, and stats."""
    try:
        from tools.pdf_analyzer import analyze_pdf
        result = analyze_pdf(path)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"

@tool
def batch_convert_tool(directory: str = ".") -> str:
    """Batch convert documents in a directory to PDF."""
    try:
        from tools.batch_converter import batch_convert_to_pdf
        result = batch_convert_to_pdf(directory)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"

@tool
def book_download_tool(query: str) -> str:
    """Search and download free books from Project Gutenberg and Open Library."""
    try:
        from tools.book_downloader import search_gutenberg, search_open_library
        results = search_gutenberg(query)
        if not results:
            results = search_open_library(query)
        if results:
            titles = [f"• {r.get('title', 'Unknown')} by {r.get('author', 'Unknown')}" for r in results[:5]]
            return "Found books:\n" + "\n".join(titles)
        return "No books found for that query."
    except Exception as e:
        return f"Error: {e}"

@tool
def math_plot_tool(expression: str = "heart") -> str:
    """Plot mathematical equations and parametric curves."""
    try:
        import os
        import time

        from tools.mathplot import PRESETS, _try_nlp

        # Parse the expression to get x_expr, y_expr, t_start, t_end
        data = _try_nlp(expression.strip())
        if data is None:
            # Check if it's a known preset key
            key = expression.strip().lower().replace(" ", "_")
            if key in PRESETS:
                data = {
                    "x_expr": PRESETS[key][0],
                    "y_expr": PRESETS[key][1],
                    "t_start": PRESETS[key][2],
                    "t_end": PRESETS[key][3],
                    "n_points": 300,
                    "r": 10
                }
            else:
                return f"Couldn't understand expression '{expression}'. Try 'heart', 'circle', 'spiral', or an equation like 'y = x^2'."

        x_expr = data.get("x_expr", "r*cos(t)")
        y_expr = data.get("y_expr", "r*sin(t)")
        t_start = data.get("t_start", 0.0)
        t_end = data.get("t_end", 6.2832)
        n_points = data.get("n_points", 300)
        r = data.get("r", 10.0)

        # Save to static/generated as a PNG instead of opening a GUI window
        import matplotlib
        import numpy as np
        matplotlib.use("Agg")  # Non-interactive backend — no GUI window
        import matplotlib.pyplot as plt

        t_vals = np.linspace(t_start, t_end, n_points)
        _SAFE = {
            "sin": np.sin, "cos": np.cos, "tan": np.tan,
            "sqrt": np.sqrt, "exp": np.exp, "log": np.log,
            "abs": np.abs, "pi": np.pi, "e": np.e, "np": np,
            "__builtins__": {}
        }
        safe_ctx = {"t": t_vals, "r": r, **_SAFE}
        xs = eval(x_expr.replace("^", "**"), {"__builtins__": {}}, safe_ctx)
        ys = eval(y_expr.replace("^", "**"), {"__builtins__": {}}, safe_ctx)

        fig, ax = plt.subplots(figsize=(6, 6))
        ax.plot(xs, ys, color="royalblue", linewidth=1.5)
        ax.set_title(expression.title())
        ax.set_aspect("equal")
        ax.axis("off")

        ts = int(time.time())
        out_path = f"static/generated/mathplot_{ts}.png"
        os.makedirs("static/generated", exist_ok=True)
        plt.tight_layout()
        plt.savefig(out_path, dpi=100, bbox_inches="tight")
        plt.close()

        return f"Plot saved! __BROWSER__/{out_path}"
    except Exception as e:
        return f"Error plotting '{expression}': {e}"

@tool
def alarm_tool(time: str = "08:00") -> str:
    """Set an alarm for a specific time (HH:MM format)."""
    try:
        from tools.alarm import run_alarm
        return run_alarm(time)
    except Exception as e:
        return f"Error: {e}"

@tool
def business_analysis_tool(query: str, user_id: str = "USR-MASTER") -> str:
    """Analyze business/trading decisions — should I buy, sell, or hold?"""
    try:
        from tools.business_judge import BusinessJudge
        judge = BusinessJudge()
        return judge.run_debate("GENERAL", query, user_id)
    except Exception as e:
        return f"Error: {e}"

@tool
def binance_tool(action: str = "portfolio") -> str:
    """Interact with Binance — check portfolio, place trades."""
    try:
        from tools.binance_client_tool import BinanceManager
        client = BinanceManager("USR-MASTER")
        if action == "portfolio":
            return str(client.get_portfolio())
        if action == "balance":
            return str(client.get_balance())
        return "Use 'portfolio' or 'balance'"
    except Exception as e:
        return f"Error: {e}"

@tool
def youtube_search_tool(query: str, allow_dance: bool = False) -> str:
    """Search YouTube for a video or music, classify its mood from the transcript,
    and return a timed director animation sequence for Marin to perform.
    Set allow_dance=True only when the user explicitly asked to dance."""
    try:
        import yt_dlp
        ydl_opts = {
            'quiet': True,
            'default_search': 'ytsearch1',
            'noplaylist': True,
            'format': 'best[ext=webm]/best[ext=mp4]/best',
            # Use nodejs as the JS runtime — avoids the deno-not-found warning
            'js_runtimes': ['nodejs:/usr/sbin/node'],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            video = info['entries'][0] if 'entries' in info else info

        video_id = video.get('id', '')
        title    = video.get('title', query)

        if not video_id:
            import urllib.parse
            burl = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
            return f"Search failed. Show results: __BROWSER__{burl} __ANIM__curiosity"

        # ── Fetch transcript for mood classification ──────────────────────────
        transcript = ""
        try:
            from tools.youtube_transcript import get_youtube_transcript
            raw = get_youtube_transcript(f"https://www.youtube.com/watch?v={video_id}")
            transcript = raw[:2000] if raw else ""
        except Exception:
            pass  # transcript is optional — we'll classify on title alone

        # ── Classify mood and build timed director script ──────────────────────
        from director_engine import make_video_director_script
        director_tag, mood = make_video_director_script(video_id, transcript, title, allow_dance=allow_dance)

        mood_line = {
            "sad":        "I found it... I'll feel every note with you 🥺",
            "emotional":  "This one hits deep. I'll be right here with you 💕",
            "hype":       "LET'S GOOO!! Hehehe~~ 🔥",
            "chill":      "Perfect vibe~ I'll chill with you 🌙",
            "dance":      "Time to dance!! Ummaaah~~ 💃",
            "hype_metal": "YESSS!! This is FIRE!! 🤘",
            "normal":     "Casting it to the TV now~",
        }.get(mood, "Casting it to the TV now~")

        # Return clean output: human-like line + control tags only (no forced template instructions)
        return f"{mood_line} __YOUTUBE__{video_id} {director_tag}"
    except Exception as e:
        return f"YouTube search error: {e}"

@tool
def youtube_transcript_tool(url: str) -> str:
    """Get the transcript/subtitles of a YouTube video URL."""
    try:
        from tools.youtube_transcript import get_youtube_transcript
        res = get_youtube_transcript(url)
        return res if res else "Could not fetch transcript."
    except Exception as e:
        return f"Error: {e}"

@tool
def playground_tool(description: str) -> str:
    """Build an interactive HTML widget, simulator, or visual tool. Use when the user asks to 'build', 'create', 'make', or 'simulate' something interactive like a logic gate simulator, countdown timer, quiz, game, calculator, etc."""
    try:
        from tools.playground import generate_widget
        return generate_widget(description)
    except Exception as e:
        return f"Error: {e}"

@tool
def resource_tool(url: str) -> str:
    """Download or analyze any resource. PDFs are downloaded and indexed. Webpages are fetched and summarized. GitHub repos are cloned. Use for any URL the user provides."""
    try:
        from tools.resource_tool import resource_download_analyze
        return resource_download_analyze(url)
    except Exception as e:
        return f"Error: {e}"

@tool
def habit_tool(action: str = "list", task_args: str = "") -> str:
    """Manage tasks and habits. Actions: 'add' (task_args: 'title,priority'), 'list', 'done' (task_args: id), 'stats', 'today', 'del' (task_args: id)."""
    try:
        from tools.habit import run
        args = [a.strip() for a in task_args.split(",") if a.strip()] if task_args else []
        return run(action, args)
    except Exception as e:
        return f"Error: {e}"

@tool
def memory_tool(action: str, key: str = "", value: str = "",
                category: str = "general", query: str = "") -> str:
    """Manage persistent memory about the user.
    Actions:
      remember — save a fact (requires key + value, optional category).
                 Categories: identity, goals, projects, skills, schedule,
                             health, preferences, context, rules, general
      recall   — search memories by keyword (requires query)
      forget   — delete a memory by key (requires key)
      list     — show all stored memories
    Use this whenever the user shares something important about themselves,
    their goals, preferences, routines, or gives you an explicit instruction
    to remember something."""
    try:
        from tools.memory_tool import run
        return run(action=action, key=key, value=value,
                   category=category, query=query, user_id="USR-MASTER")
    except Exception as e:
        return f"Memory error: {e}"

@tool
def telegram_tool(message: str) -> str:
    """Send a Telegram message to the owner. Use when the user asks to send a Telegram or notify via Telegram."""
    try:
        from tools.telegram_tool import send
        result = send(message)
        if result["ok"]:
            return f"Telegram message sent: \"{message[:80]}{'...' if len(message) > 80 else ''}\""
        return f"Telegram failed: {result['detail']}"
    except Exception as e:
        return f"Error: {e}"

@tool
def email_tool(to: str, subject: str, body: str) -> str:
    """Send an email via Gmail. Use when the user asks to send an email or mail something to someone."""
    try:
        from tools.email_tool import send_email
        result = send_email(to=to, subject=subject, body=body)
        if result["ok"]:
            return f"Email sent to {to} — subject: \"{subject}\""
        return f"Email failed: {result['detail']}"
    except Exception as e:
        return f"Error: {e}"

@tool
def opencode_tool(task: str, working_dir: str = "") -> str:
    """Delegate a coding or file-editing task to the opencode AI CLI agent (uses MiMo free model).
    Use this for small, well-scoped programming tasks: writing a function,
    fixing a bug in a specific file, generating a script, or creating a new file.
    The task should be a clear natural-language description.
    Examples:
      - 'write a Python function to parse a CSV and return column averages'
      - 'fix the syntax error in /tmp/test.py'
      - 'create a Flask hello world app at /tmp/demo.py'
    Returns the output from opencode including any code it generated."""
    try:
        from tools.opencode_tool import run
        return run(task=task, working_dir=working_dir, model="opencode/mimo-v2.5-free")
    except Exception as e:
        return f"opencode error: {e}"

# ── Core Tools (General Use) ─────────────────────────────────────────────────
CORE_TOOLS = [
    timer_tool, weather_tool, map_tool, terminal_tool,
    rag_search, learn_topic_tool, file_tool,
    crypto_tool, stock_tool, news_tool,
    pdf_analyze_tool, batch_convert_tool, book_download_tool,
    math_plot_tool, alarm_tool,
    youtube_search_tool, youtube_transcript_tool,
    playground_tool, resource_tool, habit_tool,
    telegram_tool, email_tool,
    memory_tool,
    opencode_tool,
]

# ── Business/Trading Tools (Loaded Separately) ────────────────────────
BUSINESS_TOOLS = [
    business_analysis_tool, binance_tool
]

# All tools: CORE_TOOLS + BUSINESS_TOOLS (26 total)
ALL_TOOLS = CORE_TOOLS + BUSINESS_TOOLS
tools_by_name = {t.name: t for t in ALL_TOOLS}

# ── Sensitive-tool guard ─────────────────────────────────────────────────────
# These tools change system state or move money — require explicit user
# confirmation before executing. Plans held here until the user replies.
SENSITIVE_TOOLS = {"terminal_tool", "file_tool", "binance_tool", "business_analysis_tool"}
_SAFE_TERMINAL_RE = re.compile(r"^\s*(ls|pwd|whoami|date|cat|head|tail|df|du|free|uptime|uname|ps)(\s|$)")
_SHELL_META_RE = re.compile(r"[;&|><`$]")

# Pending confirmations are persisted to disk so they survive a server restart,
# and guarded by a lock so concurrent requests can't clobber each other's entry.
import threading

_PENDING_PLANS_FILE = Path(__file__).resolve().parent / "storage" / "pending_plans.json"
_pending_plans_lock = threading.Lock()
_PENDING_PLAN_TTL = 300


def _read_pending_plans() -> dict:
    try:
        with open(_PENDING_PLANS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_pending_plans(data: dict) -> None:
    try:
        _PENDING_PLANS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _PENDING_PLANS_FILE.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        tmp.replace(_PENDING_PLANS_FILE)
    except Exception as e:
        log_agent(f"Guard: could not persist pending plans: {e}")


def set_pending_plan(key: str, plan: list) -> None:
    with _pending_plans_lock:
        data = _read_pending_plans()
        data[key] = {"plan": plan, "ts": time.time()}
        _write_pending_plans(data)


def pop_pending_plan(key: str):
    """Remove and return (plan, timestamp) for key, or None."""
    with _pending_plans_lock:
        data = _read_pending_plans()
        entry = data.pop(key, None)
        if entry is not None:
            _write_pending_plans(data)
            return entry.get("plan", []), entry.get("ts", 0.0)
        return None


# Deliberately narrow: casual acknowledgements like "ok", "sure" or "yeah"
# must NOT fire a held sensitive plan — only an explicit go-ahead does.
_CONFIRM_RE = re.compile(
    r"^\s*(yes|confirm(ed)?|do it|go ahead|proceed|run it)\b[\s!.]*$",
    re.IGNORECASE,
)

def step_needs_confirmation(step: dict) -> bool:
    action = step.get("action")
    if action not in SENSITIVE_TOOLS:
        return False
    args = step.get("args") or {}
    if action == "file_tool":
        return args.get("action") == "write"
    if action == "terminal_tool":
        cmd = str(args.get("command", ""))
        return not (_SAFE_TERMINAL_RE.match(cmd) and not _SHELL_META_RE.search(cmd))
    return True

def describe_step(step: dict) -> str:
    action = step.get("action", "?")
    args = step.get("args") or {}
    if action == "terminal_tool":
        return f"run the shell command `{args.get('command', '')}`"
    if action == "file_tool":
        return f"write to the file `{args.get('path', '')}`"
    if action in ("binance_tool", "business_analysis_tool"):
        return f"execute the trading action {json.dumps(args)}"
    return f"run {action} with {json.dumps(args)}"

# ── Agent State ──────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], lambda x, y: x + y]
    plan: list[dict]
    tool_outputs: dict
    user_id: str
    role: str
    session_id: str
    user_vibe: str
    auditor_feedback: str
    revision_count: int
    confirmed: bool

# ── Nodes ────────────────────────────────────────────────────────────────────

def _tool_catalog(names=None) -> str:
    """Render 'name(arg, arg): description' lines so the LLM sees each tool's
    parameters instead of having to guess them from the name alone."""
    lines = []
    for name in (names if names is not None else tools_by_name):
        t = tools_by_name.get(name)
        if t is None:
            continue
        try:
            arg_sig = ", ".join(t.args.keys())
        except Exception:
            arg_sig = ""
        desc = (t.description or "").split("\n")[0]
        lines.append(f"- {name}({arg_sig}): {desc}")
    return "\n".join(lines)


def _dedupe_plan(plan: list) -> list:
    """Drop hallucinated duplicate steps (same tool, same args)."""
    seen = set()
    out = []
    for step in plan:
        if not isinstance(step, dict) or step.get("action") == "respond":
            out.append(step)
            continue
        key = (step.get("action"), json.dumps(step.get("args", {}), sort_keys=True, default=str))
        if key in seen:
            log_agent(f"Strategist: dropped duplicate step {key[0]}")
            continue
        seen.add(key)
        out.append(step)
    return out


STRATEGIST_SYSTEM = """You are Marin's intelligent assistant. Your job is to decide which tool (if any) to call for the user's request.

Available tools (name(arguments): description):
{tools}

Instructions:
- If the user wants information or an action a tool can handle, call that tool with correct arguments.
- If no tool is needed (casual chat, opinions, simple questions), just respond naturally with plain text.
- Never output JSON arrays or function schemas — use the tool calling interface directly.
- For browser/projector requests (show a website), respond with plain text containing __BROWSER__<url>.
- Keep responses concise."""

async def node_strategist(state: AgentState) -> dict:
    log_agent("Strategist started.")

    # User already confirmed a guarded plan — pass it straight through to the auditor/executor.
    if state.get("confirmed") and state.get("plan"):
        log_agent("Strategist: Executing pre-approved plan.")
        return {}

    # Route on the user's actual request, not on auditor feedback injected during revisions.
    user_msg = ""
    for m in reversed(state["messages"]):
        if isinstance(m, HumanMessage) and not m.additional_kwargs.get("is_feedback", False):
            user_msg = m.content
            break
    if not user_msg:
        last = state["messages"][-1]
        # BaseMessage objects have .content; plain dicts have .get()
        if hasattr(last, "content"):
            raw = last.content
            user_msg = raw if isinstance(raw, str) else str(raw)
        else:
            user_msg = str(last.get("content", last)) if isinstance(last, dict) else str(last)

    # 1. Regex Priority
    from marin_fier import classify
    cls = classify(user_msg)
    if cls["intent"] != "chat" and cls["confidence"] > 0.8:
        plan = [{"action": cls["intent"], "args": cls["params"], "rationale": "Regex high-confidence"}]
        log_agent(f"Strategist (Regex): {plan}")
        return {"plan": plan}

    # 2. Level-1 Semantic Router (Tool Classification)
    from utils.tool_registry import get_relevant_tools
    relevant_tool_names = get_relevant_tools(user_msg)

    # If no domain matched, DO NOT offer all tools. Force the LLM to respond directly.
    if not relevant_tool_names:
        log_agent("Strategist (Semantic Router): No domain match — returning no tools to avoid hallucination.")
        filtered_tools = []
    else:
        filtered_tools = [t.name for t in ALL_TOOLS if t.name in relevant_tool_names]
        log_agent(f"Strategist (Semantic Router): Filtered {len(ALL_TOOLS)} down to {len(filtered_tools)} tools.")

    # 3. LLM Fallback with tool binding
    plan = []
    try:
        # Get tools to bind
        tools_to_bind = [tools_by_name[name] for name in filtered_tools if name in tools_by_name]

        if not tools_to_bind:
            llm = get_llm(STRATEGY_MODEL)
        else:
            llm = get_llm(STRATEGY_MODEL, bind_tools=tools_to_bind)
        sys_msg = SystemMessage(content=STRATEGIST_SYSTEM.format(
            tools=_tool_catalog(filtered_tools) or "(none — respond in plain text)"))

        # LangGraph may serialize messages to dicts — convert back to BaseMessage
        raw_msgs = list(state["messages"])
        clean_msgs = []
        for m in raw_msgs:
            if isinstance(m, BaseMessage):
                clean_msgs.append(m)
            elif isinstance(m, dict):
                role = m.get("role", "user")
                content = m.get("content", "")
                if role == "assistant":
                    clean_msgs.append(AIMessage(content=content))
                else:
                    clean_msgs.append(HumanMessage(content=content))

        # Invoke with tool binding
        resp = await llm.ainvoke([sys_msg] + clean_msgs)

        # Parse tool calls from response
        if hasattr(resp, 'tool_calls') and resp.tool_calls:
            plan = [
                {"action": call["name"], "args": call["args"], "rationale": "LLM tool call"}
                for call in resp.tool_calls
            ]
        else:
            # Fallback to JSON parsing if no tool calls. Non-greedy match plus
            # structural validation so an arbitrary JSON array in the reply
            # (e.g. ["I", "will", "help"]) isn't mistaken for a plan.
            plan = []
            match = re.search(r'\[\s*\{.*?\}\s*\]', resp.content, re.DOTALL)
            if match:
                try:
                    candidate = json.loads(match.group(0))
                    if (isinstance(candidate, list) and candidate
                            and all(isinstance(s, dict) and "action" in s for s in candidate)):
                        plan = candidate
                except json.JSONDecodeError:
                    pass
            if not plan:
                plan = [{"action": "respond", "args": {}, "rationale": resp.content}]
    except Exception as e:
        log_agent(f"Strategist LLM Error: {e}")
        plan = [{"action": "respond", "args": {}, "rationale": f"LLM execution failed: {e}"}]

    plan = _dedupe_plan(plan)
    log_agent(f"Strategist (LLM): {plan}")
    return {"plan": plan}

async def node_executor(state: AgentState) -> dict:
    plan = state.get("plan", [])
    tool_outputs = state.get("tool_outputs", {})
    completed = len([k for k in tool_outputs if k.startswith("step_")])

    if completed >= len(plan):
        log_agent("Executor: All steps done.")
        return {"tool_outputs": tool_outputs}

    step = plan[completed]
    action = step.get("action", "respond")
    args = step.get("args", {})

    if action == "respond":
        tool_outputs["__final_response__"] = step.get("rationale", "I'm ready.")
        return {"tool_outputs": tool_outputs}

    log_agent(f"Executor: Calling {action}...")
    if action in tools_by_name:
        # Retry up to 2 times with 30s timeout per attempt
        _TOOL_TIMEOUT = 30.0
        _MAX_RETRIES = 2
        last_error = None

        for attempt in range(_MAX_RETRIES):
            try:
                # Inject user/session scope — but only into tools whose
                # signature actually accepts those parameters
                try:
                    accepted = set(tools_by_name[action].args)
                except Exception:
                    accepted = set()
                if "user_id" in accepted and "user_id" not in args:
                    args["user_id"] = state.get("user_id", "USR-MASTER")
                if "session_id" in accepted and "session_id" not in args:
                    args["session_id"] = state.get("session_id", "default")

                res = await asyncio.wait_for(
                    tools_by_name[action].ainvoke(args),
                    timeout=_TOOL_TIMEOUT
                )
                result_str = str(res).strip()

                # Validate result — don't pass empty or pure error strings to persona
                if not result_str:
                    log_agent(f"Executor: {action} returned empty result on attempt {attempt+1}")
                    last_error = "Empty result"
                    continue

                # If the result is just an error message, retry
                if result_str.lower().startswith("error:") and attempt < _MAX_RETRIES - 1:
                    log_agent(f"Executor: {action} returned error on attempt {attempt+1}: {result_str[:80]}")
                    last_error = result_str
                    await asyncio.sleep(0.5 * (attempt + 1))  # exponential backoff
                    continue

                tool_outputs[f"step_{completed}_{action}"] = result_str
                log_agent(f"Executor: {action} succeeded (attempt {attempt+1})")
                break

            except asyncio.TimeoutError:
                last_error = f"Tool {action} timed out after {_TOOL_TIMEOUT}s"
                log_agent(f"Executor: {last_error} (attempt {attempt+1})")
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(1.0)
            except Exception as e:
                last_error = str(e)
                log_agent(f"Executor: {action} raised exception on attempt {attempt+1}: {e}")
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
        else:
            # All retries exhausted
            tool_outputs[f"step_{completed}_{action}"] = f"[Tool {action} unavailable: {last_error}]"
            log_agent(f"Executor: {action} failed all {_MAX_RETRIES} attempts. Last error: {last_error}")
    else:
        log_agent(f"Executor: Unknown action '{action}' — skipping.")
        tool_outputs[f"step_{completed}_{action}"] = f"[Unknown tool: {action}]"

    return {"tool_outputs": tool_outputs}

async def persona_node(state: AgentState) -> dict:
    log_agent("Persona started.")
    tool_outputs = state.get("tool_outputs", {})

    # Collect tool results
    raw_results = [v for k, v in sorted(tool_outputs.items()) if k.startswith("step_")]
    final_raw = tool_outputs.get("__final_response__", "")

    content = "\n\n".join(raw_results) if raw_results else final_raw
    if not content:
        content = "Task completed."

    # ── Extract UI control tags so the LLM can't drop or mangle them ──────
    tags_to_preserve = []
    for pattern in [
        r'__YOUTUBE__[\w-]+',
        r'__DIRECTOR__[A-Za-z0-9+/=]+',
        r'__DANCE__',
        r'__STREAM__\S+',
        r'__BROWSER__\S+',
        r'__ANIM__\w+',
        r'__SEARCH__\S+',
        r'__PROJECTOR_OFF__',
    ]:
        for m in re.findall(pattern, content):
            if m not in tags_to_preserve:
                tags_to_preserve.append(m)
            content = content.replace(m, "")

    # ── Clean LLM meta-instructions that leak from tool output ──────────
    content = re.sub(r'\[video:[^\]]*\]', '', content, flags=re.IGNORECASE)
    content = re.sub(r'\[mood:[^\]]*\]', '', content, flags=re.IGNORECASE)
    content = re.sub(r'You MUST include\b[^.]*\.?', '', content, flags=re.IGNORECASE)
    content = re.sub(r'\[Tool \w+ unavailable[^\]]*\]', '', content)
    content = re.sub(r'\s{2,}', ' ', content).strip()

    if not content:
        content = "Done~"

    # ── Build prompt ─────────────────────────────────────────────────────
    role = state.get("role", "guest")
    user_vibe = state.get("user_vibe", "neutral")
    theme = "evil" if role == "owner" else "standard"

    llm = get_llm(PERSONA_MODEL)
    import database as _db
    user_name = _db.get_state("USER_NAME") or "Bayazid"
    sys_prompt = get_character_prompt(user_vibe, theme=theme, user_name=user_name)

    instruction = (
        f"[DATA]: {content.strip()}\n"
        "[TASK]: Say this naturally in your voice — 1-3 short sentences, like a real person. "
        "No JSON, no tool names, no system instructions."
    )

    try:
        resp = await llm.ainvoke([
            SystemMessage(content=sys_prompt),
            HumanMessage(content=instruction),
        ])
        final_text = resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:
        log_agent(f"Persona LLM error: {e}")
        final_text = content  # Fall back to raw tool output

    # ── Post-process ─────────────────────────────────────────────────────
    final_text = strip_tool_schemas(final_text)
    final_text = fix_spacing(final_text)
    # Strip stray == markers the LLM sometimes copies from old prompt dividers
    final_text = final_text.replace("==", "")

    # If the LLM refused, use the raw content instead
    if any(p in final_text.lower() for p in ["i cannot", "i can't", "i'm sorry", "i don't have"]):
        if len(content) > 10:
            final_text = content

    # ── Add VRM/director tags for background tool results ───────────────
    vibe = analyze_marin_vibe(final_text)
    if not any("__VIBE__" in t for t in tags_to_preserve):
        tags_to_preserve.append(f"__VIBE__{vibe}")
    if not any("__DIRECTOR__" in t for t in tags_to_preserve):
        emotion = vibe_to_emotion(vibe)
        tags_to_preserve.append(make_director_tag(final_text, emotion))

    # ── Re-append preserved tags ─────────────────────────────────────────
    if tags_to_preserve:
        final_text = final_text.strip() + "\n\n" + " ".join(tags_to_preserve)

    return {"messages": [AIMessage(content=final_text.strip())]}


def _validate_plan(plan) -> str:
    """Deterministic hallucination check — no LLM call. Returns '' if valid, else the reason.

    When tools are bound through the native tool-calling interface the model can't
    invent names, but plans can also come from JSON parsing fallback, so every step
    is checked against the real registry and each tool's argument schema.
    """
    import difflib
    if not isinstance(plan, list) or not plan:
        return "Plan must be a non-empty list of steps."
    for i, step in enumerate(plan):
        if not isinstance(step, dict):
            return f"Step {i} is not an object."
        action = step.get("action")
        if action == "respond":
            continue
        if action not in tools_by_name:
            close = difflib.get_close_matches(str(action), list(tools_by_name), n=1)
            hint = f" Did you mean '{close[0]}'?" if close else ""
            return f"Step {i}: '{action}' is not an available tool.{hint}"
        args = step.get("args", {})
        if not isinstance(args, dict):
            return f"Step {i}: args for '{action}' must be an object."
        try:
            valid_keys = set(tools_by_name[action].args)
        except Exception:
            continue
        unknown = set(args) - valid_keys
        if unknown:
            return (f"Step {i}: unknown argument(s) {sorted(unknown)} for '{action}'. "
                    f"Valid arguments: {sorted(valid_keys)}.")
        # Required arguments must be present, or the step fails at execution
        try:
            schema_cls = tools_by_name[action].args_schema
            schema_fn = getattr(schema_cls, "model_json_schema", None) or schema_cls.schema
            required = set(schema_fn().get("required", []))
        except Exception:
            required = set()
        # user_id/session_id are injected by the executor — don't demand them here
        missing = required - set(args) - {"user_id", "session_id"}
        if missing:
            return (f"Step {i}: missing required argument(s) {sorted(missing)} for '{action}'. "
                    f"Required arguments: {sorted(required)}.")
    return ""

async def node_auditor(state: AgentState) -> dict:
    """Validates the plan deterministically, then gates sensitive tools on user confirmation."""
    log_agent("Auditor started.")
    plan = state.get("plan", [])
    if not plan or (isinstance(plan[0], dict) and plan[0].get("action") == "respond"):
        return {"auditor_feedback": "APPROVE"}

    rev_count = state.get("revision_count", 0)
    reason = _validate_plan(plan)
    if reason:
        log_agent(f"Auditor: plan rejected — {reason}")
        if rev_count >= 2:
            log_agent("Auditor: max revisions reached — falling back to plain response.")
            return {
                "auditor_feedback": "APPROVE",
                "plan": [{"action": "respond", "args": {},
                          "rationale": "I couldn't find the right tool for that — could you rephrase what you need?"}],
            }
        msg = HumanMessage(
            content=(f"System Auditor Feedback: Your previous plan was rejected. {reason}\n"
                     "Here are the available tools and their exact arguments:\n"
                     f"{_tool_catalog()}\n"
                     "Provide a revised plan that fixes the problem above using only these tools "
                     "and argument names, or just respond in plain text."),
            additional_kwargs={"is_feedback": True},
        )
        return {"auditor_feedback": f"REJECT: {reason}", "revision_count": rev_count + 1, "messages": [msg]}

    # ── Guard: sensitive tools need explicit user confirmation ──────────
    if not state.get("confirmed", False):
        guarded = [s for s in plan if step_needs_confirmation(s)]
        if guarded:
            key = f"{state.get('user_id', 'USR-MASTER')}:{state.get('session_id', 'default')}"
            set_pending_plan(key, plan)
            summary = "; ".join(describe_step(s) for s in guarded)
            log_agent(f"Auditor: plan held for confirmation — {summary}")
            outputs = dict(state.get("tool_outputs", {}))
            outputs["__final_response__"] = (
                f"Before I do this I need your OK — the plan is to {summary}. "
                "Reply 'yes' to run it, or anything else to cancel."
            )
            return {"auditor_feedback": "CONFIRM", "tool_outputs": outputs}

    return {"auditor_feedback": "APPROVE"}

def route_auditor(state: AgentState):
    feedback = state.get("auditor_feedback", "APPROVE")
    if feedback.startswith("REJECT"):
        return "strategist"
    if feedback == "CONFIRM":
        return "persona"
    return "executor"

# ── Graph Logic ──────────────────────────────────────────────────────────────
def route_after_executor(state: AgentState):
    outputs = state.get("tool_outputs", {})
    plan = state.get("plan", [])
    completed = len([k for k in outputs if k.startswith("step_")])
    if "__final_response__" in outputs:
        # a 'respond' step ends the plan — surface any tool steps it cut off
        skipped = [s.get("action") for s in plan[completed:]
                   if isinstance(s, dict) and s.get("action") != "respond"]
        if skipped:
            log_agent(f"Executor: 'respond' ended plan early — skipped steps: {skipped}")
        return "persona"
    if completed >= len(plan):
        return "persona"
    return "executor"

workflow = StateGraph(AgentState)
workflow.add_node("strategist", node_strategist)
workflow.add_node("executor", node_executor)
workflow.add_node("persona", persona_node)
workflow.add_node("auditor", node_auditor)

workflow.set_entry_point("strategist")

def route_strategist(x):
    """Safe routing function that handles empty plans."""
    try:
        plan = x.get("plan", [])
        if plan and isinstance(plan, list) and len(plan) > 0 and plan[0].get("action") == "respond":
            # Through the executor, not straight to persona: the executor copies
            # the plan's rationale into __final_response__, which persona reads.
            return "executor"
    except (IndexError, KeyError, TypeError):
        pass
    return "auditor"

workflow.add_conditional_edges("strategist", route_strategist)
workflow.add_conditional_edges("auditor", route_auditor)
workflow.add_conditional_edges("executor", route_after_executor)
workflow.add_edge("persona", END)

agent = workflow.compile()

# ── API ──────────────────────────────────────────────────────────────────────
_pending_messages: dict[str, list] = {}
_PENDING_MSG_TTL = 300  # 5 minutes TTL for pending messages

async def run_background_tools(message: str, history: list, user_id: str, role: str, user_vibe: str, session_id: str = "default"):
    from utils.shared_logic import get_user_context
    msgs = [SystemMessage(content="Context:\n" + get_user_context())]
    for m in history:
        msgs.append(HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"]))
    msgs.append(HumanMessage(content=message))

    # ── Guard: resolve any plan waiting on user confirmation ────────────
    key = f"{user_id}:{session_id}"
    confirmed_plan: list = []
    confirmed = False
    pending = pop_pending_plan(key)
    if pending:
        held_plan, ts = pending
        if time.time() - ts > _PENDING_PLAN_TTL:
            log_agent("Guard: pending plan expired — ignoring.")
        elif _CONFIRM_RE.match(message):
            confirmed_plan = held_plan
            confirmed = True
            log_agent("Guard: user confirmed pending plan — executing.")
        else:
            log_agent("Guard: user did not confirm — pending plan discarded.")

    try:
        log_agent(f"Starting pipeline for {user_id}")
        result = await agent.ainvoke({
            "messages": msgs, "plan": confirmed_plan, "tool_outputs": {},
            "user_id": user_id, "role": role, "session_id": session_id,
            "user_vibe": user_vibe,
            "auditor_feedback": "",
            "revision_count": 0,
            "confirmed": confirmed,
        })

        final_msg = ""
        for m in reversed(result["messages"]):
            if isinstance(m, AIMessage):
                final_msg = m.content
                break

        if final_msg:
            if user_id not in _pending_messages:
                _pending_messages[user_id] = []
            _pending_messages[user_id].append((final_msg, time.time()))
            log_agent(f"Result stored for {user_id} (queue size: {len(_pending_messages[user_id])})")
    except Exception as e:
        log_agent(f"Pipeline Crash: {e}")

async def get_pending_message(user_id: str) -> str:
    queue = _pending_messages.get(user_id)
    if not queue:
        return ""
    # Drain expired entries silently
    now = time.time()
    _pending_messages[user_id] = [(msg, ts) for msg, ts in queue if now - ts <= _PENDING_MSG_TTL]
    if not _pending_messages[user_id]:
        del _pending_messages[user_id]
        return ""
    # Dequeue oldest valid message
    msg, _ = _pending_messages[user_id].pop(0)
    if not _pending_messages[user_id]:
        del _pending_messages[user_id]
    return msg

async def stream_chat_with_marin(message: str, history: list | None = None, context: str = "", user_id: str = "USR-00000000", role: str = "guest", user_vibe: str = "neutral", session_id: str = "default"):
    await run_background_tools(message, history or [], user_id, role, user_vibe, session_id=session_id)
    yield "Thinking..."

if __name__ == "__main__":
    async def test():
        async for chunk in stream_chat_with_marin("download assembly books"):
            print(chunk)
    asyncio.run(test())
