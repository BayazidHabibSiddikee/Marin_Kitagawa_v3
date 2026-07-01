import asyncio
import os
import time
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── LIFESPAN ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize databases
    init_db()
    from tools.habit_store import init_todo_db
    init_todo_db()
    print("[Database] Initialized Marin Tools.")
    
    # Start the proactive conversation engine
    from proactive_engine import proactive_broadcaster, seed_from_db
    seed_from_db("marin")
    asyncio.create_task(proactive_broadcaster("marin"))
    
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

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/books", StaticFiles(directory=os.path.join(BASE_DIR, "static", "downloads")), name="books")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ── MOUNT COMMAND API AS SUB-ROUTER ──────────────────────────────────────
from command_api import app as command_api_app
app.mount("/cmd", command_api_app)

# ── MOUNT SENTINEL ENGINE (PROXY) ────────────────────────────────────────
from sentinel_engine import sentinel_app
app.mount("/v1", sentinel_app)

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

@app.get("/sentinel")
async def sentinel_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="sentinel_dashboard.html")

@app.get("/")
@app.get("/chat")
async def chat_page(request: Request):
    user = request.state.user
    response = templates.TemplateResponse(request=request, name="marin_chat.html", context={"user": user})
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

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
async def set_rag_setting(request: Request):
    import marin
    if "application/json" in request.headers.get("content-type", ""):
        data = await request.json()
        enabled = data.get("enabled", data.get("rag_enabled", True))
    else:
        form = await request.form()
        enabled = form.get("enabled") == "1" or form.get("rag_enabled") == "1"
    
    marin.RAG_ENABLED = bool(enabled)
    return {"status": "success", "rag_enabled": marin.RAG_ENABLED}

@app.get("/settings/wordlimit")
async def get_wordlimit():
    import marin
    return {"word_limit": getattr(marin, "WORD_LIMIT", 0)}

@app.post("/settings/wordlimit")
async def set_wordlimit(request: Request):
    import marin
    if "application/json" in request.headers.get("content-type", ""):
        data = await request.json()
        limit = data.get("word_limit", data.get("limit", 0))
    else:
        form = await request.form()
        limit = form.get("word_limit") or form.get("limit") or 0
    
    marin.WORD_LIMIT = int(limit)
    return {"status": "success", "word_limit": marin.WORD_LIMIT}

@app.post("/audio/stop")
async def stop_audio():
    subprocess.run(["pkill", "-f", "aplay"], capture_output=True)
    subprocess.run(["pkill", "-f", "piper-tts"], capture_output=True)
    return {"status": "stopped"}

@app.get("/audio/speak")
async def speak_audio(text: str):
    from utils.tts import generate_wav
    import io
    wav_bytes = await generate_wav(text)
    if not wav_bytes:
        raise HTTPException(status_code=500, detail="Failed to generate audio")
    return StreamingResponse(io.BytesIO(wav_bytes), media_type="audio/wav")


@app.get("/api/news/latest")
async def get_latest_news_api():
    from database import get_latest_news
    news = get_latest_news(limit=10)
    return JSONResponse(news)

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
async def get_timer_stats_api(request: Request):
    user = request.state.user
    from database import get_timer_summary
    return JSONResponse(get_timer_summary(user["user_id"]))

@app.post("/timer/command")
async def timer_command(
    request: Request,
    command: str = Form(...),
    task: str = Form("Focus")
):
    user = request.state.user
    from database import start_timer, clear_active_timers, end_timer
    import sqlite3
    from database import DB_PATH
    
    if command == "start":
        start_timer(task, user_id=user["user_id"])
        return {"status": "started", "task": task}
    elif command == "stop":
        # Find active timer ID
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        active = conn.execute("SELECT id FROM timers WHERE user_id = ? AND status = 'active' LIMIT 1", (user["user_id"],)).fetchone()
        if active:
            end_timer(active["id"])
            conn.close()
            return {"status": "stopped"}
        conn.close()
        return {"status": "no_active_timer"}
    return {"status": "ignored"}

# ── API ROUTES ────────────────────────────────────────────────────────────

