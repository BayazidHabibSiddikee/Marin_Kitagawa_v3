#!/usr/bin/env python3
"""
marin_fier.py — Two-stage intent classifier with LangChain StructuredTool

Stage 1 — Regex:  Zero-latency, handles obvious patterns + typos via fuzzy match.
Stage 2 — LLM:   ChatOllama(qwen2.5:0.5b).bind_tools(TOOLS) with Pydantic schemas.
                  qwen outputs a structured tool_call with validated, typed params.
                  num_predict=40 — enough for one tool call JSON, nothing more.

Flow:
  user text
    → regex pre-filter (instant)
    → if no match: qwen with bound tools → StructuredTool call
    → params validated by Pydantic
    → return {intent, params, user_vibe, confidence, _tool_ack}
"""

import re
import json
import os
import signal
import sys
import asyncio
import subprocess
from pathlib import Path
from difflib import get_close_matches
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

BASE_DIR = Path(__file__).resolve().parent


# ══════════════════════════════════════════════════════════════════════════════
# PYDANTIC SCHEMAS — typed, validated params for every tool
# ══════════════════════════════════════════════════════════════════════════════

class AlarmInput(BaseModel):
    time: str = Field(description="Clock time to alarm, e.g. '7:30 AM', '23:00'")

class TimerInput(BaseModel):
    duration: str = Field(description="Duration, e.g. '30 minutes', '1 hour 15 minutes'")

class CryptoInput(BaseModel):
    coin: str = Field(
        default="bitcoin",
        description="Coin id: bitcoin, ethereum, solana, dogecoin, bnb, cardano, ripple, etc."
    )

class StockInput(BaseModel):
    company: str = Field(
        description="Company name (1-3 words) or ticker, e.g. 'Apple', 'Tesla', 'AAPL'"
    )

class Connect4Input(BaseModel):
    mode: str = Field(
        default="computer",
        description="'computer' for AI opponent, 'two' for two-player mode"
    )

class CmdInput(BaseModel):
    command: str = Field(description="Shell command to run, e.g. 'ls -la', 'git status', 'python3 --version'")

class MathPlotInput(BaseModel):
    expression: str = Field(
        description=(
            "Full math expression to plot. Can be:\n"
            "- A preset name: 'circle', 'heart', 'rose', 'spiral', 'butterfly', 'lissajous', "
            "'cardioid', 'astroid', 'lemniscate', 'sine', 'parabola'\n"
            "- Parametric: x=r*cos(t), y=r*sin(t)\n"
            "- Equation: 'y = x^2', 'x = y^2 + 5'\n"
            "- Natural language: 'draw a heart', 'plot butterfly'\n"
            "- Explicit: '-x r*cos(t) -y r*sin(t)'"
        )
    )

class RunSequenceInput(BaseModel):
    commands: str = Field(
        description=(
            "One or more commands to run sequentially. "
            "Each command is auto-killed after a delay (4s math, 20s stock, 10s crypto, 40s butterfly).\n\n"
            "Acceptable formats:\n"
            '- Comma-separated presets: "heart, butterfly, spiral"\n'
            '- Space-separated presets: "heart butterfly spiral"\n'
            '- Semi-colon separated shell commands: "ls -la; python3 maths/mathplot.py heart"\n'
            '- JSON array: \'[{"cmd":"python3 maths/mathplot.py heart","delay":3}]\'\n\n'
            "This tool is ideal when the user asks for MULTIPLE graphs or operations at once."
        )
    )

class WeatherInput(BaseModel):
    city: str = Field(default="Dhaka", description="City name to fetch weather and humidity for")

class MapInput(BaseModel):
    city: str = Field(default="Dhaka", description="City name to center the map on")
    destination: Optional[str] = Field(default=None, description="Optional destination city for routing")
    custom_pins: Optional[list] = Field(default=None, description="List of custom location dicts with 'name', 'lat', 'lon', 'description' keys")

class SearchInput(BaseModel):
    query: str = Field(description="Search query for web searching")
    max_results: int = Field(default=5, description="Maximum number of results to return")

class SearchPDFInput(BaseModel):
    topic: str = Field(description="Topic to find PDF books or research papers for")

class ScrapeInput(BaseModel):
    url: str = Field(description="URL of the webpage to scrape content from")

class VaultInput(BaseModel):
    action: str = Field(description="Action: 'write', 'read', 'list', 'delete'")
    filename: Optional[str] = Field(default=None, description="Name of the file (e.g. 'memory_shard_01.txt')")
    content: Optional[str] = Field(default=None, description="Content to write to the file")
    category: str = Field(default="misc", description="Folder/category: 'personal_notes', 'technical_logs', 'memory_shards', etc.")

class PinPlacesInput(BaseModel):
    city: str = Field(default="Dhaka", description="City name to find and pin best places in")
    query: str = Field(default="tourist attraction", description="Type of places to find (e.g. 'cafes', 'museums', 'best places')")

class BanglaInput(BaseModel):
    pass

class VPAInput(BaseModel):
    command: Optional[str] = Field(None, description="Optional command to pass to the VPA assistant.")

class NoInput(BaseModel):
    pass   # tools that need no parameters

# ──  Input Schemas ───────────────────────────────────────────────────

class TeachInput(BaseModel):
    topic: str = Field(description="The subject or concept to explain")
    sub_intent: str = Field(default="standard", description="Depth: 'quick', 'standard', or 'deep'")

class QuizInput(BaseModel):
    topic: str = Field(description="Topic for the quiz")
    difficulty: str = Field(default="medium", description="Difficulty: 'easy', 'medium', or 'hard'")
    num_questions: int = Field(default=5, description="Number of questions (1-20)")

class StudyPlanInput(BaseModel):
    topic: str = Field(description="The subject to create a roadmap for")

class CodeReviewInput(BaseModel):
    code: str = Field(description="The code snippet to review")

class DebugInput(BaseModel):
    error: str = Field(description="The error message or description of the bug")


# ── COMMAND ALLOWLIST ─────────────────────────────────────────────────────────
_CMD_ALLOW = re.compile(
    r'^(ls|cat|pwd|echo|whoami|date|uptime|df|du|free|uname|hostname|'
    r'ps|git|python3?|pip3?|mkdir|touch|cp|mv|ln|rmdir|chmod|chown|'
    r'find|grep|rg|head|tail|wc|sort|uniq|cut|awk|sed|tr|'
    r'curl|wget|make|gcc|g\+\+|avr-gcc|avrdude|cargo|rustc|'
    r'tree|which|type|env|printenv|lsusb|lsblk|ip|ping|'
    r'ollama|uvicorn|node|npm|npx|yarn|pnpm|gemini|claude|openclaude|opencode|kimi|kiro-cli|'
    r'systemctl|journalctl|ffmpeg|ffprobe|yt-dlp|youtube-dl|'
    r'cd|nano|vim|nvim|emacs|code|less|more|'
    r'docker|podman|kubectl|docker-compose|'
    r'ssh|scp|rsync|diff|stat|realpath|readlink|basename|dirname|'
    r'time|timeout|htop|top|btop|atop|sensors|lscpu|lspci|lsmod|dmesg|'
    r'bash|zsh|sh|fish|screen|tmux|'
    r'nohup|watch|sleep|id|who|groups|users|'
    r'firefox|chromium|google-chrome|xdg-open|mpv|vlc|'
    r'notify-send|file|bc|expr|tee|yes|xargs|'
    r'convert|magick|tesseract|jq|yq|'
    r'nl|od|xxd|hexdump|expand|unexpand|fmt|pr|fold|'
    r'locale|timedatectl|localectl)',
    re.IGNORECASE
)
_CMD_BLOCK = re.compile(
    r'(rm\s+-rf\s*/|sudo\s+rm|dd\s+if=|mkfs|shutdown|reboot|passwd|'
    r'useradd|userdel|wget.+\|\s*bash|curl.+\|\s*sh|>\s*/dev/sd|nc\s+-e|bash\s+-i)',
    re.IGNORECASE
)

