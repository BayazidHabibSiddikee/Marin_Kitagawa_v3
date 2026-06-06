#!/usr/bin/env python3
"""
habit_store.py — Unified task/habit storage for Marin.
Uses storage/todos.db (shared with main.py).
"""

import os
import sqlite3
from datetime import datetime, date, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "storage", "todos.db")


def _get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _get_or_create_category(name: str) -> int:
    db = _get_db()
    try:
        cur = db.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
        db.commit()
        row = db.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
        return row["id"] if row else None
    finally:
        db.close()


def add_task(title: str, category: str = "general", priority: str = "medium", remind_daily: bool = False) -> dict:
    cat_id = _get_or_create_category(category)
    db = _get_db()
    cur = db.execute(
        "INSERT INTO todos (title, category_id, priority, remind_daily) VALUES (?, ?, ?, ?)",
        (title, cat_id, priority, 1 if remind_daily else 0)
    )
    db.commit()
    task_id = cur.lastrowid
    task = db.execute(
        "SELECT t.*, c.name as category FROM todos t "
        "LEFT JOIN categories c ON t.category_id = c.id WHERE t.id = ?",
        (task_id,)
    ).fetchone()
    db.close()
    return dict(task)


def complete_task(task_id: int) -> str:
    db = _get_db()
    db.execute(
        "UPDATE todos SET status = 'done', completed_at = datetime('now','localtime') WHERE id = ?",
        (task_id,)
    )
    db.commit()
    task = db.execute("SELECT title FROM todos WHERE id = ?", (task_id,)).fetchone()
    db.close()
    if task:
        return f"✅ Task #{task_id} '{task['title']}' marked done."
    return f"Task #{task_id} not found."


def list_tasks(status: str = None, category: str = None) -> list:
    db = _get_db()
    query = "SELECT t.*, c.name as category FROM todos t LEFT JOIN categories c ON t.category_id = c.id WHERE 1=1"
    params = []
    if status:
        query += " AND t.status = ?"
        params.append(status)
    if category:
        query += " AND c.name = ?"
        params.append(category)
    query += " ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, t.id DESC"
    tasks = db.execute(query, params).fetchall()
    db.close()
    return [dict(t) for t in tasks]


def get_stats() -> dict:
    db = _get_db()
    total = db.execute("SELECT COUNT(*) as c FROM todos").fetchone()["c"]
    done = db.execute("SELECT COUNT(*) as c FROM todos WHERE status='done'").fetchone()["c"]
    todo = db.execute("SELECT COUNT(*) as c FROM todos WHERE status='todo'").fetchone()["c"]
    in_prog = db.execute("SELECT COUNT(*) as c FROM todos WHERE status='in-progress'").fetchone()["c"]

    by_cat = db.execute(
        "SELECT c.name as category, COUNT(t.id) as total, "
        "SUM(CASE WHEN t.status='done' THEN 1 ELSE 0 END) as done "
        "FROM categories c "
        "LEFT JOIN todos t ON c.id = t.category_id "
        "GROUP BY c.id HAVING total > 0"
    ).fetchall()

    by_priority = db.execute(
        "SELECT priority, COUNT(*) as c FROM todos WHERE status != 'done' GROUP BY priority"
    ).fetchall()

    db.close()
    return {
        "total": total, "done": done, "todo": todo, "in_progress": in_prog,
        "categories": [dict(c) for c in by_cat],
        "pending_by_priority": {r["priority"]: r["c"] for r in by_priority},
    }


def get_reminders_for_today() -> list:
    """Get tasks that need daily reminders and aren't done today."""
    db = _get_db()
    today = date.today().isoformat()
    tasks = db.execute(
        "SELECT t.*, c.name as category FROM todos t "
        "LEFT JOIN categories c ON t.category_id = c.id "
        "WHERE t.remind_daily = 1 AND t.status != 'done' "
        "AND t.id NOT IN (SELECT task_id FROM daily_log WHERE log_date = ?)",
        (today,)
    ).fetchall()
    db.close()
    return [dict(t) for t in tasks]


def log_daily(task_id: int, note: str = ""):
    db = _get_db()
    db.execute(
        "INSERT INTO daily_log (task_id, note) VALUES (?, ?)",
        (task_id, note)
    )
    db.commit()
    db.close()


def delete_task(task_id: int) -> str:
    db = _get_db()
    db.execute("DELETE FROM todos WHERE id = ?", (task_id,))
    db.commit()
    db.close()
    return f"Task #{task_id} deleted."


def update_task(task_id: int, **kwargs) -> str:
    db = _get_db()
    allowed = {"title", "priority", "status", "remind_daily"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    
    # Handle category separately if it's a string
    if "category" in kwargs and kwargs["category"]:
        cat_id = _get_or_create_category(kwargs["category"])
        updates["category_id"] = cat_id

    if not updates:
        db.close()
        return "Nothing to update."
        
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [task_id]
    db.execute(f"UPDATE todos SET {set_clause} WHERE id = ?", values)
    if "status" in updates and updates["status"] == "done":
        db.execute("UPDATE todos SET completed_at = datetime('now','localtime') WHERE id = ?", (task_id,))
    db.commit()
    db.close()
    return f"Task #{task_id} updated."
