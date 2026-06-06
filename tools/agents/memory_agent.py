#!/usr/bin/env python3
"""
Memory Agent — Long-term memory system for Marin.
Remembers facts, preferences, conversations, and observations across sessions.
"""

import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "storage")
MEMORY_FILE = os.path.join(STORAGE_DIR, "marin_memory.json")

OWNER_USER = "Bayazid"


def _load_memory() -> Dict[str, Any]:
    os.makedirs(STORAGE_DIR, exist_ok=True)
    if os.path.exists(MEMORY_FILE):
        try:
            return json.loads(open(MEMORY_FILE).read())
        except Exception:
            pass
    return {"facts": {}, "conversations": [], "observations": [], "preferences": {}}


def _save_memory(mem: Dict[str, Any]):
    os.makedirs(STORAGE_DIR, exist_ok=True)
    with open(MEMORY_FILE, "w") as f:
        json.dump(mem, f, indent=2)


def action_remember(key: str, value: str, category: str = "facts", user: str = OWNER_USER) -> Dict[str, Any]:
    """Store a fact in memory."""
    mem = _load_memory()
    if category == "facts":
        mem["facts"][key] = {"value": value, "ts": datetime.now().isoformat(), "by": user}
    elif category == "preferences":
        mem["preferences"][key] = {"value": value, "ts": datetime.now().isoformat()}
    else:
        mem.setdefault(category, []).append({
            "key": key, "value": value, "ts": datetime.now().isoformat(), "by": user
        })
    _save_memory(mem)
    return {"ok": True, "stored": key, "category": category}


def action_recall(key: str = None, category: str = "facts", query: str = None, user: str = OWNER_USER) -> Dict[str, Any]:
    """Recall memories by key or search query."""
    mem = _load_memory()
    if key:
        if category == "facts":
            entry = mem["facts"].get(key)
            if entry:
                return {"ok": True, "key": key, "value": entry["value"], "ts": entry.get("ts")}
            return {"ok": False, "error": f"Memory not found: {key}"}
        elif category == "preferences":
            entry = mem["preferences"].get(key)
            if entry:
                return {"ok": True, "key": key, "value": entry["value"]}
            return {"ok": False, "error": f"Preference not found: {key}"}

    if query:
        q = query.lower()
        results = []
        for k, v in mem["facts"].items():
            if q in k.lower() or q in str(v.get("value", "")).lower():
                results.append({"key": k, "value": v["value"], "ts": v.get("ts")})
        for k, v in mem["preferences"].items():
            if q in k.lower() or q in str(v.get("value", "")).lower():
                results.append({"key": k, "value": v["value"], "type": "preference"})
        return {"ok": True, "results": results[:20], "count": len(results)}

    all_keys = list(mem["facts"].keys()) + list(mem["preferences"].keys())
    return {"ok": True, "keys": all_keys, "count": len(all_keys)}


def action_forget(key: str, category: str = "facts", user: str = OWNER_USER) -> Dict[str, Any]:
    """Remove a memory."""
    if user != OWNER_USER:
        return {"ok": False, "error": "Only Bayazid can forget memories."}
    mem = _load_memory()
    if category == "facts" and key in mem["facts"]:
        del mem["facts"][key]
        _save_memory(mem)
        return {"ok": True, "forgotten": key}
    if category == "preferences" and key in mem["preferences"]:
        del mem["preferences"][key]
        _save_memory(mem)
        return {"ok": True, "forgotten": key}
    return {"ok": False, "error": f"Memory not found: {key}"}


def action_log_conversation(topic: str, summary: str, user: str = OWNER_USER) -> Dict[str, Any]:
    """Log a conversation summary for future reference."""
    mem = _load_memory()
    mem["conversations"].append({
        "topic": topic, "summary": summary,
        "ts": datetime.now().isoformat(), "by": user
    })
    if len(mem["conversations"]) > 200:
        mem["conversations"] = mem["conversations"][-200:]
    _save_memory(mem)
    return {"ok": True, "logged": topic}


def action_observe(observation: str, context: str = "", user: str = OWNER_USER) -> Dict[str, Any]:
    """Record an observation about the system, user, or environment."""
    mem = _load_memory()
    mem["observations"].append({
        "observation": observation, "context": context,
        "ts": datetime.now().isoformat(), "by": user
    })
    if len(mem["observations"]) > 500:
        mem["observations"] = mem["observations"][-500:]
    _save_memory(mem)
    return {"ok": True, "recorded": observation[:80]}


def action_stats(user: str = OWNER_USER) -> Dict[str, Any]:
    """Get memory statistics."""
    mem = _load_memory()
    return {
        "ok": True,
        "facts": len(mem["facts"]),
        "preferences": len(mem["preferences"]),
        "conversations": len(mem["conversations"]),
        "observations": len(mem["observations"]),
        "total": len(mem["facts"]) + len(mem["preferences"]) + len(mem["conversations"]) + len(mem["observations"]),
    }


ACTIONS = {
    "remember": lambda p, u: action_remember(p.get("key", ""), p.get("value", ""), p.get("category", "facts"), u),
    "recall": lambda p, u: action_recall(p.get("key"), p.get("category", "facts"), p.get("query"), u),
    "forget": lambda p, u: action_forget(p.get("key", ""), p.get("category", "facts"), u),
    "log_conversation": lambda p, u: action_log_conversation(p.get("topic", ""), p.get("summary", ""), u),
    "observe": lambda p, u: action_observe(p.get("observation", ""), p.get("context", ""), u),
    "stats": lambda p, u: action_stats(u),
}


def dispatch(action: str, params: Dict[str, Any], user: str = OWNER_USER) -> Dict[str, Any]:
    fn = ACTIONS.get(action)
    if not fn:
        return {"ok": False, "error": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}"}
    try:
        return fn(params, user)
    except Exception as e:
        return {"ok": False, "error": str(e)}