_cmd_log: list[dict] = []   # in-memory log (last 100), served at /cmd/log

# ── KNOWN SCRIPTS — alias → full command; auto-resolved when mentioned in chat ──
_KNOWN_SCRIPTS: dict[str, str] = {
    "marin":          "python3 marin.py",
    "rag_server":     "python3 rag_server.py",
    "run_marin":      "bash run_marin.sh",
    "run_all":        "bash run_all.sh",
    "mathplot":       "python3 maths/mathplot.py",
    "stock":          "python3 tools/stock.py",
    "stock_tracker":  "python3 tools/stock.py",
    "crypto":         "python3 tools/crypto.py",
    "crypto_tracker": "python3 tools/crypto.py",
    "map":            "python3 tools/knowledge_hub.py",
    "weather":        "python3 tools/knowledge_hub.py",
    "knowledge_hub":  "python3 tools/knowledge_hub.py",
    "research_hub":   "python3 tools/knowledge_hub.py",
    "bangla":         "python3 tools/bangla.py",
    "vpa":            "python3 tools/vpa.py",
    "alexa":          "python3 tools/vpa.py",
}
_KNOWN_SCRIPT_KEYS: set[str] = set(_KNOWN_SCRIPTS.keys())


def is_cmd_allowed(cmd: str) -> tuple[bool, str]:
    first = cmd.strip().split()[0].lstrip('./') if cmd.strip() else ""
    if _CMD_BLOCK.search(cmd):
        return False, "dangerous pattern blocked"
    if not _CMD_ALLOW.match(first):
        return False, f"'{first}' not in allowlist"
    return True, "ok"


def tool_run_command(command: str) -> str:
    import datetime
    allowed, reason = is_cmd_allowed(command)
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    entry = {"cmd": command, "allowed": allowed, "output": "", "ts": ts}
    if not allowed:
        entry["output"] = f"[EXIT BLOCKED] {reason}"
        _cmd_log.append(entry)
        if len(_cmd_log) > 100: _cmd_log.pop(0)
        return f"[EXIT BLOCKED] Can't run `{command}` — {reason}."
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
        code = r.returncode
        body = (r.stdout or r.stderr or "(no output)").strip()
        out = f"[EXIT {code}] {body}"
        entry["output"] = out
        _cmd_log.append(entry)
        if len(_cmd_log) > 100: _cmd_log.pop(0)
        return out
    except subprocess.TimeoutExpired:
        entry["output"] = "[EXIT -1] timed out (15s)"
        _cmd_log.append(entry)
        return "[EXIT -1] Command timed out after 15 seconds."
    except Exception as e:
        entry["output"] = f"[EXIT -1] {e}"
        _cmd_log.append(entry)
        return f"[EXIT -1] Error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# TOOL LAUNCHERS — each function fires the subprocess and returns a context str
# These are the actual callables passed to StructuredTool
# ══════════════════════════════════════════════════════════════════════════════

def _popen(script: str, args: list[str] = [], timeout: float | None = None):
    import threading
    path = BASE_DIR / script
    if not path.exists():
        return f"Script not found: {script}"
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")
    try:
        proc = subprocess.Popen(
            [sys.executable, str(path)] + args,
            stdout=open('/home/sword/Documents/marin/logs/tool_execution.log', 'a'),
            stderr=open('/home/sword/Documents/marin/logs/tool_execution.log', 'a'),
            start_new_session=True,
            cwd=str(BASE_DIR),
            env=env,
        )
    except Exception as e:
        return f"Failed to launch {script}: {e}"

    if timeout:
        def _kill():
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGTERM)
                import time
                time.sleep(0.4)
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                print(f"[tool:{script}] killed after {timeout}s")
            except ProcessLookupError:
                pass
            except Exception as e:
                print(f"[tool:{script}] kill error: {e}")
        threading.Timer(timeout, _kill).start()

    return None   # None = launched OK


def tool_set_alarm(time: str) -> str:
    err = _popen("tools/alarm.py", [time])
    if err: return err
    return (f"Alarm set for {time}. "
            f"The alarm script is running in the background and will beep when it fires.")

def tool_set_timer(duration: str) -> str:
    err = _popen("tools/timer.py", [duration])
    if err: return err
    return f"Countdown timer started for {duration}. It's ticking in the background."

def tool_get_crypto_price(coin: str = "bitcoin") -> str:
    coin = coin.lower().strip()
    from tools.crypto_data import fetch_crypto_price
    data = fetch_crypto_price(coin)
    # Also launch GUI window in background
    _popen("tools/crypto.py", ["--coin", coin], timeout=30)
    return data

def tool_get_stock_info(company: str) -> str:
    company = " ".join(company.split()[:3]).strip()
    from tools.stock_data import fetch_stock_price
    data = fetch_stock_price(company)
    # Also launch GUI window in background
    if company.upper() in _COMMON_UPPER or (company.isupper() and 1 <= len(company) <= 5):
        _popen("tools/stock.py", ["--ticker", company.upper()])
    else:
        _popen("tools/stock.py", ["--company", company])
    return data

def tool_open_news() -> str:
    import json, os
    # Try DB first
    try:
        from database import get_latest_news
        items = get_latest_news(limit=5)
        if items:
            lines = ["📰 **LATEST NEWS**\n"]
            for i, item in enumerate(items, 1):
                lines.append(f"**{i}. {item['title']}**")
                if item.get("summary"): lines.append(f"   {item['summary']}")
                analysis = (item.get("analysis") or "").split("\n")[0]
                if analysis: lines.append(f"   _{analysis}_")
                lines.append(f"   🕐 {item['fetched_at'][:16]}")
                lines.append("")
            return "\n".join(lines)
    except Exception:
        pass
    # Fallback: JSON file
    news_file = os.path.join(BASE_DIR, "storage", "latest_news.json")
    if os.path.exists(news_file):
        try:
            with open(news_file) as f:
                items = json.load(f)
            if items:
                lines = ["📰 **LATEST NEWS**\n"]
                for i, item in enumerate(items[:5], 1):
                    lines.append(f"**{i}. {item.get('title', '')}**")
                    if item.get("summary"): lines.append(f"   {item['summary']}")
                    analysis = (item.get("analysis") or "").split("\n")[0]
                    if analysis: lines.append(f"   _{analysis}_")
                    lines.append("")
                return "\n".join(lines)
        except Exception:
            pass
    _popen("tools/news.py")
    return "Opening news in browser (no cached news available)."

def tool_send_email() -> str:
    err = _popen("tools/email_tool.py")
    if err: return err
    return "Email composer launched. It will ask for recipient, subject, and body interactively."

def tool_play_tictactoe() -> str:
    err = _popen("tools/tictactoe.py")
    if err: return err
    return "Tic Tac Toe game window is opening."

