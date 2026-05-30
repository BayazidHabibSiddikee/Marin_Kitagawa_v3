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

# Add the marin project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import DEFAULT_MODEL, OLLAMA_BASE_URL
from utils.shared_logic import USER_CONTEXT

# ── Tool Definitions ──────────────────────────────────────────────────────────

@tool
def knowledge_hub_tool(location: str = "Dhaka", query: str = "tourist attraction", limit: int = 5) -> str:
    """Search for location information, tourist attractions, or points of interest.
    
    Args:
        location: The city or area to search in.
        query: What to look for (e.g., 'museums', 'restaurants').
        limit: Number of results to return.
    """
    try:
        from tools.knowledge_hub import create_integrated_hub_map
        result = create_integrated_hub_map(location, query=query, limit=limit)
        return json.dumps(result)
    except Exception as e:
        return f"Error: {e}"

@tool
def stock_tool(symbol: str) -> str:
    """Get real-time stock price and info for a given ticker symbol.
    
    Args:
        symbol: The stock ticker (e.g., 'AAPL', 'TSLA').
    """
    import subprocess
    script = os.path.join(os.path.dirname(__file__), "tools", "stock.py")
    try:
        r = subprocess.run([sys.executable, script, "--ticker", symbol], capture_output=True, text=True, timeout=20)
        return r.stdout if r.returncode == 0 else r.stderr
    except Exception as e:
        return f"Error: {e}"

@tool
def crypto_tool(coin: str) -> str:
    """Get current price for a cryptocurrency.
    
    Args:
        coin: The coin name (e.g., 'bitcoin', 'ethereum').
    """
    import subprocess
    script = os.path.join(os.path.dirname(__file__), "tools", "crypto.py")
    try:
        r = subprocess.run([sys.executable, script, "--coin", coin], capture_output=True, text=True, timeout=20)
        return r.stdout if r.returncode == 0 else r.stderr
    except Exception as e:
        return f"Error: {e}"

@tool
def terminal_tool(command: str) -> str:
    """Execute a safe shell command on the local system.
    
    Args:
        command: The bash command to run.
    """
    from marin_fier import is_cmd_allowed
    allowed, reason = is_cmd_allowed(command)
    if not allowed:
        return f"Blocked: {reason}"
    
    import subprocess
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        return f"STDOUT: {r.stdout}\nSTDERR: {r.stderr}"
    except Exception as e:
        return f"Error: {e}"

tools = [knowledge_hub_tool, stock_tool, crypto_tool, terminal_tool]
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
