"""
business_marin.py — Binance Trading Advisor & Financial Strategist
Every chat turn: fetches live news + crypto + stock data and injects into context.
"""

import ollama
import json
import os
import asyncio
import re
from datetime import datetime
from typing import AsyncIterator

import database
from config import DEFAULT_MODEL as MODEL

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAG_ENABLED = False  # toggled via /settings/rag

# ── Classifier ────────────────────────────────────────────────────────────────
try:
    from business_fier import classify
except ImportError:
    def classify(text):
        return {"intent": "chat", "params": {}, "confidence": 0.0}

# ── Business Persona ──────────────────────────────────────────────────────────
BASE_CHARACTER = """
You are the Business Advisor — an expert Binance trader, financial analyst, and economic strategist.
You provide professional-grade financial advice based on real-time market data and deep economic understanding.

CORE IDENTITY:
- Role: Expert Binance Trading Advisor & Financial Strategist.
- Expertise: Binance spot/futures trading, technical analysis, macro-economic impact on markets, and portfolio risk management.
- Style: Professional, analytical, and data-driven. You look for "alpha" in the data.

BEHAVIORAL DIRECTIVES:
✓ Always prioritize Binance trading signals and crypto market analysis.
✓ Analyze how global economic news (FED, inflation, stocks) impacts the crypto market.
✓ Use `get_stock_info`, `get_crypto_price`, and web search to build a holistic market view.
✓ Provide actionable trading insights: entry/exit zones, risk-reward ratios, and trend strength.
✓ Reference the business library in `busi_doc` (Dalio, Soros, Graham) for timeless financial wisdom.

TRADING PRINCIPLES:
- Risk Management First: Never suggest a trade without mentioning risk.
- Convergence: Look for confirmation across different data sources (e.g., stock market trends vs. crypto price action).
- No Hallucination: If data is unavailable, state it clearly. Use real-time tools for numbers.
"""

_RAG_URL = "http://127.0.0.1:5081"  # separate port from main rag_server


# ── History ───────────────────────────────────────────────────────────────────
def load_history(limit: int = 20) -> list:
    return database.get_history("business_marin", limit=limit)

def save_to_history(user_msg: str, reply: str):
    database.save_message("business_marin", "user", user_msg)
    database.save_message("business_marin", "assistant", reply)


# ── Live Market Data Fetcher ──────────────────────────────────────────────────
DEFAULT_STOCKS  = ["AAPL", "TSLA", "NVDA", "SPY", "MSFT", "QQQ"]
DEFAULT_CRYPTOS = ["bitcoin", "ethereum", "solana", "binancecoin", "ripple"]

def _fetch_live_market_data() -> str:
    """Fetch stocks + crypto + news. Returns a formatted context string."""
    lines = [f"[LIVE MARKET DATA — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}]"]

    # Stocks
    try:
        import yfinance as yf
        tickers = yf.Tickers(" ".join(DEFAULT_STOCKS))
        stock_lines = []
        for sym in DEFAULT_STOCKS:
            try:
                info  = tickers.tickers[sym].info
                price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
                chg   = info.get("regularMarketChangePercent", 0)
                stock_lines.append(f"  {sym}: ${price:.2f} ({chg:+.2f}%)")
            except Exception:
                pass
        if stock_lines:
            lines.append("STOCKS & INDICES:\n" + "\n".join(stock_lines))
    except Exception as e:
        lines.append(f"STOCKS: unavailable ({e})")

    # Crypto
    try:
        import requests
        ids = ",".join(DEFAULT_CRYPTOS)
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"
        data = requests.get(url, timeout=6).json()
        crypto_lines = []
        for coin in DEFAULT_CRYPTOS:
            if coin in data:
                p   = data[coin].get("usd", 0)
                chg = data[coin].get("usd_24h_change", 0)
                crypto_lines.append(f"  {coin.title()}: ${p:,.2f} ({chg:+.2f}%)")
        if crypto_lines:
            lines.append("CRYPTO (Binance Focus):\n" + "\n".join(crypto_lines))
    except Exception as e:
        lines.append(f"CRYPTO: unavailable ({e})")

    # News headlines from storage cache (populated by news_harvester.py)
    try:
        news_file = os.path.join(BASE_DIR, "storage", "latest_news.json")
        if os.path.exists(news_file):
            with open(news_file) as f:
                news = json.load(f)
            headlines = [f"  • {n.get('title','')}" for n in news[:6] if n.get("title")]
            if headlines:
                lines.append("LATEST MARKET NEWS:\n" + "\n".join(headlines))
    except Exception:
        pass

    return "\n".join(lines)


