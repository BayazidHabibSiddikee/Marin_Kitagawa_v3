#!/usr/bin/env python3
"""
Security Module — Handles command logging.
Consolidated from the deprecated marin.py.
"""

import datetime
from typing import Any

# ── Command Log ───────────────────────────────────────────────────────────────
# Thread-safe global log of executed commands
_CMD_LOG: list[dict[str, Any]] = []

def get_cmd_log(limit: int = 100) -> list[dict[str, Any]]:
    return _CMD_LOG[-limit:]

def log_command(cmd: str, status: str, output: str = "", user_id: str = "USR-00000000"):
    entry = {
        "cmd": cmd,
        "status": status,
        "output": output[:2000],
        "ts": datetime.datetime.now().strftime("%H:%M:%S"),
        "user_id": user_id
    }
    _CMD_LOG.append(entry)
    if len(_CMD_LOG) > 200:
        _CMD_LOG.pop(0)
    return entry

async def apply_friction(user_id: str, is_owner: bool = False) -> float:
    """Friction is disabled."""
    return 0.0