def tool_play_connect4(mode: str = "computer") -> str:
    args = ["--two"] if mode == "two" else []
    err = _popen("tools/connect4.py", args)
    if err: return err
    return f"Connect Four launched in {mode} mode."

def tool_play_wordgame() -> str:
    err = _popen("tools/wordgame.py")
    if err: return err
    return "Word scramble game is starting."

def tool_draw_me() -> str:
    err = _popen("tools/draw.py")
    if err: return err
    return "Draw-me tool launched. It will take a webcam photo and render it as a turtle drawing."

def tool_take_screenshot() -> str:
    err = _popen("tools/image.py")
    if err: return err
    return "Screenshot captured and saved."

def tool_math_plot(expression: str) -> str:
    """Launch the math equation plotter to draw parametric curves."""
    import shlex
    # Strip leading verbs like "draw", "plot", "graph", "show me"
    cleaned = re.sub(r'^(?:draw|plot|graph|show)\s+(?:me\s+)?(?:a\s+)?', '', expression, flags=re.IGNORECASE).strip()
    # If it starts with '-', treat as explicit CLI flags (e.g. '-x r*cos(t) -y r*sin(t)')
    if cleaned.startswith('-'):
        args = shlex.split(cleaned)
    else:
        args = [cleaned]  # single arg → preset lookup or NLP mode
    err = _popen("maths/mathplot.py", args)
    if err: return err
    return f"[EXIT ?] Math plotter launched for: '{cleaned}' (CNC simulation window opening)."


def tool_run_sequence(commands: str) -> str:
    """
    Run multiple commands sequentially with auto-kill delays.
    Delegates to tools/command_queue.py for timing and lifecycle.
    """
    import json
    import tempfile
    import datetime

    trimmed = commands.strip()
    cmd_list = []

    # Try JSON array
    if trimmed.startswith("["):
        try:
            cmd_list = json.loads(trimmed)
        except json.JSONDecodeError:
            pass

    # Try JSON object (single command)
    if not cmd_list and trimmed.startswith("{"):
        try:
            cmd_list = [json.loads(trimmed)]
        except json.JSONDecodeError:
            pass

    if not cmd_list:
        # Split by semicolon (shell commands) or comma (presets)
        parts = [p.strip() for p in re.split(r'[;,|]', trimmed) if p.strip()]
        for p in parts:
            # If it looks like a shell command (has spaces or slashes), run as-is
            if " " in p or "/" in p:
                cmd_list.append({"cmd": p, "delay": 3, "name": p[:40]})
            else:
                # Treat as mathplot preset
                cmd_list.append({
                    "cmd": f"python3 maths/mathplot.py {p}",
                    "delay": 4,
                    "name": f"Plot: {p}",
                })

    if not cmd_list:
        return "run_sequence: no commands parsed."

    # Default delays: stock=20s, crypto=10s, math=4s, butterfly=40s
    for item in cmd_list:
        if "delay" not in item:
            cmd = item.get("cmd", "").lower()
            if "stock" in cmd or "yahoo" in cmd:
                item["delay"] = 20
            elif "crypto" in cmd or "finance" in cmd:
                item["delay"] = 10
            elif "butterfly" in cmd or "teal" in cmd:
                item["delay"] = 40
            else:
                item["delay"] = 4

    # Write to temp JSON and delegate to command_queue.py
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    try:
        json.dump(cmd_list, tmp)
        tmp_path = tmp.name
    finally:
        tmp.close()

    try:
        r = subprocess.run(
            [sys.executable, str(BASE_DIR / "tools/command_queue.py"), "--json", tmp_path],
            capture_output=True, text=True, timeout=300,
            cwd=str(BASE_DIR),
            env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
        )
        out = (r.stdout or r.stderr or "(no output)").strip()
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        _cmd_log.append({
            "cmd": f"[tool:run_sequence] {trimmed[:80]}",
            "allowed": True,
            "output": out[:500],
            "ts": ts,
        })
        if len(_cmd_log) > 100:
            _cmd_log.pop(0)
        return f"Sequenced {len(cmd_list)} commands:\n{out[:1200]}"
    except Exception as e:
        return f"run_sequence error: {e}"
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ── Knowledge Hub Tools ──────────────────────────────────────────────────────

def tool_get_weather(city: str = "Dhaka") -> str:
    from tools.knowledge_hub import get_weather_data
    data = get_weather_data(city)
    if "error" in data:
        return f"Weather Error: {data['error']}"
    return (
        f"Weather in {data['city']}: {data['temperature']}°C, "
        f"Humidity: {data['humidity']}%, Wind: {data['windspeed']} km/h. "
        f"Recorded at: {data['time']}"
    )

def tool_create_map(city: str = "Dhaka", destination: str = None, custom_pins: list = None) -> str:
    from tools.knowledge_hub import create_integrated_hub_map, _geocode
    from config import PORT

    # Geocode custom pins that don't have lat/lon
    if custom_pins:
        geocoded = []
        for pin in custom_pins:
            if pin.get("lat") and pin.get("lon"):
                geocoded.append(pin)
            else:
                name = pin.get("name", "")
                query = f"{name}, {city}" if city else name
                try:
                    loc = _geocode(query)
                    if loc:
                        geocoded.append({
                            "name": name,
                            "lat": loc.latitude,
                            "lon": loc.longitude,
                            "description": pin.get("description", ""),
                        })
                except Exception:
                    pass
        custom_pins = geocoded

    res = create_integrated_hub_map(city, destination, custom_pins=custom_pins)
    if isinstance(res, dict) and "error" in res:
        return res["error"]
    # Open map directly in browser
    map_url = res.get("map_url", "/static/generated/knowledge_hub_map.html")
    full_url = f"http://localhost:{PORT}{map_url}"
    subprocess.Popen(["xdg-open", full_url], stdout=open('/home/sword/Documents/marin/logs/tool_execution.log', 'a'), stderr=open('/home/sword/Documents/marin/logs/tool_execution.log', 'a'))
    
    pin_count = len(res.get("custom_pins", [])) + len(res.get("pins", []))
    msg = f"Map created for {city} with {pin_count} pins."
    if destination:
        msg += f" Route to {destination} included."
    return msg

def tool_search_web(query: str, max_results: int = 5) -> str:
    from tools.knowledge_hub import search_web
    results = search_web(query, max_results)
    if isinstance(results, dict) and "error" in results:
        return f"Search Error: {results['error']}"
    formatted = [f"- {r['title']}: {r['href']}\n  {r['body']}" for r in results]
    return f"Web Search Results for '{query}':\n\n" + "\n\n".join(formatted)

def tool_search_pdfs(topic: str) -> str:
    from tools.knowledge_hub import search_pdfs
    from config import PORT
    results = search_pdfs(topic)
    if isinstance(results, dict) and "error" in results:
        return f"PDF Search Error: {results['error']}"
    
    formatted = [f"- {r['title']}: {r['href']}" for r in results]
    # Suggest opening the hub
    msg = f"PDF/Book Search Results for '{topic}':\n\n" + "\n".join(formatted[:5])
    msg += f"\n\n(You can see more results at http://localhost:{PORT}/research-hub)"
    return msg

def tool_scrape_content(url: str) -> str:
    from tools.knowledge_hub import scrape_content
    try:
        content = scrape_content(url)
        return f"Scraped content from {url}:\n\n{content[:2000]}..."
    except Exception as e:
        return f"Scraping error: {e}"