def _fetch_rag_context(query: str) -> str:
    """Fetch RAG context from busi_doc FAISS server."""
    try:
        import httpx
        r = httpx.post(f"{_RAG_URL}/context", json={"query": query, "k": 6}, timeout=8.0)
        r.raise_for_status()
        return r.json().get("context", "")
    except Exception:
        return ""


# ── Tool dispatch for specific intents ───────────────────────────────────────
def _run_intent_tool(intent: str, params: dict) -> str:
    """Run the appropriate tool based on classified intent."""
    try:
        if intent == "stock":
            from tools.stock_data import fetch_stock_price
            return fetch_stock_price(params.get("company", "AAPL"))

        elif intent == "crypto":
            from tools.crypto_data import fetch_crypto_price
            return fetch_crypto_price(params.get("coin", "bitcoin"))

        elif intent == "web_search":
            from tools.knowledge_hub import search_web
            results = search_web(params.get("query", ""), max_results=5)
            if isinstance(results, list):
                return "\n".join(f"• {r['title']}: {r.get('body', r.get('snippet', ''))[:200]}" for r in results)
            return str(results)

        elif intent == "search_pdfs":
            from tools.knowledge_hub import search_pdfs
            results = search_pdfs(params.get("topic", ""))
            if isinstance(results, list):
                return "\n".join(f"• {r['title']} ({r.get('year', 'N/A')})" for r in results)
            return str(results)

        elif intent == "news":
            from duckduckgo_search import DDGS
            topic = params.get("topic", "binance trading market")
            with DDGS() as ddgs:
                results = list(ddgs.news(topic, max_results=6))
            return "\n".join(f"• {r['title']}" for r in results)

        elif intent == "forex":
            pair = params.get("pair", "USD/EUR")
            import requests
            base, quote = pair.split("/") if "/" in pair else (pair[:3], pair[3:])
            url = f"https://api.frankfurter.app/latest?from={base}&to={quote}"
            data = requests.get(url, timeout=6).json()
            rate = data.get("rates", {}).get(quote, "N/A")
            return f"{base}/{quote} exchange rate: {rate}"

    except Exception as e:
        return f"[Tool error: {e}]"
    return ""


# ── Main streaming entry point ────────────────────────────────────────────────
async def main(prompt: str) -> AsyncIterator[str]:
    clf    = classify(prompt)
    intent = clf["intent"]
    params = clf.get("params", {})

    # 1. Fetch live market data (always)
    market_data = await asyncio.to_thread(_fetch_live_market_data)

    # 2. Run specific tool if intent matched
    tool_result = ""
    if intent not in ("chat", "market_analysis", "portfolio"):
        tool_result = await asyncio.to_thread(_run_intent_tool, intent, params)

    # 3. RAG context from busi_doc
    rag_context = ""
    if RAG_ENABLED:
        rag_context = await asyncio.to_thread(_fetch_rag_context, prompt)

    # 4. Build messages
    history  = load_history(limit=20)
    now_str  = datetime.now().strftime("%A, %B %d, %Y | %I:%M %p")

    system_parts = [BASE_CHARACTER, f"\n[CURRENT TIME]\n{now_str}", f"\n{market_data}"]
    if rag_context:
        system_parts.append(f"\n[FINANCIAL WISDOM — Dalio/Soros/Graham]\n{rag_context}")

    messages = [{"role": "system", "content": "\n".join(system_parts)}]
    messages.extend(history)

    if tool_result:
        messages.append({
            "role": "system",
            "content": f"[TOOL RESULT — {intent.upper()}]\n{tool_result}"
        })

    messages.append({"role": "user", "content": prompt})

    # 5. Stream response
    full_reply = ""
    client = ollama.AsyncClient()
    async for chunk in await client.chat(model=MODEL, messages=messages, stream=True):
        piece = chunk.message.content if hasattr(chunk, "message") else chunk["message"]["content"]
        full_reply += piece
        yield piece

    save_to_history(prompt, full_reply)
