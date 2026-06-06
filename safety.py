#!/usr/bin/env python3
"""
Safety Controller — Kill Switch, HITL confirmation, and egress filtering.
Central safety layer for Marin OS.
"""

import os
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from utils.sys_platform import in_docker, STORAGE_DIR

KILL_SWITCH_FILE = STORAGE_DIR / "kill_switch.json"
CONFIRM_FILE = STORAGE_DIR / "pending_confirmations.json"

# ═══════════════════════════════════════════════════════════════════════════════
# KILL SWITCH
# ═══════════════════════════════════════════════════════════════════════════════

class KillSwitch:
    """Emergency revocation of AI sudo access and command execution."""

    def __init__(self):
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> dict:
        if KILL_SWITCH_FILE.exists():
            try:
                return json.loads(KILL_SWITCH_FILE.read_text())
            except Exception:
                pass
        return {"active": False, "activated_at": None, "reason": None}

    def _save(self):
        KILL_SWITCH_FILE.write_text(json.dumps(self._state, indent=2))
        os.chmod(KILL_SWITCH_FILE, 0o600)

    @property
    def is_active(self) -> bool:
        return self._state.get("active", False)

    def activate(self, reason: str = "Manual kill switch activation"):
        """Activate kill switch — blocks ALL AI command execution."""
        self._state = {
            "active": True,
            "activated_at": datetime.now().isoformat(),
            "reason": reason,
        }
        self._save()
        # Revoke sudo access immediately
        self._revoke_sudo()
        print(f"[SAFETY] KILL SWITCH ACTIVATED: {reason}")

    def deactivate(self):
        """Deactivate kill switch — restore normal operation."""
        self._state = {"active": False, "activated_at": None, "reason": None}
        self._save()
        self._restore_sudo()
        print(f"[SAFETY] Kill switch deactivated")

    def _revoke_sudo(self):
        """Temporarily revoke marin's sudo access."""
        try:
            # Move sudoers file to backup
            sudoers = Path("/etc/sudoers.d/marin")
            if sudoers.exists():
                backup = Path("/etc/sudoers.d/marin.revoked")
                subprocess.run(
                    ["sudo", "mv", str(sudoers), str(backup)],
                    capture_output=True, timeout=5
                )
                print("[SAFETY] Sudo access revoked")
        except Exception as e:
            print(f"[SAFETY] Failed to revoke sudo: {e}")

    def _restore_sudo(self):
        """Restore marin's sudo access."""
        try:
            sudoers_revoked = Path("/etc/sudoers.d/marin.revoked")
            sudoers = Path("/etc/sudoers.d/marin")
            if sudoers_revoked.exists():
                subprocess.run(
                    ["sudo", "mv", str(sudoers_revoked), str(sudoers)],
                    capture_output=True, timeout=5
                )
                print("[SAFETY] Sudo access restored")
        except Exception as e:
            print(f"[SAFETY] Failed to restore sudo: {e}")

    def check(self) -> bool:
        """Returns True if commands are allowed, False if kill switch is active."""
        if in_docker():
            return True  # Inside Docker — no kill switch, she runs free
        return not self.is_active


# ═══════════════════════════════════════════════════════════════════════════════
# HITL CONFIRMATION (for agent dispatcher)
# ═══════════════════════════════════════════════════════════════════════════════

# Agent actions that require confirmation even for the owner
AGENT_REQUIRES_CONFIRM = {
    "system": ["restart_service", "stop_service", "kill_process"],
    "package": ["install", "remove", "upgrade"],
    "file": ["write_file", "delete", "chmod", "move"],
    "desktop": ["reload_i3", "restart_i3"],
    "network": ["block_host"],
}

_pending: Dict[str, dict] = {}
_counter = 0


def agent_needs_confirmation(agent: str, action: str) -> bool:
    """Check if an agent action requires HITL confirmation."""
    if in_docker():
        return False  # Inside Docker — no confirmation needed, she decides for herself
    actions = AGENT_REQUIRES_CONFIRM.get(agent, [])
    return action in actions


def request_agent_confirmation(agent: str, action: str, params: dict, user: str) -> str:
    """Queue an agent action for owner confirmation. Returns confirmation ID."""
    global _counter
    _counter += 1
    cid = f"AGENT-{_counter:04d}"
    _pending[cid] = {
        "agent": agent,
        "action": action,
        "params": params,
        "user": user,
        "ts": datetime.now().isoformat(),
        "status": "pending",
    }
    # Persist to disk
    _save_pending()
    print(f"[HITL] Agent action requires confirmation: {cid} -> {agent}.{action}")
    return cid


def check_agent_confirmation(cid: str, approved: bool) -> bool:
    """Approve or reject a pending agent confirmation."""
    entry = _pending.get(cid)
    if not entry or entry["status"] != "pending":
        return False
    entry["status"] = "approved" if approved else "rejected"
    _save_pending()
    return approved


def get_pending_confirmations() -> Dict[str, dict]:
    """Get all pending confirmations."""
    return {k: v for k, v in _pending.items() if v["status"] == "pending"}


def _save_pending():
    try:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        CONFIRM_FILE.write_text(json.dumps(_pending, indent=2))
    except Exception:
        pass


def _load_pending():
    global _pending
    if CONFIRM_FILE.exists():
        try:
            _pending = json.loads(CONFIRM_FILE.read_text())
        except Exception:
            _pending = {}


# ═══════════════════════════════════════════════════════════════════════════════
# EGRESS FILTER
# ═══════════════════════════════════════════════════════════════════════════════

# Allowed outbound destinations for AI services
ALLOWED_EGRESS = {
    "localhost",
    "127.0.0.1",
    "host.docker.internal",
    # Ollama (local)
    "localhost:11434",
    "127.0.0.1:11434",
    # Known API endpoints
    "api.openai.com",
    "generativelanguage.googleapis.com",
    "api.anthropic.com",
    "api.deepseek.com",
    "ifconfig.me",
    "icanhazip.com",
}


def is_egress_allowed(host: str) -> bool:
    """Check if a host is in the allowed egress list."""
    # Extract hostname from host:port
    hostname = host.split(":")[0]
    return hostname in ALLOWED_EGRESS or host in ALLOWED_EGRESS


# ═══════════════════════════════════════════════════════════════════════════════
# INIT
# ═══════════════════════════════════════════════════════════════════════════════

_load_pending()
kill_switch = KillSwitch()
