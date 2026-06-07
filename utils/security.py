#!/usr/bin/env python3
"""
Security Module — Handles friction latency, sentinel scores, and command logging.
Consolidated from the deprecated marin.py.
"""

import asyncio
import time
import datetime
from typing import Dict, Any, List
from utils.shared_logic import sentinel as _sentinel

# ── Command Log ───────────────────────────────────────────────────────────────
# Thread-safe global log of executed commands
_CMD_LOG: List[Dict[str, Any]] = []

def get_cmd_log(limit: int = 100) -> List[Dict[str, Any]]:
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
    """Exponential async latency for guests based on SecuritySentinel score."""
    if is_owner:
        return 0.0
    
    score = _sentinel.score(user_id)
    if score <= 20:
        return 0.0
        
    wait = min((score / 20) ** 2, 20.0)
    print(f"[FRICTION] {user_id}: score={score:.1f}, sleeping {wait:.1f}s")
    await asyncio.sleep(wait)
    return wait
