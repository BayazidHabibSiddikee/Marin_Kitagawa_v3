
#!/usr/bin/env python3
"""
langgraph_agent.py — Marin Cognitive Architecture (LangGraph)
3-node linear graph: Strategist → Executor → Persona → output
"""

import os
import sys
import json
import asyncio
import re
import time
from datetime import datetime
from typing import TypedDict, Annotated, Sequence, Optional, List
from pathlib import Path

from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
)
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import (
    DEFAULT_MODEL, LOCAL_MODELS, PORT, STRATEGY_MODEL, PERSONA_MODEL,
    classify_task, get_model_for_task, get_api_key
)
import config
from utils.shared_logic import USER_CONTEXT

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
    except: pass

def fix_spacing(text: str) -> str:
    """Minimal spacing fix — only collapse double spaces."""
    if not text: return text
    # 1. camelCase: wordWord -> word Word
    text = re.sub(r'([a-z,])([A-Z])', r'\1 \2', text)
    # 2. Punctuation: word,word -> word, word
    text = re.sub(r'([,\.!?;:])([a-zA-Z])', r'\1 \2', text)
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
    text = re.sub(r'  +', ' ', text)
    return text

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
    text = re.sub(r'(?:async\s+)?def\s+\w+\([^)]*\).*?(?=\n\n|\Z)', '', text, flags=re.DOTALL)
    
    # 4. Remove OpenAI-style function calling artifacts
    text = re.sub(r'<\|tool_use\|>.*?</\|tool_use\|>', '', text, flags=re.DOTALL)
    
    # 5. Clean up orphaned brackets and commas
    text = re.sub(r'\[\s*\]|\{\s*\}', '', text)
    text = re.sub(r',\s*,', ',', text)
    
    return text.strip()

def get_llm(model_name: str, bind_tools: list = None):
    """Factory to create the right LLM instance based on model name."""
    import inspect
    from sentinel_engine import get_langchain_model
    caller_line = inspect.currentframe().f_back.f_lineno
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
    """Run a shell command in the Docker sandbox."""
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

@tool
def file_tool(action: str, path: str, content: str = "") -> str:
    """Manage files (read, write, list). Actions: 'read', 'write', 'list'."""
    from pathlib import Path
    p = Path(path).expanduser().resolve()
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
        from tools.mathplot import _try_nlp, plot, PRESETS
        import os
        import time
        
        # Parse the expression to get x_expr, y_expr, t_start, t_end
        data = _try_nlp(expression.strip())
        if data is None:
            # Check if it's a known preset key
            key = expression.strip().lower().replace(" ", "_")
            if key in PRESETS:
                data = {"x_expr": PRESETS[key][0], "y_expr": PRESETS[key][1],
                        "t_start": PRESETS[key][2], "t_end": PRESETS[key][3],
                        "n_points": 300, "r": 10}
            else:
                return f"Couldn't understand expression '{expression}'. Try 'heart', 'circle', 'spiral', or an equation like 'y = x^2'."
        
        x_expr = data.get("x_expr", "r*cos(t)")
        y_expr = data.get("y_expr", "r*sin(t)")
        t_start = data.get("t_start", 0.0)
        t_end = data.get("t_end", 6.2832)
        n_points = data.get("n_points", 300)
        r = data.get("r", 10.0)
        
        # Save to static/generated as a PNG instead of opening a GUI window
        import numpy as np
        import matplotlib
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
def business_analysis_tool(query: str) -> str:
    """Analyze business/trading decisions — should I buy, sell, or hold?"""
    try:
        from tools.business_judge import BusinessJudge
        judge = BusinessJudge()
        return judge.run_debate("GENERAL", query, "USR-MASTER")
    except Exception as e:
        return f"Error: {e}"

@tool
def binance_tool(action: str = "portfolio") -> str:
    """Interact with Binance — check portfolio, place trades."""
    try:
        from tools.binance_client import BinanceManager
        client = BinanceManager("USR-MASTER")
        if action == "portfolio":
            return str(client.get_portfolio())
        if action == "balance":
            return str(client.get_balance())
        return "Use 'portfolio' or 'balance'"
    except Exception as e:
        return f"Error: {e}"

