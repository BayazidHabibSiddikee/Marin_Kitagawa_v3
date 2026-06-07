"""
main.py — Binance Trading & Financial Advisor
Fused with market intelligence, real-time news, and specialized RAG.
"""

import os
import sys
import json
import subprocess
import asyncio
import re
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import httpx

from config import DEFAULT_MODEL, OLLAMA_BASE_URL, HOST, PORT
from database import init_db, migrate_from_json
import database
import business_marin

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAG_PORT = 5081
RAG_URL  = f"http://127.0.0.1:{RAG_PORT}"

app = FastAPI(title="Binance Trading Advisor — Financial Intelligence")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

_rag_process = None
_news_process = None

def _start_rag_server():
    """Start rag_server.py pointed at busi_doc/ on port 5081."""
    global _rag_process
    try:
        r = httpx.get(f"{RAG_URL}/health", timeout=2.0)
        if r.status_code == 200:
            return
    except Exception:
        pass

    script = os.path.join(BASE_DIR, "rag_server.py")
    log_dir = os.path.join(BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log = open(os.path.join(log_dir, "business_rag.log"), "a")
    env = {
        **os.environ,
        "RAG_DOC_DIR":   os.path.join(BASE_DIR, "busi_doc"),
        "RAG_FAISS_DIR": os.path.join(BASE_DIR, "storage", "faiss_db"),
    }
    _rag_process = subprocess.Popen(
        [sys.executable, script, "--port", str(RAG_PORT)],
        stdout=log, stderr=log, env=env,
    )
    print(f"[RAG] Started busi_doc RAG server on port {RAG_PORT}")

def _start_news_harvester():
    """Start news_harvester.py in background to populate latest_news.json."""
    global _news_process
    script = os.path.join(BASE_DIR, "tools", "news_harvester.py")
    log_dir = os.path.join(BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log = open(os.path.join(log_dir, "news_harvester.log"), "a")
    _news_process = subprocess.Popen(
        [sys.executable, script],
        stdout=log, stderr=log,
        start_new_session=True
    )
    print(f"[News] Started news harvester background process")


@app.on_event("startup")
async def startup_event():
    init_db()
    migrate_from_json()
    os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "static", "uploads"), exist_ok=True)
    
    _start_rag_server()
    _start_news_harvester()
    
    print(f"[Binance Advisor] Ready on port {PORT}")


# ── Page Routes ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request, name="chat.html", context={"agent": "business"}
    )

@app.get("/knowledge-hub", response_class=HTMLResponse)
async def knowledge_hub_page(request: Request):
    # Check if template exists, if not, it might have been deleted.
    # I'll restore it in a separate step if needed.
    return templates.TemplateResponse(request=request, name="knowledge_hub.html")


# ── Main Chat Endpoint ────────────────────────────────────────────────────────

@app.post("/message")
async def handle_message(
    message: str = Form(...),
    image: UploadFile = File(None)
):
    image_path = None
    if image and image.filename:
        safe_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', image.filename)
        image_path = os.path.join(BASE_DIR, "static", "uploads", safe_name)
        with open(image_path, "wb") as buf:
            buf.write(await image.read())
        image_path = os.path.abspath(image_path)

    return StreamingResponse(
        business_marin.main(message),
        media_type="text/plain"
    )


# ── Market & Data APIs ────────────────────────────────────────────────────────

@app.get("/api/market/live")
async def market_live():
    data = await asyncio.to_thread(business_marin._fetch_live_market_data)
    return JSONResponse({"data": data})

@app.get("/api/market/quotes")
async def market_quotes(symbols: str = "AAPL,TSLA,NVDA,SPY,MSFT,BTC-USD,ETH-USD"):
    symbols_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    out = []
    try:
        import yfinance as yf
        tickers = yf.Tickers(" ".join(symbols_list))
        for sym in symbols_list:
            try:
                info  = tickers.tickers[sym].info
                price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
                chg   = info.get("regularMarketChangePercent", 0)
                out.append({"symbol": sym, "price": price, "change_pct": round(chg, 2)})
            except Exception:
                out.append({"symbol": sym, "price": 0, "change_pct": 0.0})
    except Exception as e:
        out = [{"symbol": s, "price": 0, "change_pct": 0.0} for s in symbols_list]
    return JSONResponse(out)

@app.get("/api/crypto/prices")
async def crypto_prices(coins: str = "bitcoin,ethereum,solana,binancecoin,ripple"):
    coin_list = [c.strip().lower() for c in coins.split(",") if c.strip()]
    try:
        import requests
        ids  = ",".join(coin_list)
        url  = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"
        data = requests.get(url, timeout=6).json()
        out  = []
        for coin in coin_list:
            if coin in data:
                out.append({
                    "coin":       coin,
                    "price":      data[coin].get("usd", 0),
                    "change_24h": round(data[coin].get("usd_24h_change", 0), 2),
                })
        return JSONResponse(out)
    except Exception as e:
        return JSONResponse({"error": str(e)})

@app.get("/api/news/latest")
async def latest_news():
    news_file = os.path.join(BASE_DIR, "storage", "latest_news.json")
    if os.path.exists(news_file):
        try:
            with open(news_file) as f:
                return JSONResponse(json.load(f))
        except Exception:
            pass
    
    # Fallback to live search if file missing or corrupt
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.news("binance trading crypto economy", max_results=10))
        return JSONResponse(results)
    except Exception:
        return JSONResponse([])


# ── Research Hub API ──────────────────────────────────────────────────────────

@app.post("/api/research/search")
async def research_search_api(request: Request):
    from tools.knowledge_hub import search_pdfs, search_web
    data = await request.json()
    query = data.get("query")
    mode = data.get("mode", "pdf")  # "pdf" or "web"
    if mode == "web":
        results = search_web(query, max_results=10)
    else:
        results = search_pdfs(query)
    return JSONResponse({"results": results})


# ── Settings & Memory ─────────────────────────────────────────────────────────

@app.get("/settings/rag")
async def get_rag():
    running = False
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{RAG_URL}/health", timeout=1.0)
            running = r.status_code == 200
    except Exception:
        pass
    return {"rag_enabled": business_marin.RAG_ENABLED, "rag_running": running}

@app.post("/settings/rag")
async def set_rag(enabled: str = Form(...)):
    business_marin.RAG_ENABLED = (enabled == "1")
    if business_marin.RAG_ENABLED:
        _start_rag_server()
    return {"ok": True, "rag_enabled": business_marin.RAG_ENABLED}

@app.get("/memory/status")
async def memory_status():
    return JSONResponse({"messages": business_marin.load_history(limit=40)})

@app.post("/memory/clear")
async def memory_clear():
    database.clear_history("business_marin")
    return {"ok": True}

@app.get("/health")
async def health():
    return {"status": "operational", "codename": "BINANCE-ADVISOR-CORE"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
