import os
import re
import json
import asyncio
import subprocess
import signal
import sys
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List, Dict, Any, Optional

import ollama
import httpx

from config import DEFAULT_MODEL, FAST_MODEL, VISION_MODEL, OLLAMA_BASE_URL
from database import init_db, migrate_from_json
import database
from utils.shared_logic import (
    timer, handle_timer_command, USER_CONTEXT
)
from marin import main as marin_main, format_game_context_for_marin

from marin_fier import classify, extract_timer_task, extract_topic, extract_quiz_params # Use unified classifier
from config import UPLOAD_FOLDER, HOST, PORT

from contextlib import asynccontextmanager
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    migrate_from_json()
    print("[Database] Initialized and migrated.")

    async def _hourly_news_telegram():
<<<<<<< jules-18396265177757718316-26a03eda
        import asyncio as _aio
        while True:
            try:
                await _aio.sleep(3600)
                from tools.news_harvester import main as harvest_news
                await harvest_news()
            except Exception:
=======
        """Background task: harvest news + send top 10 headlines to Telegram every hour."""
        import asyncio as _aio
        while True:
            try:
                await _aio.sleep(3600)  # wait 1 hour
                print("[Scheduler] Running hourly news harvest...")
                from tools.news_harvester import fetch_all_news
                from tools.msg_telegram import send
                from database import init_db, save_news

                news = await fetch_all_news()
                if not news:
                    print("[Scheduler] No news found.")
                    continue

                # Save to DB
                try:
                    init_db()
                    save_news(news)
                except Exception:
                    pass

                # Send top 10 headlines to Telegram
                top = news[:10]
                msg = "🌍 **NEWS UPDATE**\n\n"
                for i, item in enumerate(top, 1):
                    src = item.get("source", "")
                    msg += f"{i}. [{src}] {item['title']}\n"
                send(msg)
                print(f"[Scheduler] Sent {len(top)} headlines to Telegram.")

            except Exception as e:
                print(f"[Scheduler] Error: {e}")
>>>>>>> main
                await _aio.sleep(60)

    async def _daily_habit_reminder():
        import asyncio as _aio
        import datetime
        while True:
            try:
                now = datetime.datetime.now()
                if now.hour == 9 and now.minute == 0:
                    from tools.habit import main as check_habits
                    check_habits()
                    await _aio.sleep(61)
                else:
                    await _aio.sleep(30)
            except Exception:
                await _aio.sleep(60)

    asyncio.create_task(_hourly_news_telegram())
    asyncio.create_task(_daily_habit_reminder())
    yield

