#!/usr/bin/env python3
"""
tools/opencode_tool.py — AI orchestration via opencode CLI.

Marin calls this to delegate small coding/file tasks to opencode,
which runs as a headless subprocess and returns the result.

Usage examples:
  opencode_tool("write a python function to reverse a string")
  opencode_tool("fix the syntax error in /tmp/test.py")
  opencode_tool("create a hello world Flask app in /tmp/demo.py")
"""

import os
import subprocess
import sys
from pathlib import Path

# Resolve opencode binary
_OPENCODE_CANDIDATES = [
    Path.home() / ".opencode" / "bin" / "opencode",
    Path("/usr/local/bin/opencode"),
    Path("/home/sword/.opencode/bin/opencode"),
]

def _find_opencode() -> str | None:
    for p in _OPENCODE_CANDIDATES:
        if p.exists() and os.access(p, os.X_OK):
            return str(p)
    # Try PATH
    result = subprocess.run(["which", "opencode"], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def run(task: str, working_dir: str = "", timeout: int = 120, model: str = "opencode/mimo-v2.5-free") -> str:
    """
    Run a task via opencode CLI non-interactively.

    Args:
        task:        Natural language task description or coding prompt.
        working_dir: Directory to run opencode in (defaults to marin project dir).
        timeout:     Max seconds to wait for opencode (default 120).
        model:       Model to use (default: opencode/mimo-v2.5-free, free tier).

    Returns:
        String output from opencode, or error message.
    """
    binary = _find_opencode()
    if not binary:
        return "Error: opencode binary not found. Install it with: curl -fsSL https://opencode.ai/install | bash"

    cwd = working_dir or str(Path(__file__).resolve().parent.parent)

    cmd = [binary, "run", "--model", model, task]

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "NO_COLOR": "1", "FORCE_COLOR": "0", "TERM": "dumb"},
        )
        output = (result.stdout + result.stderr).strip()
        # Strip ANSI escape codes
        import re
        output = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', output)
        output = re.sub(r'\x1b\][^\x07]*\x07', '', output)
        output = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', output)

        if not output:
            return f"opencode completed (exit {result.returncode}) — no output."
        return output[:4000]  # Cap at 4k chars to avoid flooding context

    except subprocess.TimeoutExpired:
        return f"opencode timed out after {timeout}s. Task may still be running in background."
    except Exception as e:
        return f"opencode error: {e}"


if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "write a one-line Python hello world"
    print(run(task))
