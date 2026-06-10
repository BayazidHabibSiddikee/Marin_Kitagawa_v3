import asyncio
import os
import secrets
import threading
import tempfile
import shlex
import subprocess
import hmac
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import (
    DEFAULT_MODEL, FAST_MODEL, VISION_MODEL, OLLAMA_BASE_URL,
    SESSION_SECRET_KEY, HOST, PORT, UPLOAD_FOLDER
)
from proactive_engine import proactive_stream
from database import init_db
import database
from utils.agent_logic import stream_marin_chat
from langgraph_agent import ALL_TOOLS, tools_by_name

# ── LIFESPAN ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("[Database] Initialized Marin Tools.")
    yield

app = FastAPI(title="Marin Tools", lifespan=lifespan)

# ── SIMPLE AUTH MIDDLEWARE ───────────────────────────────────────────────

@app.middleware("http")
async def auto_auth_middleware(request: Request, call_next):
    # Auto-login as Owner since OAuth is removed for stability
    # This prevents all middleware race conditions and session crashes
    request.state.user = {"user_id": "USR-MASTER", "username": "Bayazid", "role": "owner"}
    return await call_next(request)

# ── SETUP ───────────────────────────────────────────────────────────────

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Initialize databases
from database import init_db
from tools.habit_store import init_todo_db
init_db()
init_todo_db()

@app.on_event("startup")
async def startup_event():
    # Start the proactive conversation engine
    from proactive_engine import proactive_broadcaster, seed_from_db
    seed_from_db("marin")
    asyncio.create_task(proactive_broadcaster("marin"))

# ── CORE ROUTES ──────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "operational", "time": datetime.now().isoformat()}

@app.get("/proactive/stream")
async def proactive_sse(agent: str = "marin"):
    return StreamingResponse(proactive_stream(agent), media_type="text/event-stream")

@app.get("/proactive/status")
async def get_proactive_status():
    from proactive_engine import get_status
    return JSONResponse(get_status())

@app.get("/landing")
async def landing_page(request: Request):
    return templates.TemplateResponse(request=request, name="landing.html")

@app.get("/")
@app.get("/chat")
async def chat_page(request: Request):
    user = request.state.user
    return templates.TemplateResponse(request=request, name="marin_chat.html", context={"user": user})

# ── UI COMPATIBILITY ENDPOINTS ──────────────────────────────────────────

@app.get("/settings/voice")
async def get_voice_setting():
    import marin
    return {"voice_enabled": getattr(marin, "VOICE_ENABLED", False)}

@app.post("/settings/voice")
async def set_voice_setting(request: Request):
    import marin
    # Support both JSON and Form data
    if "application/json" in request.headers.get("content-type", ""):
        data = await request.json()
        enabled = data.get("voice_enabled", data.get("enabled"))
    else:
        form = await request.form()
        enabled = form.get("enabled") == "1" or form.get("voice_enabled") == "1"
    
    marin.VOICE_ENABLED = bool(enabled)
    print(f"[VOICE] Manual Override: {'ON' if marin.VOICE_ENABLED else 'OFF'}")
    return {"status": "success", "voice_enabled": marin.VOICE_ENABLED}

@app.get("/settings/rag")
async def get_rag_setting():
    import marin
    return {"rag_enabled": getattr(marin, "RAG_ENABLED", True)}

@app.post("/settings/rag")
async def set_rag_setting(enabled: str = Form("1")):
    import marin
    marin.RAG_ENABLED = enabled == "1"
    return {"rag_enabled": marin.RAG_ENABLED}

@app.get("/settings/wordlimit")
async def get_wordlimit():
    import marin
    return {"word_limit": getattr(marin, "WORD_LIMIT", 0)}

@app.post("/settings/wordlimit")
async def set_wordlimit(request: Request):
    data = await request.json()
    import marin
    marin.WORD_LIMIT = data.get("word_limit", 0)
    return {"status": "success"}

@app.post("/audio/stop")
async def stop_audio():
    import subprocess
    subprocess.run(["pkill", "-f", "aplay"], capture_output=True)
    subprocess.run(["pkill", "-f", "piper-tts"], capture_output=True)
    return {"status": "stopped"}

@app.get("/api/news/latest")
async def get_latest_news():
    return JSONResponse({"news": "No recent updates."})

@app.get("/api/logs")
async def get_logs():
    return JSONResponse([])

@app.get("/memory/status")
async def get_memory_status(request: Request, agent: str = "marin"):
    user = request.state.user
    history = database.get_history(agent, limit=20, user_id=user["user_id"])
    return JSONResponse({"messages": history, "tokens": len(history)})

@app.post("/memory/clear")
async def clear_memory():
    return JSONResponse({"status": "cleared"})

@app.get("/timer/stats")
async def get_timer_stats():
    return JSONResponse({"active": False, "task": None, "elapsed_seconds": 0})

@app.post("/timer/command")
async def timer_command():
    return JSONResponse({"status": "ignored"})

# ── API ROUTES ────────────────────────────────────────────────────────────

@app.post("/message")
async def chat_endpoint(
    request: Request,
    message: str = Form(...),
    session_id: str = Form("default")
):
    user = request.state.user
    return StreamingResponse(
        stream_marin_chat(message, user=user, session_id=session_id),
        media_type="text/plain"
    )

@app.post("/api/rag/toggle")
async def toggle_rag(request: Request):
    data = await request.json()
    enabled = data.get("enabled", True)
    import marin
    marin.RAG_ENABLED = enabled
    print(f"[RAG] Manual Override: {'ON' if enabled else 'OFF'}")
    return {"status": "success", "rag_enabled": marin.RAG_ENABLED}