app = FastAPI(title="Marin HS-02", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/moduleflow", StaticFiles(directory="moduleflow", html=True), name="moduleflow")

templates = Jinja2Templates(directory="templates")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("static/generated", exist_ok=True)

ACTIVE_AGENT = "marin"

# ── KNOWLEDGE HUB API ────────────────────────────────────────────────────────

@app.get("/knowledge-hub", response_class=HTMLResponse)
async def knowledge_hub_page(request: Request):
    return templates.TemplateResponse(request=request, name="knowledge_hub.html")

@app.post("/api/knowledge-hub/update")
async def knowledge_hub_update(request: Request):
    from tools.knowledge_hub import create_integrated_hub_map
    try:
        data = await request.json()
        location = data.get("location", "Dhaka")
        destination = data.get("destination")
        query = data.get("query") or "tourist attraction"
        limit = int(data.get("limit", 8))
        
        # The tool now handles searching pins internally via the 'query' parameter
        result = create_integrated_hub_map(location, destination, query=query, limit=limit)
        return JSONResponse(result)
    except Exception as e:
        print(f"[KnowledgeHub API] Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/research-hub", response_class=HTMLResponse)
async def research_hub_page(request: Request):
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/knowledge-hub?tab=research")

@app.post("/api/research/search")
async def research_search_api(request: Request):
    from tools.knowledge_hub import search_pdfs, search_web
    data = await request.json()
    query = data.get("query")
    mode = data.get("mode", "pdf")  # "pdf" or "web"
    results = search_web(query, max_results=10) if mode == "web" else search_pdfs(query)
    return JSONResponse({"results": results})



@app.post("/api/research/download")
async def research_download_api(request: Request):
    data = await request.json()
    url = data.get("url")
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return JSONResponse({"error": "Valid HTTP/HTTPS URL required"})

    import subprocess
    import time
    os.makedirs("static/downloads", exist_ok=True)

    try:
        if url.lower().endswith(".pdf"):
            filename = f"static/downloads/document_{int(time.time())}.pdf"
            subprocess.run(["curl", "-s", "-L", "-o", filename, "--", url], check=True, timeout=30)
            return JSONResponse({"status": "Success", "file": f"/{filename}"})
        else:
            filename = f"static/downloads/media_{int(time.time())}.%(ext)s"
            subprocess.run(["yt-dlp", "-o", filename, "--", url], check=True, timeout=60)
            return JSONResponse({"status": "Success", "msg": "Downloaded via yt-dlp to static/downloads/"})
    except Exception as e:
        return JSONResponse({"error": str(e)})

@app.post("/api/research/browse")
async def research_browse_api(request: Request):
    from tools.knowledge_hub import scrape_content
    data = await request.json()
    url = data.get("url")
    if not url: return JSONResponse({"error": "No URL provided"})

    try:
        content = scrape_content(url)
        return JSONResponse({"text": content})
    except Exception as e:
        return JSONResponse({"error": str(e)})

@app.get("/api/market/quotes")
async def market_quotes_api(symbols: str = "AAPL,TSLA,META"):
    symbols_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    out = []
    try:
        import yfinance as yf
        # yfinance can be slow or fail, use a try-block
        tickers = yf.Tickers(" ".join(symbols_list))
        for sym in symbols_list:
            try:
                # Some tickers might not exist in the object if they failed
                t = tickers.tickers[sym]
                info = t.info
                price = info.get("regularMarketPrice") or info.get("currentPrice")
                prev = info.get("regularMarketPreviousClose") or price
                chg = round(((price - prev) / prev) * 100, 2) if prev and price else 0.0
                out.append({"symbol": sym, "price": price or 0, "change_pct": chg})
            except Exception:
                out.append({"symbol": sym, "price": 0, "change_pct": 0.0})
    except Exception as e:
        print(f"[MarketAPI] Error: {e}")
        out = [{"symbol": s, "price": 0, "change_pct": 0.0} for s in symbols_list]
    return JSONResponse(out)

@app.get("/api/news/latest")
async def get_latest_news_api():
    try:
        from database import get_latest_news
        items = get_latest_news(limit=10)
        if items:
            return JSONResponse(items)
    except Exception:
        pass
    news_file = "storage/latest_news.json"
    if os.path.exists(news_file):
        with open(news_file, "r") as f:
            return JSONResponse(json.load(f))
    return JSONResponse([])

@app.post("/api/tools/open")
async def tools_open_api(request: Request):
    data = await request.json()
    tool = data.get("tool", "")
    params = data.get("params", {})
    
    import subprocess
    base = os.path.dirname(os.path.abspath(__file__))
    
    if tool == "get_stock_info":
        company = params.get("company", "AAPL")
        script = os.path.join(base, "tools", "stock.py")
        flag = "--ticker" if (len(company) <= 5 and company.isupper()) else "--company"
        subprocess.Popen([sys.executable, script, flag, company], start_new_session=True)
    elif tool == "get_crypto_price":
        coin = params.get("coin", "bitcoin")
        script = os.path.join(base, "tools", "crypto.py")
        subprocess.Popen([sys.executable, script, "--coin", coin], start_new_session=True)
        
    return JSONResponse({"status": "launched", "tool": tool})

@app.post("/api/cmd/run")
async def cmd_run_api(request: Request):
    from marin_fier import tool_run_command
    data = await request.json()
    command = data.get("command", "")
    output = tool_run_command(command)
    return JSONResponse({"output": output})


# ── TODO API (Integrated) ──────────────────────────────────────────────────
import sqlite3
from datetime import date

DB_TODO = "storage/todos.db"

def get_todo_db():
    conn = sqlite3.connect(DB_TODO)
    conn.row_factory = sqlite3.Row
    return conn

def init_todo_db():
    db = get_todo_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category_id INTEGER,
            status TEXT DEFAULT 'todo',
            priority TEXT DEFAULT 'medium',
            created_at TEXT DEFAULT (date('now')),
            completed_at TEXT,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
        );
    ''')
    db.commit()
    db.close()

init_todo_db()

@app.get("/todo", response_class=HTMLResponse)
async def get_todo_page(request: Request):
    return templates.TemplateResponse(request=request, name="todo.html")

@app.get("/api/todos")
async def list_todos():
    db = get_todo_db()
    todos = db.execute(
        "SELECT t.*, c.name as category_name FROM todos t "
        "LEFT JOIN categories c ON t.category_id = c.id ORDER BY t.id DESC"
    ).fetchall()
    db.close()
    return JSONResponse([dict(r) for r in todos])

@app.post("/api/todos")
async def create_todo(request: Request):
    data = await request.json()
    db = get_todo_db()
    category_id = data.get("category_id")
    db.execute(
        "INSERT INTO todos (title, category_id, priority) VALUES (?, ?, ?)",
        (data["title"], category_id or None, data.get("priority", "medium")),
    )
    db.commit()
    todo_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    todo = db.execute(
        "SELECT t.*, c.name as category_name FROM todos t "
        "LEFT JOIN categories c ON t.category_id = c.id WHERE t.id = ?",
        (todo_id,),
    ).fetchone()
    db.close()
    return JSONResponse(dict(todo), status_code=201)

@app.patch("/api/todos/{id}")
async def update_todo(id: int, request: Request):
    data = await request.json()
    db = get_todo_db()
    fields = []
    values = []
    for key in ("title", "status", "priority", "category_id"):
        if key in data:
            fields.append(f"{key} = ?")
            values.append(data[key])
    if "status" in data and data["status"] == "done":
        fields.append("completed_at = ?")
        values.append(date.today().isoformat())
    if "status" in data and data["status"] != "done":
        fields.append("completed_at = NULL")
    values.append(id)
    db.execute(f"UPDATE todos SET {', '.join(fields)} WHERE id = ?", values)
    db.commit()
    todo = db.execute(
        "SELECT t.*, c.name as category_name FROM todos t "
        "LEFT JOIN categories c ON t.category_id = c.id WHERE t.id = ?",
        (id,),
    ).fetchone()
    db.close()
    return JSONResponse(dict(todo))

@app.delete("/api/todos/{id}")
async def delete_todo(id: int):
    db = get_todo_db()
    db.execute("DELETE FROM todos WHERE id = ?", (id,))
    db.commit()
    db.close()
    return JSONResponse({"ok": True})

@app.get("/api/categories")
async def list_categories():
    db = get_todo_db()
    cats = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    db.close()
    return JSONResponse([dict(c) for c in cats])

@app.post("/api/categories")
async def create_category(request: Request):
    data = await request.json()
    db = get_todo_db()
    try:
        db.execute("INSERT INTO categories (name) VALUES (?)", (data["name"],))
        db.commit()
        cat_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    except sqlite3.IntegrityError:
        existing = db.execute(
            "SELECT * FROM categories WHERE name = ?", (data["name"],)
        ).fetchone()
        db.close()
        return JSONResponse(dict(existing))
    cat = db.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
    db.close()
    return JSONResponse(dict(cat), status_code=201)

@app.get("/api/stats")
async def stats():
    db = get_todo_db()

    status_data = db.execute(
        "SELECT status, COUNT(*) as count FROM todos GROUP BY status"
    ).fetchall()

    cat_data = db.execute(
        "SELECT c.name, "
        "  COUNT(t.id) as total, "
        "  SUM(CASE WHEN t.status='done' THEN 1 ELSE 0 END) as done, "
        "  SUM(CASE WHEN t.status='in-progress' THEN 1 ELSE 0 END) as in_progress, "
        "  SUM(CASE WHEN t.status='todo' THEN 1 ELSE 0 END) as todo "
        "FROM categories c "
        "LEFT JOIN todos t ON c.id = t.category_id "
        "GROUP BY c.id ORDER BY c.name"
    ).fetchall()

    daily = db.execute(
        "SELECT completed_at, COUNT(*) as count FROM todos "
        "WHERE status = 'done' AND completed_at IS NOT NULL "
        "GROUP BY completed_at ORDER BY completed_at DESC LIMIT 7"
    ).fetchall()

    priority = db.execute(
        "SELECT priority, COUNT(*) as count FROM todos GROUP BY priority"
    ).fetchall()

    db.close()
    return JSONResponse({
        "status": {r["status"]: r["count"] for r in status_data},
        "categories": [dict(c) for c in cat_data],
        "daily_completion": [dict(d) for d in daily],
        "priority": {r["priority"]: r["count"] for r in priority},
    })

# ── VAULT API ─────────────────────────────────────────────────────────────

@app.get("/vault", response_class=HTMLResponse)
async def vault_explorer_page(request: Request):
    return templates.TemplateResponse(request=request, name="vault_explorer.html")

@app.get("/api/vault/list/{agent}")
async def vault_list_api(agent: str):
    from tools.vault_manager import manage_vault
    return JSONResponse(manage_vault(agent, "list"))

@app.post("/api/vault/read")
async def vault_read_api(request: Request):
    from tools.vault_manager import manage_vault
    data = await request.json()
    return JSONResponse(manage_vault(data["agent"], "read", data["filename"], category=data["category"]))

@app.post("/api/vault/delete")
async def vault_delete_api(request: Request):
    from tools.vault_manager import manage_vault
    data = await request.json()
    return JSONResponse(manage_vault(data["agent"], "delete", data["filename"], category=data["category"]))

# ── PAGE ROUTES ───────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    # SIGNATURE FIX: Use request=request keyword to avoid interpretation as context
    return templates.TemplateResponse(request=request, name="marin_chat.html", context={"agent": "marin"})

@app.get("/profile", response_class=HTMLResponse)
async def get_profile(request: Request):
    return templates.TemplateResponse(request=request, name="profile.html")


# ── UPLOAD ────────────────────────────────────────────────────────────────

@app.post("/upload")
async def upload_image(image: UploadFile = File(...)):
    if not image.filename:
        return JSONResponse({"error": "No filename"}, status_code=400)
    filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', image.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    with open(filepath, "wb") as buf:
        buf.write(await image.read())
    return {"ok": True, "path": f"/{filepath}"}


# ── MAIN CHAT ENDPOINT ────────────────────────────────────────────────────

@app.post("/message")
async def handle_message(
    message: str = Form(...),
    image: UploadFile = File(None),
    study_context: str = Form(None),
    agent: str = Form(None)
):
    global ACTIVE_AGENT
    # We ignore the 'agent' parameter and always use marin now
    target_agent = "marin"
    print(f"[Message] Agent: {target_agent} | Msg: {message[:50]}...")

    image_path = None
    if image and image.filename:
        filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', image.filename)
        image_path = os.path.join(UPLOAD_FOLDER, filename)
        with open(image_path, "wb") as buf:
            buf.write(await image.read())
        image_path = os.path.abspath(image_path)

    print(f"[Routing] -> Marin Engine (LangGraph)")
    from proactive_engine import record_user_message
    record_user_message(agent)
    from games.tiktaktoe import get_game
    game = get_game()
    state = game.get_board_state() if game else None
    game_context = format_game_context_for_marin(state) if state else None
    
    # Inject timer info into the message if needed (though LangGraph should handle it via tools or context)
    timer_status = timer.get_session_status()
    msg_with_timer = message
    if timer_status["active"]:
        msg_with_timer = f"[Focus: {timer_status['task']} ({timer_status['elapsed_formatted']})]\n{message}"
    
    return StreamingResponse(
        marin_main(msg_with_timer, image_path=image_path, game_context=game_context),
        media_type="text/plain"
    )


# ── SETTINGS & UTILS ─────────────────────────────────────────────────────

@app.get("/settings/voice")
async def get_voice_setting():
    import marin
    return {"voice_enabled": marin.VOICE_ENABLED}

@app.post("/settings/voice")
async def set_voice_setting(enabled: str = Form(...)):
    import marin
    marin.VOICE_ENABLED = (enabled == "1")
    return {"ok": True, "voice_enabled": marin.VOICE_ENABLED}

@app.get("/settings/rag")
async def get_rag_setting():
    import marin
    from utils.agent_logic import RAG_URL
    running = False
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{RAG_URL}/health", timeout=1.0)
            if r.status_code == 200: running = True
    except: pass
    return {"rag_enabled": marin.RAG_ENABLED, "rag_running": running}

@app.post("/settings/rag")
async def set_rag_setting(enabled: str = Form(...)):
    import marin
    marin.RAG_ENABLED = (enabled == "1")
    if marin.RAG_ENABLED:
        # Ensure server is running
        from utils.agent_logic import RAG_URL
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{RAG_URL}/health", timeout=1.0)
                if r.status_code != 200: raise Exception("Not running")
        except:
            # Start it
            base = os.path.dirname(os.path.abspath(__file__))
            script = os.path.join(base, "rag_server.py")
            subprocess.Popen([sys.executable, script, "--port", "5080"], start_new_session=True)
            
    return JSONResponse({"ok": True, "rag_enabled": marin.RAG_ENABLED})

@app.get("/settings/wordlimit")
async def get_wordlimit():
    import marin
    return {"word_limit": marin.WORD_LIMIT}

@app.post("/settings/wordlimit")
async def set_wordlimit(limit: int = Form(...)):
    import marin
    marin.WORD_LIMIT = limit
    return {"ok": True, "word_limit": marin.WORD_LIMIT}

@app.post("/audio/stop")
async def stop_audio_endpoint():
    from marin import stop_audio
    stopped = stop_audio()
    return {"ok": True, "stopped": stopped}

@app.get("/cmd/log/json")
async def get_cmd_log(limit: int = 10):
    from marin_fier import _cmd_log
    logs = _cmd_log[-limit:] if _cmd_log else []
    return {"logs": logs}

@app.post("/timer/command")
async def timer_cmd(command: str = Form(...), task: str = Form("")):
    result = await handle_timer_command(command, task)
    return JSONResponse({"message": result, "stats": timer.get_stats()})

@app.get("/timer/stats")
async def get_timer_stats():
    return JSONResponse(timer.get_stats())

@app.get("/memory/status")
async def memory_status(agent: str = None):
    from marin import load_history
    messages = load_history(limit=60)
    return JSONResponse({"messages": messages})

@app.post("/memory/clear")
async def memory_clear_endpoint(agent: str = Form(None)):
    database.clear_history("marin")
    return {"ok": True}

@app.get("/health")
async def health():
    return {"status": "operational", "codename": "Marin HS-02"}

<<<<<<< jules-18396265177757718316-26a03eda

=======
# ── AGENT LOGS ───────────────────────────────────────────────────────────

@app.get("/logs", response_class=HTMLResponse)
async def agent_logs_page(request: Request):
    return templates.TemplateResponse(request=request, name="agent_logs.html")

@app.get("/api/logs")
async def agent_logs_api(limit: int = 100):
    from tools.agent_log import get_entries
    return JSONResponse(get_entries(limit))

# ── PROACTIVE ENGINE ─────────────────────────────────────────────────────

@app.get("/proactive/stream")
async def proactive_sse(agent: str = "marin"):
    from proactive_engine import proactive_stream
    return StreamingResponse(
        proactive_stream(agent),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )

from unique.marin_vault.core_dna.main import app as _app
app.mount("/vault/bayazid", _app, name="bayazid_vault")
>>>>>>> main

if __name__ == "__main__":
    import uvicorn
    init_db()
    migrate_from_json()
    uvicorn.run(app, host=HOST, port=PORT)