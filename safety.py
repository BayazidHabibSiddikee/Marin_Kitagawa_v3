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

STORAGE_DIR = Path(__file__).parent.parent / "storage"
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
        # OWNER-ONLY — single-user dev box trust boundary
        # In a multi-user shared host, this should be in /var/run owned by root.
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


import hashlib
import secrets

# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM GUARD (Password Authorization)
# ═══════════════════════════════════════════════════════════════════════════════

class SystemGuard:
    """Handles password-based authorization for sensitive system actions."""
    
    PASSWORD_FILE = STORAGE_DIR / ".sys_pass"
    _authorized_sessions: Dict[str, float] = {}  # user_id -> expiry_ts
    SESSION_DURATION = 3600  # 1 hour

    def __init__(self):
        self._load_password()

    def _load_password(self):
        if self.PASSWORD_FILE.exists():
            self._pass_hash = self.PASSWORD_FILE.read_text().strip()
        else:
            # Default password on first run: 'marin'
            self.set_password("marin")
            print("[SECURITY] INITIAL PASSWORD SET TO 'marin'. Change it immediately.")

    def set_password(self, password: str):
        salt = secrets.token_hex(8)
        h = hashlib.sha256((salt + password).encode()).hexdigest()
        self.PASSWORD_FILE.write_text(f"{salt}:{h}")
        self._pass_hash = f"{salt}:{h}"
        self.PASSWORD_FILE.chmod(0o600)

    def verify(self, user_id: str, password: str) -> bool:
        if not self._pass_hash or ":" not in self._pass_hash:
            return False
        salt, h = self._pass_hash.split(":")
        if hashlib.sha256((salt + password).encode()).hexdigest() == h:
            self._authorized_sessions[user_id] = time.time() + self.SESSION_DURATION
            return True
        return False

    def is_authorized(self, user_id: str) -> bool:
        expiry = self._authorized_sessions.get(user_id, 0)
        if time.time() < expiry:
            return True
        return False

    def revoke(self, user_id: str):
        if user_id in self._authorized_sessions:
            del self._authorized_sessions[user_id]

system_guard = SystemGuard()


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
    "openrouter.ai",
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


def _in_docker() -> bool:
    return os.path.exists('/.dockerenv')
