import os
import sys
import json
import asyncio
from typing import TypedDict, Annotated, List, Union, Sequence
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolExecutor, ToolInvocation
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import subprocess
import signal

# Add the marin project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import DEFAULT_MODEL, OLLAMA_BASE_URL, PORT
from utils.shared_logic import USER_CONTEXT

# ── Helper for background tools ──────────────────────────────────────────────

def _popen(script: str, args: List[str] = [], timeout: int = None):
    """Helper to launch background scripts consistently."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, script)
    if not os.path.exists(path):
        return f"Script not found: {script}"
    
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")
    try:
        proc = subprocess.Popen(
            [sys.executable, path] + args,
            start_new_session=True,
            cwd=base_dir,
            env=env,
        )
        return None
    except Exception as e:
        return f"Failed to launch {script}: {e}"

# ── Tool Definitions ──────────────────────────────────────────────────────────

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
    """Get real-time stock price and info for a given ticker symbol.
    
    Args:
        symbol: The stock ticker (e.g., 'AAPL', 'TSLA').
    """
    from tools.stock_data import fetch_stock_price
    try:
        data = fetch_stock_price(symbol)
        _popen("tools/stock.py", ["--ticker", symbol.upper()])
        return data
    except Exception as e:
        return f"Error: {e}"

@tool
def crypto_tool(coin: str) -> str:
    """Get current price for a cryptocurrency.
    
    Args:
        coin: The coin name (e.g., 'bitcoin', 'ethereum').
    """
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

tools = [
    alarm_tool, timer_tool, math_plot_tool, map_tool, 
    news_tool, weather_tool, stock_tool, crypto_tool, 
    screenshot_tool, terminal_tool
]
tool_executor = ToolExecutor(tools)

# ── Agent Logic ──────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], lambda x, y: x + y]

model = ChatOllama(model=DEFAULT_MODEL, base_url=OLLAMA_BASE_URL).bind_tools(tools)

def call_model(state):
    messages = state['messages']
    response = model.invoke(messages)
    return {"messages": [response]}

def call_tool(state):
    messages = state['messages']
    last_message = messages[-1]
    
    tool_invocations = []
    for tool_call in last_message.tool_calls:
        action = ToolInvocation(
            tool=tool_call["name"],
            tool_input=tool_call["args"],
        )
        tool_invocations.append(action)
    
    responses = tool_executor.batch(tool_invocations)
    
    tool_messages = []
    for i, response in enumerate(responses):
        tool_messages.append(ToolMessage(
            content=str(response),
            tool_call_id=last_message.tool_calls[i]["id"]
        ))
    
    return {"messages": tool_messages}

def should_continue(state):
    last_message = state['messages'][-1]
    if last_message.tool_calls:
        return "continue"
    return "end"

# ── Graph Construction ────────────────────────────────────────────────────────

workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("action", call_tool)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {"continue": "action", "end": END})
workflow.add_edge("action", "agent")

graph = workflow.compile()

# ── API Wrapper ───────────────────────────────────────────────────────────────

async def chat_with_marin(message: str, history: List[dict] = None):
    """Entry point for main.py to use LangGraph."""
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    
    # Load character from marin.py to keep persona consistent
    from marin import get_character_prompt
    system_prompt = get_character_prompt("neutral") + "\n" + USER_CONTEXT
    
    msgs = [SystemMessage(content=system_prompt)]
    
    if history:
        for m in history:
            if m["role"] == "user":
                msgs.append(HumanMessage(content=m["content"]))
            else:
                msgs.append(AIMessage(content=m["content"]))
    
    msgs.append(HumanMessage(content=message))
    
    # Run the graph
    final_state = await graph.ainvoke({"messages": msgs})
    
    # Get the last AI message
    for msg in reversed(final_state["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content
    
    return "I'm sorry, I couldn't process that request."

async def stream_chat_with_marin(message: str, history: List[dict] = None):
    """Streaming version for FastAPI."""
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    from marin import get_character_prompt
    
    system_prompt = get_character_prompt("neutral") + "\n" + USER_CONTEXT
    msgs = [SystemMessage(content=system_prompt)]
    
    if history:
        for m in history:
            if m["role"] == "user":
                msgs.append(HumanMessage(content=m["content"]))
            elif m["role"] == "assistant":
                msgs.append(AIMessage(content=m["content"]))
    
    msgs.append(HumanMessage(content=message))
    
    async for event in graph.astream_events({"messages": msgs}, version="v1"):
        kind = event["event"]
        if kind == "on_chat_model_stream":
            content = event["data"]["chunk"].content
            if content:
                yield content
        elif kind == "on_tool_start":
            yield f"\n[Executing {event['name']}...]\n"
        elif kind == "on_tool_end":
            # You might want to show tool results or just a confirmation
            pass

if __name__ == "__main__":
    async def test():
        async for chunk in stream_chat_with_marin("What is the price of Bitcoin?"):
            print(chunk, end="", flush=True)
        print()
    asyncio.run(test())
