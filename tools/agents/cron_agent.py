#!/usr/bin/env python3
"""
Cron Agent — Scheduled tasks, recurring jobs, timed actions.
Marin's scheduler. Manages timers, cron jobs, and recurring tasks.
"""

import os
import json
import subprocess
from typing import Dict, Any, List
from datetime import datetime, timedelta

STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "storage")
SCHEDULE_FILE = os.path.join(STORAGE_DIR, "scheduled_tasks.json")

OWNER_USER = "Bayazid"


def _load_tasks() -> List[Dict]:
    if os.path.exists(SCHEDULE_FILE):
        try:
            return json.loads(open(SCHEDULE_FILE).read())
        except Exception:
            pass
    return []


def _save_tasks(tasks: List[Dict]):
    os.makedirs(STORAGE_DIR, exist_ok=True)
    with open(SCHEDULE_FILE, "w") as f:
        json.dump(tasks, f, indent=2)


def action_add_task(command: str, interval_seconds: int = 3600, name: str = "",
                    max_runs: int = -1, user: str = OWNER_USER) -> Dict[str, Any]:
    """Add a scheduled task."""
    if user != OWNER_USER:
        return {"ok": False, "error": "Only Bayazid can create scheduled tasks."}
    tasks = _load_tasks()
    task_id = f"TASK-{len(tasks) + 1:04d}"
    entry = {
        "id": task_id,
        "name": name or command[:50],
        "command": command,
        "interval": interval_seconds,
        "max_runs": max_runs,
        "runs": 0,
        "created": datetime.now().isoformat(),
        "last_run": None,
        "next_run": datetime.now().isoformat(),
        "enabled": True,
    }
    tasks.append(entry)
    _save_tasks(tasks)
    return {"ok": True, "task_id": task_id, "next_run": entry["next_run"]}


def action_remove_task(task_id: str, user: str = OWNER_USER) -> Dict[str, Any]:
    """Remove a scheduled task."""
    if user != OWNER_USER:
        return {"ok": False, "error": "Only Bayazid can remove scheduled tasks."}
    tasks = _load_tasks()
    before = len(tasks)
    tasks = [t for t in tasks if t["id"] != task_id]
    if len(tasks) == before:
        return {"ok": False, "error": f"Task not found: {task_id}"}
    _save_tasks(tasks)
    return {"ok": True, "removed": task_id}


def action_list_tasks(user: str = OWNER_USER) -> Dict[str, Any]:
    """List all scheduled tasks."""
    tasks = _load_tasks()
    return {"ok": True, "tasks": tasks, "count": len(tasks)}


def action_toggle_task(task_id: str, enabled: bool, user: str = OWNER_USER) -> Dict[str, Any]:
    """Enable or disable a scheduled task."""
    if user != OWNER_USER:
        return {"ok": False, "error": "Only Bayazid can toggle scheduled tasks."}
    tasks = _load_tasks()
    for t in tasks:
        if t["id"] == task_id:
            t["enabled"] = enabled
            _save_tasks(tasks)
            return {"ok": True, "task_id": task_id, "enabled": enabled}
    return {"ok": False, "error": f"Task not found: {task_id}"}


def action_run_task(task_id: str, user: str = OWNER_USER) -> Dict[str, Any]:
    """Manually trigger a scheduled task."""
    if user != OWNER_USER:
        return {"ok": False, "error": "Only Bayazid can run scheduled tasks."}
    tasks = _load_tasks()
    for t in tasks:
        if t["id"] == task_id:
            try:
                r = subprocess.run(
                    t["command"], shell=False, capture_output=True, text=True, timeout=60
                )
                t["runs"] += 1
                t["last_run"] = datetime.now().isoformat()
                _save_tasks(tasks)
                return {
                    "ok": True, "task_id": task_id,
                    "exit": r.returncode,
                    "output": (r.stdout + r.stderr).strip()[:500],
                }
            except subprocess.TimeoutExpired:
                return {"ok": False, "error": "Task timed out (60s)"}
            except Exception as e:
                return {"ok": False, "error": str(e)}
    return {"ok": False, "error": f"Task not found: {task_id}"}


def action_add_cron(expression: str, command: str, name: str = "", user: str = OWNER_USER) -> Dict[str, Any]:
    """Add a cron-style scheduled task (for system cron integration)."""
    if user != OWNER_USER:
        return {"ok": False, "error": "Only Bayazid can create cron jobs."}
    cron_line = f"{expression} {command}  # marin:{name or 'task'}"
    try:
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True
        )
        existing = result.stdout if result.returncode == 0 else ""
        new_cron = existing.rstrip() + "\n" + cron_line + "\n"
        subprocess.run(
            ["crontab", "-"], input=new_cron, capture_output=True, text=True
        )
        return {"ok": True, "cron_line": cron_line, "message": "Added to system cron"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


ACTIONS = {
    "add_task": lambda p, u: action_add_task(
        p.get("command", ""), int(p.get("interval", 3600)),
        p.get("name", ""), int(p.get("max_runs", -1)), u),
    "remove_task": lambda p, u: action_remove_task(p.get("task_id", ""), u),
    "list_tasks": lambda p, u: action_list_tasks(u),
    "toggle_task": lambda p, u: action_toggle_task(p.get("task_id", ""), p.get("enabled", True), u),
    "run_task": lambda p, u: action_run_task(p.get("task_id", ""), u),
    "add_cron": lambda p, u: action_add_cron(
        p.get("expression", "0 * * * *"), p.get("command", ""),
        p.get("name", ""), u),
}


def dispatch(action: str, params: Dict[str, Any], user: str = OWNER_USER) -> Dict[str, Any]:
    fn = ACTIONS.get(action)
    if not fn:
        return {"ok": False, "error": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}"}
    try:
        return fn(params, user)
    except Exception as e:
        return {"ok": False, "error": str(e)}
