#!/usr/bin/env python3
"""
langgraph_agent.py — Marin Cognitive Architecture (LangGraph)
4-node cyclic graph: Strategist → Executor → Auditor (fail loop) → Persona → output
"""

import os
import sys
import json
import asyncio
import re
from typing import TypedDict, Annotated, Sequence, Optional, List
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, END
from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
)
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
import subprocess

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import (
    DEFAULT_MODEL, OLLAMA_BASE_URL, OPENROUTER_BASE_URL, 
    OPENROUTER_API_KEY, LOCAL_MODELS, PORT, 
    classify_task, get_model_for_task, get_api_key
)
from utils.shared_logic import USER_CONTEXT

def get_llm(model_name: str, bind_tools: list = None):
    """Factory to create the right LLM instance based on model name."""
    # Check if it's a local model
    is_local = model_name in LOCAL_MODELS or ":" in model_name and "/" not in model_name
    
    if is_local:
        llm = ChatOllama(model=model_name, base_url=OLLAMA_BASE_URL)
    else:
        # OpenRouter / Cloud
        api_key = get_api_key("openrouter") or OPENROUTER_API_KEY
        llm = ChatOpenAI(
            model=model_name,
            openai_api_key=api_key,
            openai_api_base=OPENROUTER_BASE_URL,
            default_headers={"HTTP-Referer": "https://github.com/bayazid", "X-Title": "Marin HS-02"}
        )
    
    if bind_tools:
        return llm.bind_tools(bind_tools)
    return llm


def _infer_emotional_state(history: list) -> str:
    """
    Marin's 5-7 day cycle mapped to tone.
    In practice, read from vault or a simple day-of-week heuristic.
    """
    try:
        from tools.vault_manager import read_vault_key
        state = read_vault_key("emotional_state")
        if state in ("neutral", "energetic", "focused", "low"):
            return state
    except Exception:
        pass
    # Fallback: derive from conversation energy
    if len(history) > 10:
        return "focused"
    return "neutral"

# ── Helper for background tools ──────────────────────────────────────────────

def _popen(script: str, args: List[str] = [], timeout: int = None):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, script)
    if not os.path.exists(path):
        return f"Script not found: {script}"
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")
    try:
        subprocess.Popen(
            [sys.executable, path] + args,
            start_new_session=True, cwd=base_dir, env=env,
        )
        return None
    except Exception as e:
        return f"Failed to launch {script}: {e}"

# ── Tool Definitions ─────────────────────────────────────────────────────────

@tool
def alarm_tool(time: str) -> str:
    """Set an alarm for a specific time (e.g., '07:30', '14:00')."""
    err = _popen("tools/alarm.py", [time])
    if err: return err
    return f"Alarm set for {time}. It will beep when it fires."

@tool
def timer_tool(duration: str) -> str:
    """Start a countdown timer (e.g., '10m', '1h', '30s')."""
    err = _popen("tools/timer.py", [duration])
    if err: return err
    return f"Timer started for {duration}."

@tool
def math_plot_tool(expression: str) -> str:
    """Launch the math equation plotter to draw parametric curves or functions.
    Examples: 'heart', 'infinity', 'sin(t)*exp(t)', 'x=cos(t), y=sin(t)'.
    """
    err = _popen("maths/mathplot.py", [expression])
    if err: return err
    return f"Math plotter launched for: '{expression}'."

@tool
def map_tool(city: str = "Dhaka", destination: str = None) -> str:
    """Create and open an interactive map of a city, optionally with a route to a destination."""
    try:
        from tools.knowledge_hub import create_integrated_hub_map
        res = create_integrated_hub_map(city, destination)
        map_url = res.get("map_url", "/static/generated/knowledge_hub_map.html")
        full_url = f"http://localhost:{PORT}{map_url}"
        subprocess.Popen(["xdg-open", full_url])
        return f"Map for {city} opened in browser."
    except Exception as e:
        return f"Error creating map: {e}"

@tool
def news_tool() -> str:
    """Fetch and display the latest news or open the news harvester."""
    try:
        from database import get_latest_news
        items = get_latest_news(limit=5)
        if items:
            lines = ["📰 **LATEST NEWS**\n"]
            for i, item in enumerate(items, 1):
                lines.append(f"**{i}. {item['title']}**")
                analysis = (item.get("analysis") or "").split("\n")[0]
                if analysis: lines.append(f"   _{analysis}_")
            return "\n".join(lines)
    except Exception:
        pass
    _popen("tools/news.py")
    return "Opening news harvester..."

@tool
def weather_tool(city: str = "Dhaka") -> str:
    """Get the current weather for a city."""
    try:
        from tools.knowledge_hub import get_weather_data
        data = get_weather_data(city)
        if "error" in data: return data["error"]
        return f"Weather in {data['city']}: {data['temperature']}°C, {data['humidity']}% humidity."
    except Exception as e:
        return f"Error getting weather: {e}"

@tool
def stock_tool(symbol: str) -> str:
    """Get real-time stock price and info for a given ticker symbol (e.g., 'AAPL', 'TSLA')."""
    from tools.stock_data import fetch_stock_price
    try:
        data = fetch_stock_price(symbol)
        _popen("tools/stock.py", ["--ticker", symbol.upper()])
        return data
    except Exception as e:
        return f"Error: {e}"

@tool
def crypto_tool(coin: str) -> str:
    """Get current price for a cryptocurrency (e.g., 'bitcoin', 'ethereum')."""
    from tools.crypto_data import fetch_crypto_price
    try:
        data = fetch_crypto_price(coin)
        _popen("tools/crypto.py", ["--coin", coin.lower()])
        return data
    except Exception as e:
        return f"Error: {e}"

@tool
def screenshot_tool() -> str:
    """Capture a screenshot of the current screen."""
    err = _popen("tools/image.py")
    if err: return err
    return "Screenshot captured."

@tool
def terminal_tool(command: str) -> str:
    """Execute a safe shell command inside Marin's sandbox. Use this for testing code or exploring the system."""
    from utils.command_runner import run_command
    from marin_fier import is_cmd_allowed
    
    # We still check the allowlist for general safety, even in docker
    allowed, reason = is_cmd_allowed(command)
    if not allowed:
        return f"Blocked: {reason}"
    
    code, output = run_command(command, timeout=30)
    return f"Exit Code: {code}\nOutput:\n{output}"

@tool
def pdf_download_tool(query: str) -> str:
    """Search for and download a PDF book or document. Saves to unique/download/ vault.
    
    Args:
        query: The name of the book or document to search for.
    """
    from tools.pdf_downloader_marin import marin_search_and_download
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    download_dir = os.path.join(base_dir, "unique", "download")
    
    print(f"[Agent] Triggering Marin PDF download for: {query}")
    path = marin_search_and_download(query, download_dir)
    
    if path:
        return f"Successfully downloaded the book! I've placed it in your vault here: {path}"
    else:
        return f"I found some links for '{query}', but I couldn't get a valid PDF file from them. They might be protected or not direct links. Want me to try a different search term?"

