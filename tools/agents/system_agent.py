#!/usr/bin/env python3
"""
System Agent — service management, process control, system health.
Only Bayazid can run destructive operations. Guests get read-only.
"""

import subprocess
import os
import time
from typing import Dict, Any, Optional
from datetime import datetime

OWNER_USER = "Bayazid"

SYSTEMD_SERVICES = {
    "ollama":      "ollama.service",
    "marin":       "marin.service",
    "marin-web":   "marin-web.service",
    "rag":         "rag.service",
    "command-api": "command-api.service",
    "lightdm":     "lightdm.service",
    "network":     "NetworkManager.service",
    "ssh":         "ssh.service",
    "docker":      "docker.service",
    "cron":        "cron.service",
}


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


def _resolve_service(name: str) -> str:
    """Resolve friendly service name to systemd unit."""
    return SYSTEMD_SERVICES.get(name, name)


def _check_owner(user: str) -> Optional[str]:
    """Returns error message if user is not owner, None if ok."""
    if user != OWNER_USER:
        return "DENIED: Only Bayazid can perform this action."
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def action_restart_service(service: str, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    unit = _resolve_service(service)
    r = _run(f"sudo systemctl restart {unit}")
    return {"ok": r["exit"] == 0, "service": unit, "output": r["stdout"] or r["stderr"]}


def action_stop_service(service: str, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    unit = _resolve_service(service)
    r = _run(f"sudo systemctl stop {unit}")
    return {"ok": r["exit"] == 0, "service": unit, "output": r["stdout"] or r["stderr"]}


def action_start_service(service: str, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    unit = _resolve_service(service)
    r = _run(f"sudo systemctl start {unit}")
    return {"ok": r["exit"] == 0, "service": unit, "output": r["stdout"] or r["stderr"]}


def action_status_service(service: str, user: str = OWNER_USER) -> Dict[str, Any]:
    unit = _resolve_service(service)
    r = _run(f"systemctl is-active {unit}")
    is_active = r["stdout"] == "active"
    info = _run(f"systemctl show {unit} --property=ActiveState,SubState,MainPID,MemoryCurrent")
    return {"ok": True, "service": unit, "active": is_active, "info": info["stdout"]}


def action_list_services(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("systemctl list-units --type=service --state=running --no-pager --no-legend")
    services = []
    for line in r["stdout"].splitlines():
        parts = line.split()
        if len(parts) >= 4:
            services.append({"name": parts[0], "load": parts[1], "active": parts[2], "sub": parts[3]})
    return {"ok": True, "services": services, "count": len(services)}


def action_kill_process(pid: int, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _run(f"sudo kill {pid}")
    return {"ok": r["exit"] == 0, "pid": pid, "output": r["stdout"] or r["stderr"]}


def action_list_processes(filter_user: str = None, user: str = OWNER_USER) -> Dict[str, Any]:
    cmd = "ps aux --sort=-%mem"
    if filter_user:
        cmd = f"ps aux --user={filter_user} --sort=-%mem"
    r = _run(cmd)
    procs = []
    for line in r["stdout"].splitlines()[1:20]:  # top 20
        parts = line.split(None, 10)
        if len(parts) >= 11:
            procs.append({
                "user": parts[0], "pid": parts[1],
                "cpu": parts[2], "mem": parts[3],
                "command": parts[10][:100],
            })
    return {"ok": True, "processes": procs}


def action_system_health(user: str = OWNER_USER) -> Dict[str, Any]:
    uptime = _run("uptime -p")
    disk = _run("df -h / --output=target,size,used,avail,pcent | tail -1")
    mem = _run("free -h | grep Mem")
    load = _run("cat /proc/loadavg")
    temp = _run("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo N/A")

    temp_val = temp["stdout"]
    if temp_val and temp_val != "N/A":
        try:
            temp_val = f"{int(temp_val) / 1000:.1f}°C"
        except ValueError:
            pass

    return {
        "ok": True,
        "uptime": uptime["stdout"],
        "disk_root": disk["stdout"],
        "memory": mem["stdout"],
        "load_avg": load["stdout"],
        "cpu_temp": temp_val,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def action_journal(service: str, lines: int = 30, user: str = OWNER_USER) -> Dict[str, Any]:
    unit = _resolve_service(service)
    r = _run(f"journalctl -u {unit} --no-pager -n {lines}")
    return {"ok": True, "service": unit, "logs": r["stdout"]}


def action_uptime(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("uptime -p && uptime -s")
    return {"ok": True, "uptime": r["stdout"]}


# ═══════════════════════════════════════════════════════════════════════════════
# DISPATCH
# ═══════════════════════════════════════════════════════════════════════════════

ACTIONS = {
    "restart_service":    lambda p, u: action_restart_service(p.get("service", ""), u),
    "stop_service":       lambda p, u: action_stop_service(p.get("service", ""), u),
    "start_service":      lambda p, u: action_start_service(p.get("service", ""), u),
    "status_service":     lambda p, u: action_status_service(p.get("service", ""), u),
    "list_services":      lambda p, u: action_list_services(u),
    "kill_process":       lambda p, u: action_kill_process(int(p.get("pid", 0)), u),
    "list_processes":     lambda p, u: action_list_processes(p.get("user"), u),
    "system_health":      lambda p, u: action_system_health(u),
    "journal":            lambda p, u: action_journal(p.get("service", ""), int(p.get("lines", 30)), u),
    "uptime":             lambda p, u: action_uptime(u),
}


def dispatch(action: str, params: Dict[str, Any], user: str = OWNER_USER) -> Dict[str, Any]:
    fn = ACTIONS.get(action)
    if not fn:
        return {"ok": False, "error": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}"}
    try:
        return fn(params, user)
    except Exception as e:
        return {"ok": False, "error": str(e)}
