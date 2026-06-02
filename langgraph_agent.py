#!/usr/bin/env python3
"""
langgraph_agent.py — Marin Cognitive Architecture (LangGraph)
4-node cyclic graph: Strategist → Executor → Auditor (fail loop) → Persona → output
"""

import os
import sys
import json
import asyncio
from typing import TypedDict, Annotated, Sequence, Optional, List
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, END
from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
)
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
import subprocess

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import DEFAULT_MODEL, OLLAMA_BASE_URL, PORT
from utils.shared_logic import USER_CONTEXT


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
    """Execute a safe shell command on the local system."""
    from marin_fier import is_cmd_allowed
    allowed, reason = is_cmd_allowed(command)
    if not allowed:
        return f"Blocked: {reason}"
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        return f"STDOUT: {r.stdout}\nSTDERR: {r.stderr}"
    except Exception as e:
        return f"Error: {e}"

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

# ── Tool registry (kept for reference; Node B uses tools_by_name) ────────────

ALL_TOOLS = [
    alarm_tool, timer_tool, math_plot_tool, map_tool,
    news_tool, weather_tool, stock_tool, crypto_tool,
    screenshot_tool, terminal_tool, vault_access, rag_search,
    pdf_download_tool, msg_telegram, email_send, app_launch, app_list,
    swordwatch_inspect, swordwatch_kill,
    habit_add, habit_complete, habit_list, habit_stats, habit_today, habit_delete,
]
tools_by_name = {t.name: t for t in ALL_TOOLS}

# Planner tools: Node A can call vault/rag to gather info before making a plan
PLANNER_TOOLS = [vault_access, rag_search]

# Executor tools: Node B has full tool access
EXECUTOR_TOOLS = ALL_TOOLS

# ── State Schema ─────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages:              Annotated[Sequence[BaseMessage], lambda x, y: x + y]
    plan:                  List[dict]           # [{"step": 1, "action": "...", "tool": "..."}]
    tool_outputs:          dict                 # {"raw": "...", "rejection_reason": "..."}
    technical_verification: bool               # set by Node C
    emotional_state:       str                 # "neutral" | "energetic" | "focused" | "low"

# ── LLM instances ────────────────────────────────────────────────────────────

# Node A (Strategist): bound to planner tools
llm_planner = ChatOllama(model=DEFAULT_MODEL, base_url=OLLAMA_BASE_URL).bind_tools(PLANNER_TOOLS)

# Node B (Executor): bound to all execution tools
llm_executor = ChatOllama(model=DEFAULT_MODEL, base_url=OLLAMA_BASE_URL).bind_tools(EXECUTOR_TOOLS)

# Node C (Auditor): no tools bound — pure reasoning
llm_auditor = ChatOllama(model=DEFAULT_MODEL, base_url=OLLAMA_BASE_URL)

# ── Node A: The Strategist ──────────────────────────────────────────────────

AVAILABLE_TOOLS_DESC = """
AVAILABLE TOOLS (Executor can call these — plan steps using their names):
- alarm_tool(time: str) — Set alarm. Args: {"time": "HH:MM"}
- timer_tool(duration: str) — Start countdown. Args: {"duration": "5m", "1h", "30s"}
- math_plot_tool(expression: str) — Plot math curves. Args: {"expression": "heart", "sin(t)"}
- map_tool(city: str, destination: str) — Open map. Args: {"city": "Dhaka"}
- news_tool() — Get latest news. Args: {}
- weather_tool(city: str) — Get weather. Args: {"city": "Dhaka"}
- stock_tool(symbol: str) — Stock price. Args: {"symbol": "AAPL"}
- crypto_tool(coin: str) — Crypto price. Args: {"coin": "bitcoin"}
- screenshot_tool() — Capture screen. Args: {}
- terminal_tool(command: str) — Run shell command. Args: {"command": "ls"}
- vault_access(category: str, query: str) — Search vault storage. Args: {"category": "misc", "query": "notes"}
- rag_search(query: str) — Search knowledge base. Args: {"query": "search terms"}
- pdf_download_tool(query: str) — Search & download PDF to unique/download vault. Args: {"query": "book name or topic"}
- msg_telegram(message: str) — Send message to operator via Telegram. Args: {"message": "text"}
- email_send(to, subject, body, attachment_path) — Send email via Gmail, attach .txt/.tex. Args: {"to": "...", "subject": "...", "body": "...", "attachment_path": "/path/to/file"}
- habit_add(title, category, priority, remind_daily) — Add task with optional daily reminder. Args: {"title": "...", "category": "study", "priority": "high", "remind_daily": true}
- habit_complete(task_id) — Mark task done. Args: {"task_id": 1}
- habit_list(status, category) — List tasks. Args: {"status": "todo", "category": "study"}
- habit_stats() — Get overview. Args: {}
- habit_today() — Show pending daily reminders. Args: {}
- habit_delete(task_id) — Delete a task permanently. Args: {"task_id": 1}
- app_launch(app_name: str) — Open an app by name. Args: {"app_name": "code|brave|obsidian|mpv|..."}
- app_list() — List all available apps. Args: {}
- swordwatch_inspect(target) — Deep inspect a process (CPU, mem, threads, files, network). Args: {"target": "name or pid"}
- swordwatch_kill(target, force) — Kill a process (SIGTERM or SIGKILL). Args: {"target": "name or pid", "force": false}
- whatsapp_manage(action, message_data, limit) — WhatsApp integration. Actions: 'process', 'list_messages', 'list_todos', 'stats', 'list_actionable'. Args: {"action": "list_todos", "limit": 10}
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
6. Do NOT execute tools yourself — only plan.

Output ONLY the plan JSON. No extra text."""

