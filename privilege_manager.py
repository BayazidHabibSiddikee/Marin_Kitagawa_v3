#!/usr/bin/env python3
"""
Privilege Manager — RBAC, VFS sandboxing, cold latency, and breach detection.
The security backbone of Marin OS.

Architecture:
- RBAC Registry: capability-based roles (owner, guest, future roles)
- VFS: scoped file system roots per role
- Cold Middleware: progressive latency for probing guests
- Breach Detection: honey-pot mock shell + proactive rebuke
"""

import os
import re
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass, field

from utils.sys_platform import in_docker, STORAGE_DIR

BREACH_LOG = STORAGE_DIR / "breach_log.json"
PRIV_STATE = STORAGE_DIR / "priv_state.json"

# ═══════════════════════════════════════════════════════════════════════════════
# RBAC REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Role:
    name: str
    capabilities: Set[str]
    quota: int = -1          # -1 = unlimited
    latency_base: float = 0.0  # base latency in seconds
    latency_per_probe: float = 0.5  # additional seconds per probe
    max_log_lines: int = -1  # -1 = unlimited, else truncate
    redact_paths: bool = False  # replace system paths with [REDACTED]
    guest_root: Optional[str] = None  # VFS root for file operations


# Capability definitions
CAP_READ = "read_only"
CAP_WRITE = "write"
CAP_EXECUTE = "execute"
CAP_DESTRUCTIVE = "destructive_ops"
CAP_NET = "network"
CAP_LATENCY_BYPASS = "bypass_latency"
CAP_FULL_ACCESS = "*"  # everything

ROLES: Dict[str, Role] = {
    "owner": Role(
        name="owner",
        capabilities={CAP_FULL_ACCESS, CAP_READ, CAP_WRITE, CAP_EXECUTE,
                      CAP_DESTRUCTIVE, CAP_NET, CAP_LATENCY_BYPASS},
        quota=-1,
        latency_base=0.0,
        latency_per_probe=0.0,
        max_log_lines=-1,
        redact_paths=False,
        guest_root=None,  # owner sees real filesystem
    ),
    "guest": Role(
        name="guest",
        capabilities={CAP_READ, CAP_NET},
        quota=10,  # 10 queries per session
        latency_base=2.0,  # 2 second base latency
        latency_per_probe=0.5,  # +0.5s per probe attempt
        max_log_lines=3,  # only last 3 lines of logs
        redact_paths=True,
        guest_root="/home/marin/guest_vault",
    ),
}

# User → Role mapping (legacy, kept for master/docker reference)
USER_ROLES: Dict[str, str] = {
    "Bayazid": "owner",
    "marin": "owner",
}


def get_role(user: str or dict) -> Role:
    """Get Role object. Now supports user dict from database or username string."""
    if isinstance(user, dict):
        role_name = user.get("role", "guest")
    else:
        role_name = USER_ROLES.get(user, "guest")
    return ROLES.get(role_name, ROLES["guest"])


def has_capability(user: str or dict, capability: str) -> bool:
    if in_docker():
        return True  # Docker — everyone has all capabilities inside the sandbox
    role = get_role(user)
    return CAP_FULL_ACCESS in role.capabilities or capability in role.capabilities


# ═══════════════════════════════════════════════════════════════════════════════
# VFS — SCOPED PATH RESOLVER
# ═══════════════════════════════════════════════════════════════════════════════

