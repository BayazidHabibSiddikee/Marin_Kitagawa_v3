#!/usr/bin/env python3
"""
Simple LangGraph agent that can execute tools.
Demonstrates how to build a tool-using agent with LangGraph.
"""
import os
from typing import TypedDict, Annotated, List, Union
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolExecutor, ToolInvocation
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI  # or any other LLM you have configured

# Define the state for our graph
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], "The messages in the conversation"]
    # You can add other state variables if needed

# Example tools - you can replace these with actual tools from your marin project
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

# List of tools available to the agent
tools = [get_current_time, calculate, read_file]

# Create a ToolExecutor that can run our tools
tool_executor = ToolExecutor(tools)

# We'll use a simple LLM - you need to configure your own API key/model
# For demonstration, we'll use a placeholder. In practice, you'd set up your LLM.
# os.environ["OPENAI_API_KEY"] = "your-api-key-here"
# llm = ChatOpenAI(model="gpt-4o", temperature=0)

# Since we don't have an LLM configured in this environment, we'll simulate
# the agent's decision making with a simple rule-based approach for the demo.
# In a real scenario, you'd let the LLM decide which tool to use.

def agent_node(state: AgentState) -> AgentState:
    """
    Agent node that decides what to do next.
    For demo purposes, we'll look at the last human message and choose a tool.
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    # If the last message is from a human, we decide based on content
    if isinstance(last_message, HumanMessage):
        content = last_message.content.lower()
        
        # Simple rule-based tool selection (replace with LLM reasoning)
        if "time" in content or "date" in content:
            # Ask for time
            action = ToolInvocation(
                tool="get_current_time",
                tool_input={"format": "%Y-%m-%d %H:%M:%S"}
            )
        elif any(word in content for word in ["calculate", "math", "+", "-", "*", "/"]):
            # Extract a simple expression (very naive)
            import re
            # Look for something like "2+2" or "5 * 3"
            match = re.search(r'[\d\.\+\-\*/\(\)\s]+', content)
            if match:
                expr = match.group(0).strip()
                action = ToolInvocation(
                    tool="calculate",
                    tool_input={"expression": expr}
                )
            else:
                # Default response
                ai_msg = AIMessage(content="I can help you calculate, tell time, or read files. What would you like to do?")
                return {"messages": messages + [ai_msg]}
        elif "read" in content or "file" in content:
            # Try to extract a file path
            import re
            # Look for something after "read file" or similar
            match = re.search(r'read\s+file\s+([^\s]+)', content)
            if match:
                file_path = match.group(1)
                action = ToolInvocation(
                    tool="read_file",
                    tool_input={"file_path": file_path}
                )
            else:
                ai_msg = AIMessage(content="Please specify which file you'd like me to read.")
                return {"messages": messages + [ai_msg]}
        else:
            # Default: ask for clarification
            ai_msg = AIMessage(content="I'm not sure what you want. Try asking for the time, a calculation, or to read a file.")
            return {"messages": messages + [ai_msg]}
    else:
        # If the last message is not human (e.g., a tool result), we just pass through
        return state

    # Execute the chosen tool
    try:
        result = tool_executor.invoke(action)
        # Create a ToolMessage to record the result
        tool_msg = ToolMessage(
            content=str(result),
            tool_call_id=action.tool,  # Simple ID for demo
            name=action.tool
        )
        return {"messages": messages + [tool_msg]}
    except Exception as e:
        ai_msg = AIMessage(content=f"Error executing tool: {e}")
        return {"messages": messages + [ai_msg]}

def should_continue(state: AgentState) -> str:
    """
    Decide whether to continue the loop or end.
    We'll end after the agent has responded (when we have an AIMessage that is not a tool call).
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    # If the last message is an AIMessage (and not a ToolMessage), we consider the agent done
    if isinstance(last_message, AIMessage):
        return "end"
    else:
        # Continue to agent node
        return "continue"

# Build the graph
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("agent", agent_node)

# Set entry point
workflow.set_entry_point("agent")

# Add conditional edges
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "continue": "agent",  # Loop back to agent for more tool use
        "end": END
    }
)

# Compile the graph
app = workflow.compile()

if __name__ == "__main__":
    print("LangGraph Agent Demo")
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
                            print(f"Agent: {last_msg.content}")
                        elif isinstance(last_msg, ToolMessage):
                            # Optionally show tool results
                            print(f"[Tool {last_msg.name} result: {last_msg.content[:100]}...]")
        print()  # Blank line for readability