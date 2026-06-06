#!/usr/bin/env python3
"""
Monitor Agent — logs, system metrics, alerting, cron jobs.
Read-only for all users.
"""

import subprocess
import os
import json
from typing import Dict, Any, Optional
from datetime import datetime

OWNER_USER = "Bayazid"
ALERT_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "storage", "alerts.json")


def _run(cmd: str, timeout: int = 30) -> Dict[str, Any]:
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return {"exit": r.returncode, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"exit": -1, "stdout": "", "stderr": f"Timeout ({timeout}s)"}
    except Exception as e:
        return {"exit": -1, "stdout": "", "stderr": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIONS (all read-only)
# ═══════════════════════════════════════════════════════════════════════════════

def action_cpu_info(user: str = OWNER_USER) -> Dict[str, Any]:
    load = _run("cat /proc/loadavg")
    stat = _run("grep 'cpu ' /proc/stat")
    cores = _run("nproc")
    return {
        "ok": True,
        "load_avg": load["stdout"],
        "cores": cores["stdout"],
        "cpu_line": stat["stdout"][:200],
    }


def action_memory_info(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("free -h")
    vmstat = _run("vmstat 1 2 | tail -1")
    return {"ok": True, "memory": r["stdout"], "vmstat": vmstat["stdout"]}


def action_disk_info(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("df -h")
    inode = _run("df -i | head -5")
    return {"ok": True, "disk": r["stdout"], "inodes": inode["stdout"]}


def action_top_processes(user: str = OWNER_USER, sort_by: str = "mem", count: int = 10) -> Dict[str, Any]:
    sort_flag = "%mem" if sort_by == "mem" else "%cpu"
    r = _run(f"ps aux --sort=-{sort_flag} | head -{count + 1}")
    procs = []
    lines = r["stdout"].splitlines()
    if lines:
        header = lines[0]
        for line in lines[1:]:
            parts = line.split(None, 10)
            if len(parts) >= 11:
                procs.append({
                    "user": parts[0], "pid": parts[1],
                    "cpu%": parts[2], "mem%": parts[3],
                    "command": parts[10][:120],
                })
    return {"ok": True, "processes": procs, "sort_by": sort_by}


def action_system_logs(lines: int = 50, user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run(f"journalctl --no-pager -n {lines} --output=short-iso")
    return {"ok": True, "logs": r["stdout"]}


def action_service_logs(service: str, lines: int = 50, user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run(f"journalctl -u {service} --no-pager -n {lines} --output=short-iso")
    return {"ok": True, "service": service, "logs": r["stdout"]}


def action_kernel_messages(lines: int = 30, user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run(f"dmesg --time-format=iso 2>/dev/null | tail -{lines} || dmesg | tail -{lines}")
    return {"ok": True, "messages": r["stdout"]}


def action_list_cron(user: str = OWNER_USER) -> Dict[str, Any]:
    system = _run("ls /etc/cron.d/ 2>/dev/null")
    user_cron = _run("crontab -l 2>/dev/null || echo 'no crontab'")
    timers = _run("systemctl list-timers --no-pager --no-legend | head -20")
    return {
        "ok": True,
        "system_cron": system["stdout"],
        "user_cron": user_cron["stdout"],
        "systemd_timers": timers["stdout"],
    }


def action_log_search(query: str, lines: int = 100, user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run(f"journalctl --no-pager -n {lines} 2>/dev/null | grep -i '{query}' | tail -30")
    matches = [l for l in r["stdout"].splitlines() if l.strip()]
    return {"ok": True, "query": query, "matches": matches, "count": len(matches)}


def action_alerts(user: str = OWNER_USER) -> Dict[str, Any]:
    """Get recent alerts from the monitor."""
    if not os.path.exists(ALERT_LOG):
        return {"ok": True, "alerts": [], "count": 0}
    try:
        with open(ALERT_LOG) as f:
            alerts = json.load(f)
        return {"ok": True, "alerts": alerts[-20:], "count": len(alerts)}
    except Exception:
        return {"ok": True, "alerts": [], "count": 0}


def action_record_alert(severity: str, message: str, user: str = OWNER_USER) -> Dict[str, Any]:
    """Record an alert (for health_check.py to use)."""
    os.makedirs(os.path.dirname(ALERT_LOG), exist_ok=True)
    alerts = []
    if os.path.exists(ALERT_LOG):
        try:
            with open(ALERT_LOG) as f:
                alerts = json.load(f)
        except Exception:
            pass
    alerts.append({
        "severity": severity,
        "message": message,
        "ts": datetime.now().isoformat(),
    })
    alerts = alerts[-500:]  # keep last 500
    with open(ALERT_LOG, "w") as f:
        json.dump(alerts, f, indent=2)
    return {"ok": True, "recorded": severity}


def action_uptime_detail(user: str = OWNER_USER) -> Dict[str, Any]:
    up = _run("uptime -p")
    since = _run("uptime -s")
    who = _run("who")
    return {
        "ok": True,
        "uptime": up["stdout"],
        "since": since["stdout"],
        "logged_in": who["stdout"],
    }


def action_full_report(user: str = OWNER_USER) -> Dict[str, Any]:
    """Combined system report."""
    cpu = action_cpu_info(user)
    mem = action_memory_info(user)
    disk = action_disk_info(user)
    procs = action_top_processes(user, count=5)
    up = action_uptime_detail(user)
    return {
        "ok": True,
        "cpu": cpu,
        "memory": mem,
        "disk": disk,
        "top_processes": procs,
        "uptime": up,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DISPATCH
# ═══════════════════════════════════════════════════════════════════════════════

ACTIONS = {
    "cpu_info":         lambda p, u: action_cpu_info(u),
    "memory_info":      lambda p, u: action_memory_info(u),
    "disk_info":        lambda p, u: action_disk_info(u),
    "top_processes":    lambda p, u: action_top_processes(u, p.get("sort_by", "mem"), int(p.get("count", 10))),
    "system_logs":      lambda p, u: action_system_logs(int(p.get("lines", 50)), u),
    "service_logs":     lambda p, u: action_service_logs(p.get("service", ""), int(p.get("lines", 50)), u),
    "kernel_messages":  lambda p, u: action_kernel_messages(int(p.get("lines", 30)), u),
    "list_cron":        lambda p, u: action_list_cron(u),
    "log_search":       lambda p, u: action_log_search(p.get("query", ""), int(p.get("lines", 100)), u),
    "alerts":           lambda p, u: action_alerts(u),
    "record_alert":     lambda p, u: action_record_alert(p.get("severity", "info"), p.get("message", ""), u),
    "uptime_detail":    lambda p, u: action_uptime_detail(u),
    "full_report":      lambda p, u: action_full_report(u),
}


def dispatch(action: str, params: Dict[str, Any], user: str = OWNER_USER) -> Dict[str, Any]:
    fn = ACTIONS.get(action)
    if not fn:
        return {"ok": False, "error": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}"}
    try:
        return fn(params, user)
    except Exception as e:
        return {"ok": False, "error": str(e)}
