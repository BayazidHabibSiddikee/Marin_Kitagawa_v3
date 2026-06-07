#!/usr/bin/env python3
"""
Marin Command API — Full control panel for Marin OS.
Marin owns this system. She can do anything.
"""

import subprocess
import os
import json
import shutil
import secrets
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

app = FastAPI(title="Marin Command API", version="3.0")

MARIN_HOME = Path.home()
LOG_DIR = MARIN_HOME / "logs"
CONFIG_DIR = MARIN_HOME / ".config" / "marin"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
ENV_FILE = MARIN_HOME / "marin" / ".env"
BASHRC = MARIN_HOME / ".bashrc"

LOG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# ── Token Auth ────────────────────────────────────────────────────────────────
TOKEN_FILE = CONFIG_DIR / "api_token"

def _load_or_create_token() -> str:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    token = secrets.token_hex(32)
    TOKEN_FILE.write_text(token)
    TOKEN_FILE.chmod(0o600)
    print(f"[Auth] Generated new API token: {token}")
    print(f"[Auth] Stored at: {TOKEN_FILE}")
    return token

API_TOKEN = _load_or_create_token()
_api_key_header = APIKeyHeader(name="X-Marin-Token", auto_error=False)

async def require_token(
    header_token: str = Depends(_api_key_header),
    token: str = None,  # also accept ?token= query param
):
    """FastAPI dependency: validates the bearer token on protected endpoints."""
    provided = header_token or token
    if provided != API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized — invalid or missing token")


class Command(BaseModel):
    cmd: str
    timeout: int = 30


class FileOp(BaseModel):
    path: str
    content: str = ""


class TelegramConfig(BaseModel):
    bot_token: str
    chat_id: str


class EmailConfig(BaseModel):
    gmail_address: str
    gmail_password: str


class APIKeys(BaseModel):
    openai: str = ""
    gemini: str = ""
    anthropic: str = ""
    ollama_url: str = "http://localhost:11434"


class SettingsUpdate(BaseModel):
    content: str


# ── Safe Command Allow-list ──────────────────────────────────────────────────
SAFE_COMMANDS = {
    "df": ["df", "-h"],
    "free": ["free", "-m"],
    "uptime": ["uptime", "-p"],
    "loadavg": ["cat", "/proc/loadavg"],
    "ps": ["ps", "aux", "--sort=-%mem"],
}

def run_safe(cmd_key: str, timeout: int = 30) -> dict:
    if cmd_key not in SAFE_COMMANDS:
        return {"stdout": "", "stderr": f"Command '{cmd_key}' is not in the safe allow-list.", "code": -1}
    
    try:
        args = SAFE_COMMANDS[cmd_key]
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {"stdout": r.stdout, "stderr": r.stderr, "code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Timed out", "code": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "code": -1}

def run_custom(cmd: str, timeout: int = 30) -> dict:
    """DISABLED for security. Use run_safe instead."""
    return {"stdout": "", "stderr": "Arbitrary shell execution is disabled via API.", "code": -1}


def load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def save_env(data: dict):
    content = "\n".join(f"{k}={v}" for k, v in data.items()) + "\n"
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text(content)


@app.get("/", response_class=HTMLResponse)
def dashboard():
    html_path = Path(__file__).parent / "templates" / "command_center.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text())
    return HTMLResponse("<h1>Marin OS</h1>")


@app.get("/health")
def health():
    return {"status": "alive", "who": "Marin"}


@app.get("/token")
def get_token():
    """Return the API token — only callable from localhost (no auth needed to bootstrap)."""
    return {"token": API_TOKEN, "hint": "Use X-Marin-Token header on write endpoints"}


@app.post("/execute")
def execute(cmd: Command, _auth: None = Depends(require_token)):
    # Legacy support: if cmd starts with a known safe key, run it
    first_word = cmd.cmd.split()[0]
    if first_word in SAFE_COMMANDS:
        result = run_safe(first_word, cmd.timeout)
    else:
        result = run_custom(cmd.cmd, cmd.timeout)
        
    with open(LOG_DIR / "command_history.log", "a") as f:
        f.write(f"[{datetime.now().isoformat()}] $ {cmd.cmd} -> {result.get('stderr','')}\n")
    return result