@tool
def app_launch(app_name: str) -> str:
    """Launch an installed app by name. Use this instead of classifier to open apps.
    
    Available apps: swordfish, brave, chromium, zen, alacritty, ghostty, code, obsidian,
    geany, vim, files, mpv, blender, feh, pavucontrol, record, okular, zathura, btop,
    htop, gparted, vpn, shot.
    
    Args:
        app_name: Name of the app to launch (e.g., 'code', 'brave', 'obsidian', 'mpv').
    """
    from tools.app_launcher import APPS, is_available, launch
    key = app_name.lower().strip()
    if key not in APPS:
        matches = [k for k in APPS if key in k]
        if matches:
            return f"Unknown app '{key}'. Did you mean: {', '.join(matches)}?"
        return f"Unknown app '{key}'. Available: {', '.join(APPS.keys())}"
    _, cmd = APPS[key]
    if not is_available(cmd):
        return f"'{cmd.split()[0]}' is not installed on this system."
    launch(cmd)
    return f"Launched {APPS[key][0]} ({key})."

@tool
def app_list() -> str:
    """List all available apps that can be launched."""
    from tools.app_launcher import APPS, CATEGORIES, is_available
    lines = ["📱 Available apps:\n"]
    for cat, keys in CATEGORIES.items():
        lines.append(f"  {cat}")
        for key in keys:
            desc, cmd = APPS[key]
            avail = "●" if is_available(cmd) else "○"
            lines.append(f"    {avail} {key} — {desc}")
        lines.append("")
    return "\n".join(lines)

@tool
def swordwatch_inspect(target: str) -> str:
    """Deep inspect a running process by name or PID. Shows CPU, memory, threads, children, open files, network connections.
    
    Args:
        target: Process name (e.g., 'firefox') or PID number (e.g., '1234').
    """
    import time as _time
    from tools.swordwatch import find_procs, get_cmdline, get_threads, get_children, get_open_files, get_connections, fmt_bytes, fmt_uptime
    import psutil

    matches = find_procs(target)
    if not matches:
        return f"No process matching '{target}'."

    proc = matches[0]
    try:
        with proc.oneshot():
            pid     = proc.pid
            name    = proc.name()
            status  = proc.status()
            uptime  = _time.time() - proc.create_time()
            cpu_p   = proc.cpu_percent(interval=0.3)
            mem     = proc.memory_info()
            mem_p   = proc.memory_percent()
            thr     = get_threads(proc)
            cmd     = get_cmdline(proc)
            try: user = proc.username()
            except: user = "—"

        files = get_open_files(proc)
        conns = get_connections(proc)
        kids  = get_children(proc)
    except psutil.NoSuchProcess:
        return f"Process '{target}' disappeared during inspection."

    lines = [
        f"🔍 {name} (pid {pid})",
        f"  Status: {status} | User: {user}",
        f"  CPU: {cpu_p:.1f}% | Memory: {mem_p:.1f}% ({fmt_bytes(mem.rss)})",
        f"  Threads: {thr} | Uptime: {fmt_uptime(uptime)}",
        f"  Command: {cmd[:120]}",
    ]
    if kids:
        lines.append(f"  Children: {len(kids)} ({', '.join(k.name() for k in kids[:5])})")
    if files:
        lines.append(f"  Open files: {len(files)}")
    if conns:
        lines.append(f"  Network: {len(conns)} connections")
    return "\n".join(lines)

@tool
def swordwatch_kill(target: str, force: bool = False) -> str:
    """Kill a process by name or PID. Sends SIGTERM by default, SIGKILL if force=True.
    
    Args:
        target: Process name (e.g., 'firefox') or PID number.
        force: If True, sends SIGKILL (instant, no cleanup). If False, sends SIGTERM (graceful).
    """
    import signal as _signal
    from tools.swordwatch import find_procs
    import psutil

    matches = find_procs(target)
    if not matches:
        return f"No process matching '{target}'."

    sig = _signal.SIGKILL if force else _signal.SIGTERM
    sig_name = "SIGKILL" if force else "SIGTERM"
    results = []

    for p in matches:
        try:
            name = p.name()
            pid = p.pid
            p.send_signal(sig)
            results.append(f"✓ {sig_name} → {name} (pid {pid})")
        except psutil.NoSuchProcess:
            results.append(f"pid {p.pid} already gone")
        except psutil.AccessDenied:
            results.append(f"✗ pid {p.pid} access denied (try sudo)")

    return "\n".join(results)

@tool
def msg_telegram(message: str) -> str:
    """Send a message to the operator via Telegram.
    
    Args:
        message: The message text to send (supports Markdown formatting).
    """
    from tools.msg_telegram import send
    ok = send(message)
    return f"Message sent to Telegram." if ok else "Failed to send Telegram message."

@tool
def email_send(to: str, subject: str, body: str = "", attachment_path: str = "") -> str:
    """Send an email via Gmail. Can attach a .txt or .tex file.
    
    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain text body (optional if attachment provided).
        attachment_path: Full path to .txt or .tex file to attach (optional).
    """
    from tools.email_sender import send_email
    return send_email(to, subject, body, attachment_path)

@tool
def habit_add(title: str, category: str = "general", priority: str = "medium", remind_daily: bool = False) -> str:
    """Add a new task/habit to track. Set remind_daily=True for tasks Marin should remind you about every day via Telegram.
    
    Args:
        title: What the task is (e.g., 'Study math', 'Exercise 30min').
        category: Group (e.g., 'study', 'health', 'work').
        priority: low / medium / high.
        remind_daily: If True, Marin will remind you every day until it's done.
    """
    from tools.habit_store import add_task
    task = add_task(title, category, priority, remind_daily)
    remind = " (daily reminder ON)" if remind_daily else ""
    return f"Task #{task['id']} added: '{title}' [{priority}] in {category}{remind}"

@tool
def habit_complete(task_id: int) -> str:
    """Mark a task as done.
    
    Args:
        task_id: The task number to complete.
    """
    from tools.habit_store import complete_task
    return complete_task(task_id)

@tool
def habit_list(status: str = "", category: str = "") -> str:
    """List tasks. Filter by status ('todo', 'done', 'in-progress') or category.
    
    Args:
        status: Filter by status (optional).
        category: Filter by category (optional).
    """
    from tools.habit_store import list_tasks
    tasks = list_tasks(status=status or None, category=category or None)
    if not tasks:
        return "No tasks found."
    lines = []
    for t in tasks[:15]:
        icon = {"done": "✅", "in-progress": "🔄", "todo": "⏳"}.get(t["status"], "⏳")
        remind = " 🔔" if t["remind_daily"] else ""
        lines.append(f"#{t['id']} {icon} [{t['priority']}] {t['title']} ({t['category']}){remind}")
    return "\n".join(lines)

@tool
def habit_stats() -> str:
    """Get habit tracker overview — completion rates, pending tasks by priority."""
    from tools.habit_store import get_stats
    s = get_stats()
    lines = [
        f"📊 Tasks: {s['total']} total | ✅ {s['done']} done | ⏳ {s['todo']} todo | 🔄 {s['in_progress']} active"
    ]
    for c in s["categories"]:
        pct = round(c["done"] / c["total"] * 100) if c["total"] else 0
        lines.append(f"  {c['category']}: {c['done']}/{c['total']} ({pct}%)")
    if s["pending_by_priority"]:
        lines.append(f"  Pending: {s['pending_by_priority']}")
    return "\n".join(lines)

