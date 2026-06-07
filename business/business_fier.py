"""
business_fier.py — Business/Market intent classifier (regex-only, zero-latency)
Intents: stock, crypto, news, market_analysis, web_search, forex, portfolio, search_pdfs, chat
"""
import re
from typing import Dict, Any


def classify(text: str) -> Dict[str, Any]:
    lower = text.lower().strip()
    intent = "chat"
    params: Dict[str, Any] = {}

    # ── PDF SEARCH (Books/Papers) ──────────────────────────────────────────
    if re.search(r'\b(pdf|book|paper|textbook|research|thesis)\b', lower) and re.search(r'\b(search|find|lookup)\b', lower):
        # Extract topic by removing search keywords
        topic = re.sub(r'\b(search|find|lookup|pdf|book|paper|textbook|research|thesis)\b', '', lower).strip()
        if not topic: topic = lower
        return {"intent": "search_pdfs", "params": {"topic": topic.title()}, "confidence": 1.0}

    # ── STOCK ──────────────────────────────────────────────────────────────
    m = re.search(
        r'(?:stock|share|equity|price of|ticker)\s+(?:of\s+|for\s+)?([A-Za-z]{1,5}|[A-Za-z ]{3,30})',
        lower
    )
    if m:
        intent = "stock"
        params["company"] = m.group(1).strip()
    elif re.search(r'\b(aapl|tsla|msft|amzn|googl|nvda|meta|nflx|baba|spy)\b', lower):
        intent = "stock"
        params["company"] = re.search(
            r'\b(aapl|tsla|msft|amzn|googl|nvda|meta|nflx|baba|spy)\b', lower
        ).group(1).upper()

    # ── CRYPTO ─────────────────────────────────────────────────────────────
    elif re.search(r'\b(bitcoin|btc|ethereum|eth|solana|sol|bnb|xrp|doge|ada|crypto|binance|signal)\b', lower):
        intent = "crypto"
        coin_map = {"btc": "bitcoin", "eth": "ethereum", "sol": "solana", "bnb": "binance-coin"}
        m2 = re.search(r'\b(bitcoin|btc|ethereum|eth|solana|sol|bnb|xrp|doge|ada)\b', lower)
        raw = m2.group(1) if m2 else "bitcoin"
        params["coin"] = coin_map.get(raw, raw)

    # ── FOREX ──────────────────────────────────────────────────────────────
    elif re.search(r'\b(forex|currency|exchange rate|usd|eur|gbp|jpy|bdt)\b', lower):
        intent = "forex"
        m3 = re.search(r'([A-Z]{3})\s*(?:to|\/)\s*([A-Z]{3})', text)
        if m3:
            params["pair"] = f"{m3.group(1)}/{m3.group(2)}"

    # ── NEWS ───────────────────────────────────────────────────────────────
    elif re.search(r'\b(news|headline|latest|breaking|update|report)\b', lower):
        intent = "news"
        m4 = re.search(r'(?:news|headline|update)\s+(?:about|on|for)?\s*(.+)', lower)
        if m4:
            params["topic"] = m4.group(1).strip()

    # ── WEB SEARCH ─────────────────────────────────────────────────────────
    elif re.search(r'\b(search|look up|find|google|what is|who is|when did)\b', lower):
        intent = "web_search"
        params["query"] = text

    # ── MARKET ANALYSIS ────────────────────────────────────────────────────
    elif re.search(
        r'\b(market|analyze|analysis|trend|bull|bear|outlook|forecast|sector|economy|gdp|inflation|fed|interest rate)\b',
        lower
    ):
        intent = "market_analysis"

    # ── PORTFOLIO ──────────────────────────────────────────────────────────
    elif re.search(r'\b(portfolio|invest|allocation|diversif|rebalance|holdings)\b', lower):
        intent = "portfolio"

    return {"intent": intent, "params": params, "confidence": 0.95}