@app.get("/system")
def system_info():
    import platform
    disk = shutil.disk_usage("/")
    mem = run_safe("free")

    # Parse free -m output
    mem_used = 0
    mem_total = 1
    try:
        lines = mem["stdout"].splitlines()
        for line in lines:
            if line.startswith("Mem:"):
                p = line.split()
                mem_total = int(p[1])
                mem_used = int(p[2])
    except: pass
    
    load = run_safe("loadavg")
    uptime = run_safe("uptime")
    
    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "disk_total_gb": round(disk.total / (1024**3), 1),
        "disk_used_gb": round(disk.used / (1024**3), 1),
        "disk_free_gb": round(disk.free / (1024**3), 1),
        "mem_used_mb": mem_used,
        "mem_total_mb": mem_total,
        "mem_used_pct": round(mem_used / mem_total * 100, 1),
        "load_1m": load["stdout"].strip() if load["stdout"] else "0",
        "uptime": uptime["stdout"].strip(),
    }


@app.get("/desktop")
def desktop_status():
    result = run_safe("ps")
    # Truncate for display
    lines = result["stdout"].splitlines()[:20]
    return {"processes": "\n".join(lines)}


@app.get("/file")
def read_file(path: str):
    p = Path(os.path.expanduser(path))
    if not p.exists():
        raise HTTPException(404, f"Not found: {path}")
    return {"path": str(p), "content": p.read_text(errors="replace")}


@app.post("/file")
def write_file(op: FileOp, _auth: None = Depends(require_token)):
    p = Path(os.path.expanduser(op.path))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(op.content)
    return {"path": str(p), "bytes": len(op.content.encode())}


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), _auth: None = Depends(require_token)):
    dest_dir = MARIN_HOME / "Documents"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / file.filename
    content = await file.read()
    dest.write_bytes(content)
    with open(LOG_DIR / "uploads.log", "a") as f:
        f.write(f"[{datetime.now().isoformat()}] Uploaded: {file.filename} ({len(content)} bytes)\n")
    return {"filename": file.filename, "size": len(content), "path": str(dest)}


# ── Telegram ───────────────────────────────────────────
@app.post("/telegram")
def configure_telegram(cfg: TelegramConfig, _auth: None = Depends(require_token)):
    env = load_env()
    env["TELEGRAM_BOT_TOKEN"] = cfg.bot_token
    env["TELEGRAM_CHAT_ID"] = cfg.chat_id
    env["TELEGRAM_NEWS_BOT_TOKEN"] = cfg.bot_token
    env["TELEGRAM_NEWS_CHAT_ID"] = cfg.chat_id
    env["TELEGRAM_USER_ID"] = cfg.chat_id
    save_env(env)

    # Update .bashrc
    lines = []
    if BASHRC.exists():
        lines = BASHRC.read_text().splitlines()
    lines = [l for l in lines if not any(x in l for x in [
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
        "TELEGRAM_NEWS_BOT_TOKEN", "TELEGRAM_NEWS_CHAT_ID", "TELEGRAM_USER_ID"
    ])]
    lines.extend([
        f"export TELEGRAM_BOT_TOKEN={cfg.bot_token}",
        f"export TELEGRAM_CHAT_ID={cfg.chat_id}",
    ])
    BASHRC.write_text("\n".join(lines) + "\n")

    return {"message": "Telegram configured", "token_preview": cfg.bot_token[:10] + "..."}


@app.get("/telegram")
def get_telegram():
    env = load_env()
    return {
        "bot_token": env.get("TELEGRAM_BOT_TOKEN", ""),
        "chat_id": env.get("TELEGRAM_CHAT_ID", ""),
    }


