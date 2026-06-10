import os
import re
import json
import signal
import sys
import asyncio
import subprocess
from pathlib import Path
from difflib import get_close_matches
from typing import Optional, Tuple, Dict, Any
from pydantic import BaseModel, Field

# Single Source of Truth for Tools
from langgraph_agent import ALL_TOOLS, tools_by_name

# ── Command execution logic (shared) ─────────────────────────────────────────
_cmd_log = []

# ── Intent Classification (Regex Stage) ───────────────────────────────────────

_TIMER_PAT   = re.compile(r'\b(timer|countdown|stopwatch)\b')
_ALARM_PAT   = re.compile(r'\b(alarm|wake|remind)\b')
_CRYPTO_PAT  = re.compile(r'\b(crypto|bitcoin|ethereum|solana|price|market)\b')
_STOCK_PAT   = re.compile(r'\b(stock|share|equity|company|aapl|tsla|nvda)\b')
_NEWS_PAT    = re.compile(r'\b(news|headlines|world|latest)\b')
_WEATHER_PAT = re.compile(r'\b(weather|temp|humidity|rain|sun)\b')
_MAP_PAT     = re.compile(r'\b(map|location|places|find|pin)\b')
_MATH_PAT    = re.compile(r'\b(plot|draw|graph|math|equation|calculate)\b')
_BUSINESS_PAT = re.compile(r'\b(trade|buy|sell|portfolio|binance|arena|judge|finance|market)\b')
_STUDY_PAT   = re.compile(r'\b(learn|teach|study|master|become\s+expert|start\s+learning)\b')
_PDF_PAT     = re.compile(r'\b(pdf|document|paper|analyzer|batch|convert)\b')
_BOOK_PAT    = re.compile(r'\b(search|find|lookup|book|textbook|epub)\b')

def _regex_stage(text: str) -> dict | None:
    """Returns {intent, params, confidence} or None if uncertain."""
    lower = text.lower().strip()
    
    # Study / Learning (God-Tier Workflow)
    if _STUDY_PAT.search(lower):
        topic = re.sub(_STUDY_PAT, '', lower).replace('me', '').replace('how to', '').strip()
        return {"intent": "learn_topic_tool", "params": {"topic": topic or lower}, "confidence": 1.0}

    # Business / Trading (The Arena)
    if _BUSINESS_PAT.search(lower):
        action = "portfolio"
        if "buy" in lower: action = "buy"
        elif "sell" in lower: action = "sell"
        elif "arena" in lower or "judge" in lower or "should i" in lower:
            return {"intent": "business_analysis_tool", "params": {"query": lower}, "confidence": 1.0}
        return {"intent": "binance_tool", "params": {"action": action}, "confidence": 0.9}

    # PDF / Documents
    if _PDF_PAT.search(lower):
        if "batch" in lower or "folder" in lower:
            return {"intent": "batch_convert_tool", "params": {"directory": "."}, "confidence": 0.9}
        return {"intent": "pdf_analyze_tool", "params": {"path": "document.pdf"}, "confidence": 0.8}

    # Books
    if _BOOK_PAT.search(lower):
        return {"intent": "book_download_tool", "params": {"query": lower}, "confidence": 0.9}

    # Standard Tools
    if _TIMER_PAT.search(lower):
        return {"intent": "timer_tool", "params": {"duration": "10m"}, "confidence": 0.9}
    if _ALARM_PAT.search(lower):
        return {"intent": "alarm_tool", "params": {"time": "08:00"}, "confidence": 0.9}
    if _CRYPTO_PAT.search(lower):
        return {"intent": "crypto_tool", "params": {"coin": "bitcoin"}, "confidence": 0.9}
    if _STOCK_PAT.search(lower):
        return {"intent": "stock_tool", "params": {"symbol": "AAPL"}, "confidence": 0.9}
    if _NEWS_PAT.search(lower):
        return {"intent": "news_tool", "params": {}, "confidence": 0.9}
    if _WEATHER_PAT.search(lower):
        return {"intent": "weather_tool", "params": {"city": "Dhaka"}, "confidence": 0.9}
    if _MAP_PAT.search(lower):
        return {"intent": "map_tool", "params": {"city": "Dhaka"}, "confidence": 0.9}
    if _MATH_PAT.search(lower):
        return {"intent": "math_plot_tool", "params": {"expression": "heart"}, "confidence": 0.9}

    return None

def _detect_vibe(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ["love","miss","cute","hug","kiss","mwah","sweetheart","ummaah","❤️"]):
        return "lovely"
    if any(w in lower for w in ["tease","hehe","playful","naughty"]):
        return "flirty"
    if any(w in lower for w in ["hate","mad","angry","fuck","ugh","damn"]):
        return "angry"
    return "neutral"

# ── PUBLIC API ─────────────────────────────────────────────────────────────

def classify(text: str) -> dict:
    """
    Unified classifier for Marin Tools.
    Returns: {intent, params, user_vibe, confidence}
    """
    result = _regex_stage(text)
    
    if result is None:
        result = {"intent": "chat", "params": {}, "confidence": 0.8}
        
    result["user_vibe"] = _detect_vibe(text)
    return result

async def execute_tool(intent: str, params: dict, user_id: str = "USR-00000000") -> str | None:
    """Run a tool from the central registry."""
    if intent not in tools_by_name:
        return None
    try:
        # Inject user context
        if "user_id" not in params:
            params["user_id"] = user_id
            
        result = await asyncio.to_thread(tools_by_name[intent].invoke, params)
        
        ts = datetime.now().strftime("%H:%M:%S")
        _cmd_log.append({
            "cmd": f"[tool:{intent}] {json.dumps(params)}",
            "ok": True,
            "output": str(result)[:500],
            "ts": ts
        })
        return str(result)
    except Exception as e:
        return f"Tool {intent} failed: {e}"

def extract_timer_task(text: str) -> Optional[str]:
    m = re.search(r'(?:timer|countdown)\s+(?:for|on)?\s*(.+)', text, re.I)
    return m.group(1).strip() if m else None

def is_cmd_allowed(cmd: str) -> Tuple[bool, str]:
    """
    Validates if a command is allowed to run.
    Checks against blocked patterns and metacharacters.
    """
    # 1. Block dangerous characters (preventing simple escapes)
    # Note: we allow spaces, dots, dashes, and basic alphanum
    # We block pipes, ampersands, redirects, etc. for guests
    # (The system prompt has more detailed rules)
    forbidden = r'[;&|`$(){}!\n\r<>]'
    if re.search(forbidden, cmd):
        return False, "Command contains forbidden characters."

    # 2. Block destructive commands
    destructive = [
        r'\brm\s+-rf\b', r'\bmkfs\b', r'\bdd\b', r'\bformat\b',
        r'\bshutdown\b', r'\breboot\b', r'\bpasswd\b',
    ]
    for pattern in destructive:
        if re.search(pattern, cmd, re.IGNORECASE):
            return False, "Command matches a destructive pattern."

    return True, ""