@app.post("/message")
async def chat_endpoint(
    request: Request,
    message: str = Form(...),
    session_id: str = Form("default")
):
    from proactive_engine import record_user_message
    record_user_message("marin")
    
    user = request.state.user
    return StreamingResponse(
        stream_marin_chat(message, user=user, session_id=session_id),
        media_type="text/plain"
    )

@app.get("/api/pending")
async def pending_messages(request: Request):
    """Poll for background tool pipeline results."""
    user = request.state.user
    from langgraph_agent import get_pending_message
    msg = await get_pending_message(user["user_id"])
    return {"message": msg, "has_pending": bool(msg)}

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
    try:
        sym_list = [s.upper().strip() for s in symbols.split(",") if s.strip()]
        binance_syms = [s for s in sym_list if s.endswith("USDT") or s.endswith("BTC")]
        
        market_data = {}
        if binance_syms:
            import httpx, json
            url = f"https://api.binance.com/api/v3/ticker/24hr?symbols={json.dumps(binance_syms).replace(' ', '')}"
            async with httpx.AsyncClient(timeout=5) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    for item in res.json():
                        market_data[item['symbol']] = {
                            "price": f"{float(item['lastPrice']):,.2f}",
                            "change": f"{float(item['priceChangePercent']):+.2f}%"
                        }
        
        for s in sym_list:
            if s in market_data:
                data.append({"symbol": s, "price": market_data[s]["price"], "change": market_data[s]["change"]})
            else:
                data.append({"symbol": s, "price": "N/A", "change": "N/A"})
    except Exception as e:
        print(f"Market quotes error: {e}")
        for s in symbols.split(","):
            data.append({"symbol": s.strip(), "price": "Error", "change": "Error"})
            
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

@app.get("/pdf-library", response_class=HTMLResponse)
async def pdf_library_page(request: Request):
    return templates.TemplateResponse(request=request, name="pdf_library.html")

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

@app.post("/api/research/browse")
async def research_browse_api(request: Request):
    from tools.knowledge_hub import scrape_content
    import urllib.parse
    data = await request.json()
    url = data.get("url", "")
    # Basic SSRF guard: only http/https schemes
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return JSONResponse({"error": "Only http/https URLs are allowed"}, status_code=400)
    except Exception:
        return JSONResponse({"error": "Invalid URL"}, status_code=400)
    try:
        text = scrape_content(url)
        return JSONResponse({"text": text})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/research/download")
async def research_download_api(request: Request):
    from tools.pdf_downloader import download_pdf
    data = await request.json()
    url = data.get("url")
    title = data.get("title", "downloaded_document")
    download_dir = os.path.join(BASE_DIR, "static", "downloads")
    try:
        path = download_pdf(url, title, output_dir=download_dir)
        if path:
            return JSONResponse({"status": "success", "file": f"/static/downloads/{os.path.basename(path)}"})
        return JSONResponse({"error": "Download failed"}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# /api/documents — single definition scanning both downloads + books
@app.get("/api/documents")
async def list_documents():
    docs = []
    seen = set()
    for scan_dir in [
        os.path.join(BASE_DIR, "static", "downloads"),
        os.path.join(BASE_DIR, "books"),
    ]:
        if not os.path.exists(scan_dir):
            continue
        for f in sorted(os.listdir(scan_dir)):
            if f in seen:
                continue
            if f.endswith((".pdf", ".docx", ".txt", ".md")):
                path = os.path.join(scan_dir, f)
                size_bytes = os.path.getsize(path)
                size_str = (
                    f"{size_bytes / (1024 * 1024):.1f} MB"
                    if size_bytes >= 1024 * 1024
                    else f"{size_bytes / 1024:.0f} KB"
                )
                docs.append({"filename": f, "size": size_str, "type": f.split(".")[-1]})
                seen.add(f)
    return {"documents": docs[:50]}

@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".pdf", ".docx", ".txt", ".md"):
        return {"error": "Unsupported file type. Use PDF, DOCX, TXT, or MD."}
    content = await file.read()
    uploads_dir = os.path.join(BASE_DIR, "static", "downloads")
    os.makedirs(uploads_dir, exist_ok=True)
    safe_filename = os.path.basename(file.filename.replace('\\', '/'))
    filepath = os.path.join(uploads_dir, safe_filename)
    with open(filepath, "wb") as f:
        f.write(content)
    upload_size_mb = len(content) / (1024 * 1024)
    # Trigger RAG re-indexing in background
    async def _trigger_reindex():
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post("http://127.0.0.1:5091/reindex")
        except Exception:
            pass
    asyncio.create_task(_trigger_reindex())
    return {"success": True, "filename": file.filename, "size": f"{upload_size_mb:.1f}MB"}