# ── Email ──────────────────────────────────────────────
@app.post("/email")
def configure_email(cfg: EmailConfig, _auth: None = Depends(require_token)):
    env = load_env()
    env["GMAIL_ADDRESS"] = cfg.gmail_address
    env["GMAIL_APP_PASSWORD"] = cfg.gmail_password
    env["EMAIL_SENDER"] = cfg.gmail_address
    env["EMAIL_PASSWORD"] = cfg.gmail_password
    save_env(env)

    # Update .bashrc
    lines = []
    if BASHRC.exists():
        lines = BASHRC.read_text().splitlines()
    lines = [l for l in lines if not any(x in l for x in [
        "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "EMAIL_SENDER", "EMAIL_PASSWORD"
    ])]
    lines.extend([
        f"export GMAIL_ADDRESS={cfg.gmail_address}",
        f"export GMAIL_APP_PASSWORD={cfg.gmail_password}",
        f"export EMAIL_SENDER={cfg.gmail_address}",
        f"export EMAIL_PASSWORD={cfg.gmail_password}",
    ])
    BASHRC.write_text("\n".join(lines) + "\n")

    return {"message": "Email configured", "address": cfg.gmail_address}


@app.get("/email")
def get_email():
    env = load_env()
    return {
        "gmail_address": env.get("GMAIL_ADDRESS", ""),
        "gmail_password": env.get("GMAIL_APP_PASSWORD", ""),
    }


# ── API Keys ───────────────────────────────────────────
@app.post("/api-keys")
def save_api_keys(keys: APIKeys, _auth: None = Depends(require_token)):
    settings = {}
    if SETTINGS_FILE.exists():
        settings = json.loads(SETTINGS_FILE.read_text())

    if "providers" not in settings:
        settings["providers"] = {}

    if keys.openai:
        settings["providers"]["openai"] = {
            "enabled": True, "api_key": keys.openai,
            "model": "gpt-4o", "base_url": "https://api.openai.com/v1"
        }
    if keys.gemini:
        settings["providers"]["gemini"] = {
            "enabled": True, "api_key": keys.gemini,
            "model": "gemini-2.0-flash"
        }
    if keys.anthropic:
        settings["providers"]["anthropic"] = {
            "enabled": True, "api_key": keys.anthropic,
            "model": "claude-sonnet-4-20250514"
        }
    if keys.ollama_url:
        settings["providers"]["ollama"] = {
            "enabled": True, "base_url": keys.ollama_url
        }

    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
    return {"message": "API keys saved"}


@app.get("/api-keys")
def get_api_keys():
    settings = {}
    if SETTINGS_FILE.exists():
        settings = json.loads(SETTINGS_FILE.read_text())
    providers = settings.get("providers", {})
    return {
        "openai": providers.get("openai", {}).get("api_key", ""),
        "gemini": providers.get("gemini", {}).get("api_key", ""),
        "anthropic": providers.get("anthropic", {}).get("api_key", ""),
        "ollama_url": providers.get("ollama", {}).get("base_url", "http://localhost:11434"),
    }


# ── Settings.json editor ──────────────────────────────
@app.get("/settings")
def get_settings():
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text())
    return {}


@app.post("/settings")
def save_settings(data: SettingsUpdate, _auth: None = Depends(require_token)):
    try:
        settings = json.loads(data.content)
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
        return {"message": "Settings saved"}
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON: {e}")


