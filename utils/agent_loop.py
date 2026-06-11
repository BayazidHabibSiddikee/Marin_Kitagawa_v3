#!/usr/bin/env python3
"""
Agent loop for Marin: enables tool use via simple command parsing.
"""
import json
import re
import subprocess
import sys
import asyncio
from pathlib import Path
from typing import Dict, Any

# Ensure we can import local_llm from the parent directory
sys.path.append(str(Path(__file__).resolve().parents[1]))
from local_llm import stream_local_chat
# Import persona for system prompt (same directory)
from persona import get_character_prompt

# Import hermes web_search tool
try:
    from hermes_tools import web_search
except Exception:  # pragma: no cover
    web_search = None

def _run_terminal(cmd: str, timeout: int = 60) -> Dict[str, Any]:
    """Run a shell command with basic safety checks."""
    cmd_lower = cmd.lower().strip()
    blocked = [
        "rm -rf /", "rm -rf ~", "mkfs", "> /dev/sd", "dd if=",
        "shutdown", "reboot", "halt", "init 0", "init 6",
        ":(){:|:&};:", "chmod -R 777 /", "wget", "curl|sh", "curl|bash",
    ]
    for b in blocked:
        if b in cmd_lower:
            return {"error": f"Blocked dangerous command: {cmd}"}
    try:
        completed = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "returncode": completed.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s"}
    except Exception as e:  # pragma: no cover
        return {"error": str(e)}

def _web_search(query: str) -> Dict[str, Any]:
    """Search using Hermes web_search tool and return first result snippet."""
    if web_search is None:
        return {"error": "Hermes web_search tool not available"}
    try:
        # web_search returns dict with data.web list of results
        result = web_search({"query": query, "limit": 1})
        # result shape: {"data": {"web": [{"url":..., "title":..., "description":...}, ...]}}
        web_list = result.get("data", {}).get("web", [])
        if not web_list:
            return {"abstract": "No results found."}
        first = web_list[0]
        title = first.get("title", "").strip()
        desc = first.get("description", "").strip()
        abstract = f"{title} - {desc}" if title or desc else "No abstract."
        return {"abstract": abstract}
    except Exception as e:  # pragma: no cover
        return {"error": str(e)}

_BLOCKED_READ_PATHS = [".env", ".sys_pass", ".session_key"]

def _read_file(path_str: str) -> Dict[str, Any]:
    """Read a file with basic safety checks."""
    try:
        p = Path(path_str).expanduser().resolve()
        for blocked in _BLOCKED_READ_PATHS:
            if blocked in str(p):
                return {"error": f"Access denied: {path_str} is a protected file."}
        if not p.is_file():
            return {"error": f"Not a file: {path_str}"}
        content = p.read_text(errors="ignore")
        if len(content) > 2000:
            content = content[:2000] + "\n... [truncated]"
        return {"content": content}
    except Exception as e:  # pragma: no cover
        return {"error": str(e)}

_BLOCKED_WRITE_PATHS = [".env", "config.py", "database.py", "privilege_manager.py"]

def _write_file(input_str: str) -> Dict[str, Any]:
    """Expect format: 'path::content'. Write content to path (sandboxed)."""
    try:
        if "::" not in input_str:
            return {"error": "Invalid format. Expected 'path::content'"}
        path_str, content = input_str.split("::", 1)
        p = Path(path_str).expanduser().resolve()
        base_dir = Path(__file__).resolve().parents[1]
        if not str(p).startswith(str(base_dir)) and not str(p).startswith(str(Path.home())):
            return {"error": f"Access denied: {path_str} is outside allowed workspace."}
        for blocked in _BLOCKED_WRITE_PATHS:
            if blocked in str(p):
                return {"error": f"Access denied: {path_str} is a protected system file."}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"written": len(content), "path": str(p)}
    except Exception as e:  # pragma: no cover
        return {"error": str(e)}

TOOL_MAP = {
    "TERMINAL": _run_terminal,
    "WEB_SEARCH": _web_search,
    "READ_FILE": _read_file,
    "WRITE_FILE": _write_file,
}

async def _gather_stream(aiter):
    """Collect all chunks from an async iterator into a string."""
    chunks = []
    async for chunk in aiter:
        chunks.append(chunk)
    return "".join(chunks)

def agent_loop(user_prompt: str) -> str:
    """
    Main agent loop:
    1. Build system prompt with tool-use instruction.
    2. Get LLM response (may contain a TOOL line).
    3. If TOOL line present, execute tool and call LLM again with result.
    4. Return final natural-language answer.
    """
    system_prompt = get_character_prompt(vibe="neutral", is_owner=True)
    tool_instruction = """
You are an agentic AI. When you need information or to perform an action, emit a single line in the format:
TOOL: <tool_name> :: <tool_input>
Valid tool_names: TERMINAL, WEB_SEARCH, READ_FILE, WRITE_FILE.
After you emit the tool line, wait for the tool result (which will be provided in the next turn) before continuing.
Do not emit JSON, code blocks, or any other structured data—only natural language and the TOOL line when needed.
"""

    # First LLM call to decide on tool use (or answer directly)
    async def _first_call():
        return await _gather_stream(
            stream_local_chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{tool_instruction}\n\nUser: {user_prompt}"}
            ])
        )
    llm_output = asyncio.run(_first_call())

    # Check if LLM emitted a tool command
    tool_match = re.search(r"TOOL:\s*(\w+)\s*::\s*(.+)", llm_output, re.IGNORECASE)
    if tool_match:
        tool_name, tool_input = tool_match.group(1).upper(), tool_match.group(2).strip()
        func = TOOL_MAP.get(tool_name)
        if not func:
            return f"Error: Unknown tool '{tool_name}'."
        tool_result = func(tool_input)
        # Second LLM call to incorporate tool result
        async def _second_call():
            return await _gather_stream(
                stream_local_chat([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"""You previously decided to use the tool {tool_name} with input: {tool_input}
The tool returned: {json.dumps(tool_result)}
Now, based on that result, answer the user's original request in natural language."""
                    }]
                )
            )
        final_answer = asyncio.run(_second_call())
        return final_answer.strip()
    else:
        # No tool needed; return the LLM's direct answer
        return llm_output.strip()

if __name__ == "__main__":  # pragma: no cover
    # Simple CLI test
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        print(agent_loop(prompt))
    else:
        print("Usage: python agent_loop.py <your prompt>")