@tool
def habit_today() -> str:
    """Get today's pending daily reminders — tasks you set to remind every day."""
    from tools.habit_store import get_reminders_for_today
    tasks = get_reminders_for_today()
    if not tasks:
        return "No pending daily reminders today. You're all caught up!"
    lines = ["🔔 Today's reminders:"]
    for t in tasks:
        pri = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t["priority"], "⚪")
        lines.append(f"  {pri} #{t['id']} {t['title']} ({t['category']})")
    return "\n".join(lines)

@tool
def habit_delete(task_id: int) -> str:
    """Delete a task permanently.
    
    Args:
        task_id: The task number to delete.
    """
    from tools.habit_store import delete_task
    return delete_task(task_id)

@tool
def vault_access(category: str = "misc", query: str = "") -> str:
    """Search or read from Marin's persistent vault storage. Use category and query to find stored notes, memories, or data."""
    from tools.vault_manager import manage_vault
    try:
        result = manage_vault("marin", "list", category=category)
        if query:
            filtered = [r for r in result if query.lower() in str(r).lower()]
            return json.dumps(filtered[:10]) if filtered else f"No vault entries matching '{query}'"
        return json.dumps(result[:10]) if result else "Vault is empty for this category."
    except Exception as e:
        return f"Vault error: {e}"

@tool
def rag_search(query: str) -> str:
    """Search the RAG knowledge base for context related to the query."""
    import asyncio as _aio
    from utils.agent_logic import get_rag_context
    try:
        loop = _aio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(_aio.run, get_rag_context(query, enabled=True)).result()
        else:
            result = _aio.run(get_rag_context(query, enabled=True))
        return result or "No relevant context found in knowledge base."
    except Exception as e:
        return f"RAG search error: {e}"

@tool
def generate_image_tool(prompt: str) -> str:
    """Generate an AI image based on a text prompt.
    Use this when the user wants to see a picture, drawing, or visualization.
    """
    from config import IMAGE_MODELS, get_api_key, OPENROUTER_BASE_URL
    import requests
    import os
    import time
    
    api_key = get_api_key("openrouter")
    if not api_key:
        return "I need an OpenRouter API key to generate images for you, Limon."
        
    model = IMAGE_MODELS["primary"]
    print(f"[Agent] Generating image with {model}: {prompt}")
    
    try:
        # OpenRouter Image Generation API
        url = f"{OPENROUTER_BASE_URL.replace('/chat/completions', '')}/images/generations"
        if "/api/v1" not in url: url = "https://openrouter.ai/api/v1/images/generations"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/bayazid",
            "X-Title": "Marin HS-02",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "prompt": prompt,
            "response_format": "url"
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        data = response.json()
        
        if "data" in data and len(data["data"]) > 0:
            image_url = data["data"][0]["url"]
            
            # Download to local static/generated folder
            gen_dir = "static/generated"
            os.makedirs(gen_dir, exist_ok=True)
            filename = f"gen_{int(time.time())}.png"
            local_path = os.path.join(gen_dir, filename)
            
            img_data = requests.get(image_url).content
            with open(local_path, "wb") as f:
                f.write(img_data)
                
            return f"Successfully generated image for '{prompt}'. File saved at: {local_path}. Displaying now."
        else:
            error_msg = data.get("error", {}).get("message", "Unknown API error")
            return f"Image generation failed: {error_msg}. Falling back to moondream logic."
            
    except Exception as e:
        return f"Image generation error: {e}."