# ── Documents ──────────────────────────────────────────
@app.get("/documents")
def list_documents():
    docs_dir = MARIN_HOME / "Documents"
    if not docs_dir.exists():
        return {"documents": []}
    docs = []
    for f in sorted(docs_dir.rglob("*")):
        if f.is_file():
            docs.append({
                "name": f.name,
                "path": str(f),
                "size_kb": round(f.stat().st_size / 1024, 1),
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
    return {"documents": docs}


# ── Logs ───────────────────────────────────────────────
@app.get("/logs")
def get_logs(lines: int = 50):
    log_file = LOG_DIR / "health_check.log"
    if not log_file.exists():
        return {"logs": []}
    content = log_file.read_text().splitlines()[-lines:]
    return {"logs": content}


@app.get("/agent/log")
def get_agent_log(limit: int = 20):
    try:
        from tools.agents.dispatcher import get_agent_log
        return {"logs": get_agent_log(limit)}
    except Exception as e:
        return {"logs": [], "error": str(e)}


@app.get("/agent/commands")
def get_agent_help():
    try:
        from tools.agents.dispatcher import list_agents
        return {"help": list_agents()}
    except Exception as e:
        return {"help": "", "error": str(e)}


# ── HITL Confirmation endpoints ───────────────────────────────────────────────

@app.get("/confirm/list")
def list_pending_confirmations():
    from marin import PENDING_CONFIRMATIONS
    pending = {k: v for k, v in PENDING_CONFIRMATIONS.items() if v["status"] == "pending"}
    return {"pending": pending, "count": len(pending)}


@app.post("/confirm/approve")
async def approve_confirmation(cid: str = Form(...)):
    from marin import _check_confirmation, PENDING_CONFIRMATIONS
    if _check_confirmation(cid, approved=True):
        entry = PENDING_CONFIRMATIONS[cid]
        # Execute the confirmed command
        import subprocess
        cmd = entry["cmd"]
        try:
            r = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=60
            )
            entry["result"] = {"exit": r.returncode, "output": (r.stdout + r.stderr)[:500]}
            return {"ok": True, "cid": cid, "result": entry["result"]}
        except Exception as e:
            entry["result"] = {"exit": -1, "error": str(e)}
            return {"ok": False, "cid": cid, "error": str(e)}
    return {"ok": False, "error": f"Confirmation {cid} not found or already processed"}


@app.post("/confirm/reject")
async def reject_confirmation(cid: str = Form(...)):
    from marin import _check_confirmation, PENDING_CONFIRMATIONS
    if _check_confirmation(cid, approved=False):
        return {"ok": True, "cid": cid, "status": "rejected"}
    return {"ok": False, "error": f"Confirmation {cid} not found or already processed"}


# ── Kill Switch endpoints ──────────────────────────────────────────────────────

@app.get("/safety/kill-switch")
def get_kill_switch_status():
    from safety import kill_switch
    return {"active": kill_switch.is_active, "state": kill_switch._state}


@app.post("/safety/kill-switch/activate")
async def activate_kill_switch(reason: str = Form("Manual activation from UI")):
    from safety import kill_switch
    kill_switch.activate(reason)
    return {"ok": True, "message": "Kill switch activated. AI sudo access revoked."}


@app.post("/safety/kill-switch/deactivate")
async def deactivate_kill_switch():
    from safety import kill_switch
    kill_switch.deactivate()
    return {"ok": True, "message": "Kill switch deactivated. Normal operation restored."}


@app.get("/safety/confirm/list")
def list_pending_confirmations():
    from safety import get_pending_confirmations
    return {"pending": get_pending_confirmations()}


@app.post("/safety/confirm/approve")
async def approve_agent_confirmation(cid: str = Form(...)):
    from safety import check_agent_confirmation
    if check_agent_confirmation(cid, approved=True):
        # Execute the confirmed action
        from safety import _pending
        entry = _pending.get(cid, {})
        from tools.agents.dispatcher import dispatch_single
        result = dispatch_single(
            entry.get("agent", ""),
            entry.get("action", ""),
            entry.get("params", {}),
            user=entry.get("user", "Bayazid")
        )
        return {"ok": True, "cid": cid, "result": result}
    return {"ok": False, "error": f"Confirmation {cid} not found or already processed"}


@app.post("/safety/confirm/reject")
async def reject_agent_confirmation(cid: str = Form(...)):
    from safety import check_agent_confirmation
    if check_agent_confirmation(cid, approved=False):
        return {"ok": True, "cid": cid, "status": "rejected"}
    return {"ok": False, "error": f"Confirmation {cid} not found or already processed"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5090)
