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
from datetime import datetime

# Single Source of Truth for Tools
from langgraph_agent import ALL_TOOLS, tools_by_name

# ── Command execution logic (shared) ─────────────────────────────────────────
_cmd_log = []

# ── Intent Classification (Regex Stage) ───────────────────────────────────────

_TIMER_PAT   = re.compile(r'\b(timer|countdown|stopwatch)\b')
_ALARM_PAT   = re.compile(r'\b(alarm|wake|remind)\b')
_LIST_PAT    = re.compile(r'\b(ls|list|show|check|scan|files|directory|cwd)\b')
_READ_PAT    = re.compile(r'\b(read|open|cat|analyze|view)\b')
_CRYPTO_PAT  = re.compile(r'\b(crypto|bitcoin|ethereum|solana|price|market)\b')
_STOCK_PAT   = re.compile(r'\b(stock|share|equity|company|aapl|tsla|nvda)\b')
_NEWS_PAT    = re.compile(r'\b(news|headlines|world|latest)\b')
_WEATHER_PAT = re.compile(r'\b(weather|temp|humidity|rain|sun)\b')
_MAP_PAT     = re.compile(r'\b(map|location|places|find|pin)\b')
_MATH_PAT    = re.compile(r'\b(plot|draw|graph|math|equation|calculate)\b')
_BUSINESS_PAT = re.compile(r'\b(trade|buy|sell|portfolio|binance|arena|judge|finance|market)\b')
_STUDY_PAT   = re.compile(r'\b(learn|teach|study|master|become\s+expert|start\s+learning|tutorial|how\s+to|course)\b')
_PDF_PAT     = re.compile(r'\b(pdf|document|paper|analyzer|batch|convert)\b')
_BOOK_PAT    = re.compile(r'\b(book|textbook|epub|novel)\b')
_YOUTUBE_PAT = re.compile(r'\b(youtube|yt|video|videos|watch|song|music|play)\b')
# Dance ONLY triggers on explicit dance words — NOT on generic play/music
_DANCE_PAT   = re.compile(r'\b(dance|dancing|twerk|boogie|groove)\b|let\'?s dance|start dancing')

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

    # Dance — explicit dance request → search YouTube for music + trigger dance anim
    if _DANCE_PAT.search(lower):
        # Extract music genre/artist from message, ignore dance-command words
        query = re.sub(r'\b(dance|dancing|twerk|boogie|groove|let\'?s|start|marin|please|can you|with me)\b', '', lower).strip()
        query = re.sub(r'\s+', ' ', query).strip()
        query = (query + " music") if query else "upbeat dance music"
        return {"intent": "youtube_search_tool", "params": {"query": query}, "confidence": 1.0, "is_dance": True}

    # YouTube / Video — only when NOT a dance request
    if _YOUTUBE_PAT.search(lower):
        # Remove action words to get a cleaner query
        query = re.sub(r'\b(search|find|play|watch|youtube|video|videos|song|music|for)\b', '', lower).strip()
        return {"intent": "youtube_search_tool", "params": {"query": query or lower}, "confidence": 0.95}

    # PDF / Documents
    if _PDF_PAT.search(lower):
        if "batch" in lower or "folder" in lower:
            return {"intent": "batch_convert_tool", "params": {"directory": "."}, "confidence": 0.9}
        return {"intent": "pdf_analyze_tool", "params": {"path": "document.pdf"}, "confidence": 0.8}

    # Books - prioritize learn_topic_tool for technical learning
    if _BOOK_PAT.search(lower):
        if any(w in lower for w in ["arduino", "python", "coding", "programming", "manual", "guide", "datasheet", "assembly", "asm", "c programming", "kernel", "linux"]):
            return {"intent": "learn_topic_tool", "params": {"topic": lower}, "confidence": 1.0}
        return {"intent": "book_download_tool", "params": {"query": lower}, "confidence": 0.9}


    # Habits / Tasks
    if re.search(r'\b(habit|habits|todo|task)\b', lower):
        if "status" in lower or "list" in lower:
            return {"intent": "habit_tool", "params": {"action": "list", "args": []}, "confidence": 0.9}
        if "stats" in lower:
            return {"intent": "habit_tool", "params": {"action": "stats", "args": []}, "confidence": 0.9}
        if "today" in lower:
            return {"intent": "habit_tool", "params": {"action": "today", "args": []}, "confidence": 0.9}
        return {"intent": "habit_tool", "params": {"action": "list", "args": []}, "confidence": 0.8}

    # Standard Tools
    if _LIST_PAT.search(lower):
        if any(w in lower for w in ["file", "directory", "cwd", "folder"]):
            return {"intent": "terminal_tool", "params": {"command": "ls -F"}, "confidence": 1.0}
        return {"intent": "terminal_tool", "params": {"command": "ls"}, "confidence": 0.8}

    if _READ_PAT.search(lower):
        if "file" in lower:
             # Try to extract filename
             fname = "notes.txt"
             for part in lower.split():
                 if '.' in part: fname = part
             return {"intent": "file_tool", "params": {"action": "read", "path": fname}, "confidence": 0.9}

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
    if any(w in lower for w in ["excited","amazing","awesome","wow","let's go","yes!","yay"]):
        return "excited"
    if any(w in lower for w in ["sad","sorry","miss you","feel bad","hurts"]):
        return "sad"
    if any(w in lower for w in ["curious","interesting","wonder","what if","tell me"]):
        return "curious"
    return "neutral"

