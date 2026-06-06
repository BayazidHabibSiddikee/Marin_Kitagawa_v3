#!/usr/bin/env python3
"""
Package Agent — apt, pip, system updates.
Only Bayazid can install/remove. Guests can query.
"""

import subprocess
from typing import Dict, Any, Optional
from datetime import datetime

OWNER_USER = "Bayazid"


def _run(cmd: str, timeout: int = 120) -> Dict[str, Any]:
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
        return "DENIED: Only Bayazid can modify packages."
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def action_search(query: str, user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run(f"apt-cache search {query} 2>/dev/null | head -20")
    results = []
    for line in r["stdout"].splitlines():
        parts = line.split(" - ", 1)
        if len(parts) == 2:
            results.append({"package": parts[0].strip(), "description": parts[1].strip()})
    return {"ok": True, "query": query, "results": results, "count": len(results)}


def action_info(package: str, user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run(f"apt-cache show {package} 2>/dev/null | head -30")
    if r["exit"] != 0:
        return {"ok": False, "error": f"Package not found: {package}"}
    installed = _run(f"dpkg -l {package} 2>/dev/null | grep '^ii'")
    return {
        "ok": True, "package": package,
        "info": r["stdout"],
        "installed": bool(installed["stdout"]),
    }


def action_list_installed(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("dpkg -l | grep '^ii' | awk '{print $2, $3}'")
    packages = []
    for line in r["stdout"].splitlines():
        parts = line.split()
        if len(parts) >= 2:
            packages.append({"name": parts[0], "version": parts[1]})
    return {"ok": True, "packages": packages, "count": len(packages)}


def action_install(package: str, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _run(f"sudo apt-get install -y {package}", timeout=180)
    return {"ok": r["exit"] == 0, "package": package, "output": r["stdout"][-500:] or r["stderr"][-500:]}


def action_remove(package: str, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _run(f"sudo apt-get remove -y {package}", timeout=180)
    return {"ok": r["exit"] == 0, "package": package, "output": r["stdout"][-500:] or r["stderr"][-500:]}


def action_update(user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _run("sudo apt-get update", timeout=120)
    return {"ok": r["exit"] == 0, "output": r["stdout"][-500:] or r["stderr"][-500:]}


def action_upgrade(user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _run("sudo apt-get upgrade -y", timeout=300)
    return {"ok": r["exit"] == 0, "output": r["stdout"][-500:] or r["stderr"][-500:]}


def action_pip_list(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("pip3 list --format=json 2>/dev/null || pip list --format=json 2>/dev/null")
    try:
        import json
        packages = json.loads(r["stdout"])
        return {"ok": True, "packages": packages, "count": len(packages)}
    except Exception:
        return {"ok": True, "raw": r["stdout"][:2000]}


def action_pip_install(package: str, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _run(f"pip3 install {package}", timeout=180)
    return {"ok": r["exit"] == 0, "package": package, "output": r["stdout"][-500:] or r["stderr"][-500:]}


def action_apt_clean(user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    r = _run("sudo apt-get autoremove -y && sudo apt-get clean")
    return {"ok": r["exit"] == 0, "output": r["stdout"][-300:] or r["stderr"][-300:]}


def action_check_updates(user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run("apt list --upgradable 2>/dev/null | head -20")
    updates = [l for l in r["stdout"].splitlines() if "/" in l]
    return {"ok": True, "updates": updates, "count": len(updates)}


# ═══════════════════════════════════════════════════════════════════════════════
# DISPATCH
# ═══════════════════════════════════════════════════════════════════════════════

ACTIONS = {
    "search":           lambda p, u: action_search(p.get("query", ""), u),
    "info":             lambda p, u: action_info(p.get("package", ""), u),
    "list_installed":   lambda p, u: action_list_installed(u),
    "install":          lambda p, u: action_install(p.get("package", ""), u),
    "remove":           lambda p, u: action_remove(p.get("package", ""), u),
    "update":           lambda p, u: action_update(u),
    "upgrade":          lambda p, u: action_upgrade(u),
    "pip_list":         lambda p, u: action_pip_list(u),
    "pip_install":      lambda p, u: action_pip_install(p.get("package", ""), u),
    "apt_clean":        lambda p, u: action_apt_clean(u),
    "check_updates":    lambda p, u: action_check_updates(u),
}


def dispatch(action: str, params: Dict[str, Any], user: str = OWNER_USER) -> Dict[str, Any]:
    fn = ACTIONS.get(action)
    if not fn:
        return {"ok": False, "error": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}"}
    try:
        return fn(params, user)
    except Exception as e:
        return {"ok": False, "error": str(e)}