@tool
def youtube_search_tool(query: str) -> str:
    """Search YouTube for a video or music, classify its mood from the transcript,
    and return a timed director animation sequence for Marin to perform."""
    import random
    try:
        import yt_dlp
        ydl_opts = {
            'quiet': True,
            'default_search': 'ytsearch1',
            'noplaylist': True,
            'format': 'best[ext=webm]/best[ext=mp4]/best'
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
        allow_dance = bool(re.search(r'\b(dance|dancing|twerk|boogie|groove)\b', query, re.I))
        director_tag, mood = make_video_director_script(
            video_id, transcript, title, allow_dance=allow_dance
        )

        mood_line = {
            "sad":        "Okay… putting this on. I'll watch with you.",
            "emotional":  "This one's got feeling. I'm here with you.",
            "hype":       "Ooh this goes hard — putting it on!",
            "chill":      "Nice vibe. Let's just watch this together~",
            "dance":      "Hehe okay, let's move to this one~",
            "hype_metal": "Alright, cranking this up!",
            "normal":     "Found it — putting it on the TV now.",
        }.get(mood, "Found it — putting it on the TV now.")

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

# ── Core Tools (General Use) ─────────────────────────────────────────
CORE_TOOLS = [
    timer_tool, weather_tool, map_tool, terminal_tool,
    rag_search, learn_topic_tool, file_tool,
    crypto_tool, stock_tool, news_tool,
    pdf_analyze_tool, batch_convert_tool, book_download_tool,
    math_plot_tool, alarm_tool,
    youtube_search_tool, youtube_transcript_tool,
    playground_tool, resource_tool, habit_tool
]

# ── Business/Trading Tools (Loaded Separately) ────────────────────────
BUSINESS_TOOLS = [
    business_analysis_tool, binance_tool
]

# Default: use CORE_TOOLS only (follow Custom Instruction §3)
ALL_TOOLS = CORE_TOOLS
tools_by_name = {t.name: t for t in ALL_TOOLS}

# ── Agent State ──────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], lambda x, y: x + y]
    plan: List[dict]
    tool_outputs: dict
    user_id: str
    role: str
    session_id: str
    user_vibe: str

# ── Nodes ────────────────────────────────────────────────────────────────────

STRATEGIST_SYSTEM = """You are Marin's Strategist. Your goal is to select the right tool to fulfill the user's request.
AVAILABLE TOOLS: {tools}
Call the appropriate tool natively using the provided functions.
If no tool is needed, just respond with plain text describing your intent.
To show a website or YouTube search on the projector directly, you can skip tools and just respond with the tag in plain text: Opening browser to __BROWSER__https://www.youtube.com/results?search_query=query"""

async def node_strategist(state: AgentState) -> dict:
    log_agent("Strategist started.")
    last = state["messages"][-1]
    user_msg = last.content if hasattr(last, 'content') else last.get("content", str(last))

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
    
    # If no domain matched, offer all tools so the strategist can still plan
    if not relevant_tool_names:
        log_agent("Strategist (Semantic Router): No domain match — using all tools.")
        filtered_tools = [t.name for t in ALL_TOOLS]
    else:
        filtered_tools = [t.name for t in ALL_TOOLS if t.name in relevant_tool_names]
        log_agent(f"Strategist (Semantic Router): Filtered {len(ALL_TOOLS)} down to {len(filtered_tools)} tools.")

    # 3. LLM Fallback with tool binding
    plan = []
    try:
        # Get tools to bind
        tools_to_bind = [tools_by_name[name] for name in filtered_tools if name in tools_by_name]

        llm = get_llm(STRATEGY_MODEL, bind_tools=tools_to_bind)
        sys_msg = SystemMessage(content=STRATEGIST_SYSTEM.format(tools=filtered_tools))

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
            # Fallback to JSON parsing if no tool calls, but also handle plain text
            match = re.search(r'\[\s*\{.*\}\s*\]', resp.content, re.DOTALL)
            if match:
                try:
                    plan = json.loads(match.group(0))
                except Exception:
                    plan = [{"action": "respond", "args": {}, "rationale": resp.content}]
            else:
                plan = [{"action": "respond", "args": {}, "rationale": resp.content}]
    except Exception as e:
        log_agent(f"Strategist LLM Error: {e}")
        plan = [{"action": "respond", "args": {}, "rationale": f"LLM execution failed: {e}"}]

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
        try:
            # Inject context
            if action in ("learn_topic_tool", "rag_search", "file_tool"):
                args["user_id"] = state.get("user_id", "USR-MASTER")
                args["session_id"] = state.get("session_id", "default")
            
            res = await tools_by_name[action].ainvoke(args)
            tool_outputs[f"step_{completed}_{action}"] = str(res)
        except Exception as e:
            tool_outputs[f"step_{completed}_{action}"] = f"Error: {e}"
    
    return {"tool_outputs": tool_outputs}

async def persona_node(state: AgentState) -> dict:
    log_agent("Persona started.")
    tool_outputs = state.get("tool_outputs", {})
    
    # Collect data
    raw_results = [v for k, v in sorted(tool_outputs.items()) if k.startswith("step_")]
    final_raw = tool_outputs.get("__final_response__", "")
    
    content = "\n\n".join(raw_results) if raw_results else final_raw
    if not content: content = "Task completed."

    # Extract UI control tags to prevent the LLM from dropping or mangling them
    tags_to_preserve = []
    for pattern in [
        r'__YOUTUBE__[\w-]+', r'__DIRECTOR__[A-Za-z0-9+/=]+', r'__DANCE__',
        r'__STREAM__\S+', r'__BROWSER__\S+', r'__ANIM__\w+', r'__SEARCH__\S+', r'__PROJECTOR_OFF__',
    ]:
        matches = re.findall(pattern, content)
        for m in matches:
            tags_to_preserve.append(m)
            content = content.replace(m, '')

    role = state.get("role", "guest")
    user_vibe = state.get("user_vibe", "neutral")
    theme = "evil" if role == "owner" else "standard"

    llm = get_llm(PERSONA_MODEL)
    from utils.persona import get_character_prompt
    sys_prompt = get_character_prompt(user_vibe, theme=theme)

    instruction = (
        f"[DATA]: {content.strip()}\n"
        "[TASK]: Say this naturally in your voice — 1-3 short sentences, like a real person. "
        "No JSON, no tool names, no system instructions."
    )
    
    try:
        resp = await llm.ainvoke([SystemMessage(content=sys_prompt), HumanMessage(content=instruction)])
        final_text = resp.content
        if "i cannot" in final_text.lower() or "i'm sorry" in final_text.lower() or "don't have access" in final_text.lower():
            if len(content) > 10 and not ("i cannot" in content.lower() and "don't have access" in content.lower()):
                final_text = f"Limon~~! I've checked that for you. Ummaaah~~!\n\n{content}"
    except:
        final_text = content

    # ── CRITICAL: Apply text cleanup (Fix #1 & #3) ────────────────────
    # 1. Remove tool schemas and function definitions
    final_text = strip_tool_schemas(final_text)
    
    # 2. Fix spacing issues from small models
    final_text = fix_spacing(final_text)

    # VRM tags for background tool results (if not already from tool output)
    from utils.persona import analyze_marin_vibe
    from director_engine import build_director_script, encode_director_script, decode_director_script, vibe_to_emotion
    vibe = analyze_marin_vibe(final_text)
    if not any("__VIBE__" in t for t in tags_to_preserve):
        tags_to_preserve.append(f"__VIBE__{vibe}")
        
    # Always build the speaking script for lip-sync and expressions
    speaking_script = build_director_script(final_text, vibe_to_emotion(vibe))
    
    # Check if there's an existing director tag (e.g., background anim from youtube)
    existing_director_idx = -1
    for i, t in enumerate(tags_to_preserve):
        if t.startswith("__DIRECTOR__"):
            existing_director_idx = i
            break
            
    if existing_director_idx != -1:
        # Merge speaking script with the background script
        # Push background animations further in time so they happen after speaking
        max_speaking_t = max([a['t'] + a.get('dur', 0) for a in speaking_script], default=0.0)
        
        existing_encoded = tags_to_preserve[existing_director_idx][len("__DIRECTOR__"):]
        existing_script = decode_director_script(existing_encoded)
        
        for action in existing_script:
            action['t'] += max_speaking_t
            
        merged_script = speaking_script + existing_script
        merged_script.sort(key=lambda x: x['t'])
        
        tags_to_preserve[existing_director_idx] = f"__DIRECTOR__{encode_director_script(merged_script)}"
    else:
        tags_to_preserve.append(f"__DIRECTOR__{encode_director_script(speaking_script)}")

    # Re-append extracted tags
    if tags_to_preserve:
        final_text += "\n\n" + " ".join(tags_to_preserve)
    
    return {"messages": [AIMessage(content=final_text.strip())]}

# ── Graph Logic ──────────────────────────────────────────────────────────────

def route_after_executor(state: AgentState):
    if "__final_response__" in state.get("tool_outputs", {}) or len([k for k in state.get("tool_outputs", {}) if k.startswith("step_")]) >= len(state.get("plan", [])):
        return "persona"
    return "executor"

workflow = StateGraph(AgentState)
workflow.add_node("strategist", node_strategist)
workflow.add_node("executor", node_executor)
workflow.add_node("persona", persona_node)

workflow.set_entry_point("strategist")

def route_strategist(x):
    """Safe routing function that handles empty plans."""
    try:
        plan = x.get("plan", [])
        if plan and isinstance(plan, list) and len(plan) > 0:
            if plan[0].get("action") == "respond":
                return "persona"
    except (IndexError, KeyError, TypeError):
        pass
    return "executor"

workflow.add_conditional_edges("strategist", route_strategist)
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

    try:
        log_agent(f"Starting pipeline for {user_id}")
        result = await agent.ainvoke({
            "messages": msgs, "plan": [], "tool_outputs": {},
            "user_id": user_id, "role": role, "session_id": session_id,
            "user_vibe": user_vibe,
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

async def stream_chat_with_marin(message: str, history: list = None, context: str = "", user_id: str = "USR-00000000", role: str = "guest", user_vibe: str = "neutral"):
    await run_background_tools(message, history or [], user_id, role, user_vibe)
    yield "Thinking..."

if __name__ == "__main__":
    async def test():
        async for chunk in stream_chat_with_marin("download assembly books"):
            print(chunk)
    asyncio.run(test())