@app.delete("/api/documents/{filename}")
async def delete_document(filename: str):
    # Search both directories for the file
    for scan_dir in [
        os.path.join(BASE_DIR, "static", "downloads"),
        os.path.join(BASE_DIR, "books"),
    ]:
        candidate = os.path.realpath(os.path.join(scan_dir, filename))
        if candidate.startswith(os.path.realpath(scan_dir) + os.sep) and os.path.exists(candidate):
            os.remove(candidate)
            return {"success": True, "message": f"Deleted {filename}"}
    return {"error": "File not found"}

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

# ── VIDEO PROXY — streams external video through localhost ──────────────────
# Bypasses CORS and iframe restrictions. The <video> element loads from
# localhost while this endpoint fetches from googlevideo.com / youtube.com
# with the correct Referer and User-Agent headers.

# Allowlist of safe domains for video proxy (SSRF mitigation)
_PROXY_ALLOWED_DOMAINS = (
    "googlevideo.com",
    "youtube.com",
    "youtu.be",
    "ytimg.com",
)

@app.get("/proxy/stream")
async def proxy_stream(request: Request, url: str = ""):
    """Proxy a video stream URL so the browser can play it from same-origin.
    Only allows requests to whitelisted video CDN domains (SSRF mitigation).
    """
    import urllib.parse
    if not url:
        raise HTTPException(400, "Missing 'url' parameter")

    # SSRF guard: only allow whitelisted video domains
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
        if parsed.scheme not in ("http", "https") or not any(
            host == d or host.endswith("." + d) for d in _PROXY_ALLOWED_DOMAINS
        ):
            raise HTTPException(403, "URL not in allowed domain list")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Invalid URL")

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.youtube.com/",
            "Origin": "https://www.youtube.com",
        }

        range_header = request.headers.get("range")
        if range_header:
            headers["Range"] = range_header

        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url, headers=headers)

            resp_headers = {}
            if "content-type" in resp.headers:
                resp_headers["Content-Type"] = resp.headers["content-type"]
            if "content-length" in resp.headers:
                resp_headers["Content-Length"] = resp.headers["content-length"]
            if "content-range" in resp.headers:
                resp_headers["Content-Range"] = resp.headers["content-range"]
            if "accept-ranges" in resp.headers:
                resp_headers["Accept-Ranges"] = resp.headers["accept-ranges"]

            status = resp.status_code if resp.status_code in (200, 206) else 200

            return StreamingResponse(
                resp.aiter_bytes(chunk_size=65536),
                status_code=status,
                headers=resp_headers,
                media_type=resp_headers.get("Content-Type", "video/mp4"),
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Proxy error: {e}")

# ── MODULEFLOW ────────────────────────────────────────────────────────────

@app.get("/moduleflow")
async def moduleflow_page(request: Request):
    with open(os.path.join(BASE_DIR, "moduleflow", "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/moduleflow/graph.json")
async def moduleflow_graph(request: Request):
    with open(os.path.join(BASE_DIR, "moduleflow", "graph.json"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read(), media_type="application/json")

@app.get("/api/settings")
async def get_settings():
    import llm_manager
    from fastapi.responses import JSONResponse
    response = JSONResponse({
        "user_name": database.get_state("USER_NAME") or "Bayazid",
        "location": database.get_state("LOCATION") or "Rajshahi",
        "openrouter_key": database.get_state("OPENROUTER_API_KEY") or "",
        "image_model": database.get_state("IMAGE_MODEL") or "black-forest-labs/flux-schnell",
        "vision_model": database.get_state("VISION_MODEL") or "",
        "selected_models": database.get_state("SELECTED_MODELS") or [],
        "fallback_models": database.get_state("FALLBACK_MODELS") or [],
        "active_model": database.get_state("ACTIVE_MODEL") or "",
        "user_avatar": database.get_state("USER_AVATAR") or "",
        "hf_token": database.get_state("HF_TOKEN") or "",
        # ── Multi-provider fields ──
        "providers": llm_manager.get_providers(),
        "deep_models": llm_manager.get_deep_models(),
    })
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response

@app.post("/api/settings/avatar")
async def upload_avatar(avatar: UploadFile = File(...)):
    ext = os.path.splitext(avatar.filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        return {"error": "Unsupported image type"}
    content = await avatar.read()
    if len(content) > 2 * 1024 * 1024:
        return {"error": "Image too large (max 2MB)"}
    avatar_path = os.path.join("static", "images", f"user_avatar{ext}")
    os.makedirs(os.path.dirname(avatar_path), exist_ok=True)
    with open(avatar_path, "wb") as f:
        f.write(content)
    url = f"/static/images/user_avatar{ext}?t={int(time.time())}"
    database.set_state("USER_AVATAR", url)
    return {"url": url}

@app.post("/api/settings")
async def save_settings(request: Request):
    import llm_manager
    data = await request.json()
    database.set_state("USER_NAME", data.get("user_name", "Bayazid"))
    database.set_state("LOCATION", data.get("location", "Rajshahi"))
    if data.get("openrouter_key"): database.set_state("OPENROUTER_API_KEY", data.get("openrouter_key"))
    if data.get("image_model") is not None: database.set_state("IMAGE_MODEL", data.get("image_model"))
    if data.get("vision_model") is not None: database.set_state("VISION_MODEL", data.get("vision_model"))
    if data.get("selected_models") is not None: database.set_state("SELECTED_MODELS", data.get("selected_models"))
    if data.get("fallback_models") is not None: database.set_state("FALLBACK_MODELS", data.get("fallback_models"))
    if data.get("active_model") is not None: database.set_state("ACTIVE_MODEL", data.get("active_model"))
    if "user_avatar" in data: database.set_state("USER_AVATAR", data.get("user_avatar", ""))
    if data.get("hf_token") is not None: database.set_state("HF_TOKEN", data.get("hf_token", ""))
    # ── Multi-provider fields ──
    if data.get("providers") is not None:
        llm_manager.save_providers(data["providers"])
    if data.get("deep_models") is not None:
        llm_manager.save_deep_models(data["deep_models"])

    database.set_state("ONBOARDING_COMPLETE", "true")
    return {"status": "success"}

@app.post("/api/settings/uninstall")
async def uninstall(request: Request):
    """
    Clears downloaded data. Flags in body:
      clear_faiss: bool  — deletes FAISS index files from disk
      clear_hf_cache: bool — deletes HuggingFace model cache (~/.cache/huggingface)
      clear_all_state: bool — wipes all user_state DB keys (keeps chat history)
    """
    data = await request.json()
    results = {}

    if data.get("clear_faiss"):
        from config import FAISS_DIR
        import shutil
        try:
            if os.path.exists(FAISS_DIR):
                shutil.rmtree(FAISS_DIR)
                os.makedirs(FAISS_DIR, exist_ok=True)
            results["faiss"] = "cleared"
        except Exception as e:
            results["faiss"] = f"error: {e}"

    if data.get("clear_hf_cache"):
        hf_cache = os.path.expanduser("~/.cache/huggingface")
        import shutil
        try:
            if os.path.exists(hf_cache):
                shutil.rmtree(hf_cache)
            results["hf_cache"] = "cleared"
        except Exception as e:
            results["hf_cache"] = f"error: {e}"

    if data.get("clear_all_state"):
        try:
            database.clear_all_state()
            results["state"] = "cleared"
        except Exception as e:
            results["state"] = f"error: {e}"

    return {"status": "ok", "results": results}

# ── LIBRARY API ─────────────────────────────────────────────────────────────
@app.get("/library", response_class=HTMLResponse)
async def library_page(request: Request):
    return templates.TemplateResponse(request=request, name="library.html", context={"request": request})

@app.get("/api/rag/health")
async def rag_health_proxy():
    """Proxy to the RAG server's /health so the library UI can read storage stats."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get("http://127.0.0.1:5091/health")
            return r.json()
    except Exception as e:
        return {"status": "unavailable", "error": str(e)}

@app.get("/api/rag/index_progress")
async def rag_index_progress_proxy():
    """Proxy to the RAG server's /index_progress for UI status polling."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get("http://127.0.0.1:5091/index_progress")
            return r.json()
    except Exception:
        return {"state": "idle", "current": 0, "total": 0, "file": ""}

# ── MISSING API ENDPOINTS (called by library.html, pdf_library.html, marin_chat.html) ──

@app.post("/api/chat/context")
async def save_chat_tool_context(request: Request):
    """Save a tool result as system context so Marin knows what happened."""
    try:
        data = await request.json()
        tool_name = data.get("tool", "tool")
        result = data.get("result", "")
        if result:
            database.save_message("marin", "system", f"[TOOL RESULTS — {tool_name}] {str(result)[:2000]}")
            return {"ok": True}
        return {"ok": False, "error": "No result"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/validate-key")
async def validate_api_key_endpoint(request: Request):
    """Validate an LLM provider API key."""
    try:
        import llm_manager
        data = await request.json()
        key = data.get("key", "")
        base_url = data.get("base_url", "https://openrouter.ai/api/v1")
        if not key:
            return {"valid": False, "error": "No key provided"}
        success, message = llm_manager.validate_api_key(key, base_url)
        return {"valid": success, "error": message if not success else "Key is valid"}
    except Exception as e:
        return {"valid": False, "error": str(e)}

from pydantic import BaseModel as _BaseModel
class PlaygroundRequest(_BaseModel):
    title: str = ""
    description: str = ""
    html: str = ""
    css: str = ""
    js: str = ""

@app.post("/api/playground/build")
async def build_playground(req: PlaygroundRequest):
    """Build a sandboxed HTML playground page from html/css/js fragments."""
    page = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Inter', -apple-system, sans-serif; background: #0d1117; color: #e6edf3; padding: 16px; min-height: 100vh; }}
{req.css}
</style>
</head>
<body>
{req.html}
<script>
(function() {{
{req.js}
}})();
</script>
</body>
</html>"""
    return {"html": page, "title": req.title, "description": req.description}

@app.get("/api/documents/{filename}/content")
async def get_document_content(filename: str):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    books_dir = os.path.join(base_dir, "books")
    path = os.path.realpath(os.path.join(books_dir, filename))

    if not path.startswith(os.path.realpath(books_dir)) or not os.path.exists(path):
        return {"error": "File not found"}

    ext = filename.split(".")[-1].lower()
    content = ""

    try:
        if ext == "pdf":
            import fitz
            try:
                import pymupdf4llm
                content = pymupdf4llm.to_markdown(path)
            except ImportError:
                doc = fitz.open(path)
                for page in doc:
                    content += page.get_text() + "\n\n"
        elif ext == "docx":
            import mammoth
            with open(path, "rb") as f:
                result = mammoth.extract_raw_text(f)
                content = result.value
        elif ext in ["txt", "md"]:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

        return {"content": content[:50000]}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/documents/{filename}/page/{page_num}")
async def get_document_page(filename: str, page_num: int):
    """Extract text from a single PDF page (1-indexed). Used by library chat for page-aware context."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    books_dir = os.path.join(base_dir, "books")
    path = os.path.realpath(os.path.join(books_dir, filename))

    if not path.startswith(os.path.realpath(books_dir)) or not os.path.exists(path):
        return {"error": "File not found"}

    ext = filename.split(".")[-1].lower()
    if ext != "pdf":
        return {"error": "Page extraction only supported for PDF files"}

    try:
        import fitz
        # BUG 6 fix: use context manager so doc.close() is guaranteed on any exception
        with fitz.open(path) as doc:
            total = doc.page_count

            if page_num < 1 or page_num > total:
                return {"error": f"Page {page_num} out of range (1-{total})", "total_pages": total}

            text = doc[page_num - 1].get_text()  # fitz uses 0-indexed

        if not text.strip():
            return {
                "page": page_num,
                "total_pages": total,
                "content": "",
                "warning": "This page appears to be a scanned image with no extractable text."
            }

        return {
            "page": page_num,
            "total_pages": total,
            "content": text
        }
    except Exception as e:
        return {"error": str(e)}

# Duplicate /api/documents DELETE and POST removed — single definitions kept above (lines ~472-530)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
