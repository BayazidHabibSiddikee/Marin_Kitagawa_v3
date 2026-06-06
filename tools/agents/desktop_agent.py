#!/usr/bin/env python3
"""
Desktop Agent — i3 window manager integration via IPC.
Allows Marin to manage workspaces, windows, layout, and react to desktop events.
"""

import subprocess
import json
import os
from typing import Dict, Any, Optional

OWNER_USER = "Bayazid"


def _run(cmd: str, timeout: int = 10) -> Dict[str, Any]:
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return {"exit": r.returncode, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"exit": -1, "stdout": "", "stderr": f"Timeout ({timeout}s)"}
    except Exception as e:
        return {"exit": -1, "stdout": "", "stderr": str(e)}


def _check_owner(user: str) -> Optional[str]:
    if user != OWNER_USER:
        return "DENIED: Only Bayazid can control the desktop."
    return None


def _i3_msg(command: str) -> Dict[str, Any]:
    """Send a command to i3 via i3-msg."""
    return _run(f"i3-msg '{command}'")


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def action_list_workspaces(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("i3-msg -t get_workspaces")
    try:
        workspaces = json.loads(r["stdout"])
        return {"ok": True, "workspaces": workspaces}
    except Exception:
        return {"ok": False, "error": "Failed to parse workspaces", "raw": r["stdout"][:200]}


def action_list_windows(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("i3-msg -t get_tree")
    try:
        tree = json.loads(r["stdout"])
        windows = []
        def _find_windows(node):
            if node.get("window"):
                windows.append({
                    "id": node["window"],
                    "name": node.get("name", ""),
                    "app": node.get("window_properties", {}).get("class", ""),
                    "workspace": node.get("workspace", ""),
                })
            for child in node.get("nodes", []) + node.get("floating_nodes", []):
                _find_windows(child)
        _find_windows(tree)
        return {"ok": True, "windows": windows, "count": len(windows)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def action_focus_workspace(number: int, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _i3_msg(f"workspace number {number}")
    return {"ok": r["exit"] == 0, "workspace": number}


def action_move_to_workspace(number: int, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _i3_msg(f"move container to workspace number {number}")
    return {"ok": r["exit"] == 0}


def action_open_app(app: str, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _run(f"nohup {app} &>/dev/null &")
    return {"ok": True, "app": app}


def action_close_window(user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _i3_msg("kill")
    return {"ok": r["exit"] == 0}


def action_fullscreen(user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _i3_msg("fullscreen toggle")
    return {"ok": r["exit"] == 0}


def action_split(horizontal: bool = True, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    direction = "horizontal" if horizontal else "vertical"
    r = _i3_msg(f"split {direction}")
    return {"ok": r["exit"] == 0}


def action_layout(mode: str = "toggle", user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _i3_msg(f"layout {mode}")
    return {"ok": r["exit"] == 0}


def action_floating_toggle(user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _i3_msg("floating toggle")
    return {"ok": r["exit"] == 0}


def action_resize(direction: str, pixels: int, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _i3_msg(f"resize grow {direction} {pixels} px")
    return {"ok": r["exit"] == 0}


def action_reload_i3(user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _i3_msg("reload")
    return {"ok": r["exit"] == 0}


def action_restart_i3(user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _i3_msg("restart")
    return {"ok": r["exit"] == 0}


def action_workspace_info(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("i3-msg -t get_workspaces")
    focused = _run("i3-msg -t get_workspaces | python3 -c \"import sys,json; ws=json.load(sys.stdin); print([w['name'] for w in ws if w['focused']][0])\"")
    return {"ok": True, "focused": focused["stdout"], "workspaces_raw": r["stdout"][:500]}


def action_run_command(command: str, user: str = OWNER_USER) -> Dict[str, Any]:
    """Run arbitrary i3 command. Owner only."""
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    # Sanitize: only allow i3 commands
    blocked = ["exec", "reload", "restart", "exit"]
    cmd_lower = command.strip().lower()
    for b in blocked:
        if cmd_lower.startswith(b):
            return {"ok": False, "error": f"Command '{b}' is not allowed via this endpoint"}
    r = _i3_msg(command)
    return {"ok": r["exit"] == 0, "output": r["stdout"][:200]}


# ═══════════════════════════════════════════════════════════════════════════════
# DISPATCH
# ═══════════════════════════════════════════════════════════════════════════════

ACTIONS = {
    "list_workspaces":   lambda p, u: action_list_workspaces(u),
    "list_windows":      lambda p, u: action_list_windows(u),
    "focus_workspace":   lambda p, u: action_focus_workspace(int(p.get("number", 1)), u),
    "move_to_workspace": lambda p, u: action_move_to_workspace(int(p.get("number", 1)), u),
    "open_app":          lambda p, u: action_open_app(p.get("app", ""), u),
    "close_window":      lambda p, u: action_close_window(u),
    "fullscreen":        lambda p, u: action_fullscreen(u),
    "split":             lambda p, u: action_split(p.get("horizontal", "true").lower() == "true", u),
    "layout":            lambda p, u: action_layout(p.get("mode", "toggle"), u),
    "floating_toggle":   lambda p, u: action_floating_toggle(u),
    "resize":            lambda p, u: action_resize(p.get("direction", "right"), int(p.get("pixels", "20")), u),
    "reload_i3":         lambda p, u: action_reload_i3(u),
    "restart_i3":        lambda p, u: action_restart_i3(u),
    "workspace_info":    lambda p, u: action_workspace_info(u),
    "run_command":       lambda p, u: action_run_command(p.get("command", ""), u),
}


def dispatch(action: str, params: Dict[str, Any], user: str = OWNER_USER) -> Dict[str, Any]:
    fn = ACTIONS.get(action)
    if not fn:
        return {"ok": False, "error": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}"}
    try:
        return fn(params, user)
    except Exception as e:
        return {"ok": False, "error": str(e)}
