#!/usr/bin/env python3
"""
Security Agent — Intrusion detection, audit logging, breach monitoring.
Marin's defensive shield. Watches for threats and reports to the master.
"""

import os
import json
import hashlib
from typing import Dict, Any, List
from datetime import datetime

STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "storage")
SECURITY_LOG = os.path.join(STORAGE_DIR, "security_log.json")
BREACH_LOG = os.path.join(STORAGE_DIR, "breach_log.json")
FAILED_ATTEMPTS = os.path.join(STORAGE_DIR, "failed_attempts.json")

OWNER_USER = "Bayazid"


def _load_json(path: str) -> list:
    if os.path.exists(path):
        try:
            return json.loads(open(path).read())
        except Exception:
            pass
    return []


def _save_json(path: str, data: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data[-1000:], f, indent=2)


def action_log_attempt(user: str, cmd: str, result: str = "blocked", user_context: str = OWNER_USER) -> Dict[str, Any]:
    """Log a command attempt (successful or blocked)."""
    entry = {
        "user": user, "cmd": cmd[:200], "result": result,
        "ts": datetime.now().isoformat(),
        "fingerprint": hashlib.md5(f"{user}:{cmd}".encode()).hexdigest()[:12],
    }
    log = _load_json(SECURITY_LOG)
    log.append(entry)
    _save_json(SECURITY_LOG, log)
    return {"ok": True, "logged": entry["fingerprint"]}


def action_log_breach(user: str, cmd: str, method: str = "blocked") -> Dict[str, Any]:
    """Log a security breach attempt."""
    entry = {
        "user": user, "cmd": cmd[:200], "method": method,
        "ts": datetime.now().isoformat(),
        "fingerprint": hashlib.md5(f"{user}:{cmd}".encode()).hexdigest()[:12],
    }
    log = _load_json(BREACH_LOG)
    log.append(entry)
    _save_json(BREACH_LOG, log)

    # Track failed attempts per user for auto-lockout
    attempts = _load_json(FAILED_ATTEMPTS)
    user_attempts = [a for a in attempts if a.get("user") == user]
    user_attempts.append(entry)
    attempts = [a for a in attempts if a.get("user") != user] + user_attempts[-50:]
    _save_json(FAILED_ATTEMPTS, attempts)

    count = len(user_attempts)
    return {"ok": True, "breach_count": count, "fingerprint": entry["fingerprint"]}


def action_check_intruder(user: str, threshold: int = 5, user_context: str = OWNER_USER) -> Dict[str, Any]:
    """Check if a user has exceeded breach threshold (potential intruder)."""
    attempts = _load_json(FAILED_ATTEMPTS)
    user_attempts = [a for a in attempts if a.get("user") == user]
    count = len(user_attempts)

    if count >= threshold:
        recent = user_attempts[-3:]
        return {
            "ok": True, "intruder": True, "attempts": count,
            "recent_cmds": [a.get("cmd", "") for a in recent],
            "action": "LOCKOUT_RECOMMENDED",
            "message": f"Intrusion attempt detected. {count} failed attempts by {user}. "
                       f"Session should be frozen. Awaiting Master's judgment.",
        }
    return {"ok": True, "intruder": False, "attempts": count, "threshold": threshold}


def action_get_audit_log(user: str = None, limit: int = 50, user_context: str = OWNER_USER) -> Dict[str, Any]:
    """Get the security audit log."""
    log = _load_json(SECURITY_LOG)
    if user:
        log = [e for e in log if e.get("user") == user]
    return {"ok": True, "entries": log[-limit:], "total": len(log)}


def action_get_breach_report(user_context: str = OWNER_USER) -> Dict[str, Any]:
    """Get a summary of all breach attempts."""
    breaches = _load_json(BREACH_LOG)
    by_user = {}
    for b in breaches:
        u = b.get("user", "unknown")
        by_user[u] = by_user.get(u, 0) + 1

    return {
        "ok": True,
        "total_breaches": len(breaches),
        "by_user": by_user,
        "recent": breaches[-10:],
    }


def action_scan_system(user_context: str = OWNER_USER) -> Dict[str, Any]:
    """Quick security scan — check for common issues."""
    issues = []

    # Check if kill switch exists
    kill_file = os.path.join(STORAGE_DIR, "kill_switch.json")
    if os.path.exists(kill_file):
        try:
            state = json.loads(open(kill_file).read())
            if state.get("active"):
                issues.append("KILL SWITCH IS ACTIVE — AI command execution disabled")
        except Exception:
            pass

    # Check for exposed sensitive files
    sensitive = ["/etc/shadow", "/etc/gshadow"]
    for path in sensitive:
        if os.path.exists(path):
            mode = oct(os.stat(path).st_mode)[-3:]
            if mode in ("644", "666", "777"):
                issues.append(f"WARNING: {path} has permissive permissions ({mode})")

    # Check vault encryption
    vault_file = os.path.join(STORAGE_DIR, "vault.enc")
    if os.path.exists(vault_file):
        size = os.path.getsize(vault_file)
        if size < 100:
            issues.append("Vault file exists but may be empty/corrupted")

    # Check for unauthorized SSH keys
    ssh_dir = os.path.expanduser("~/.ssh")
    if os.path.exists(ssh_dir):
        for f in os.listdir(ssh_dir):
            if f.endswith(".pub"):
                key_path = os.path.join(ssh_dir, f)
                try:
                    content = open(key_path).read().strip()
                    if len(content) > 0:
                        issues.append(f"SSH key present: {f}")
                except Exception:
                    pass

    return {
        "ok": True,
        "issues": issues,
        "status": "CLEAN" if not issues else f"{len(issues)} ISSUES FOUND",
        "scanned_at": datetime.now().isoformat(),
    }


ACTIONS = {
    "log_attempt": lambda p, u: action_log_attempt(p.get("user", ""), p.get("cmd", ""), p.get("result", "blocked"), u),
    "log_breach": lambda p, u: action_log_breach(p.get("user", ""), p.get("cmd", ""), p.get("method", "blocked")),
    "check_intruder": lambda p, u: action_check_intruder(p.get("user", ""), int(p.get("threshold", 5)), u),
    "get_audit_log": lambda p, u: action_get_audit_log(p.get("user"), int(p.get("limit", 50)), u),
    "get_breach_report": lambda p, u: action_get_breach_report(u),
    "scan_system": lambda p, u: action_scan_system(u),
}


def dispatch(action: str, params: Dict[str, Any], user: str = OWNER_USER) -> Dict[str, Any]:
    fn = ACTIONS.get(action)
    if not fn:
        return {"ok": False, "error": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}"}
    try:
        return fn(params, user)
    except Exception as e:
        return {"ok": False, "error": str(e)}
