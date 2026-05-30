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
import database
from utils.shared_logic import (
    timer, handle_timer_command, USER_CONTEXT
)
from marin import main as marin_main, format_game_context_for_marin

from marin_fier import classify, extract_timer_task, extract_topic, extract_quiz_params # Use unified classifier
from config import UPLOAD_FOLDER, HOST, PORT

app = FastAPI(title="Marin HS-02")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/codeflow", StaticFiles(directory="codeflow", html=True), name="codeflow")

from  import app as _app
app.mount("/", _app, name="")
templates = Jinja2Templates(directory="templates")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("static/generated", exist_ok=True)

@app.on_event("startup")
async def startup_event():
    init_db()
    migrate_from_json()
    print("[Database] Initialized and migrated.")

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
async def chat_page(request: Request, agent: str = "marin"):
    global ACTIVE_AGENT
    ACTIVE_AGENT = "marin"
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


if __name__ == "__main__":
    import uvicorn
    init_db()
    migrate_from_json()
    uvicorn.run(app, host=HOST, port=PORT)