def node_strategist(state: AgentState) -> dict:
    """Node A — Builds the execution plan. Owns state.plan."""
    messages = state["messages"]
    system = SystemMessage(content=STRATEGIST_SYSTEM)
    response = llm_planner.invoke([system] + list(messages))

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
        followup = llm_planner.invoke(
            [system] + list(messages) +
            [response] + tool_msgs +
            [SystemMessage(content="Now output the final plan as a JSON array of steps. No more tool calls.")]
        )
        content = followup.content if followup.content else ""
    else:
        content = response.content if response.content else ""

    # Parse plan from LLM output
    try:
        # Strip markdown code fences if present
        clean = content.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()
        plan = json.loads(clean)
        if not isinstance(plan, list):
            plan = [{"action": "respond", "args": {}, "rationale": str(plan)}]
    except (json.JSONDecodeError, TypeError):
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
6. If the step action is unknown, respond with an explanation of what you can do."""

def node_executor(state: AgentState) -> dict:
    """Node B — Executes one plan step. Owns state.tool_outputs."""
    messages = state["messages"]
    plan = state.get("plan", [])
    tool_outputs = dict(state.get("tool_outputs", {}))
    correction = tool_outputs.get("__correction_hint__", "")

    # Determine current step
    completed_steps = len(tool_outputs)
    current_step = plan[completed_steps] if completed_steps < len(plan) else None

    if current_step is None:
        # All steps done — generate final response
        executor_msgs = [
            SystemMessage(content="All plan steps are complete. Generate a comprehensive, helpful response to the user based on the collected information."),
        ] + list(messages)
        response = llm_executor.invoke(executor_msgs)
        # Store the final response content in tool_outputs under a sentinel key
        tool_outputs["__final_response__"] = response.content or ""
        return {"tool_outputs": tool_outputs}

    action = current_step.get("action", "respond")
    args = current_step.get("args", {})

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
        response = llm_executor.invoke([SystemMessage(content=prompt)])
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

    response = await llm.ainvoke([SystemMessage(content=wrap_instruction)])

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

async def chat_with_marin(message: str, history: list = None):
    """Non-streaming entry point for main.py."""
    from marin import get_character_prompt
    msgs = [SystemMessage(content=get_character_prompt("neutral") + "\n" + USER_CONTEXT)]
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
    }

    result = await agent.ainvoke(initial_state)

    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content
    return "I'm sorry, I couldn't process that request."

async def stream_chat_with_marin(message: str, history: list = None):
    from marin import get_character_prompt
    msgs = [SystemMessage(content=get_character_prompt("neutral") + "\n" + USER_CONTEXT)]
    if history:
        for m in history:
            msgs.append(HumanMessage(content=m["content"]) if m["role"] == "user"
                        else AIMessage(content=m["content"]))
    msgs.append(HumanMessage(content=message))

    initial_state = {
        "messages":               msgs,
        "plan":                   [],
        "tool_outputs":           {},
        "technical_verification": False,
        "emotional_state":        _infer_emotional_state(history or []),
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