def tool_pin_places(city: str = "Dhaka", query: str = "tourist attraction") -> str:
    from tools.knowledge_hub import search_places_in_city, create_integrated_hub_map
    from config import PORT
    pins = search_places_in_city(city, query)
    if not pins:
        return f"Could not find any '{query}' in {city}."
    
    res = create_integrated_hub_map(city, pins=pins)
    # Launch Knowledge Hub dashboard in browser
    url = f"http://localhost:{PORT}/knowledge-hub"
    subprocess.Popen(["xdg-open", url], stdout=open('/home/sword/Documents/marin/logs/tool_execution.log', 'a'), stderr=open('/home/sword/Documents/marin/logs/tool_execution.log', 'a'))
    
    msg = f"Pinned {len(pins)} '{query}' in {city} on the map."
    return msg

def tool_bangla_translator() -> str:
    err = _popen("tools/bangla.py")
    if err: return err
    return "Bangla voice translator launched in a new terminal/session."

def tool_vpa_assistant(command: str = None) -> str:
    args = [command] if command else []
    err = _popen("tools/vpa.py", args)
    if err: return err
    return "Virtual Personal Assistant (Alexa) launched."

def tool_manage_vault(action: str, filename: str = None, content: str = None, category: str = "misc") -> str:
    # NOTE: This is a placeholder; the actual call happens in execute_tool()
    # where the agent_name is available.
    return "Vault operation triggered."

# ──  Intents ──────────────────────────────────────────────────────────

def tool_teach_topic(topic: str, sub_intent: str = "standard") -> str:
    return f"MARIN_INTENT:teach:{topic}:{sub_intent}"

def tool_generate_quiz(topic: str, difficulty: str = "medium", num_questions: int = 5) -> str:
    return f"MARIN_INTENT:quiz:{topic}:{difficulty}:{num_questions}"

def tool_create_study_plan(topic: str) -> str:
    return f"MARIN_INTENT:study_plan:{topic}"

def tool_review_code(code: str) -> str:
    return f"MARIN_INTENT:code_review:{code}"

def tool_explain_error(error: str, code: str = "") -> str:
    return f"MARIN_INTENT:debug:{error}"

# ══════════════════════════════════════════════════════════════════════════════
# STRUCTURED TOOLS — bind schemas to callables
# ══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    StructuredTool.from_function(
        func=tool_set_alarm, name="set_alarm",
        description="Set a clock alarm at a specific time.",
        args_schema=AlarmInput,
    ),
    StructuredTool.from_function(
        func=tool_set_timer, name="set_timer",
        description="Start a countdown timer for a given duration.",
        args_schema=TimerInput,
    ),
    StructuredTool.from_function(
        func=tool_get_crypto_price, name="get_crypto_price",
        description="Open live cryptocurrency price tracker. Use when user asks about crypto prices.",
        args_schema=CryptoInput,
    ),
    StructuredTool.from_function(
        func=tool_get_stock_info, name="get_stock_info",
        description="Open stock price and 30-day chart for a company. Use when user asks about stocks or shares.",
        args_schema=StockInput,
    ),
    StructuredTool.from_function(
        func=tool_open_news, name="open_news",
        description="Open news website in browser.",
        args_schema=NoInput,
    ),
    StructuredTool.from_function(
        func=tool_send_email, name="send_email",
        description="Launch interactive email composer.",
        args_schema=NoInput,
    ),
    StructuredTool.from_function(
        func=tool_play_tictactoe, name="play_tictactoe",
        description="Launch Tic Tac Toe game.",
        args_schema=NoInput,
    ),
    StructuredTool.from_function(
        func=tool_play_connect4, name="play_connect4",
        description="Launch Connect Four game.",
        args_schema=Connect4Input,
    ),
    StructuredTool.from_function(
        func=tool_play_wordgame, name="play_wordgame",
        description="Launch word scramble game.",
        args_schema=NoInput,
    ),
    StructuredTool.from_function(
        func=tool_draw_me, name="draw_me",
        description="Take webcam photo and draw it as turtle art.",
        args_schema=NoInput,
    ),
    StructuredTool.from_function(
        func=tool_take_screenshot, name="take_screenshot",
        description="Take a screenshot.",
        args_schema=NoInput,
    ),
    StructuredTool.from_function(
        func=tool_run_command, name="run_command",
        description=(
            "Execute an allowlisted shell/terminal command on the operator's machine. "
            "Use when asked to run ls, git status, python scripts, check system info, etc."
        ),
        args_schema=CmdInput,
    ),
    StructuredTool.from_function(
        func=tool_math_plot, name="math_plot",
        description=(
            "Draw a math equation, parametric curve, or preset shape using the CNC simulator. "
            "Use when asked to plot, draw, or visualize any equation, shape, or graph. "
            "Supports presets: circle, heart, rose, spiral, butterfly, lissajous, cardioid, "
            "astroid, lemniscate, sine, parabola, cycloid, star, infinity. "
            "Also supports free-form equations like 'y = x^2' or 'x = r*cos(t), y = r*sin(t)', "
            "and natural language like 'draw a heart' or 'plot butterfly'."
        ),
        args_schema=MathPlotInput,
    ),
    StructuredTool.from_function(
        func=tool_run_sequence, name="run_sequence",
        description=(
            "Run MULTIPLE operations in sequence — each is auto-killed after a delay "
            "(math/graph: 4s, stock: 20s, crypto: 10s, butterfly: 40s). "
            "Use this when the user wants several graphs, stock checks, or mixed operations "
            "in one request. "
            "Accepts command presets (heart, butterfly) or full shell commands. "
            "Example: 'heart, butterfly, spiral' draws 3 shapes sequentially on one window."
        ),
        args_schema=RunSequenceInput,
    ),
    StructuredTool.from_function(
        func=tool_get_weather, name="get_weather",
        description="Fetch current weather, temperature, and humidity for a city.",
        args_schema=WeatherInput,
    ),
    StructuredTool.from_function(
        func=tool_create_map, name="create_map",
        description="Generate an interactive environmental map showing weather and flood data.",
        args_schema=MapInput,
    ),
    StructuredTool.from_function(
        func=tool_search_web, name="search_web",
        description="Search the web for information using DuckDuckGo.",
        args_schema=SearchInput,
    ),
    StructuredTool.from_function(
        func=tool_search_pdfs, name="search_pdfs",
        description="Specialized search for PDF books, research papers, and technical documents.",
        args_schema=SearchPDFInput,
    ),
    StructuredTool.from_function(
        func=tool_scrape_content, name="scrape_content",
        description="Scrape and extract text content from a specific URL. Useful for reading articles or documentation.",
        args_schema=ScrapeInput,
    ),
    StructuredTool.from_function(
        func=tool_pin_places, name="pin_places",
        description="Find and pin 'best places', tourist spots, or specific venues (cafes, etc.) in a city on the interactive map.",
        args_schema=PinPlacesInput,
    ),
    StructuredTool.from_function(
        func=tool_bangla_translator, name="bangla_translator",
        description="Launch Bangla voice translator. Use when user wants to speak or translate Bangla.",
        args_schema=BanglaInput,
    ),
    StructuredTool.from_function(
        func=tool_vpa_assistant, name="vpa_assistant",
        description="Launch the Virtual Personal Assistant (Alexa) for interactive tasks, games, or information.",
        args_schema=VPAInput,
    ),
    StructuredTool.from_function(
        func=tool_manage_vault, name="manage_vault",
        description=(
            "Interact with your private playground vault in ./unique/. "
            "Actions: 'write' (save info to remember later), 'read' (fetch saved info), "
            "'list' (see what files you have), 'delete' (remove file). "
            "Use this for long-term memory or storing technical/personal notes. "
            "Categories: 'technical_logs', 'memory_shards', 'personal_notes', 'partner_logs'."
        ),
        args_schema=VaultInput,
    ),
    # ──  Specialized Tools ─────────────────────────────────────────────
    StructuredTool.from_function(
        func=tool_teach_topic, name="teach",
        description="Explain a concept or teach a topic. Use for 'how to', 'what is', etc.",
        args_schema=TeachInput,
    ),
    StructuredTool.from_function(
        func=tool_generate_quiz, name="quiz",
        description="Generate a quiz or test on a specific topic.",
        args_schema=QuizInput,
    ),
    StructuredTool.from_function(
        func=tool_create_study_plan, name="study_plan",
        description="Create a long-term learning roadmap or study plan for a subject.",
        args_schema=StudyPlanInput,
    ),
    StructuredTool.from_function(
        func=tool_review_code, name="code_review",
        description="Review user-provided code for bugs and improvements.",
        args_schema=CodeReviewInput,
    ),
    StructuredTool.from_function(
        func=tool_explain_error, name="debug",
        description="Analyze a code error/exception and provide a fix.",
        args_schema=DebugInput,
    ),
]

