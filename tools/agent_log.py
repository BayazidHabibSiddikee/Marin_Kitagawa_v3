#!/usr/bin/env python3
"""
agent_log.py — Live agent activity logger.
Writes structured log entries to storage/agent.log.
Each entry has timestamp, node, action, and detail.
"""

import os
import json
import time
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "storage")
LOG_FILE = os.path.join(LOG_DIR, "agent.log")
MAX_LINES = 500  # keep last N lines


def log(node: str, action: str, detail: str = "", extra: dict = None):
    """Write a log entry. Called by each graph node."""
    os.makedirs(LOG_DIR, exist_ok=True)
    entry = {
        "t": datetime.now().strftime("%H:%M:%S"),
        "node": node,
        "action": action,
        "detail": detail[:300],
    }
    if extra:
        entry["extra"] = extra
    line = json.dumps(entry, ensure_ascii=False)

    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

    # Trim to MAX_LINES
    _trim()

    # Also print to terminal
    colors = {
        "strategist": "\033[96m",  # cyan
        "executor":   "\033[92m",  # green
        "auditor":    "\033[93m",  # yellow
        "persona":    "\033[95m",  # magenta
        "system":     "\033[97m",  # white
    }
    reset = "\033[0m"
    c = colors.get(node, "\033[97m")
    print(f"{c}[{entry['t']}] {node:<12} {action:<20} {detail[:100]}{reset}", flush=True)


def _trim():
    """Keep only the last MAX_LINES entries."""
    try:
        if not os.path.exists(LOG_FILE):
            return
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
        if len(lines) > MAX_LINES:
            with open(LOG_FILE, "w") as f:
                f.writelines(lines[-MAX_LINES:])
    except Exception:
        pass


def get_entries(limit: int = 100) -> list:
    """Read last N log entries."""
    try:
        if not os.path.exists(LOG_FILE):
            return []
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
        entries = []
        for line in lines[-limit:]:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries
    except Exception:
        return []


def clear_log():
    """Clear the log file."""
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
