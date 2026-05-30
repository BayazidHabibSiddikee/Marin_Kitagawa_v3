#!/usr/bin/env python3
"""
A simple LangGraph agent that demonstrates the structure without relying on
the problematic ToolExecutor. This version uses a custom tool node.
"""
import os
import sys
from typing import TypedDict, Annotated, List, Union
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool

# Add the marin project root to the path so we can import from tools
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Define some tools (same as before)
@tool
def get_current_time(format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Get the current date and time."""
    from datetime import datetime
    return datetime.now().strftime(format)

@tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression."""
    try:
        # Note: using eval is dangerous in production, but ok for demo
        result = eval(expression, {"__builtins__": {}}, {})
        return str(result)
    except Exception as e:
        return f"Error: {e}"

@tool
def read_file(file_path: str) -> str:
    """Read the contents of a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"

tools = [get_current_time, calculate, read_file]
tools_by_name = {tool.name: tool for tool in tools}

# Define the state
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], "The messages in the conversation"]

# Agent node: decides what to do next
def agent_node(state: AgentState) -> AgentState:
    """
    In a real agent, this would call an LLM to decide.
    For this demo, we'll use a simple rule-based approach.
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    if isinstance(last_message, HumanMessage):
        content = last_message.content.lower()
        
        # Simple rule-based tool selection
        if "time" in content or "date" in content:
            # We'll return a message indicating we want to use the time tool
            # In a real agent, the LLM would output a tool call.
            # Here, we'll simulate by adding an AIMessage that says we want to use the tool.
            # Then the tool node will pick it up.
            ai_msg = AIMessage(content="", tool_calls=[{"name": "get_current_time", "args": {"format": "%Y-%m-%d %H:%M:%S"}, "id": "1"}])
            return {"messages": messages + [ai_msg]}
        elif any(word in content for word in ["calculate", "math", "+", "-", "*", "/"]):
            # Extract a very simple expression
            import re
            match = re.search(r'[\d\.\+\-\*/\(\)\s]+', content)
            if match:
                expr = match.group(0).strip()
                ai_msg = AIMessage(content="", tool_calls=[{"name": "calculate", "args": {"expression": expr}, "id": "1"}])
                return {"messages": messages + [ai_msg]}
            else:
                ai_msg = AIMessage(content="I can help you calculate, tell time, or read files. What would you like to do?")
                return {"messages": messages + [ai_msg]}
        elif "read" in content or "file" in content:
            import re
            match = re.search(r'read\s+file\s+([^\s]+)', content)
            if match:
                file_path = match.group(1)
                ai_msg = AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"file_path": file_path}, "id": "1"}])
                return {"messages": messages + [ai_msg]}
            else:
                ai_msg = AIMessage(content="Please specify which file you'd like me to read.")
                return {"messages": messages + [ai_msg]}
        else:
            ai_msg = AIMessage(content="I'm not sure what you want. Try asking for the time, a calculation, or to read a file.")
            return {"messages": messages + [ai_msg]}
    else:
        # If the last message is not human (e.g., a tool result), we just pass through
        return state

# Tool node: executes the tool called by the agent
def tool_node(state: AgentState) -> AgentState:
    """
    Executes the tool specified in the last AIMessage's tool_calls.
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        # We'll handle the first tool call for simplicity
        tool_call = last_message.tool_calls[0]
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        
        if tool_name in tools_by_name:
            tool_func = tools_by_name[tool_name]
            try:
                result = tool_func.invoke(tool_args)
                # Create a ToolMessage with the result
                tool_msg = ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call["id"]
                )
                return {"messages": messages + [tool_msg]}
            except Exception as e:
                tool_msg = ToolMessage(
                    content=f"Error: {e}",
                    tool_call_id=tool_call["id"]
                )
                return {"messages": messages + [tool_msg]}
        else:
            # Tool not found
            tool_msg = ToolMessage(
                content=f"Error: Tool {tool_name} not found.",
                tool_call_id=tool_call["id"]
            )
            return {"messages": messages + [tool_msg]}
    else:
        # No tool calls, just return the state
        return state

# Decide what to do after the agent node
def should_continue(state: AgentState) -> str:
    """
    If the last message is a ToolMessage, we go to the agent node to decide next.
    If the last message is an AIMessage without tool calls, we end.
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    if isinstance(last_message, ToolMessage):
        # After a tool result, go back to agent to decide what to do next
        return "agent"
    elif isinstance(last_message, AIMessage):
        # If the AIMessage has no tool calls, we are done
        if not last_message.tool_calls:
            return "end"
        else:
            # This shouldn't happen in our flow, but if it does, go to tool node
            return "tool"
    else:
        # Default to agent
        return "agent"

# Build the graph
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("agent", agent_node)
workflow.add_node("tool", tool_node)

# Set entry point
workflow.set_entry_point("agent")

# Add edges
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "agent": "agent",   # Loop back to agent (though this might cause infinite loop, we'll see)
        "tool": "tool",
        "end": END
    }
)

workflow.add_conditional_edges(
    "tool",
    should_continue,
    {
        "agent": "agent",
        "tool": "tool",   # Shouldn't happen
        "end": END
    }
)

# Compile the graph
app = workflow.compile()

if __name__ == "__main__":
    print("Simple LangGraph Agent Demo")
    print("Try asking for the time, a calculation, or to read a file.")
    print("Type 'quit' to exit.\n")
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["quit", "exit"]:
            break
        
        # Initialize state with the user's message
        initial_state = {
            "messages": [HumanMessage(content=user_input)]
        }
        
        # Run the agent
        for event in app.stream(initial_state):
            # The stream yields tuples (node_name, state)
            for node_name, state in event.items():
                if "__end__" not in node_name:
                    # Print the last message from the state
                    messages = state.get("messages", [])
                    if messages:
                        last_msg = messages[-1]
                        if isinstance(last_msg, AIMessage):
                            if last_msg.tool_calls:
                                print(f"Agent: [Calling tool {last_msg.tool_calls[0]['name']}]")
                            else:
                                print(f"Agent: {last_msg.content}")
                        elif isinstance(last_msg, ToolMessage):
                            print(f"Tool result: {last_msg.content[:200]}")
                        elif isinstance(last_msg, HumanMessage):
                            # We don't need to print the human message again
                            pass
        print()  # Blank line for readability