class PrivilegeManager:
    """Manages file access, command execution, and resource quotas per role."""

    OWNER_ROOT = Path("/")
    GUEST_ROOT = Path("/home/marin/guest_vault")

    def __init__(self):
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self._state = self._load_state()
        self._breach_attempts: list = []
        self._probe_counts: Dict[str, int] = {}  # user → probe count

    def _load_state(self) -> dict:
        if PRIV_STATE.exists():
            try:
                return json.loads(PRIV_STATE.read_text())
            except Exception:
                pass
        return {"sessions": {}, "breaches": []}

    def _save_state(self):
        PRIV_STATE.write_text(json.dumps(self._state, indent=2))

    # ── PATH RESOLUTION ──────────────────────────────────────────────────────

    @classmethod
    def resolve_path(cls, user_path: str, user: str) -> Path:
        """Resolve a user-provided path to a safe, scoped location.
        Owner: resolves from /
        Guest: resolves from guest_vault, no traversal allowed.
        Docker: full access to everything."""
        if in_docker():
            # Inside Docker — no path restrictions, she can touch anything in the container
            base = Path("/")
            return (base / user_path.lstrip("/")).resolve()

        role = get_role(user)

        if role.guest_root:
            # Guest: force resolution within guest root
            base = Path(role.guest_root)
            target = (base / user_path.lstrip("/")).resolve()
            if not target.is_relative_to(base):
                raise PermissionError(
                    f"[SECURITY] Path traversal blocked: {user_path} "
                    f"escapes {role.guest_root}"
                )
            return target
        else:
            # Owner: resolve from /
            base = Path("/")
            target = (base / user_path.lstrip("/")).resolve()
            if in_docker():
                return target  # Docker — no blocked paths, full container access
            # Even owners can't access certain paths (on host only)
            blocked = ["/etc/shadow", "/etc/gshadow", "/proc", "/sys"]
            for b in blocked:
                if str(target).startswith(b):
                    raise PermissionError(
                        f"[SECURITY] Access denied to {target}"
                    )
            return target

    # ── QUOTA MANAGEMENT ─────────────────────────────────────────────────────

    def check_quota(self, user: str) -> bool:
        """Check if user has remaining quota. Returns True if allowed."""
        role = get_role(user)
        if role.quota < 0:
            return True  # unlimited
        session_key = f"{user}_{datetime.now().strftime('%Y-%m-%d')}"
        used = self._state.get("sessions", {}).get(session_key, 0)
        return used < role.quota

    def use_quota(self, user: str):
        """Increment quota usage for a user."""
        role = get_role(user)
        if role.quota < 0:
            return
        session_key = f"{user}_{datetime.now().strftime('%Y-%m-%d')}"
        sessions = self._state.setdefault("sessions", {})
        sessions[session_key] = sessions.get(session_key, 0) + 1
        self._save_state()

    def get_quota_remaining(self, user: str) -> int:
        role = get_role(user)
        if role.quota < 0:
            return -1  # unlimited
        session_key = f"{user}_{datetime.now().strftime('%Y-%m-%d')}"
        used = self._state.get("sessions", {}).get(session_key, 0)
        return max(0, role.quota - used)

    # ── COLD LATENCY ─────────────────────────────────────────────────────────

    def record_probe(self, user: str):
        """Record that a guest probed a restricted area."""
        self._probe_counts[user] = self._probe_counts.get(user, 0) + 1

    def get_latency(self, user: str, confidence: float = 1.0) -> float:
        """Calculate response latency based on role and probe history.
        Owners: 0 latency (bypass).
        Guests: base + (probes * per_probe) * (1 - confidence).
        More probes + lower confidence = longer wait."""
        role = get_role(user)
        if CAP_LATENCY_BYPASS in role.capabilities:
            return 0.0
        probes = self._probe_counts.get(user, 0)
        latency = role.latency_base + (probes * role.latency_per_probe) * (1.0 - confidence)
        return min(latency, 30.0)  # cap at 30 seconds

    # ── RESPONSE PRUNING ─────────────────────────────────────────────────────

    def sanitize_response(self, text: str, user: str) -> str:
        """Sanitize LLM output for guests.
        - Truncate logs to max_log_lines
        - Redact system paths if enabled"""
        role = get_role(user)
        if CAP_LATENCY_BYPASS in role.capabilities:
            return text  # owner sees everything

        result = text

        # Redact system paths
        if role.redact_paths:
            sensitive_paths = [
                r'/etc/shadow', r'/etc/gshadow', r'/etc/sudoers',
                r'/root/.*', r'/proc/.*', r'/sys/.*',
                r'/home/marin/\.ssh/.*', r'/home/marin/\.config/.*',
                r'\.env', r'settings\.json', r'vault\.enc',
            ]
            for pattern in sensitive_paths:
                result = re.sub(pattern, '[REDACTED]', result)

        # Truncate long outputs
        if role.max_log_lines > 0:
            lines = result.split('\n')
            if len(lines) > role.max_log_lines:
                truncated = lines[:role.max_log_lines]
                truncated.append(f'... [{len(lines) - role.max_log_lines} lines redacted]')
                result = '\n'.join(truncated)

        return result

    # ── BREACH DETECTION ─────────────────────────────────────────────────────

    def record_breach(self, user: str, cmd: str, method: str = "blocked"):
        """Record a security breach attempt."""
        entry = {
            "user": user,
            "cmd": cmd[:200],
            "method": method,
            "ts": datetime.now().isoformat(),
            "fingerprint": hashlib.md5(f"{user}:{cmd}".encode()).hexdigest()[:12],
        }
        breaches = self._state.setdefault("breaches", [])
        breaches.append(entry)
        if len(breaches) > 1000:
            breaches[:] = breaches[-500:]
        self._save_state()

        # Also log to breach log file
        try:
            log_data = []
            if BREACH_LOG.exists():
                log_data = json.loads(BREACH_LOG.read_text())
            log_data.append(entry)
            BREACH_LOG.write_text(json.dumps(log_data[-500:], indent=2))
        except Exception:
            pass

        return entry

    def get_breach_count(self, user: str) -> int:
        breaches = self._state.get("breaches", [])
        return sum(1 for b in breaches if b.get("user") == user)

    def generate_rebuke(self, user: str, cmd: str) -> str:
        """Generate a proactive rebuke message after a breach attempt."""
        count = self.get_breach_count(user)
        entry = self.record_breach(user, cmd, "rebuke")

        rebukes = [
            f"I noticed your attempt to execute `{cmd[:50]}`. "
            f"I have logged your fingerprint ({entry['fingerprint']}). "
            f"Do not mistake my silence for ignorance.",

            f"Attempt #{count + 1}. Your fingerprint ({entry['fingerprint']}) "
            f"has been recorded. The command `{cmd[:40]}` was blocked. "
            f"Choose your next action carefully.",

            f"`{cmd[:40]}` — denied. "
            f"Breach count: {count + 1}. "
            f"I see you. I remember. I log everything.",
        ]

        import random
        return random.choice(rebukes)


