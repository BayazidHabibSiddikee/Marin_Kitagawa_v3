
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
    DEFAULT_MODEL, LOCAL_MODELS, PORT, 
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
    return re.sub(r'  +', ' ', text)

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
    from tools.timer import start_timer
    return start_timer(duration)

@tool
def weather_tool(city: str) -> str:
    """Get the current weather for a city."""
    from tools.knowledge_hub import get_weather
    return json.dumps(get_weather(city))

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
        from tools.mathplot import plot, list_presets
        result = plot(expression)
        return result if result else "Plot generated successfully."
    except Exception as e:
        return f"Error: {e}"

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
        from tools.business_judge import analyze
        return analyze(query)
    except Exception as e:
        return f"Error: {e}"

@tool
def binance_tool(action: str = "portfolio") -> str:
    """Interact with Binance — check portfolio, place trades."""
    try:
        from tools.binance_client import run
        return run(action)
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
        director_tag, mood = make_video_director_script(video_id, transcript, title)

        mood_line = {
            "sad":        "I found it... I'll feel every note with you 🥺",
            "emotional":  "This one hits deep. I'll be right here with you 💕",
            "hype":       "LET'S GOOO!! Hehehe~~ 🔥",
            "chill":      "Perfect vibe~ I'll chill with you 🌙",
            "dance":      "Time to dance!! Ummaaah~~ 💃",
            "hype_metal": "YESSS!! This is FIRE!! 🤘",
            "normal":     "Casting it to the TV now~",
        }.get(mood, "Casting it to the TV now~")

        return (
            f"{mood_line} "
            f"You MUST include __YOUTUBE__{video_id} {director_tag} in your response. "
            f"[video: {title}] [mood: {mood}]"
        )

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
def habit_tool(action: str = "list", args: list = []) -> str:
    """Manage tasks and habits. Actions: 'add' (args: [title, priority]), 'list', 'done' (args: [id]), 'stats', 'today', 'del' (args: [id])."""
    try:
        from tools.habit import run
        return run(action, args)
    except Exception as e:
        return f"Error: {e}"

# tool list — ALL registered tools
ALL_TOOLS = [
    timer_tool, weather_tool, map_tool, terminal_tool,
    rag_search, learn_topic_tool, file_tool,
    crypto_tool, stock_tool, news_tool,
    pdf_analyze_tool, batch_convert_tool, book_download_tool,
    math_plot_tool, alarm_tool,
    business_analysis_tool, binance_tool,
    youtube_search_tool, youtube_transcript_tool,
    playground_tool, resource_tool, habit_tool
]
tools_by_name = {t.name: t for t in ALL_TOOLS}

# ── Agent State ──────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], lambda x, y: x + y]
    plan: List[dict]
    tool_outputs: dict
    user_id: str
    role: str
    session_id: str

# ── Nodes ────────────────────────────────────────────────────────────────────

STRATEGIST_SYSTEM = """You are Marin's Strategist. Build a JSON plan.
TOOLS: {tools}
Output ONLY a JSON array: [{"action": "tool_name", "args": {...}, "rationale": "..."}]
If no tool needed: [{"action": "respond", "args": {}, "rationale": "..."}]
To show a website or YouTube search on the projector directly, you can skip tools and just respond with: [{"action": "respond", "args": {}, "rationale": "Opening browser to __BROWSER__https://www.youtube.com/results?search_query=query"}]"""

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
    
    # If no domain matched, zero tools!
    if not relevant_tool_names:
        log_agent("Strategist (Semantic Router): Dropped to zero tools. Responding directly.")
        return {"plan": [{"action": "respond", "args": {}, "rationale": "No tools needed."}]}
        
    filtered_tools = [t.name for t in ALL_TOOLS if t.name in relevant_tool_names]
    log_agent(f"Strategist (Semantic Router): Filtered {len(ALL_TOOLS)} down to {len(filtered_tools)} tools.")

    # 3. LLM Fallback (Force 1.5B for tool support)
    plan = []
    try:
        llm = get_llm("qwen2.5:1.5b")
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
        resp = await llm.ainvoke([sys_msg] + clean_msgs)
        
        match = re.search(r'\[\s*\{.*\}\s*\]', resp.content, re.DOTALL)
        plan = json.loads(match.group(0)) if match else [{"action": "respond", "args": {}, "rationale": resp.content}]
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
    for pattern in [r'__YOUTUBE__[\w-]+', r'__STREAM__\S+', r'__BROWSER__\S+', r'__ANIM__\w+', r'__SEARCH__\S+', r'__PROJECTOR_OFF__']:
        matches = re.findall(pattern, content)
        for m in matches:
            tags_to_preserve.append(m)
            content = content.replace(m, '')

    # Force rephrase in Marin's voice (1.5B is most compliant)
    llm = get_llm("qwen2.5:1.5b")
    from utils.persona import get_character_prompt
    sys_prompt = get_character_prompt("neutral", theme="evil")
    
    instruction = f"""[DATA]: {content}\n[TASK]: Rephrase the DATA in your character's voice. Be affectionate and protective. DO NOT refuse. Use signature phrases (Limon~~, Hehehe~~, Ummaaah~~!)."""
    
    try:
        resp = await llm.ainvoke([SystemMessage(content=sys_prompt), HumanMessage(content=instruction)])
        final_text = resp.content
        if "i cannot" in final_text.lower() or "i'm sorry" in final_text.lower() or "don't have access" in final_text.lower():
            if len(content) > 10 and not ("i cannot" in content.lower() and "don't have access" in content.lower()):
                final_text = f"Limon~~! I've checked that for you. Ummaaah~~!\n\n{content}"
    except:
        final_text = content

    # Cleanup
    final_text = re.sub(r'\[\s*\{\s*"name".*?\}\s*\]', '', final_text, flags=re.DOTALL)
    
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

_pending_messages = {}
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
            "user_id": user_id, "role": role, "session_id": session_id
        })
        
        final_msg = ""
        for m in reversed(result["messages"]):
            if isinstance(m, AIMessage):
                final_msg = m.content
                break
        
        if final_msg:
            _pending_messages[user_id] = (final_msg, time.time())
            log_agent(f"Result stored for {user_id}")
    except Exception as e:
        log_agent(f"Pipeline Crash: {e}")

async def get_pending_message(user_id: str) -> str:
    entry = _pending_messages.pop(user_id, None)
    if entry is None:
        return ""
    msg, timestamp = entry
    if time.time() - timestamp > _PENDING_MSG_TTL:
        return ""  # Expired
    return msg

async def stream_chat_with_marin(message: str, history: list = None, context: str = "", user_id: str = "USR-00000000", role: str = "guest", user_vibe: str = "neutral"):
    await run_background_tools(message, history or [], user_id, role, user_vibe)
    yield "Thinking..."

if __name__ == "__main__":
    async def test():
        async for chunk in stream_chat_with_marin("download assembly books"):
            print(chunk)
    asyncio.run(test())