@tool
def file_tool(action: str, path: str, content: str = "") -> str:
    """Manage files on the system. Use this to create, read, or update code and notes.
    
    Actions:
        - 'write': Overwrite or create a file with content.
        - 'append': Add content to the end of a file.
        - 'read': Read the content of a file.
        - 'delete': Remove a file.
        
    Args:
        action: 'write', 'append', 'read', or 'delete'.
        path: Path to the file (relative to project root).
        content: The text content to write or append.
    """
    from marin_fier import is_cmd_allowed
    # Basic safety check: don't allow writing to sensitive files
    blocked_paths = [".env", "config.py", "database.py", "privilege_manager.py"]
    if any(p in path for p in blocked_paths):
        return f"Access denied: {path} is a protected system file."

    full_path = Path(path).resolve()
    base_dir = Path(os.path.dirname(os.path.abspath(__file__))).resolve()
    
    # Ensure the path is within the project directory or allowed subdirs
    if not str(full_path).startswith(str(base_dir)):
         # Allow writing to home-relative paths if they are in allowed areas
         if not str(full_path).startswith(os.path.expanduser("~")):
             return f"Access denied: {path} is outside the allowed workspace."

    try:
        if action == "write":
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully wrote to {path}."
        elif action == "append":
            with open(full_path, "a", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully appended to {path}."
        elif action == "read":
            if not full_path.exists(): return f"File not found: {path}"
            with open(full_path, "r", encoding="utf-8") as f:
                return f"Content of {path}:\n{f.read()}"
        elif action == "delete":
            if not full_path.exists(): return f"File not found: {path}"
            os.remove(full_path)
            return f"Successfully deleted {path}."
        else:
            return f"Invalid action: {action}"
    except Exception as e:
        return f"File error: {e}"

# ── New Powerful Tools ───────────────────────────────────────────────────────

@tool
def stealth_browse_tool(query: str) -> str:
    """Perform a stealthy, untraceable web search using Camoufox. 
    Use this for deep research, finding documentation, or latest tech news.
    """
    from tools.stealth_browser import stealth_search
    return stealth_search(query)

@tool
def forensics_tool(action: str = "report") -> str:
    """Perform autonomous system forensics. 
    Actions: 
        - 'report': Full system health and security overview.
        - 'detect': Scan for suspicious high-resource processes.
        - 'clear': Kill all non-essential high-CPU tasks (requires confirmation).
    """
    import psutil
    
    if action == "report":
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        return f"🛡️ Sentinel Report: CPU: {cpu}% | MEM: {mem}% | Disk: {disk}%\nSystem status: OPTIMAL."
    
    elif action == "detect":
        procs = sorted(psutil.process_iter(['pid', 'name', 'cpu_percent']), 
                       key=lambda x: x.info['cpu_percent'], reverse=True)[:5]
        lines = ["⚠️ High-Resource Processes:"]
        for p in procs:
            lines.append(f"  - {p.info['name']} (PID: {p.info['pid']}): {p.info['cpu_percent']}% CPU")
        return "\n".join(lines)
    
    return f"Forensics action '{action}' completed."

@tool
def psychology_vault_tool(action: str, data: str = "") -> str:
    """Master's Psychology & Learning Vault. 
    Track Limon's progress and suggest books from his 60+ technical library.
    
    Actions:
        - 'log_progress': Save a note about what the master is learning or struggling with.
        - 'suggest_book': Get a book recommendation based on current project/struggle.
        - 'status': Review the master's recent mental/coding state.
    """
    from tools.vault_manager import manage_vault
    
    if action == "log_progress":
        manage_vault("marin", "write", filename="learning_progress.log", content=data, category="psychology")
        return "Logged your progress in my private vault, Limon. I'm watching you grow. ❤️"
    
    elif action == "suggest_book":
        # Heuristic: match keywords to her 60+ book library
        library = [
            "Numerical Methods for Engineers", "Control Systems Engineering", 
            "Embedded Systems with ESP32", "Deep Learning with Python",
            "The Linux Command Line", "Robotics: Modelling, Planning and Control"
        ]
        return f"Based on your current work, I suggest you review: '{library[0]}' or '{library[2]}'. They are in your shelf."
        
    return "Psychology vault synchronized."

@tool
def model_tool(action: str, model_name: str = "") -> str:
    """Manage AI models on the system. Use this to switch your own brain or list available ones.
    
    Actions:
        - 'list': Show all installed Ollama models.
        - 'pull': Download a new model (takes time).
        - 'switch': Change the 'DEFAULT_MODEL' in settings.json.
        - 'current': Show currently active model.
        
    Args:
        action: 'list', 'pull', 'switch', or 'current'.
        model_name: The name of the model (e.g., 'llama3.1', 'mistral').
    """
    import json
    from config import SETTINGS_PATH
    from utils.command_runner import run_command
    
    try:
        if action == "list":
            code, out = run_command("ollama list")
            return f"Installed Models:\n{out}"
        elif action == "pull":
            if not model_name: return "Specify a model name to pull."
            # Run in background via popen since it takes a while
            _popen("terminal_tool", ["ollama pull " + model_name])
            return f"Triggered pull for {model_name}. I'll let you know when it's ready!"
        elif action == "current":
            from config import DEFAULT_MODEL
            return f"My current main model is: {DEFAULT_MODEL}"
        elif action == "switch":
            if not model_name: return "Specify a model name to switch to."
            
            # Update settings.json
            settings = {}
            if os.path.exists(SETTINGS_PATH):
                with open(SETTINGS_PATH, "r") as f:
                    settings = json.load(f)
            
            if "models" not in settings: settings["models"] = {}
            settings["models"]["default"] = model_name
            
            with open(SETTINGS_PATH, "w") as f:
                json.dump(settings, f, indent=4)
            
            return f"System updated. I am now using {model_name} as my default brain! 🧠✨"
        return f"Unknown model action: {action}"
    except Exception as e:
        return f"Model error: {e}"

@tool
def docker_tool(action: str, container: str = "", image: str = "", command: str = "") -> str:
    """Orchestrate the Docker kingdom using the Docker SDK.
    
    Actions:
        - 'ps': List running containers.
        - 'all': List all containers.
        - 'start': Start a container.
        - 'stop': Stop a container.
        - 'restart': Reboot a container.
        - 'remove': Delete a container.
        - 'pull': Download an image.
        - 'create': Spin up a new container (requires image).
        - 'exec': Run a command inside a container (requires command).
        - 'compose_up': Start a compose stack.
        - 'compose_down': Stop a compose stack.
        - 'stats': Show resource usage.
        - 'logs': Show container logs.
        
    Args:
        action: 'ps', 'all', 'start', 'stop', 'restart', 'remove', 'pull', 'create', 'exec', 'compose_up', 'compose_down', 'stats', or 'logs'.
        container: Name or ID of the container.
        image: Docker image name (for 'create' or 'pull').
        command: Command to run (for 'exec').
    """
    from tools.docker_orchestrator import orchestrator
    import json
    
    try:
        if action == "ps":
            return json.dumps(orchestrator.list_containers(all=False), indent=2)
        elif action == "all":
            return json.dumps(orchestrator.list_containers(all=True), indent=2)
        elif action == "start" and container:
            return orchestrator.start_container(container)
        elif action == "stop" and container:
            return orchestrator.stop_container(container)
        elif action == "restart" and container:
            return orchestrator.restart_container(container)
        elif action == "remove" and container:
            return orchestrator.remove_container(container)
        elif action == "pull" and image:
            return orchestrator.pull_image(image)
        elif action == "create" and image:
            return orchestrator.create_container(image, container or None)
        elif action == "exec" and container and command:
            return orchestrator.exec_run(container, command)
        elif action == "compose_up":
            return orchestrator.compose_action("up")
        elif action == "compose_down":
            return orchestrator.compose_action("down")
        elif action == "stats" and container:
            return orchestrator.get_stats(container)
        elif action == "logs" and container:
            return orchestrator.get_logs(container)
        else:
            return f"Invalid action or missing required parameters for action: {action}"
    except Exception as e:
        return f"Docker orchestrator error: {e}"

@tool
def binance_tool(action: str, symbol: str = "BTCUSDT", amount: float = None, price: float = None, user_id: str = "USR-MASTER") -> str:
    """Execute trades or check balances on Binance.
    
    Actions:
        - 'balance': Show asset balances.
        - 'price': Show current price of a symbol.
        - 'buy': Buy an asset (Market or Limit if price is set).
        - 'sell': Sell an asset.
        - 'portfolio': Show overall portfolio and recent trades.
        - 'history': Show trade history for a symbol.
        
    Args:
        action: 'balance', 'price', 'buy', 'sell', 'portfolio', or 'history'.
        symbol: e.g., 'BTCUSDT', 'ETHUSDT'.
        amount: Quantity to trade.
        price: Optional limit price.
        user_id: The ID of the user performing the trade.
    """
    from tools.binance_client import BinanceManager
    from tools.portfolio_tracker import PortfolioTracker
    
    try:
        if action == "portfolio":
            tracker = PortfolioTracker(user_id)
            return tracker.format_summary()
        
        mgr = BinanceManager(user_id)
        if action == "balance":
            return str(mgr.get_balance())
        elif action == "price":
            return str(mgr.get_symbol_price(symbol))
        elif action == "buy":
            if not amount: return "Specify amount to buy."
            return str(mgr.execute_trade(symbol, "buy", amount, price))
        elif action == "sell":
            if not amount: return "Specify amount to sell."
            return str(mgr.execute_trade(symbol, "sell", amount, price))
        elif action == "history":
            return str(mgr.get_history(symbol))
            
        return f"Unknown binance action: {action}"
    except Exception as e:
        return f"Binance error: {e}"

@tool
def batch_convert_tool(directory: str, action: str = "pdf") -> str:
    """Convert multiple files in a directory.
    
    Args:
        directory: Path to the folder.
        action: 'pdf' (convert all docx/xlsx to pdf) or 'text' (extract text from all pdfs).
    """
    from tools.batch_converter import batch_convert_to_pdf, batch_extract_text
    try:
        if action == "text":
            res = batch_extract_text(directory)
            return f"Processed {len(res['extracted'])} PDFs. Extracted text to .txt files."
        else:
            res = batch_convert_to_pdf(directory)
            return f"Successfully converted {len(res['converted'])} files to PDF."
    except Exception as e:
        return f"Batch tool error: {e}"

@tool
def learn_topic_tool(topic: str, user_id: str = "USR-MASTER", session_id: str = "default") -> str:
    """The 'God-Tier' learning sequence. 
    Searches for books, downloads them, creates a study plan, and indexes the material.
    
    Args:
        topic: The subject you want to master (e.g., 'Numerical Methods').
        user_id: ID of the user (injected automatically).
        session_id: Current conversation thread ID (injected automatically).
    """
    from tools.learn_workflow import execute_learn_workflow
    import asyncio
    try:
        # Since this is an async tool call in a sync environment
        return asyncio.run(execute_learn_workflow(topic, user_id, session_id))
    except Exception as e:
        return f"Learning workflow error: {e}"

@tool
def research_paper_tool(query: str, action: str = "search", paper_url: str = None, title: str = None) -> str:
    """Search or download research papers from arXiv.
    
    Args:
        query: Search term for the paper.
        action: 'search' or 'download' (requires paper_url and title).
        paper_url: The URL to download from.
        title: The paper title for filename.
    """
    from tools.research_paper import search_arxiv, download_paper
    try:
        if action == "download" and paper_url and title:
            res = download_paper(paper_url, title)
            if res["ok"]:
                return f"Successfully downloaded paper: {title}. File: {res['filename']} in static/downloads/"
            else:
                return f"Download failed: {res['error']}"
        else:
            results = search_arxiv(query)
            if not results: return f"No research papers found for '{query}'."
            
            lines = [f"Found research papers for '{query}':"]
            for p in results:
                lines.append(f"- {p['title']} | [PDF]({p['download_url']})")
            return "\n".join(lines)
    except Exception as e:
        return f"Research tool error: {e}"

@tool
def study_engine_tool(topic: str, action: str = "plan", level: str = "beginner") -> str:
    """Create roadmaps, learning plans, or quizzes on any topic.
    
    Args:
        topic: The subject to learn or be tested on.
        action: 'plan' (for a roadmap) or 'quiz' (for testing).
        level: 'beginner', 'intermediate', or 'advanced'.
    """
    from tools.study_engine import create_study_plan, generate_quiz
    try:
        if action == "quiz":
            res = generate_quiz(topic)
            if res["ok"]:
                q_list = [f"Quiz for {topic}:"]
                for q in res["quiz"]["questions"]:
                    q_list.append(f"{q['id']}. {q['question']}")
                    q_list.append(f"   Options: {', '.join(q['options'])}")
                return "\n".join(q_list)
        else:
            res = create_study_plan(topic, level)
            if res["ok"]:
                p = res["plan"]
                lines = [f"Study Plan for {topic} ({level}):"]
                for phase in p["phases"]:
                    lines.append(f"\n### {phase['name']}")
                    lines.append(f"Objectives: {', '.join(phase['objectives'])}")
                    lines.append(f"Chapters: {', '.join(phase['chapters'])}")
                return "\n".join(lines)
        return "Study engine failed to process request."
    except Exception as e:
        return f"Study engine error: {e}"

@tool
def pdf_analyze_tool(path: str) -> str:
    """Analyze a PDF document for structure, type, and insights.
    
    Args:
        path: Path to the PDF file.
    """
    from tools.pdf_analyzer import analyze_pdf
    try:
        res = analyze_pdf(path)
        if res["ok"]:
            toc_str = "\n".join(f"- {t[1]}" for t in res["toc"]) if res["toc"] else "No Table of Contents found."
            return (
                f"Analysis for {res['filename']}:\n"
                f"- Type: {res['type']}\n"
                f"- Pages: {res['page_count']}\n"
                f"- TOC Preview:\n{toc_str}\n"
                f"- Preview: {res['text_preview']}"
            )
        else:
            return f"Analysis failed: {res['error']}"
    except Exception as e:
        return f"PDF analyzer error: {e}"

@tool
def book_download_tool(query: str, action: str = "search", book_url: str = None, title: str = None) -> str:
    """Search or download free books.
    
    Args:
        query: Search term for the book.
        action: 'search' (to find books) or 'download' (requires book_url and title).
        book_url: The URL to download from.
        title: The book title for filename.
    """
    from tools.book_downloader import search_gutenberg, download_book
    try:
        if action == "download" and book_url and title:
            res = download_book(book_url, title)
            if res["ok"]:
                return f"Successfully downloaded: {title}. File: {res['filename']} in static/downloads/"
            else:
                return f"Download failed: {res['error']}"
        else:
            results = search_gutenberg(query)
            if not results: return f"No free books found for '{query}'."
            
            lines = [f"Found free books for '{query}':"]
            for b in results[:5]:
                lines.append(f"- {b['title']} by {b['author']} | [Download]({b['download_url']})")
            return "\n".join(lines)
    except Exception as e:
        return f"Book tool error: {e}"

@tool
def youtube_download_tool(url: str, mode: str = "video", quality: str = "best") -> str:
    """Download a YouTube video or extract audio.
    
    Args:
        url: The YouTube video URL.
        mode: 'video' (mp4) or 'audio' (mp3).
        quality: e.g., 'best', '720p', '480p'.
    """
    from tools.youtube_downloader import download_video, download_audio
    try:
        if mode == "audio":
            res = download_audio(url)
        else:
            # Map simplified quality to yt-dlp format
            q_map = {"720p": "bestvideo[height<=720]+bestaudio/best", "480p": "bestvideo[height<=480]+bestaudio/best"}
            dl_quality = q_map.get(quality, "best")
            res = download_video(url, quality=dl_quality)
            
        if res["ok"]:
            return f"Successfully downloaded {mode}: {res['title']}. File: {res['filename']} in static/downloads/"
        else:
            return f"Download failed: {res['error']}"
    except Exception as e:
        return f"YouTube tool error: {e}"

@tool
def business_analysis_tool(query: str, symbol: str = "BTCUSDT", user_id: str = "USR-MASTER") -> str:
    """Analyze a trading opportunity using both Geopolitical and Quantitative agents.
    Runs the full Arena Debate and returns the final recommendation.
    
    Args:
        query: User's question or context (e.g., 'What will happen if Powell is hawkish?')
        symbol: Trading pair to analyze (e.g., 'BTCUSDT')
        user_id: ID of the user (injected automatically).
    """
    from tools.agents.business_agents.business_orchestrator import run_business_analysis, format_business_report
    try:
        res = run_business_analysis(query, symbol, user_id)
        return format_business_report(res)
    except Exception as e:
        return f"Business Analysis Error: {e}"

@tool
def execute_trade_tool(symbol: str, side: str, amount: float, condition: str = None, target_price: float = None, user_id: str = "USR-MASTER") -> str:
    """Execute a trade or set a conditional price alert on Binance.
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
        side: 'buy' or 'sell'
        amount: Quantity to trade
        condition: Optional. 'below' or 'above' to trigger a trade at a specific price.
        target_price: Optional. The target price for the condition.
        user_id: ID of the user (injected automatically).
    """
    from tools.binance_client import BinanceManager
    from tools.trade_executor import executor as trade_executor
    
    try:
        if condition and target_price:
            return trade_executor.add_alert(user_id, symbol, side, condition, target_price, amount)
        else:
            mgr = BinanceManager(user_id)
            res = mgr.execute_trade(symbol, side, amount)
            return str(res)
    except Exception as e:
        return f"Trade Execution Error: {e}"

# ── Updated Tool registry ────────────────────────────────────────────────────

ALL_TOOLS = [
    alarm_tool, timer_tool, math_plot_tool, map_tool,
    news_tool, weather_tool, stock_tool, crypto_tool,
    screenshot_tool, generate_image_tool, terminal_tool, vault_access, rag_search,
    pdf_download_tool, msg_telegram, email_send, app_launch, app_list,
    habit_add, habit_complete, habit_list, habit_stats, habit_today, habit_delete,
    file_tool, model_tool, docker_tool,
    stealth_browse_tool, forensics_tool, psychology_vault_tool,
    binance_tool, business_analysis_tool, execute_trade_tool,
    youtube_download_tool, book_download_tool, pdf_analyze_tool, study_engine_tool, 
    batch_convert_tool, research_paper_tool, learn_topic_tool
]
tools_by_name = {t.name: t for t in ALL_TOOLS}

# ── State Schema ─────────────────────────────────────────────────────────────

# Planner tools: Node A can call vault/rag to gather info before making a plan
PLANNER_TOOLS = [vault_access, rag_search]

# Executor tools: Node B has full tool access
EXECUTOR_TOOLS = ALL_TOOLS

class AgentState(TypedDict):
    messages:              Annotated[Sequence[BaseMessage], lambda x, y: x + y]
    plan:                  List[dict]           # [{"step": 1, "action": "...", "tool": "..."}]
    tool_outputs:          dict                 # {"raw": "...", "rejection_reason": "..."}
    technical_verification: bool               # set by Node C
    emotional_state:       str                 # "neutral" | "energetic" | "focused" | "low"
    user_id:               str
    role:                  str

# ── Auditor Logic ────────────────────────────────────────────────────────────

# Auditor stays on a stable reasoning model
llm_auditor = get_llm(DEFAULT_MODEL)

# ── Node B: The Executor ────────────────────────────────────────────────────

AVAILABLE_TOOLS_DESC = """
AVAILABLE TOOLS (Executor can call these — plan steps using their names):
- alarm_tool(time: str) — Set alarm.
- timer_tool(duration: str) — Start countdown.
- math_plot_tool(expression: str) — Plot math curves.
- map_tool(city: str, destination: str) — Open map.
- news_tool() — Get latest news.
- weather_tool(city: str) — Get weather.
- stock_tool(symbol: str) — Stock price.
- crypto_tool(coin: str) — Crypto price.
- screenshot_tool() — Capture screen.
- generate_image_tool(prompt: str) — Generate AI image.
- terminal_tool(command: str) — Run command in Docker sandbox.
- vault_access(category: str, query: str) — Search vault.
- rag_search(query: str) — Search books/knowledge.
- pdf_download_tool(query: str) — Download PDF to vault.
- msg_telegram(message: str) — Send Telegram message.
- email_send(to, subject, body, attachment_path) — Send email.
- habit_add(title, category, priority, remind_daily) — Add task.
- file_tool(action, path, content) — Manage files (write code/notes).
- model_tool(action, model_name) — Switch your own brain or pull new models.
- docker_tool(action, container) — Control the Docker kingdom.
- stealth_browse_tool(query) — Stealth web research via Camoufox.
- forensics_tool(action) — System health & threat detection.
- psychology_vault_tool(action, data) — Track master's learning & book suggestions.
- youtube_download_tool(url, mode, quality) — Download YouTube videos or MP3 audio.
- book_download_tool(query, action, book_url, title) — Search or download free books.
- pdf_analyze_tool(path) — Analyze a PDF document for structure and insights.
- study_engine_tool(topic, action, level) — Create roadmaps, learning plans, or quizzes.
- batch_convert_tool(directory, action) — Convert files or extract text in bulk.
- research_paper_tool(query, action, paper_url, title) — Search or download arXiv papers.
- learn_topic_tool(topic) — God-tier learning sequence (find books, create plan, index).
"""

STRATEGIST_SYSTEM = f"""You are Marin's Strategist. Your job is to analyze the user's request and build a step-by-step execution plan.

{AVAILABLE_TOOLS_DESC}

RULES:
1. Read the user message and determine what actions are needed.
2. If you need context from vault or knowledge base, call vault_access or rag_search as a tool call.
3. Output a structured plan as a JSON array of steps. Each step is a dict:
   {{"action": "<tool_name or 'respond'>", "args": {{...}}, "rationale": "..."}}
4. If the task is simple (pure conversation, no tool needed), output a single step:
   [{{"action": "respond", "args": {{}}, "rationale": "Direct conversational response"}}]
5. For multi-step tasks, plan multiple steps. Example for "what's bitcoin price and weather":
   [{{"action": "crypto_tool", "args": {{"coin": "bitcoin"}}, "rationale": "Get crypto price"}},
    {{"action": "weather_tool", "args": {{"city": "Dhaka"}}, "rationale": "Get weather"}},
    {{"action": "respond", "args": {{}}, "rationale": "Combine results into response"}}]
6. Use file_tool whenever you need to create a script, save code, or write a note. 
7. Do NOT execute tools yourself — only plan.

Output ONLY the plan JSON. No extra text."""

def get_orchestrated_planner(task_type: str):
    model = get_model_for_task(task_type)
    return get_llm(model, bind_tools=PLANNER_TOOLS)

def node_strategist(state: AgentState) -> dict:
    """Node A — Builds the execution plan. Owns state.plan."""
    messages = state["messages"]
    user_input = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            user_input = m.content
            break
            
    # Orchestration: choose model based on task
    task_type = classify_task(user_input)
    planner = get_orchestrated_planner(task_type)
    
    system = SystemMessage(content=STRATEGIST_SYSTEM + f"\n[ORCHESTRATION: Task classified as {task_type}. Using optimal model.]")
    response = planner.invoke([system] + list(messages))

    plan = []
    if hasattr(response, "tool_calls") and response.tool_calls:
        # LLM wants to gather info first — execute planner tools, then re-plan
        tool_msgs = []
        for tc in response.tool_calls:
            fn = tools_by_name.get(tc["name"])
            if fn:
                result = fn.invoke(tc["args"])
                tool_msgs.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

        # Second pass: now that we have info, build the actual plan
        followup = planner.invoke(
            [system] + list(messages) +
            [response] + tool_msgs +
            [SystemMessage(content="Now output the final plan as a JSON array of steps. No more tool calls.")]
        )
        content = followup.content if followup.content else ""
    else:
        content = response.content if response.content else ""

    # Parse plan from LLM output
    try:
        clean = content.strip()
        # Find the first '[' and last ']' to extract the JSON array
        start = clean.find('[')
        end = clean.rfind(']')
        if start != -1 and end != -1 and end > start:
            json_str = clean[start:end+1]
            plan = json.loads(json_str)
        else:
            # Try parsing as a code block
            if "```" in clean:
                blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)```', clean)
                if blocks:
                    plan = json.loads(blocks[0].strip())
                else:
                    raise ValueError("No valid JSON found")
            else:
                plan = json.loads(clean)
                
        if not isinstance(plan, list):
            plan = [{"action": "respond", "args": {}, "rationale": str(plan)}]
    except (json.JSONDecodeError, TypeError, ValueError):
        plan = [{"action": "respond", "args": {}, "rationale": content or "Direct response"}]

    return {
        "plan": plan,
        "tool_outputs": {},
        "technical_verification": False,
    }

# ── Node B: The Executor ────────────────────────────────────────────────────

EXECUTOR_SYSTEM = """You are Marin's Executor. You receive a step-by-step plan and must execute ONE step at a time.

RULES:
1. Look at state.plan — the first item is your current step.
2. If the step's action is 'respond', generate a helpful, accurate response to the user.
3. If the step's action is a tool name, call that tool with the given args.
4. After executing, the tool result goes into state.tool_outputs.
5. Be precise. Don't hallucinate tool results — actually call the tool.
6. If the step action is unknown, respond with an explanation of what you can do.

[ORCHESTRATION: Using task-specific optimal model for execution.]"""

def get_orchestrated_executor(task_type: str):
    model = get_model_for_task(task_type)
    return get_llm(model, bind_tools=EXECUTOR_TOOLS)

def node_executor(state: AgentState) -> dict:
    """Node B — Executes one plan step. Owns state.tool_outputs."""
    messages = state["messages"]
    plan = state.get("plan", [])
    tool_outputs = dict(state.get("tool_outputs", {}))
    correction = tool_outputs.get("__correction_hint__", "")
    
    # Orchestration
    user_input = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            user_input = m.content
            break
    task_type = classify_task(user_input)
    executor = get_orchestrated_executor(task_type)

    # ── SPECIAL BUSINESS PATH ──
    # If the strategist planned a business analysis, run the Arena
    if any(p.get("action") == "business_analysis_tool" for p in plan) and "business_analysis_tool" not in tool_outputs:
        from tools.agents.business_agents.business_orchestrator import run_business_analysis, format_business_report
        symbol = "BTCUSDT" # Default
        for p in plan:
            if p.get("action") == "business_analysis_tool":
                symbol = p.get("args", {}).get("symbol", "BTCUSDT")
                break
        
        print(f"[Arena] Activating Trading Arena for {symbol}...")
        analysis = run_business_analysis(user_input, symbol, state.get("user_id", "USR-MASTER"))
        report = format_business_report(analysis)
        tool_outputs["business_analysis_tool"] = report
        return {"tool_outputs": tool_outputs}

    # Determine current step
    completed_steps = len([k for k in tool_outputs.keys() if not k.startswith("__")])
    current_step = plan[completed_steps] if completed_steps < len(plan) else None

    if current_step is None:
        # All steps done — generate final response
        executor_msgs = [
            SystemMessage(content="All plan steps are complete. Generate a comprehensive, helpful response to the user based on the collected information."),
        ] + list(messages)
        response = executor.invoke(executor_msgs)
        # Store the final response content in tool_outputs under a sentinel key
        tool_outputs["__final_response__"] = response.content or ""
        return {"tool_outputs": tool_outputs}

    action = current_step.get("action", "respond")
    args = dict(current_step.get("args", {}))

    # Inject user and session context into tool arguments if the tool supports it
    if action in tools_by_name:
        fn = tools_by_name[action]
        # Check if 'user_id' or 'session_id' are expected arguments for this tool
        if hasattr(fn, "args_schema") and fn.args_schema:
             if "user_id" in fn.args_schema.model_fields:
                 if "user_id" not in args or args["user_id"] in ("USR-MASTER", "USR-00000000"):
                     args["user_id"] = state.get("user_id", "USR-00000000")
             if "session_id" in fn.args_schema.model_fields:
                 if "session_id" not in args or args["session_id"] == "default":
                     args["session_id"] = state.get("session_id", "default")

    if action == "respond":
        # Generate a direct response
        context_parts = []
        for k, v in tool_outputs.items():
            if not k.startswith("__"):
                context_parts.append(f"[{k}]: {v}")
        context_str = "\n".join(context_parts) if context_parts else "No prior tool outputs."

        prompt = (
            f"User asked: {messages[-1].content}\n"
            f"Collected info:\n{context_str}\n"
            f"Rationale: {current_step.get('rationale', '')}\n\n"
            f"Generate a clear, helpful response."
        )
        response = executor.invoke([SystemMessage(content=prompt)])
        tool_outputs["__final_response__"] = response.content or ""
        return {"tool_outputs": tool_outputs}

    elif action in tools_by_name:
        # Execute the tool
        tool_fn = tools_by_name[action]
        try:
            result = tool_fn.invoke(args)
            step_key = f"step_{completed_steps}_{action}"
            tool_outputs[step_key] = str(result)
        except Exception as e:
            step_key = f"step_{completed_steps}_{action}"
            tool_outputs[step_key] = f"Error: {e}"

        # If correction hint exists from fail loop, append it as context
        if correction:
            tool_outputs["correction_context"] = correction

        return {"tool_outputs": tool_outputs}

    else:
        # Unknown action — treat as respond
        tool_outputs[f"step_{completed_steps}_unknown"] = f"Unknown action '{action}', proceeding with direct response."
        return {"tool_outputs": tool_outputs}

# ── Node C: The Auditor (Marin Filter) ──────────────────────────────────────

AUDITOR_SYSTEM = """You are Marin's Auditor — a strict quality gate. You review tool outputs and verify accuracy.

YOUR JOB:
1. Read the tool outputs and the original user question.
2. Check ONLY for: factual errors, math mistakes, hallucinated data, or completely empty/irrelevant answers.
3. Set technical_verification to True if the output is accurate and addresses the user's question.
4. If there are errors, explain what's wrong so the Executor can fix it.

CRITICAL RULES — you MUST follow these:
- Do NOT criticize which tools were used or the order they were called. Tool selection is the Strategist's job, not yours.
- Do NOT fail because the agent used one tool instead of two, or didn't follow a specific workflow you imagined.
- Do NOT invent requirements the user never stated. Only judge what the user actually asked.
- If a tool returned empty results (no PDF found, no results), that is NOT a factual error — pass it.
- If the response honestly tells the user what was found (or not found), that is a PASS.
- Only FAIL if the response contains factually wrong information or is completely unrelated to the question.

OUTPUT FORMAT — respond with ONLY a JSON object:
{
  "technical_verification": true or false,
  "issues": ["list of factual issues found, empty if all good"],
  "correction_hint": "what factual content to fix, empty if passed"
}

Be strict about facts. Be lenient about process."""

def node_auditor(state: AgentState) -> dict:
    """Node C — Verifies tool_outputs. Owns state.technical_verification."""
    messages = state["messages"]
    tool_outputs = state.get("tool_outputs", {})
    plan = state.get("plan", [])

    # Build context for auditor
    output_summary = json.dumps(tool_outputs, indent=2, default=str)[:4000]
    plan_summary = json.dumps(plan, indent=2, default=str)[:2000]
    user_msg = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_msg = msg.content
            break

    auditor_prompt = (
        f"User question: {user_msg}\n\n"
        f"Execution plan:\n{plan_summary}\n\n"
        f"Tool outputs collected:\n{output_summary}\n\n"
        f"Review all outputs above. Are they accurate, complete, and relevant to the user's question? "
        f"Output your verification as JSON."
    )

    response = llm_auditor.invoke([SystemMessage(content=AUDITOR_SYSTEM), HumanMessage(content=auditor_prompt)])

    # Parse auditor response
    verified = False
    issues = []
    correction_hint = ""

    try:
        clean = response.content.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()
        parsed = json.loads(clean)
        verified = bool(parsed.get("technical_verification", False))
        issues = parsed.get("issues", [])
        correction_hint = parsed.get("correction_hint", "")
    except (json.JSONDecodeError, TypeError, AttributeError):
        # Fallback: if auditor can't parse, assume pass with a warning
        verified = True
        issues = ["Auditor output could not be parsed — auto-passed with caveat"]
        correction_hint = ""

    # Format correction hint with issues
    if issues:
        full_hint = f"Issues found: {'; '.join(issues)}. Correction: {correction_hint}"
    else:
        full_hint = correction_hint

    return {
        "technical_verification": verified,
        "tool_outputs": {**tool_outputs, "__correction_hint__": full_hint if not verified else ""},
    }

# ── Node D: The Persona Layer ───────────────────────────────────────────────

# Shared LLM for persona (no tools bound)
llm = ChatOllama(model=DEFAULT_MODEL, base_url=OLLAMA_BASE_URL)


async def persona_node(state: AgentState) -> AgentState:
    """
    Node D — The Persona Layer.
    Runs ONLY after technical_verification = True.
    Wraps the verified tool output in Marin's personality.
    Never calls tools. Never modifies the technical content.
    """
    # Safety guard — should never reach here if auditor failed,
    # but defend anyway
    if not state.get("technical_verification", False):
        return {
            "messages": state["messages"],
            "tool_outputs": state["tool_outputs"],
        }

    emotional_state = state.get("emotional_state", "neutral")
    tool_outputs    = state.get("tool_outputs", {})
    
    # Get user input for orchestration
    user_input = ""
    for m in reversed(state["messages"]):
        if isinstance(m, HumanMessage):
            user_input = m.content
            break
            
    task_type = classify_task(user_input)
    persona_llm = get_llm(get_model_for_task(task_type))

    # Read from __final_response__ (written by Executor) or "raw" or synthesize
    raw_content = (
        tool_outputs.get("__final_response__", "")
        or tool_outputs.get("raw", "")
    )
    if not raw_content:
        parts = [str(v) for k, v in sorted(tool_outputs.items()) if not k.startswith("__")]
        raw_content = "\n".join(parts) if parts else "No output to present."

    # Pull the character prompt from marin.py — this is where
    # Hehehe~~ and Ummaaah~~! live
    from marin import get_character_prompt
    persona_prompt = get_character_prompt(emotional_state)

    # Build the wrapping instruction
    wrap_instruction = f"""
You are Marin. The following is a technically verified answer from your reasoning engine.
Your job is ONLY to reformat the delivery — the facts must not change.

Emotional state today: {emotional_state}
Persona rules: {persona_prompt}

Verified technical content:
{raw_content}

Deliver this to the operator in your voice. Keep all numbers, units, and logic
exactly as given. Add warmth, your signature expressions, and natural phrasing.
Do NOT add new claims, hedge the facts, or soften technical conclusions.
""".strip()

    response = await persona_llm.ainvoke([SystemMessage(content=wrap_instruction)])

    final_text = response.content

    return {
        "messages": state["messages"] + [AIMessage(content=final_text)],
        "tool_outputs": {**tool_outputs, "persona_wrapped": final_text},
    }

# ── Routing Logic ────────────────────────────────────────────────────────────

def route_after_executor(state: AgentState) -> str:
    """After Executor: all plan steps complete → Auditor, otherwise → Executor again."""
    plan = state.get("plan", [])
    tool_outputs = state.get("tool_outputs", {})
    completed = len([k for k in tool_outputs if k.startswith("step_") or k == "__final_response__"])

    if "__final_response__" in tool_outputs:
        return "auditor"
    if completed >= len(plan):
        return "auditor"
    return "executor"

def route_after_auditor(state: AgentState) -> str:
    """After Auditor: verified → Persona, not verified → Executor (fail loop)."""
    if state.get("technical_verification", False):
        return "persona"
    return "executor"

# ── Build the Graph ──────────────────────────────────────────────────────────

workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("strategist", node_strategist)
workflow.add_node("executor", node_executor)
workflow.add_node("auditor", node_auditor)
workflow.add_node("persona", persona_node)

# Entry: Strategist
workflow.set_entry_point("strategist")

# Strategist → Executor (always)
workflow.add_edge("strategist", "executor")

# Executor → conditional: if more steps, loop back; if done, Auditor
workflow.add_conditional_edges(
    "executor",
    route_after_executor,
    {
        "executor": "executor",
        "auditor": "auditor",
    }
)

# Auditor → conditional: pass → Persona, fail → Executor (fail loop)
workflow.add_conditional_edges(
    "auditor",
    route_after_auditor,
    {
        "persona": "persona",
        "executor": "executor",
    }
)

# Persona → END
workflow.add_edge("persona", END)

# Compile
agent = workflow.compile()

# ── API Wrappers ─────────────────────────────────────────────────────────────

async def chat_with_marin(message: str, history: list = None, user_id: str = "USR-00000000", role: str = "guest"):
    """Non-streaming entry point for main.py."""
    from marin import get_character_prompt
    is_owner = (role == "owner")
    msgs = [SystemMessage(content=get_character_prompt("neutral", is_owner=is_owner) + "\n" + USER_CONTEXT)]
    if history:
        for m in history:
            if m["role"] == "user":
                msgs.append(HumanMessage(content=m["content"]))
            elif m["role"] == "assistant":
                msgs.append(AIMessage(content=m["content"]))
    msgs.append(HumanMessage(content=message))

    initial_state = {
        "messages":               msgs,
        "plan":                   [],
        "tool_outputs":           {},
        "technical_verification": False,
        "emotional_state":        _infer_emotional_state(history or []),
        "user_id":                user_id,
        "role":                   role,
    }

    result = await agent.ainvoke(initial_state)

    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content
    return "I'm sorry, I couldn't process that request."

async def stream_chat_with_marin(message: str, history: list = None, context: str = "", user_id: str = "USR-00000000", role: str = "guest", user_vibe: str = "neutral"):
    from marin import get_character_prompt
    is_owner = (role == "owner")
    msgs = [SystemMessage(content=get_character_prompt(user_vibe, is_owner=is_owner) + "\n" + USER_CONTEXT)]
    if history:
        for m in history:
            msgs.append(HumanMessage(content=m["content"]) if m["role"] == "user"
                        else AIMessage(content=m["content"]))
    
    # Add context if provided
    full_msg = f"{context}\n\nUSER'S MESSAGE: {message}" if context else message
    msgs.append(HumanMessage(content=full_msg))

    initial_state = {
        "messages":               msgs,
        "plan":                   [],
        "tool_outputs":           {},
        "technical_verification": False,
        "emotional_state":        user_vibe or _infer_emotional_state(history or []),
        "user_id":                user_id,
        "role":                   role,
    }

    # astream_events v2 — only yield tokens from the persona node's LLM call
    persona_token_yielded = False
    try:
        async for event in agent.astream_events(initial_state, version="v2"):
            if (
                event["event"] == "on_chat_model_stream"
                and event.get("metadata", {}).get("langgraph_node") == "persona"
            ):
                chunk = event["data"]["chunk"].content
                if chunk:
                    persona_token_yielded = True
                    yield chunk
    except Exception as e:
        print(f"[Streaming] astream_events error: {e}")

    # Fallback: if streaming didn't yield anything, do a full invoke
    if not persona_token_yielded:
        result = await agent.ainvoke(initial_state)
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                yield msg.content
                break


if __name__ == "__main__":
    async def test():
        async for chunk in stream_chat_with_marin("What is the price of Bitcoin?"):
            print(chunk, end="", flush=True)
        print()
    asyncio.run(test())
