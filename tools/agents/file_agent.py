#!/usr/bin/env python3
"""
File Agent — read, write, copy, move, permissions, disk usage.
Guests: read-only, sandboxed to guest_vault. Owner: full access.
Uses PrivilegeManager for VFS path resolution.
"""

import os
import shutil
import subprocess
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime

try:
    from privilege_manager import get_privilege_manager, has_capability, run_as_user
except ImportError:
    has_capability = lambda u, c: u == "Bayazid"
    get_privilege_manager = None
    def run_as_user(cmd, user, timeout=30):
        import subprocess as sp
        try:
            r = sp.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return {"exit": r.returncode, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
        except Exception as e:
            return {"exit": -1, "stdout": "", "stderr": str(e)}

OWNER_USER = "Bayazid"
MAX_READ_BYTES = 1_000_000  # 1MB max read per call


def _run(cmd: str, user: str = OWNER_USER, timeout: int = 30) -> Dict[str, Any]:
    return run_as_user(cmd, user, timeout=timeout)


def _check_owner(user: str) -> Optional[str]:
    if user != OWNER_USER:
        return "DENIED: Only Bayazid can perform this action."
    return None


def _resolve(path: str, user: str) -> str:
    """Resolve path through PrivilegeManager VFS."""
    if get_privilege_manager:
        try:
            pm = get_privilege_manager()
            resolved = pm.resolve_path(path, user)
            return str(resolved)
        except PermissionError as e:
            return None
    # Fallback to basic expansion
    return os.path.expanduser(path)


def _safe_path(path: str, user: str = OWNER_USER) -> bool:
    """Block path traversal via PrivilegeManager."""
    resolved = _resolve(path, user)
    if resolved is None:
        return False
    # Owner gets additional blocked paths
    if user == OWNER_USER:
        blocked = ["/etc/shadow", "/etc/gshadow", "/proc", "/sys"]
        real = os.path.realpath(resolved)
        for b in blocked:
            if real.startswith(b):
                return False
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def action_read_file(path: str, offset: int = 0, limit: int = 200, user: str = OWNER_USER) -> Dict[str, Any]:
    resolved = _resolve(path, user)
    if resolved is None:
        return {"ok": False, "error": f"[VFS] Path traversal blocked: {path}"}
    if not _safe_path(path, user):
        return {"ok": False, "error": "Access denied to this path."}
    if not os.path.exists(resolved):
        return {"ok": False, "error": f"File not found: {resolved}"}
    if not os.path.isfile(resolved):
        return {"ok": False, "error": f"Not a file: {resolved}"}
    try:
        with open(resolved, "r", errors="replace") as f:
            lines = f.readlines()
        total = len(lines)
        selected = lines[offset:offset + limit]
        content = "".join(selected)
        return {
            "ok": True, "path": resolved, "total_lines": total,
            "offset": offset, "shown": len(selected), "content": content,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def action_write_file(path: str, content: str, append: bool = False, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    resolved = _resolve(path, user)
    if resolved is None:
        return {"ok": False, "error": f"[VFS] Path traversal blocked: {path}"}
    if not _safe_path(path, user):
        return {"ok": False, "error": "Access denied to this path."}
    try:
        os.makedirs(os.path.dirname(resolved) or ".", exist_ok=True)
        mode = "a" if append else "w"
        with open(resolved, mode) as f:
            f.write(content)
        return {"ok": True, "path": resolved, "bytes_written": len(content), "append": append}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def action_list_dir(path: str = ".", user: str = OWNER_USER) -> Dict[str, Any]:
    resolved = _resolve(path, user)
    if resolved is None:
        return {"ok": False, "error": f"[VFS] Path traversal blocked: {path}"}
    if not os.path.isdir(resolved):
        return {"ok": False, "error": f"Not a directory: {resolved}"}
    try:
        entries = []
        for name in sorted(os.listdir(resolved)):
            full = os.path.join(resolved, name)
            stat = os.stat(full)
            entries.append({
                "name": name + ("/" if os.path.isdir(full) else ""),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "permissions": oct(stat.st_mode)[-3:],
            })
        return {"ok": True, "path": resolved, "entries": entries, "count": len(entries)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def action_file_info(path: str, user: str = OWNER_USER) -> Dict[str, Any]:
    resolved = _resolve(path, user)
    if resolved is None:
        return {"ok": False, "error": f"[VFS] Path traversal blocked: {path}"}
    if not os.path.exists(resolved):
        return {"ok": False, "error": f"Not found: {resolved}"}
    stat = os.stat(resolved)
    md5 = None
    if os.path.isfile(resolved):
        try:
            with open(resolved, "rb") as f:
                md5 = hashlib.md5(f.read(8192)).hexdigest()
        except Exception:
            pass
    return {
        "ok": True, "path": resolved,
        "type": "directory" if os.path.isdir(resolved) else "file",
        "size": stat.st_size,
        "size_human": _human_size(stat.st_size),
        "permissions": oct(stat.st_mode)[-3:],
        "owner_uid": stat.st_uid,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "md5_prefix": md5,
    }


def action_copy(src: str, dst: str, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    src_resolved = _resolve(src, user)
    dst_resolved = _resolve(dst, user)
    if src_resolved is None or dst_resolved is None:
        return {"ok": False, "error": "[VFS] Path traversal blocked."}
    if not os.path.exists(src_resolved):
        return {"ok": False, "error": f"Source not found: {src_resolved}"}
    try:
        if os.path.isdir(src_resolved):
            shutil.copytree(src_resolved, dst_resolved)
        else:
            os.makedirs(os.path.dirname(dst_resolved) or ".", exist_ok=True)
            shutil.copy2(src_resolved, dst_resolved)
        return {"ok": True, "src": src_resolved, "dst": dst_resolved}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def action_move(src: str, dst: str, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    src_resolved = _resolve(src, user)
    dst_resolved = _resolve(dst, user)
    if src_resolved is None or dst_resolved is None:
        return {"ok": False, "error": "[VFS] Path traversal blocked."}
    if not os.path.exists(src_resolved):
        return {"ok": False, "error": f"Source not found: {src_resolved}"}
    try:
        os.makedirs(os.path.dirname(dst_resolved) or ".", exist_ok=True)
        shutil.move(src_resolved, dst_resolved)
        return {"ok": True, "src": src_resolved, "dst": dst_resolved}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def action_delete(path: str, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    resolved = _resolve(path, user)
    if resolved is None:
        return {"ok": False, "error": f"[VFS] Path traversal blocked: {path}"}
    if not os.path.exists(resolved):
        return {"ok": False, "error": f"Not found: {resolved}"}
    try:
        if os.path.isdir(resolved):
            shutil.rmtree(resolved)
        else:
            os.remove(resolved)
        return {"ok": True, "deleted": resolved}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def action_chmod(path: str, mode: str, user: str = OWNER_USER) -> Dict[str, Any]:
    err = _check_owner(user)
    if err:
        return {"ok": False, "error": err}
    resolved = _resolve(path, user)
    if resolved is None:
        return {"ok": False, "error": f"[VFS] Path traversal blocked: {path}"}
    try:
        os.chmod(resolved, int(mode, 8))
        return {"ok": True, "path": resolved, "mode": mode}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def action_disk_usage(path: str = "/", user: str = OWNER_USER) -> Dict[str, Any]:
    r = _run(f"du -sh {path} 2>/dev/null || echo 'error'", user)
    df = _run("df -h / --output=source,size,used,avail,pcent | tail -1")
    return {"ok": True, "usage": r["stdout"], "disk": df["stdout"]}


def action_find_files(pattern: str, path: str = ".", max_results: int = 30, user: str = OWNER_USER) -> Dict[str, Any]:
    resolved = _resolve(path, user)
    if resolved is None:
        return {"ok": False, "error": f"[VFS] Path traversal blocked: {path}"}
    r = _run(f"find {resolved} -name '{pattern}' -type f 2>/dev/null | head -{max_results}", user)
    files = [f for f in r["stdout"].splitlines() if f.strip()]
    return {"ok": True, "matches": files, "count": len(files)}


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# ═══════════════════════════════════════════════════════════════════════════════
# DISPATCH
# ═══════════════════════════════════════════════════════════════════════════════

ACTIONS = {
    "read_file":    lambda p, u: action_read_file(p.get("path", ""), int(p.get("offset", 0)), int(p.get("limit", 200)), u),
    "write_file":   lambda p, u: action_write_file(p.get("path", ""), p.get("content", ""), p.get("append", False), u),
    "list_dir":     lambda p, u: action_list_dir(p.get("path", "."), u),
    "file_info":    lambda p, u: action_file_info(p.get("path", ""), u),
    "copy":         lambda p, u: action_copy(p.get("src", ""), p.get("dst", ""), u),
    "move":         lambda p, u: action_move(p.get("src", ""), p.get("dst", ""), u),
    "delete":       lambda p, u: action_delete(p.get("path", ""), u),
    "chmod":        lambda p, u: action_chmod(p.get("path", ""), p.get("mode", "644"), u),
    "disk_usage":   lambda p, u: action_disk_usage(p.get("path", "/"), u),
    "find_files":   lambda p, u: action_find_files(p.get("pattern", "*"), p.get("path", "."), int(p.get("max", 30)), u),
}


def dispatch(action: str, params: Dict[str, Any], user: str = OWNER_USER) -> Dict[str, Any]:
    fn = ACTIONS.get(action)
    if not fn:
        return {"ok": False, "error": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}"}
    try:
        return fn(params, user)
    except Exception as e:
        return {"ok": False, "error": str(e)}
