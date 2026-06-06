#!/usr/bin/env python3
"""
Agent Dispatcher — central routing for all Marin agents.
Parses structured agent commands and routes to the correct agent.

Trigger format:
  [AGENT: <agent_name> | action: <action_name> | key: value | ...]

Examples:
  [AGENT: system | action: restart_service | service: ollama]
  [AGENT: network | action: ping | host: 1.1.1.1]
  [AGENT: file | action: read_file | path: /etc/hostname]
  [AGENT: monitor | action: full_report]
"""

import re
import json
import time
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

OWNER_USER = "Bayazid"

# ═══════════════════════════════════════════════════════════════════════════════
# AGENT REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

AGENTS = {
    "system": {
        "module": "tools.agents.system_agent",
        "description": "Service management, process control, system health",
        "actions": [
            "restart_service", "stop_service", "start_service", "status_service",
            "list_services", "kill_process", "list_processes", "system_health",
            "journal", "uptime",
        ],
    },
    "network": {
        "module": "tools.agents.network_agent",
        "description": "Interfaces, connections, firewall, DNS, WiFi",
        "actions": [
            "list_interfaces", "ip_address", "default_gateway", "dns_servers",
            "ping", "open_ports", "established_connections", "wifi_scan",
            "block_host", "network_stats", "public_ip",
        ],
    },
    "file": {
        "module": "tools.agents.file_agent",
        "description": "File read/write/copy/move/delete, permissions, disk usage",
        "actions": [
            "read_file", "write_file", "list_dir", "file_info",
            "copy", "move", "delete", "chmod", "disk_usage", "find_files",
        ],
    },
    "package": {
        "module": "tools.agents.package_agent",
        "description": "apt, pip, system updates",
        "actions": [
            "search", "info", "list_installed", "install", "remove",
            "update", "upgrade", "pip_list", "pip_install", "apt_clean",
            "check_updates",
        ],
    },
    "monitor": {
        "module": "tools.agents.monitor_agent",
        "description": "Logs, metrics, alerts, system reports",
        "actions": [
            "cpu_info", "memory_info", "disk_info", "top_processes",
            "system_logs", "service_logs", "kernel_messages", "list_cron",
            "log_search", "alerts", "record_alert", "uptime_detail", "full_report",
        ],
    },
    "desktop": {
        "module": "tools.agents.desktop_agent",
        "description": "i3 window manager control, workspaces, windows, layout",
        "actions": [
            "list_workspaces", "list_windows", "focus_workspace",
            "move_to_workspace", "open_app", "close_window", "fullscreen",
            "split", "layout", "floating_toggle", "resize",
            "reload_i3", "restart_i3", "workspace_info", "run_command",
        ],
    },
    "memory": {
        "module": "tools.agents.memory_agent",
        "description": "Long-term memory, facts, preferences, observations",
        "actions": [
            "remember", "recall", "forget", "log_conversation",
            "observe", "stats",
        ],
    },
    "security": {
        "module": "tools.agents.security_agent",
        "description": "Intrusion detection, audit logs, breach monitoring, system scan",
        "actions": [
            "log_attempt", "log_breach", "check_intruder",
            "get_audit_log", "get_breach_report", "scan_system",
        ],
    },
    "cron": {
        "module": "tools.agents.cron_agent",
        "description": "Scheduled tasks, recurring jobs, timers, cron jobs",
        "actions": [
            "add_task", "remove_task", "list_tasks", "toggle_task",
            "run_task", "add_cron",
        ],
    },
    "intel": {
        "module": "tools.agents.intelligence_agent",
        "description": "Web scraping, news search, weather, IP info, URL monitoring",
        "actions": [
            "scrape_url", "search_news", "check_weather",
            "get_ip_info", "monitor_url", "extract_links",
        ],
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# PARSER
# ═══════════════════════════════════════════════════════════════════════════════

_AGENT_PATTERN = re.compile(
    r'\[AGENT:\s*(\w+)\s*\|(.+?)\]',
    re.IGNORECASE | re.DOTALL
)

_PARAM_PATTERN = re.compile(
    r'(\w+)\s*:\s*([^|]+)'
)


def parse_agent_command(text: str) -> list[Tuple[str, Dict[str, str]]]:
    """Extract all agent commands from text. Returns list of (agent, params)."""
    commands = []
    for match in _AGENT_PATTERN.finditer(text):
        agent = match.group(1).lower()
        raw_params = match.group(2)
        params = {}
        for pm in _PARAM_PATTERN.finditer(raw_params):
            key = pm.group(1).strip().lower()
            value = pm.group(2).strip()
            params[key] = value
        commands.append((agent, params))
    return commands


def _load_agent(agent_name: str):
    """Dynamic import of agent module."""
    info = AGENTS.get(agent_name)
    if not info:
        return None
    import importlib
    try:
        mod = importlib.import_module(info["module"])
        return mod
    except ImportError as e:
        print(f"[Dispatcher] Failed to load agent '{agent_name}': {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# DISPATCH LOG
# ═══════════════════════════════════════════════════════════════════════════════

AGENT_LOG = []  # circular buffer of last 200 dispatches


def _log_dispatch(agent: str, action: str, params: dict, result: dict, user: str or dict, elapsed_ms: float):
    user_name = user["username"] if isinstance(user, dict) else user
    entry = {
        "agent": agent,
        "action": action,
        "params": params,
        "ok": result.get("ok", False),
        "user": user_name,
        "ts": datetime.now().strftime("%H:%M:%S"),
        "elapsed_ms": round(elapsed_ms, 1),
    }
    AGENT_LOG.append(entry)
    if len(AGENT_LOG) > 200:
        AGENT_LOG.pop(0)


def get_agent_log(limit: int = 20) -> list:
    return AGENT_LOG[-limit:]


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN DISPATCH
# ═══════════════════════════════════════════════════════════════════════════════

def dispatch_single(agent: str, action: str, params: Dict[str, str], user: str or dict = OWNER_USER) -> Dict[str, Any]:
    """Dispatch a single agent action. Returns the result dict."""
    mod = _load_agent(agent)
    if not mod:
        return {"ok": False, "error": f"Unknown agent: '{agent}'. Available: {list(AGENTS.keys())}"}

    # Convert string params to proper types where needed
    clean_params = {}
    for k, v in params.items():
        if k in ("append",):
            clean_params[k] = v.lower() in ("true", "1", "yes")
        elif k in ("count", "limit", "lines", "offset", "max"):
            try:
                clean_params[k] = int(v)
            except ValueError:
                clean_params[k] = v
        else:
            clean_params[k] = v

    t0 = time.time()
    result = mod.dispatch(action, clean_params, user=user)
    elapsed = (time.time() - t0) * 1000

    _log_dispatch(agent, action, clean_params, result, user, elapsed)
    return result


def dispatch_all(text: str, user: str or dict = OWNER_USER) -> list[Dict[str, Any]]:
    """Find all agent commands in text, dispatch them, return results."""
    commands = parse_agent_command(text)
    results = []
    for agent, params in commands:
        action = params.pop("action", "unknown")
        result = dispatch_single(agent, action, params, user)
        results.append({
            "agent": agent,
            "action": action,
            "result": result,
        })
    return results


def dispatch_from_text(text: str, user: str or dict = OWNER_USER) -> str:
    """Parse text, execute agents, return a formatted summary string."""
    results = dispatch_all(text, user)
    if not results:
        return ""

    lines = []
    for r in results:
        agent = r["agent"]
        action = r["action"]
        res = r["result"]
        ok = res.get("ok", False)
        status = "[OK]" if ok else "[FAIL]"
        lines.append(f"[AGENT:{agent}] {action} {status}")

        if ok:
            # Summarize the result
            for k, v in res.items():
                if k == "ok":
                    continue
                if isinstance(v, list):
                    lines.append(f"  {k}: {len(v)} items")
                elif isinstance(v, str) and len(v) > 200:
                    lines.append(f"  {k}: {v[:200]}...")
                else:
                    lines.append(f"  {k}: {v}")
        else:
            lines.append(f"  error: {res.get('error', 'unknown')}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# HELP
# ═══════════════════════════════════════════════════════════════════════════════

def list_agents() -> str:
    """Return a help string listing all agents and their actions."""
    lines = ["AVAILABLE AGENTS:"]
    for name, info in AGENTS.items():
        lines.append(f"\n  [{name}] — {info['description']}")
        lines.append(f"    actions: {', '.join(info['actions'])}")
    lines.append("\nTRIGGER FORMAT:")
    lines.append("  [AGENT: <name> | action: <action> | key: value | ...]")
    lines.append("\nEXAMPLES:")
    lines.append("  [AGENT: system | action: system_health]")
    lines.append("  [AGENT: network | action: ping | host: 1.1.1.1]")
    lines.append("  [AGENT: file | action: read_file | path: /etc/hostname]")
    lines.append("  [AGENT: monitor | action: full_report]")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        result = dispatch_from_text(text, user=OWNER_USER)
        print(result)
    else:
        print(list_agents())
