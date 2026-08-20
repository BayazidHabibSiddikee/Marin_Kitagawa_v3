#!/usr/bin/env python3
"""
tools/memory_tool.py — Marin's persistent user memory.

Marin calls this tool to remember, recall, or forget facts about the user.
All entries are stored in the SQLite database (user_memory table) and are
automatically injected into every conversation context.

Actions:
  remember  — save a fact   (key, value, category)
  recall    — search facts  (query)
  forget    — delete a fact (key)
  list      — show all facts
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Categories Marin uses ────────────────────────────────────────────────────
CATEGORIES = {
    "identity":   "Who the user is — name, age, gender, nationality",
    "goals":      "Long-term objectives, ambitions, career targets",
    "projects":   "Active projects, side hustles, builds",
    "skills":     "Known skills, tools, languages, expertise level",
    "schedule":   "Routines, wake time, workout time, study blocks",
    "health":     "Fitness level, diet, injuries, supplements",
    "preferences":"Likes, dislikes, favourite things",
    "context":    "Current situation, mood patterns, life stage",
    "rules":      "Explicit instructions Marin must follow for this user",
    "general":    "Anything that doesn't fit above",
}


def run(action: str, key: str = "", value: str = "",
        category: str = "general", query: str = "",
        user_id: str = "USR-MASTER") -> str:
    """
    Execute a memory action. Returns a human-readable result string.

    Actions:
      remember  — store key/value under a category
      recall    — search memories by query text
      forget    — delete a memory by key
      list      — list all memories (optionally filter by category)
    """
    from database import memory_delete, memory_list, memory_save, memory_search

    action = action.strip().lower()

    # ── remember ─────────────────────────────────────────────────────────────
    if action == "remember":
        if not key or not value:
            return "Error: both 'key' and 'value' are required to remember something."
        if category not in CATEGORIES:
            category = "general"
        ok = memory_save(key=key, value=value, category=category,
                         user_id=user_id, source="marin")
        if ok:
            return f"Noted. [{category}] {key}: {value}"
        return "Failed to save memory — database error."

    # ── recall ────────────────────────────────────────────────────────────────
    if action == "recall":
        q = query or key or value
        if not q:
            return "Error: provide a 'query' to search for."
        rows = memory_search(query=q, user_id=user_id)
        if not rows:
            return f"No memories found matching '{q}'."
        lines = [f"• [{r['category']}] {r['key']}: {r['value']}" for r in rows]
        return f"Found {len(rows)} memories:\n" + "\n".join(lines)

    # ── forget ────────────────────────────────────────────────────────────────
    if action == "forget":
        if not key:
            return "Error: provide the 'key' of the memory to forget."
        ok = memory_delete(key=key, user_id=user_id)
        if ok:
            return f"Forgotten: {key}"
        return f"No memory found with key '{key}'."

    # ── list ──────────────────────────────────────────────────────────────────
    if action == "list":
        cat = category if category != "general" else None
        rows = memory_list(user_id=user_id, category=cat, limit=50)
        if not rows:
            return "Memory is empty." if not cat else f"No memories in category '{cat}'."
        # Group by category for readability
        grouped: dict[str, list] = {}
        for r in rows:
            grouped.setdefault(r["category"], []).append(f"  • {r['key']}: {r['value']}")
        parts = []
        for cat_name, entries in grouped.items():
            parts.append(f"[{cat_name}]\n" + "\n".join(entries))
        return "\n\n".join(parts)

    return f"Unknown action '{action}'. Use: remember | recall | forget | list"


if __name__ == "__main__":
    # Quick test
    print(run("remember", key="name", value="Bayazid", category="identity"))
    print(run("remember", key="main_project", value="SwordFish AI OS", category="projects"))
    print(run("remember", key="wake_time", value="6:00 AM", category="schedule"))
    print(run("list"))
    print(run("recall", query="project"))
    print(run("forget", key="wake_time"))
    print(run("list"))
