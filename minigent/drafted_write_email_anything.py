from typing import Annotated, TypedDict

from langchain_core.messages import (
    BaseMessage,
    AIMessage,
    ToolMessage,
    SystemMessage,
    HumanMessage,
)
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode


# Global document state
document = ""


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


@tool
def update(content: str) -> str:
    """Update the document with the provided full content."""
    global document
    document = content
    result = f"Document updated successfully.\n\nCurrent content:\n{document}"
    print(f"\n[TOOL:update]\n{result}\n")
    return result


@tool
def save(filename: str) -> str:
    """Save the current document to a text file and finish the process.

    Args:
        filename: Name for the text file
    """
    global document

    if not filename.endswith(".txt"):
        filename = f"{filename}.txt"

    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(document)

        result = f"Document saved successfully to {filename}. FINISHED."
        print(f"\n[TOOL:save] {result}\n")
        return result

    except Exception as e:
        result = f"Error saving to file {filename}: {str(e)}"
        print(f"\n[TOOL:save] {result}\n")
        return result


tools = [update, save]
tool_node = ToolNode(tools)
model = ChatOllama(model="llama3.2").bind_tools(tools)


def get_system_message() -> SystemMessage:
    return SystemMessage(
        content=f"""
You are a drafter, a helpful writing assistant.
You help the user write and update emails, blogs, assignments, and reports.

Rules:
- If the user wants to create, modify, rewrite, or update the document, use the `update` tool.
- Always send the FULL new document content to `update`, not just a diff.
- If the user wants to save and finish, use the `save` tool.
- If the user asks a simple question, you may answer directly.

Current document state:
{document}
"""
    )


def user_node(state: AgentState):
    if not state["messages"]:
        print("AI: I'm ready to help you create or update a document.")

    user_input = input("User: ").strip()

    if user_input.lower() in {"exit", "quit"}:
        goodbye = AIMessage(content="Goodbye!")
        print(f"AI: {goodbye.content}")
        return {"messages": [goodbye]}

    return {"messages": [HumanMessage(content=user_input)]}


def agent_node(state: AgentState):
    system = get_system_message()
    response = model.invoke([system] + list(state["messages"]))

    # Print response for visibility
    if response.content:
        print(f"AI: {response.content}")
    elif getattr(response, "tool_calls", None):
        tool_names = ", ".join(tc["name"] for tc in response.tool_calls)
        print(f"AI: Calling tool(s): {tool_names}")

    return {"messages": [response]}


def route_after_user(state: AgentState) -> str:
    last_message = state["messages"][-1]

    if isinstance(last_message, AIMessage) and last_message.content == "Goodbye!":
        return "end"

    return "agent"


def route_after_agent(state: AgentState) -> str:
    last_message = state["messages"][-1]

    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return "tools"

    return "user"


def route_after_tools(state: AgentState) -> str:
    # Check trailing tool messages
    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage):
            if "FINISHED" in msg.content:
                return "end"
        else:
            break

    return "agent"


# Build the graph
workflow = StateGraph(AgentState)

workflow.add_node("user", user_node)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)

workflow.add_edge(START, "user")

workflow.add_conditional_edges(
    "user",
    route_after_user,
    {
        "agent": "agent",
        "end": END,
    },
)

workflow.add_conditional_edges(
    "agent",
    route_after_agent,
    {
        "tools": "tools",
        "user": "user",
    },
)

workflow.add_conditional_edges(
    "tools",
    route_after_tools,
    {
        "agent": "agent",
        "end": END,
    },
)

app = workflow.compile()


def run():
    print("========== Drafting process has started ==========")
    try:
        app.invoke({"messages": []})
    except KeyboardInterrupt:
        print("\nProcess interrupted.")
    print("========== Drafting process has ended ==========")


if __name__ == "__main__":
    run()