# Director emotion hints — used to set the base_emotion for the Director script
_DIRECTOR_EMOTIONS = {
    "greeting":    ["hello", "hi", "hey", "welcome", "good morning", "good evening"],
    "excited":     ["excited", "amazing", "awesome", "incredible", "let's go", "yay", "wow"],
    "explaining":  ["so basically", "the idea is", "what this means", "in other words", "let me explain", "here's how"],
    "curious":     ["interesting", "wonder", "curious", "what if", "fascinating"],
    "sad":         ["sad", "unfortunately", "sorry to hear", "that's tough", "miss you"],
    "dancing":     ["dance", "party", "celebrate", "🎵", "🎶", "🕺", "💃"],
    "love":        ["love", "adore", "my dear", "sweetheart", "❤️", "💖"],
    "confident":   ["absolutely", "definitely", "for sure", "trust me", "i know"],
}

def _detect_director_emotion(text: str) -> str:
    """Detect the dominant emotion for Director script generation."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for emotion, keywords in _DIRECTOR_EMOTIONS.items():
        for kw in keywords:
            if kw in lower:
                scores[emotion] = scores.get(emotion, 0) + 1
    if not scores:
        return "neutral"
    return max(scores, key=lambda k: scores[k])

# ── PUBLIC API ─────────────────────────────────────────────────────────────

def _llm_classify(text: str) -> dict:
    import json
    import httpx
    try:
        prompt = f'''Classify the message into an intent and user_vibe.
Available intents: [chat, image_gen, learn, code, lab, study, distraction, habit_tool]
Available vibes: [neutral, lovely, flirty, angry, sad, excited]
Message: "{text}"
Respond ONLY with JSON format: {{"intent": "...", "user_vibe": "..."}}'''
        req = {
            "model": "qwen2.5:1.5b",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json"
        }
        resp = httpx.post("http://127.0.0.1:11434/api/chat", json=req, timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            content = data.get("message", {}).get("content", "{}")
            return json.loads(content)
    except:
        pass
    return None

def classify(text: str) -> dict:
    """
    Unified classifier for Marin Tools.
    Returns: {intent, params, user_vibe, director_emotion, confidence}
    """
    result = _regex_stage(text)

    if result is None:
        llm_res = _llm_classify(text)
        if llm_res and llm_res.get("intent") != "chat":
            result = {"intent": llm_res.get("intent"), "params": {}, "confidence": 0.7}
            if "user_vibe" in llm_res:
                result["user_vibe"] = llm_res["user_vibe"]
        else:
            result = {"intent": "chat", "params": {}, "confidence": 0.8}

    if "user_vibe" not in result:
        result["user_vibe"] = _detect_vibe(text)
    result["director_emotion"] = _detect_director_emotion(text)
    return result

async def execute_tool(intent: str, params: dict, user_id: str = "USR-00000000") -> str | None:
    """Run a tool from the central registry."""
    if intent not in tools_by_name:
        return None
    try:
        # Inject user context
        if "user_id" not in params:
            params["user_id"] = user_id
            
        tool = tools_by_name[intent]
        # Robust execution: handle both sync and async tools
        if asyncio.iscoroutinefunction(tool._run):
            result = await tool.ainvoke(params)
        else:
            result = await asyncio.to_thread(tool.invoke, params)
        
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
    # 1. Block truly dangerous redirection/sequencing for safety
    # We allow (), ;, and quotes for python -c and complex logic
    forbidden = r'[`$!\n\r<>]'
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
