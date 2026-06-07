import os
import re
import secrets
import threading
import tempfile
import shlex
import subprocess
import hmac
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth

from config import (
    DEFAULT_MODEL, FAST_MODEL, VISION_MODEL, OLLAMA_BASE_URL,
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_CONF_URL, SESSION_SECRET_KEY,
    HOST, PORT, UPLOAD_FOLDER
)
from database import init_db, get_user_by_api_key, create_user, promote_user
from utils.agent_logic import stream_marin_chat
from langgraph_agent import ALL_TOOLS, tools_by_name

# ── LIFESPAN ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("[Database] Initialized Marin Tools.")
    yield

app = FastAPI(title="Marin Tools — AI sentinel", lifespan=lifespan)

# ── MIDDLEWARE ───────────────────────────────────────────────────────────

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)

API_SECRET = os.getenv("MARIN_API_SECRET")
if not API_SECRET:
    API_SECRET = secrets.token_hex(32)
    print(f"[SECURITY] Generated temporary runtime secret: {API_SECRET}")

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    path = request.url.path
    
    # Public routes
    if path in ("/", "/landing", "/login", "/auth", "/logout", "/setup", "/health"):
        return await call_next(request)
        
    # Static files
    if path.startswith("/static/"):
        return await call_next(request)

    # Auth check
    session_user = request.session.get("user")
    api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")

    if session_user:
        request.state.user = session_user
    elif api_key and hmac.compare_digest(api_key, API_SECRET):
        request.state.user = {"user_id": "USR-MASTER", "username": "admin", "role": "owner"}
    elif api_key:
        user = get_user_by_api_key(api_key)
        if user:
            request.state.user = user
        else:
            return JSONResponse(status_code=403, content={"detail": "Invalid API Key"})
    else:
        if path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"detail": "Authentication required"})
        return RedirectResponse(url="/landing")

    return await call_next(request)

# ── SETUP ───────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ── CORE ROUTES ──────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "operational", "time": datetime.now().isoformat()}

@app.get("/landing", response_class=HTMLResponse)
async def landing_page(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    user = getattr(request.state, "user", None)
    if not user: return RedirectResponse("/landing")
    return templates.TemplateResponse("marin_chat.html", {"request": request, "user": user})

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    user = getattr(request.state, "user", None)
    if not user: return RedirectResponse("/landing")
    return templates.TemplateResponse("marin_chat.html", {"request": request, "user": user})

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

@app.get("/api/tools")
async def list_tools_api():
    return JSONResponse([{"name": t.name, "description": t.description} for t in ALL_TOOLS])

@app.post("/api/tools/{name}")
async def call_tool_api(name: str, request: Request):
    if name not in tools_by_name:
        raise HTTPException(404, f"Tool {name} not found")
    data = await request.json()
    data["user_id"] = request.state.user["user_id"]
    try:
        result = tools_by_name[name].invoke(data)
        return {"result": result}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/todos")
async def list_todos_api(request: Request):
    user_id = request.state.user["user_id"]
    import sqlite3
    db = sqlite3.connect("storage/todos.db")
    db.row_factory = sqlite3.Row
    todos = db.execute("SELECT * FROM todos WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    db.close()
    return JSONResponse([dict(r) for r in todos])

@app.get("/api/market/quotes")
async def market_quotes_api(symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT,SPY"):
    from marin import _fetch_live_market_data
    # This is a bit of a hack but reusing the existing logic
    # In a real app we'd have a separate market module
    data = []
    for s in symbols.split(","):
        data.append({"symbol": s, "price": "63240.50", "change": "+1.2%"}) # Mock for now
    return JSONResponse(data)

@app.get("/api/conversations")
async def list_conversations_api(request: Request):
    user_id = request.state.user["user_id"]
    import database
    with database.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT session_id FROM chat_history WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        )
        return JSONResponse([r["session_id"] for r in cursor.fetchall()])

# ── AUTH (Google OAuth) ────────────────────────────────────────────────────

oauth = OAuth()
if GOOGLE_CLIENT_ID:
    oauth.register(
        name='google',
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url=GOOGLE_CONF_URL,
        client_kwargs={'scope': 'openid email profile'}
    )

@app.get("/login")
async def login_redirect(request: Request):
    if not GOOGLE_CLIENT_ID:
        user = create_user("developer", role="owner")
        request.session["user"] = user
        return RedirectResponse("/")
    return await oauth.google.authorize_redirect(request, request.url_for('auth'))

@app.get("/auth")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')
    request.session["temp_user"] = user_info
    return RedirectResponse("/setup")

@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    temp = request.session.get("temp_user")
    return templates.TemplateResponse("onboarding.html", {"request": request, "username": temp.get("name")})

@app.post("/setup")
async def complete_setup(request: Request, display_name: str = Form(...)):
    temp = request.session.get("temp_user")
    user = create_user(temp["email"], display_name=display_name)
    request.session["user"] = user
    request.session.pop("temp_user")
    return RedirectResponse("/")

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/landing")

@app.post("/api/authorize")
async def authorize_session(request: Request):
    data = await request.json()
    password = data.get("password")
    user_id = request.state.user["user_id"]
    
    from safety import system_guard
    if system_guard.verify(user_id, password):
        return {"status": "success", "message": "Session authorized."}
    else:
        raise HTTPException(status_code=403, detail="Invalid system password.")

@app.post("/api/settings/password")
async def update_system_password(request: Request):
    data = await request.json()
    current = data.get("current")
    new_pass = data.get("new")
    user_id = request.state.user["user_id"]
    
    if request.state.user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the master can change the system password.")
        
    from safety import system_guard
    if system_guard.verify(user_id, current):
        system_guard.set_password(new_pass)
        return {"status": "success", "message": "System password updated."}
    else:
        raise HTTPException(status_code=403, detail="Invalid current password.")

# ── MODULEFLOW ────────────────────────────────────────────────────────────

@app.get("/moduleflow")
async def moduleflow_page(request: Request):
    from moduleflow.serve import get_index
    return HTMLResponse(await get_index())

@app.get("/moduleflow/graph.json")
async def moduleflow_graph(request: Request):
    from moduleflow.analyze import analyze_brain
    return JSONResponse(analyze_brain())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
