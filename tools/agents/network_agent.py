#!/usr/bin/env python3
"""
Network Agent — interfaces, connections, firewall, DNS.
Guests: read-only. Owner: full control.
"""

import subprocess
import re
from typing import Dict, Any, Optional
from datetime import datetime

OWNER_USER = "Bayazid"


def _run(cmd: str, timeout: int = 30) -> Dict[str, Any]:
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return {"exit": r["returncode"], "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"exit": -1, "stdout": "", "stderr": f"Timeout ({timeout}s)"}
    except Exception as e:
        return {"exit": -1, "stdout": "", "stderr": str(e)}


def _check_owner(user: str) -> Optional[str]:
    if user != OWNER_USER:
        return "DENIED: Only Bayazid can perform this action."
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def action_list_interfaces(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("ip -o link show | awk -F': ' '{print $2}'")
    interfaces = [i.strip() for i in r["stdout"].splitlines() if i.strip()]
    result = []
    for iface in interfaces:
        addr = _run(f"ip -4 addr show dev {iface} | grep inet | awk '{{print $2}}'")
        state = _run(f"cat /sys/class/net/{iface}/operstate 2>/dev/null || echo unknown")
        result.append({
            "name": iface,
            "state": state["stdout"],
            "ipv4": addr["stdout"] or "none",
        })
    return {"ok": True, "interfaces": result}


def action_ip_address(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("ip -4 addr show")
    return {"ok": True, "output": r["stdout"]}


def action_default_gateway(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("ip route | grep default")
    return {"ok": True, "gateway": r["stdout"]}


def action_dns_servers(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("cat /etc/resolv.conf | grep nameserver")
    servers = []
    for line in r["stdout"].splitlines():
        parts = line.split()
        if len(parts) >= 2:
            servers.append(parts[1])
    return {"ok": True, "dns_servers": servers}


def action_ping(host: str, count: int = 4, user: str = OWNER_USER) -> Dict[str, Any]:
    safe = re.match(r'^[a-zA-Z0-9._-]+$', host)
    if not safe:
        return {"ok": False, "error": "Invalid hostname"}
    r = _run(f"ping -c {count} -W 3 {host}")
    return {"ok": r["exit"] == 0, "host": host, "output": r["stdout"] or r["stderr"]}


def action_open_ports(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("ss -tlnp | tail -n +2")
    ports = []
    for line in r["stdout"].splitlines():
        parts = line.split()
        if len(parts) >= 6:
            ports.append({
                "local": parts[3],
                "process": parts[5] if len(parts) > 5 else "",
            })
    return {"ok": True, "listening": ports, "count": len(ports)}


def action_established_connections(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("ss -tnp state established | tail -n +2")
    conns = []
    for line in r["stdout"].splitlines():
        parts = line.split()
        if len(parts) >= 5:
            conns.append({
                "local": parts[3],
                "remote": parts[4],
                "process": parts[5] if len(parts) > 5 else "",
            })
    return {"ok": True, "connections": conns[:50], "count": len(conns)}


def action_wifi_scan(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("nmcli -t -f SSID,SIGNAL,SECURITY dev wifi list 2>/dev/null || echo 'nmcli not available'")
    networks = []
    for line in r["stdout"].splitlines():
        parts = line.split(":")
        if len(parts) >= 2:
            networks.append({
                "ssid": parts[0],
                "signal": parts[1] + "%" if len(parts) > 1 else "",
                "security": parts[2] if len(parts) > 2 else "",
            })
    return {"ok": True, "networks": networks[:20]}


def action_block_host(host: str, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    safe = re.match(r'^[a-zA-Z0-9._-]+$', host)
    if not safe:
        return {"ok": False, "error": "Invalid hostname"}
    r = _run(f"sudo iptables -A OUTPUT -d {host} -j DROP")
    return {"ok": r["exit"] == 0, "blocked": host, "output": r["stdout"] or r["stderr"]}


def action_network_stats(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("cat /proc/net/dev | tail -n +3")
    stats = []
    for line in r["stdout"].splitlines():
        parts = line.split()
        if len(parts) >= 10:
            iface = parts[0].rstrip(":")
            stats.append({
                "interface": iface,
                "rx_bytes": int(parts[1]),
                "tx_bytes": int(parts[9]),
                "rx_mb": round(int(parts[1]) / 1048576, 2),
                "tx_mb": round(int(parts[9]) / 1048576, 2),
            })
    return {"ok": True, "stats": stats}


def action_public_ip(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("curl -s --max-time 5 ifconfig.me || curl -s --max-time 5 icanhazip.com")
    return {"ok": True, "public_ip": r["stdout"]}


# ═══════════════════════════════════════════════════════════════════════════════
# DISPATCH
# ═══════════════════════════════════════════════════════════════════════════════

ACTIONS = {
    "list_interfaces":       lambda p, u: action_list_interfaces(u),
    "ip_address":            lambda p, u: action_ip_address(u),
    "default_gateway":       lambda p, u: action_default_gateway(u),
    "dns_servers":           lambda p, u: action_dns_servers(u),
    "ping":                  lambda p, u: action_ping(p.get("host", "1.1.1.1"), int(p.get("count", 4)), u),
    "open_ports":            lambda p, u: action_open_ports(u),
    "established_connections": lambda p, u: action_established_connections(u),
    "wifi_scan":             lambda p, u: action_wifi_scan(u),
    "block_host":            lambda p, u: action_block_host(p.get("host", ""), u),
    "network_stats":         lambda p, u: action_network_stats(u),
    "public_ip":             lambda p, u: action_public_ip(u),
}


def dispatch(action: str, params: Dict[str, Any], user: str = OWNER_USER) -> Dict[str, Any]:
    fn = ACTIONS.get(action)
    if not fn:
        return {"ok": False, "error": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}"}
    try:
        return fn(params, user)
    except Exception as e:
        return {"ok": False, "error": str(e)}