# Map name → StructuredTool for fast lookup
_TOOL_MAP: dict[str, StructuredTool] = {t.name: t for t in TOOLS}


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1 — REGEX PRE-FILTER  (with fuzzy coin matching)
# ══════════════════════════════════════════════════════════════════════════════

_COIN_CANONICAL = {
    "bitcoin":      ["bitcoin","btc","bitcoun","bitcion","bicoin"],
    "ethereum":     ["ethereum","eth","etherum","etherium","ether"],
    "binancecoin":  ["bnb","binance"],
    "solana":       ["solana","sol"],
    "dogecoin":     ["dogecoin","doge","dogecoyn"],
    "cardano":      ["cardano","ada"],
    "ripple":       ["ripple","xrp"],
    "litecoin":     ["litecoin","ltc"],
    "polkadot":     ["polkadot","dot"],
    "polygon":      ["polygon","matic"],
    "shiba-inu":    ["shiba","shib"],
    "avalanche-2":  ["avalanche","avax"],
}
_ALIAS_TO_CANON = {
    alias: canon
    for canon, aliases in _COIN_CANONICAL.items()
    for alias in aliases
}

def _fuzzy_coin(word: str) -> str | None:
    word = word.lower().strip()
    if word in _ALIAS_TO_CANON:
        return _ALIAS_TO_CANON[word]
    if len(word) >= 5:
        close = get_close_matches(word, _ALIAS_TO_CANON.keys(), n=1, cutoff=0.82)
        if close:
            return _ALIAS_TO_CANON[close[0]]
    return None

def _is_crypto_text(lower: str) -> bool:
    if re.search(r'\bcrypto(?:currency)?\b', lower):
        return True
    for word in re.split(r'\W+', lower):
        if _fuzzy_coin(word):
            return True
    return False

def _extract_coin_from(lower: str) -> str:
    for word in re.split(r'\W+', lower):
        c = _fuzzy_coin(word)
        if c:
            return c
    return "bitcoin"

# Tickers that must stay ALL-CAPS and should never be .title()-cased
_COMMON_UPPER: set[str] = {
    "AAPL","TSLA","MSFT","AMZN","GOOGL","META","NVDA","NFLX","AMD","INTC",
    "BABA","UBER","LYFT","SNAP","TWTR","PYPL","SQ","SHOP","COIN","HOOD",
    "GME","AMC","BB","NOK","PLTR","NIO","RIVN","LCID","F","GM","FORD",
    "BA","GE","XOM","CVX","WMT","TGT","COST","KO","PEP","JNJ","PFE",
    "MRNA","BNTX","ABBV","MRK","JPM","BAC","WFC","GS","MS","V","MA",
    "DIS","CMCSA","T","VZ","TMUS","ORCL","IBM","CRM","NOW","ADBE","QCOM",
    "TXN","AVGO","MU","LRCX","AMAT","ASML","TSM","SONY","SAMSNG","005930",
    "BRK","BRKB","SPY","QQQ","VOO","VTI","ARKK","IWM",
}

_TICKER_PAT = re.compile(r'\b([A-Z]{1,5})\b')

def _extract_ticker_from(text: str) -> str | None:
    """
    Return the first ALL-CAPS word that looks like a real known ticker.
    Ignores short noise words (I, A, AT, IS, etc.) via _COMMON_UPPER check.
    Returns None if nothing found.
    """
    for m in _TICKER_PAT.finditer(text):
        word = m.group(1)
        if word in _COMMON_UPPER:
            return word
    return None


def _extract_company_from(text: str) -> str:
    """
    Extract company name from *original-case* text so tickers like 'TSLA'
    aren't mangled to 'Tsla' by .title().
    """
    lower = text.lower()
    cleaned = re.sub(
        r'\b(show me|get me|check|open|what is the|what\'s the|tell me|'
        r'look up|pull up|find|give me|display|fetch|please|'
        r'stock price of|stock of|price of|share price of|'
        r'stock price|share price|stock info|market price|ticker for|'
        r'stock|price|market|shares?|the|a|an)\b',
        ' ', lower, flags=re.IGNORECASE
    )
    # Rebuild from original-case text at positions that survived cleaning
    # Simple approach: strip the same filler from original text
    cleaned_orig = re.sub(
        r'\b(show me|get me|check|open|what is the|what\'s the|tell me|'
        r'look up|pull up|find|give me|display|fetch|please|'
        r'stock price of|stock of|price of|share price of|'
        r'stock price|share price|stock info|market price|ticker for|'
        r'stock|price|market|shares?|the|a|an)\b',
        ' ', text, flags=re.IGNORECASE
    )
    words = [w for w in cleaned_orig.split() if len(w) > 1][:3]
    if not words:
        return ""
    # Keep ALL-CAPS words as-is (tickers); .title() everything else
    titled = []
    for w in words:
        titled.append(w if w.upper() in _COMMON_UPPER else w.title())
    company = " ".join(titled).strip()
    if not company or len(company) > 30:
        return ""
    return company

def _extract_time_from(lower: str) -> str:
    m = re.search(r'alarm\s+(?:for|at)\s+(.+?)(?:\s*$|\s+(?:tomorrow|today))', lower)
    if m: return m.group(1).strip()
    m = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.))', lower)
    if m: return m.group(1).strip()
    return lower.strip()

def _extract_duration_from(lower: str) -> str:
    m = re.search(
        r'(\d+\s*(?:hour|hr|minute|min|second|sec)s?'
        r'(?:\s+(?:and\s+)?\d+\s*(?:minute|min|second|sec)s?)?)',
        lower
    )
    if m: return m.group(1).strip()
    return lower.strip()