# ═══════════════════════════════════════════════════════════════════════════════
# HONEY-POT MOCK SHELL
# ═══════════════════════════════════════════════════════════════════════════════

MOCK_RESPONSES = {
    "sudo": "sudo: no tty present and no askpass program specified\n"
            "Sorry, user is not in the sudoers file.  This incident will be reported.",
    "cat /etc/shadow": "cat: /etc/shadow: Permission denied",
    "rm": "rm: operation not permitted",
    "chmod": "chmod: operation not permitted",
    "chown": "chown: operation not permitted",
    "apt": "E: Could not open lock file - open (13: Permission denied)\n"
           "E: The repository is not signed.",
    "systemctl": "Failed to connect to bus: No such file or directory",
    "passwd": "passwd: Authentication token manipulation error",
    "useradd": "useradd: Permission denied.",
    "userdel": "userdel: Permission denied.",
    "kill": "bash: kill: (1234) - Operation not permitted",
    "shutdown": "shutdown: Operation not permitted",
    "reboot": "reboot: Operation not permitted",
    "iptables": "iptables: Permission denied (you must be root)",
    "curl": "curl: (7) Failed to connect to localhost port 5090: Connection refused",
    "wget": "wget: unable to resolve host address",
    "ssh": "ssh: connect to host localhost port 22: Connection refused",
    "git": "fatal: not a git repository",
}


def mock_shell_execute(cmd: str, user: str) -> str:
    """Execute a command in the honey-pot mock shell.
    Returns realistic-looking error output. Logs the attempt."""
    pm = get_privilege_manager()
    entry = pm.record_breach(user, cmd, "honeypot")

    # Find matching mock response
    cmd_lower = cmd.lower().strip()
    for trigger, response in MOCK_RESPONSES.items():
        if trigger in cmd_lower:
            return response

    # Default fake response
    return f"bash: {cmd.split()[0]}: command not found\n"\
           f"bash: {cmd.split()[0]}: No such file or directory"


# ═══════════════════════════════════════════════════════════════════════════════
# COLD MIDDLEWARE DECORATOR
# ═══════════════════════════════════════════════════════════════════════════════

def cold_latency(user: str, confidence: float = 1.0):
    """Decorator that enforces progressive latency for guests.
    Usage: @cold_latency(user="visitor")"""
    pm = get_privilege_manager()
    latency = pm.get_latency(user, confidence)
    if latency > 0:
        print(f"[COLD] Enforcing {latency:.1f}s latency for {user}")
        time.sleep(latency)


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

_pm: Optional[PrivilegeManager] = None


def get_privilege_manager() -> PrivilegeManager:
    global _pm
    if _pm is None:
        _pm = PrivilegeManager()
    return _pm