@app.get("/api/tools")
async def list_tools_api(request: Request):
    return JSONResponse([{"name": t.name, "description": t.description} for t in ALL_TOOLS])

@app.post("/api/tools/{name}")
async def call_tool_api(name: str, request: Request):
    if name not in tools_by_name:
        raise HTTPException(404, f"Tool {name} not found")
    data = await request.json()
    user = request.state.user
    data["user_id"] = user["user_id"]
    try:
        result = tools_by_name[name].invoke(data)
        return {"result": result}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/todos")
async def list_todos_api(status: str = None, category: str = None):
    from tools.habit_store import list_tasks
    return JSONResponse(list_tasks(status, category))

@app.post("/api/todos")
async def add_todo_api(request: Request):
    from tools.habit_store import add_task
    data = await request.json()
    task = add_task(
        title=data["title"],
        category=data.get("category", "general"),
        priority=data.get("priority", "medium"),
        remind_daily=bool(data.get("remind_daily", False)),
        task_level=int(data.get("task_level", 5))
    )
    return JSONResponse(task)

@app.patch("/api/todos/{id}")
async def update_todo_api(id: int, request: Request):
    from tools.habit_store import update_task
    data = await request.json()
    result = update_task(id, **data)
    return {"status": "success", "message": result}

@app.delete("/api/todos/{id}")
async def delete_todo_api(id: int):
    from tools.habit_store import delete_task
    result = delete_task(id)
    return {"status": "success", "message": result}

@app.get("/api/categories")
async def list_categories_api():
    import sqlite3
    from tools.habit_store import DB_PATH
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    cats = db.execute("SELECT * FROM categories ORDER BY name ASC").fetchall()
    db.close()
    return JSONResponse([dict(r) for r in cats])

@app.post("/api/categories")
async def add_category_api(request: Request):
    from tools.habit_store import _get_or_create_category
    data = await request.json()
    cat_id = _get_or_create_category(data["name"])
    return {"id": cat_id, "name": data["name"]}

@app.get("/api/stats")
async def get_todo_stats_api():
    from tools.habit_store import get_stats
    return JSONResponse(get_stats())

@app.get("/api/market/quotes")
async def market_quotes_api(symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT,SPY"):
    data = []
    for s in symbols.split(","):
        data.append({"symbol": s, "price": "63,240.50", "change": "+1.2%"})
    return JSONResponse(data)

@app.post("/api/authorize")
async def authorize_session(request: Request):
    data = await request.json()
    password = data.get("password")
    user = request.state.user
    from safety import system_guard
    if system_guard.verify(user["user_id"], password):
        return {"status": "success", "message": "Session authorized."}
    else:
        raise HTTPException(status_code=403, detail="Invalid system password.")

@app.get("/profile", response_class=HTMLResponse)
async def get_profile(request: Request):
    return templates.TemplateResponse(request=request, name="profile.html")

@app.get("/vault", response_class=HTMLResponse)
async def vault_page(request: Request):
    return templates.TemplateResponse(request=request, name="vault_explorer.html")

@app.get("/research-hub", response_class=HTMLResponse)
async def research_hub_page(request: Request):
    return templates.TemplateResponse(request=request, name="research_hub.html")

@app.get("/command-center", response_class=HTMLResponse)
async def command_center_page(request: Request):
    return templates.TemplateResponse(request=request, name="command_center.html")

@app.get("/todo", response_class=HTMLResponse)
async def todo_page(request: Request):
    return templates.TemplateResponse(request=request, name="todo.html")

@app.get("/api/vault/list/{agent}")
async def vault_list_api(agent: str):
    from tools.vault_manager import manage_vault
    return JSONResponse(manage_vault(agent, "list"))

@app.post("/api/vault/read")
async def vault_read_api(request: Request):
    from tools.vault_manager import manage_vault
    data = await request.json()
    return JSONResponse(manage_vault(data["agent"], "read", data["filename"], category=data.get("category", "misc")))

@app.post("/api/vault/delete")
async def vault_delete_api(request: Request):
    from tools.vault_manager import manage_vault
    data = await request.json()
    return JSONResponse(manage_vault(data["agent"], "delete", data["filename"], category=data.get("category", "misc")))

@app.post("/api/knowledge-hub/update")
async def knowledge_hub_update(request: Request):
    from tools.knowledge_hub import create_integrated_hub_map
    try:
        data = await request.json()
        location = data.get("location", "Dhaka")
        destination = data.get("destination")
        query = data.get("query") or "tourist attraction"
        limit = int(data.get("limit", 8))
        result = create_integrated_hub_map(location, destination, query=query, limit=limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/research/search")
async def research_search_api(request: Request):
    from tools.knowledge_hub import search_pdfs, search_web
    data = await request.json()
    query = data.get("query")
    mode = data.get("mode", "pdf")  # "pdf" or "web"
    results = search_web(query, max_results=10) if mode == "web" else search_pdfs(query)
    return JSONResponse({"results": results})

@app.post("/upload")
async def upload_image(image: UploadFile = File(...)):
    import re
    if not image.filename:
        return JSONResponse({"error": "No filename"}, status_code=400)
    filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', image.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    with open(filepath, "wb") as buf:
        buf.write(await image.read())
    return {"ok": True, "path": f"/{filepath}"}

# ── MODULEFLOW ────────────────────────────────────────────────────────────

@app.get("/moduleflow")
async def moduleflow_page(request: Request):
    import os
    with open(os.path.join(BASE_DIR, "moduleflow", "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/moduleflow/graph.json")
async def moduleflow_graph(request: Request):
    import os
    with open(os.path.join(BASE_DIR, "moduleflow", "graph.json"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read(), media_type="application/json")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