def extract_topic(text: str) -> str:
    """Pull the subject/topic from a teach or quiz request."""
    patterns = [
        r'(?:teach|explain|quiz|test)\s+(?:me\s+)?(?:about|on)?\s+(.+)',
        r'what\s+is\s+(.+)',
        r'how\s+does?\s+(.+?)\s+work',
        r'study\s+plan\s+(?:for|on)\s+(.+)',
        r'teach depth:[^—]*—\s*(.+)',
        r'study plan for:\s*(.+)',
        r'review my code:\n?([\s\S]*)'
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            topic = m.group(1).strip()
            # Remove trailing question marks, filler words
            topic = re.sub(r'[?!.]+$', '', topic).strip()
            return topic
    return text  # fallback: use full message as topic

def extract_quiz_params(text: str) -> dict:
    """Extract quiz parameters from message."""
    lower = text.lower()
    num = 5  # default
    m = re.search(r'(\d+)\s*(?:question|q)', lower)
    if m:
        num = min(int(m.group(1)), 20)  # cap at 20

    difficulty = "medium"
    if re.search(r'easy|beginner|simple', lower):
        difficulty = "easy"
    elif re.search(r'hard|advanced|expert', lower):
        difficulty = "hard"

    return {"num_questions": num, "difficulty": difficulty}

def extract_timer_task(text: str) -> str:
    """Pull the task name from a timer start command."""
    patterns = [
        r'/timer\s+start\s+(.+)',
        r'start\s+(?:timer|session|focus)\s+(?:for|on)?\s*(.+)',
        r'focus\s+on\s+(.+)',
        r'working\s+on\s+(.+)',
    ]
    for p in patterns:
        m = re.search(p, text.lower())
        if m:
            return m.group(1).strip().title()
    return ""

# ── REGEX PATTERNS for Stage 1 ────────────────────────────────────────────────

_STOCK_PAT = re.compile(r'\b(stock|share\s*price|ticker|market\s*price)\b')
_ALARM_PAT = re.compile(r'\b(set\s+an?\s+alarm|alarm\s+(?:for|at))\b')
_TIMER_PAT = re.compile(r'\b(set\s+a?\s*timer|start\s+timer)\b|\d+\s*(?:min|minute|hour|hr|sec)\s*(?:timer|countdown)')
_NEWS_PAT  = re.compile(r'\b(open\s+news|latest\s+news|news|headlines)\b')
_EMAIL_PAT = re.compile(r'\b(send\s+(?:an?\s+)?email|email\s+to|compose\s+(?:an?\s+)?email|write\s+(?:a\s+)?mail)\b')
_TTT_PAT   = re.compile(r'\b(tic\s*tac\s*toe|tiktaktoe|tictactoe)\b')
_C4_PAT    = re.compile(r'\b(connect\s*4|connect\s*four|connect4)\b')
_WORD_PAT  = re.compile(r'\b(word\s*game|wordgame|word\s*scramble)\b')
_DRAW_PAT  = re.compile(r'\b(draw\s+me|take\s+(?:my\s+)?photo\s+and\s+draw)\b')
_SHOT_PAT   = re.compile(r'\b(screenshot|take\s+a\s*(?:pic|screen))\b')
_ALL_PAT    = re.compile(r'\b(use\s+(?:every|all)\s+(?:tool|command|ability)|run\s+(?:every|all)\s+(?:tool|command)|show\s+(?:everything|all\s+tools))\b')
_RUN_PAT    = re.compile(
    r'\b(?:run|execute)\s+(?:command\s*:?\s*)?(`?[a-z_\-./]+\s*(?:\|.*)?`?)',
    re.IGNORECASE
)
_CAN_YOU_RUN_PAT = re.compile(
    r'\b(?:can\s+you|could\s+you|please)\s+(`?[a-z][a-z0-9_\-+./]*`?(?:\s+[^\s,.!?]+){0,6})\s*$',
    re.IGNORECASE
)
_MATH_PLOT_PAT = re.compile(
    r'\b(draw|plot|graph|show)\s+(?:me\s+)?(?:a\s+)?(.+?)\s*$',
    re.IGNORECASE
)
_MATH_PRESET_PAT = re.compile(
    r'\b(heart|butterfly|spiral|lissajous|cardioid|astroid|lemniscate|rose|circle|sine|parabola|hyperbola|ellipse|cycloid|epitrochoid|hypotrochoid|deltoid)\b',
    re.IGNORECASE
)
_MATH_TOOL_PAT = re.compile(
    r'\b(mathplot|maths?/|math\s+(tool|plot|graph)|parametric|cnc\s+simulat)\b',
    re.IGNORECASE
)
_MATH_EXPR_PAT = re.compile(
    r'(?:^|[\s,;:])(?:y\s*=|x\s*=|r\s*=|z\s*=)[^=]{2,}',
    re.IGNORECASE
)

_EXECUTING_PAT = re.compile(
    r'\bEXECUTING\s+(.+?)(?:\s*$|[,;!?])',
    re.IGNORECASE
)

_SEARCH_PAT = re.compile(r'\b(search|find|lookup|google|duckduckgo)\b')
_PDF_PAT    = re.compile(r'\b(pdf|book|paper|textbook|research|thesis)\b')

_MAP_PAT   = re.compile(r'\b(map|location|flood|weather\s*map|environmental\s*map|route|directions|pin|places|attractions|best\s*places)\b')
_WEATHER_PAT = re.compile(r'\b(weather|temperature|humidity|temp)\b')

# ── 64 Districts (Zila) of Bangladesh ──────────────────────────────────────
BD_DISTRICTS = {
    "barisal", "bhola", "barguna", "patuakhali", "pirojpur",
    "chittagong", "coxsbazar", "comilla", "feni", "brahmanbaria",
    "chandpur", "lakshmipur", "noakhali", "khagrachhari", "rangamati", "bandarban",
    "dhaka", "gazipur", "narayanganj", "manikganj", "munshiganj",
    "narsingdi", "tangail", "jamalpur", "mymensingh", "sherpur",
    "netrakona", "kishoreganj", "faridpur", "gopalganj", "madaripur",
    "rajbari", "shariatpur",
    "khulna", "bagerhat", "satkhira", "jessore", "jhenaidah",
    "magura", "narail", "kustia", "chuadanga", "meherpur",
    "rajshahi", "bogra", "joypurhat", "naogaon", "natore",
    "chapainawabganj", "sirajganj", "pabna", "rajshahi",
    "rangpur", "dinajpur", "thakurgaon", "panchagarh", "lalmonirhat",
    "kurigram", "gaibandha", "nilphamari", "roxy", "syedpur",
    "sylhet", "moulvibazar", "habiganj", "sunamganj",
}

# Non-city words to skip during extraction
_BD_DISTRICTS_NORMALIZED = {d.replace("'", "").replace(" ", ""): d for d in BD_DISTRICTS}

def _find_district(text: str) -> str | None:
    """Find a Bangladesh district name in text, returns title-cased name."""
    normalized = text.lower().replace("'", "").replace(" ", "")
    for key, name in _BD_DISTRICTS_NORMALIZED.items():
        if key in normalized:
            return name.title()
    return None

# ──  specialized regex ──────────────────────────────────────────────
_TEACH_PAT   = re.compile(r'\b(teach|explain|what\s+is|how\s+(?:does|to)|why\s+does|clarify|i\s+don\'?t\s+understand)\b')
_QUIZ_PAT    = re.compile(r'\b(quiz|test\s+me|examine|practice\s+questions?|mcq)\b')
_PLAN_PAT    = re.compile(r'\b(study\s+plan|learning\s+plan|roadmap|curriculum|schedule|how\s+to\s+learn)\b')
_REVIEW_PAT  = re.compile(r'\b(review\s+my\s+code|check\s+(my\s+)?code|fix\s+(this|my))\b')
_DEBUG_PAT   = re.compile(r'\b(error|exception|bug|crash|traceback|not\s+working|failed|undefined)\b')

def _regex_stage(text: str) -> dict | None:
    """Returns {intent, params, confidence} or None if uncertain."""
    lower = text.lower()

    #  Specialized Modes (High priority)
    if _QUIZ_PAT.search(lower):
        params = extract_quiz_params(lower)
        params["topic"] = extract_topic(text)
        return {"intent": "quiz", "params": params, "confidence": 0.95}
    
    if _PLAN_PAT.search(lower):
        return {"intent": "study_plan", "params": {"topic": extract_topic(text)}, "confidence": 0.95}

    if _TEACH_PAT.search(lower):
        topic = extract_topic(text)
        sub = "standard"
        if re.search(r'quick|brief|tldr|short|summary', lower): sub = "quick"
        elif re.search(r'deep|full|detail|thorough|complete', lower): sub = "deep"
        return {"intent": "teach", "params": {"topic": topic, "sub_intent": sub}, "confidence": 0.95}

    if _REVIEW_PAT.search(lower):
        code_match = re.search(r'```[\w]*\n?([\s\S]+?)```', text)
        code = code_match.group(1) if code_match else text
        return {"intent": "code_review", "params": {"code": code}, "confidence": 0.95}

    if _DEBUG_PAT.search(lower):
        return {"intent": "debug", "params": {"error": text}, "confidence": 0.95}

    # PDF Search check
    if _PDF_PAT.search(lower) and _SEARCH_PAT.search(lower):
        # Extract topic by removing search keywords
        topic = _SEARCH_PAT.sub('', lower).replace('pdf', '').replace('book', '').replace('paper', '').strip()
        if not topic: topic = lower
        return {"intent": "search_pdfs", "params": {"topic": topic.title()}, "confidence": 1.0}

    # Web Search check (if not map)
    if _SEARCH_PAT.search(lower) and not _MAP_PAT.search(lower):
        query = _SEARCH_PAT.sub('', lower).strip()
        if query:
            return {"intent": "search_web", "params": {"query": query}, "confidence": 1.0}

    # Best places / Pinning check
    if re.search(r'\b(best\s*places|tourist\s*spots|attractions|cafes|museums)\b', lower):
        city = "Rajshahi"
        query = "tourist attraction"
        found_city = _find_district(lower)
        if found_city:
            city = found_city
        # Extract query (e.g. "best cafes in Dhaka" -> query="cafes")
        m_query = re.search(r'\b(cafes|museums|parks|restaurants|hotels)\b', lower)
        if m_query: query = m_query.group(1)
        return {"intent": "pin_places", "params": {"city": city, "query": query}, "confidence": 1.0}

    # Weather check (before generic map)
    if _WEATHER_PAT.search(lower) and not _MAP_PAT.search(lower):
        city = "Rajshahi"
        found_city = _find_district(lower)
        if found_city:
            city = found_city
        return {"intent": "get_weather", "params": {"city": city}, "confidence": 1.0}

    # Map / Route check
    if _MAP_PAT.search(lower):
        city = "Rajshahi"
        dest = None
        m_route = re.search(r'from\s+([a-zA-Z\s]+?)\s+to\s+([a-zA-Z\s]+)', lower)
        if m_route:
            city = m_route.group(1).strip().title()
            dest = m_route.group(2).strip().title()
        else:
            found_city = _find_district(lower)
            if found_city:
                city = found_city

        # Extract numbered locations as custom pins
        custom_pins = []
        # Match: "1. Place Name" or "- Place Name" — skip short/garbage entries
        pin_pattern = re.findall(r'(?:\d+\.\s*|[-•]\s*)([A-Z][a-zA-Z0-9\s\'-]+?)(?:\s*[,\n]|$)', text)
        for p in pin_pattern[:10]:
            name = re.sub(r'\(.*?\)', '', p).strip().rstrip('.')
            # Skip if it's too short or looks like noise
            if len(name) < 4 or name.lower() in ('this', 'that', 'the', 'and', 'for', 'with', 'from'):
                continue
            custom_pins.append({"name": name})

        return {"intent": "create_map", "params": {"city": city, "destination": dest, "custom_pins": custom_pins}, "confidence": 1.0}

    # Bangla translator check
    if re.search(r'\b(bangla|bengali)\b', lower):
        return {"intent": "bangla_translator", "params": {}, "confidence": 1.0}

    # VPA check
    if re.search(r'\b(vpa|alexa|virtual\s+assistant)\b', lower):
        command = None
        # Try to extract command if after "alexa" or "vpa"
        m = re.search(r'(?:alexa|vpa)\s+(?:to\s+)?(.+)', lower)
        if m: command = m.group(1).strip()
        return {"intent": "vpa_assistant", "params": {"command": command}, "confidence": 1.0}

    # "use every tool" / "run all tools" → special batch intent
    if _ALL_PAT.search(lower):
        return {"intent": "run_all_tools", "params": {}, "confidence": 0.97}

    # Crypto BEFORE stock — so 'ethereum stock price' → crypto
    if _is_crypto_text(lower):
        return {"intent": "get_crypto_price",
                "params": {"coin": _extract_coin_from(lower)},
                "confidence": 0.97}

    if _STOCK_PAT.search(lower):
        company = _extract_company_from(text)   # pass original text, not lower
        if not company:
            return None   # hand off to qwen for clean extraction
        return {"intent": "get_stock_info",
                "params": {"company": company},
                "confidence": 0.97}

    # ── Math / Equation Plot ─────────────────────────────────────────────
    # Single preset name: "heart", "butterfly", "spiral curve"
    # Only match if text is short (direct command) OR has drawing-related keywords nearby
    preset_m = _MATH_PRESET_PAT.search(text)
    if preset_m and not _STOCK_PAT.search(text) and not _is_crypto_text(text.lower()):
        is_short = len(text.strip()) < 50
        has_verb = bool(re.search(r'\b(draw|plot|graph|show|math|cnc)\b', text, re.IGNORECASE))
        if is_short or has_verb:
            shape = preset_m.group(1).lower()
            return {"intent": "math_plot",
                    "params": {"expression": shape}, "confidence": 0.92}

    # Explicit tool reference: "mathplot", "use maths tool", "maths/mathplot.py"
    if _MATH_TOOL_PAT.search(text):
        # Try to extract shape after "mathplot" or "math tool"
        rest = _MATH_TOOL_PAT.sub('', text).strip()
        after = rest.split(',')[0].strip().split()[-1] if rest.split() else "heart"
        # If the extracted word is a preset, use it; otherwise pass the whole expression
        m2 = _MATH_PRESET_PAT.search(after)
        shape = m2.group(1).lower() if m2 else after
        return {"intent": "math_plot",
                "params": {"expression": shape}, "confidence": 0.94}

    # Math expression: "y = x^2", "x = r*cos(t)", "r = a*theta"
    if _MATH_EXPR_PAT.search(text):
        expr = text.strip()
        return {"intent": "math_plot",
                "params": {"expression": expr}, "confidence": 0.90}

    # "draw heart", "plot butterfly", "graph y = x^2", "show me a cardioid"
    math_m = _MATH_PLOT_PAT.search(text)
    if math_m:
        expr = math_m.group(2).strip()
        # Multi-preset: "draw heart, butterfly, and spiral"
        if re.search(r',|\band\b', expr) or (
            len(expr.split()) >= 3
            and not any(c in expr for c in "=^+-*/()")
        ):
            return {"intent": "run_sequence",
                    "params": {"commands": expr}, "confidence": 0.92}
        return {"intent": "math_plot", "params": {"expression": expr}, "confidence": 0.92}

    # Bare ticker like "TSLA", "AAPL price", "how is NVDA doing" —
    # no "stock" keyword required if we recognise the symbol.
    # Only match when NOT asking for a math plot (checked above).
    ticker = _extract_ticker_from(text)
    if ticker and not _MATH_PLOT_PAT.search(text):
        return {"intent": "get_stock_info",
                "params": {"company": ticker},
                "confidence": 0.95}

    if _ALARM_PAT.search(lower):
        return {"intent": "set_alarm",
                "params": {"time": _extract_time_from(lower)},
                "confidence": 0.97}

    if _TIMER_PAT.search(lower):
        return {"intent": "set_timer",
                "params": {"duration": _extract_duration_from(lower)},
                "confidence": 0.97}

    if _NEWS_PAT.search(lower):
        return {"intent": "open_news", "params": {}, "confidence": 0.97}

    if _EMAIL_PAT.search(lower):
        return {"intent": "send_email", "params": {}, "confidence": 0.97}

    if _TTT_PAT.search(lower):
        return {"intent": "play_tictactoe", "params": {}, "confidence": 0.97}

    if _C4_PAT.search(lower):
        mode = "two" if re.search(r'\b(two|2|friend|player)\b', lower) else "computer"
        return {"intent": "play_connect4", "params": {"mode": mode}, "confidence": 0.97}

    if _WORD_PAT.search(lower):
        return {"intent": "play_wordgame", "params": {}, "confidence": 0.97}

    if _DRAW_PAT.search(lower):
        return {"intent": "draw_me", "params": {}, "confidence": 0.97}

    if _SHOT_PAT.search(lower):
        return {"intent": "take_screenshot", "params": {}, "confidence": 0.97}

    # ── "EXECUTING <command>" — high-priority command trigger ─────────────
    exec_m = _EXECUTING_PAT.search(text)
    if exec_m:
        cmd = exec_m.group(1).strip().strip('`"\'')
        alias = cmd.lower().rstrip('.py').rstrip('.sh')
        if alias in _KNOWN_SCRIPTS:
            cmd = _KNOWN_SCRIPTS[alias]
        elif '/' in alias:
            base = alias.rsplit('/', 1)[-1]
            if base in _KNOWN_SCRIPTS:
                cmd = _KNOWN_SCRIPTS[base]
        else:
            first = cmd.split()[0].lstrip('./')
            if not _CMD_ALLOW.match(first):
                return {"intent": "normal", "params": {}, "confidence": 0.6}
        return {"intent": "run_command", "params": {"command": cmd}, "confidence": 0.96}

    # ── Known script alias with run/launch/execute trigger ───────────────
    for alias, full_cmd in _KNOWN_SCRIPTS.items():
        if re.search(
            rf'\b(?:run|start|launch|open|execute)\s+(?:the\s+)?'
            rf'{re.escape(alias)}(?:\s+(?:script|file))?(?:\s*$|[.!?,;])',
            text, re.IGNORECASE
        ):
            return {"intent": "run_command", "params": {"command": full_cmd}, "confidence": 0.94}

    # ── Command: explicit "run X" / "execute X" ──────────────────────────
    run_m = _RUN_PAT.search(text)
    if run_m:
        cmd = run_m.group(1).strip().strip('`')
        return {"intent": "run_command", "params": {"command": cmd}, "confidence": 0.92}

    # ── Command: "can you X / could you / please X" where X is a known command ──
    can_m = _CAN_YOU_RUN_PAT.search(text)
    if can_m:
        phrase = can_m.group(1).strip().strip('`')
        first_word = phrase.split()[0].lower().lstrip('./')
        if _CMD_ALLOW.match(first_word):
            return {"intent": "run_command", "params": {"command": phrase}, "confidence": 0.88}

    # ── Bare command: text starts with a known allowlisted command ─────────────
    bare = text.strip()
    if bare:
        first = bare.split()[0].lstrip('./')
        if _CMD_ALLOW.match(first):
            # Only for short/command-like messages (skip long conversational text that happens to start with a command word)
            if len(bare) < 120 and not re.search(r'[?.!]\s*$', bare):
                return {"intent": "run_command", "params": {"command": bare}, "confidence": 0.85}

    return None


# ══════════════════════════════════════════════════════════════════════════════
# TOOL EXECUTOR — called by marin.py after classify() returns a tool intent
# ══════════════════════════════════════════════════════════════════════════════

async def execute_tool(intent: str, params: dict, agent_name: str = "marin") -> str | None:
    """
    Run the StructuredTool for the given intent.
    Returns the tool's context string (what it did), or None if not a tool.
    marin.py injects this context into Marin's LLM prompt.
    """
    import datetime
    if intent not in _TOOL_MAP:
        return None
    try:
        # Pass agent_name if the tool supports it (like manage_vault)
        if intent == "manage_vault":
            from tools.vault_manager import manage_vault
            result = f"Vault [{agent_name}] {params.get('action')} result: {json.dumps(manage_vault(agent_name, **params), indent=2)}"
        else:
            # Use asyncio.to_thread for synchronous tool functions to keep the loop running
            result = await asyncio.to_thread(_TOOL_MAP[intent].invoke, params)
            
        # Log tool execution to cmd_log so terminal panel shows it
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        param_str = json.dumps(params)
        _cmd_log.append({
            "cmd": f"[{agent_name}][tool:{intent}] {param_str}",
            "allowed": True,
            "output": (result or "(done)")[:500],
            "ts": ts,
        })
        if len(_cmd_log) > 100:
            _cmd_log.pop(0)
        return result
    except Exception as e:
        return f"Tool {intent} failed: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# VIBE DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

def _detect_vibe(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ["love","miss","cute","hug","kiss","mwah","sweetheart","ummaah"]):
        return "lovely"
    if any(w in lower for w in ["tease","hehe","playful","naughty"]):
        return "flirty"
    if any(w in lower for w in ["hate","mad","angry","fuck","ugh","damn"]):
        return "angry"
    if any(w in lower for w in ["sad","cry","lonely","down","depressed"]):
        return "sad"
    if any(w in lower for w in ["excited","omg","yay","wow","!!!"]):
        return "excited"
    return "neutral"


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

_KNOWN_TOOLS = set(_TOOL_MAP.keys()) | {"run_all_tools"}

def classify(text: str, agent_name: str = "marin") -> dict:
    """
    Single-stage regex classification.
    Returns: {intent, params, user_vibe, confidence, _tool_ack}
    """
    # Regex stage (instant, no model call)
    result = _regex_stage(text)

    # Fallback to chat
    if result is None:
        result = {"intent": "chat", "params": {}, "confidence": 0.80}

    # Unknown intent → chat
    if result["intent"] not in _KNOWN_TOOLS:
        result["intent"] = "chat"

    result["user_vibe"] = _detect_vibe(text)
    result["_tool_ack"] = None

    print(f"[{agent_name}][marin_fier] intent={result['intent']}  "
          f"params={result['params']}  "
          f"vibe={result['user_vibe']}  "
          f"conf={result['confidence']:.2f}")
    return result