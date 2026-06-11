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
    caller_line = inspect.currentframe().f_back.f_lineno
    log_agent(f"Creating LLM: {model_name} @ {config.OLLAMA_BASE_URL} (Line: {caller_line})")
    
    llm = ChatOllama(
        model=model_name,
        base_url=config.OLLAMA_BASE_URL,
        request_timeout=120,
    )
    if bind_tools:
        return llm.bind_tools(bind_tools)
    return llm

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

# tool list
ALL_TOOLS = [
    timer_tool, weather_tool, map_tool, terminal_tool, 
    rag_search, learn_topic_tool, file_tool
]
tools_by_name = {t.name: t for t in ALL_TOOLS}

# ── Agent State ──────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], lambda x, y: x + y]
    marin_fast_response: str
    plan: List[dict]
    tool_outputs: dict
    user_id: str
    role: str
    session_id: str

# ── Nodes ────────────────────────────────────────────────────────────────────

STRATEGIST_SYSTEM = """You are Marin's Strategist. Build a JSON plan.
TOOLS: {tools}
Marin has already told the user: "{marin_fast_response}"
Plan the steps needed to fulfill the request.
Output ONLY a JSON array: [{{"action": "tool_name", "args": {{...}}, "rationale": "..."}}]
If no tool needed: [{{"action": "respond", "args": {{}}, "rationale": "..."}}]"""

async def node_strategist(state: AgentState) -> dict:
    log_agent("Strategist started.")
    user_msg = state["messages"][-1].content
    fast_resp = state.get("marin_fast_response", "")
    
    # 1. Regex Priority
    from marin_fier import classify
    cls = classify(user_msg)
    if cls["intent"] != "chat" and cls["confidence"] > 0.8:
        plan = [{"action": cls["intent"], "args": cls["params"], "rationale": "Regex high-confidence"}]
        log_agent(f"Strategist (Regex): {plan}")
        return {"plan": plan}

    # 2. LLM Fallback (Force 1.5B for tool support)
    plan = []
    try:
        llm = get_llm("qwen2.5:1.5b")
        sys_msg = SystemMessage(content=STRATEGIST_SYSTEM.format(
            tools=[t.name for t in ALL_TOOLS],
            marin_fast_response=fast_resp
        ))
        resp = await llm.ainvoke([sys_msg] + list(state["messages"]))
        
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

async def node_audit(state: AgentState) -> dict:
    log_agent("Audit started.")
    tool_outputs = state.get("tool_outputs", {})
    raw_results = [v for k, v in sorted(tool_outputs.items()) if k.startswith("step_")]
    audit_summary = "Tool outputs:\n" + "\n".join(raw_results)
    tool_outputs["__audit_summary__"] = audit_summary
    return {"tool_outputs": tool_outputs}

async def persona_node(state: AgentState) -> dict:
    log_agent("Persona started.")
    tool_outputs = state.get("tool_outputs", {})
    fast_resp = state.get("marin_fast_response", "")
    
    if "__final_response__" in tool_outputs:
        content = tool_outputs["__final_response__"]
    else:
        content = tool_outputs.get("__audit_summary__", "Task completed.")

    llm = get_llm("qwen2.5:1.5b")
    from utils.persona import get_character_prompt
    sys_prompt = get_character_prompt("neutral", is_owner=True)
    
    instruction = f"[CONTEXT: You already told the user: '{fast_resp}']\n[TOOL RESULTS]: {content}\n[TASK]: Write your final follow-up response. Deliver the results naturally as a continuation of your previous message. Be affectionate. DO NOT refuse."
    
    try:
        resp = await llm.ainvoke([SystemMessage(content=sys_prompt), HumanMessage(content=instruction)])
        final_text = resp.content
    except:
        final_text = content

    final_text = re.sub(r'\[\s*\{\s*"name".*?\}\s*\]', '', final_text, flags=re.DOTALL)
    return {"messages": [AIMessage(content=final_text.strip())]}

# ── Graph Logic ──────────────────────────────────────────────────────────────

workflow = StateGraph(AgentState)
workflow.add_node("strategist", node_strategist)
workflow.add_node("executor", node_executor)
workflow.add_node("audit", node_audit)
workflow.add_node("persona", persona_node)

workflow.set_entry_point("strategist")
workflow.add_conditional_edges("strategist", lambda x: "persona" if x["plan"][0]["action"] == "respond" else "executor")
workflow.add_conditional_edges("executor", lambda x: "audit" if len([k for k in x.get("tool_outputs", {}) if k.startswith("step_")]) >= len(x.get("plan", [])) else "executor")
workflow.add_edge("audit", "persona")
workflow.add_edge("persona", END)

agent = workflow.compile()

# ── API ──────────────────────────────────────────────────────────────────────

async def run_background_tools(message: str, history: list, user_id: str, role: str, user_vibe: str, session_id: str = "default", marin_fast_response: str = ""):
    from utils.shared_logic import get_user_context
    msgs = [SystemMessage(content="Context:\n" + get_user_context())]
    for m in history:
        msgs.append(HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"]))
    msgs.append(HumanMessage(content=message))
    if marin_fast_response:
        msgs.append(AIMessage(content=marin_fast_response))

    try:
        log_agent(f"Starting pipeline for {user_id}")
        result = await agent.ainvoke({
            "messages": msgs, "plan": [], "tool_outputs": {}, 
            "user_id": user_id, "role": role, "session_id": session_id,
            "marin_fast_response": marin_fast_response
        })
        
        final_msg = ""
        for m in reversed(result["messages"]):
            if isinstance(m, AIMessage):
                final_msg = m.content
                break
        
        if final_msg:
            _pending_messages[user_id] = final_msg
            log_agent(f"Result stored for {user_id}")
    except Exception as e:
        log_agent(f"Pipeline Crash: {e}")

_pending_messages = {}
async def get_pending_message(user_id: str) -> str:
    return _pending_messages.pop(user_id, "")

async def stream_chat_with_marin(message: str, history: list = None, context: str = "", user_id: str = "USR-00000000", role: str = "guest", user_vibe: str = "neutral"):
    await run_background_tools(message, history or [], user_id, role, user_vibe)
    yield "Thinking..."

if __name__ == "__main__":
    async def test():
        async for chunk in stream_chat_with_marin("download assembly books"):
            print(chunk)
    asyncio.run(test())
