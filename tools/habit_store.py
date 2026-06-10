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


def init_todo_db():
    db = _get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'USR-MASTER',
            category_id INTEGER,
            title TEXT NOT NULL,
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'todo',
            task_level INTEGER DEFAULT 5,
            remind_daily INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT (datetime('now','localtime')),
            completed_at DATETIME,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS daily_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            log_date DATE DEFAULT (date('now','localtime')),
            note TEXT,
            FOREIGN KEY (task_id) REFERENCES todos (id)
        )
    ''')
    
    # Migration: Add task_level column if it doesn't exist
    try:
        db.execute("ALTER TABLE todos ADD COLUMN task_level INTEGER DEFAULT 5")
    except sqlite3.OperationalError:
        pass # Column already exists
        
    # Insert default category
    db.execute("INSERT OR IGNORE INTO categories (name) VALUES ('general')")
    db.commit()
    db.close()


def _get_or_create_category(name: str) -> int:
    db = _get_db()
    try:
        cur = db.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
        db.commit()
        row = db.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
        return row["id"] if row else None
    finally:
        db.close()


def add_task(title: str, category: str = "general", priority: str = "medium", remind_daily: bool = False, task_level: int = 5) -> dict:
    cat_id = _get_or_create_category(category)
    db = _get_db()
    cur = db.execute(
        "INSERT INTO todos (title, category_id, priority, remind_daily, task_level) VALUES (?, ?, ?, ?, ?)",
        (title, cat_id, priority, 1 if remind_daily else 0, task_level)
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
    
    # 1. Status summary
    status_rows = db.execute("SELECT status, COUNT(*) as c FROM todos GROUP BY status").fetchall()
    status_map = {row["status"]: row["c"] for row in status_rows}
    # Ensure all statuses exist
    for s in ["todo", "in-progress", "done"]:
        if s not in status_map: status_map[s] = 0
        
    # 2. Categories
    by_cat = db.execute(
        "SELECT c.name, COUNT(t.id) as total, "
        "SUM(CASE WHEN t.status='done' THEN 1 ELSE 0 END) as done, "
        "SUM(CASE WHEN t.status='in-progress' THEN 1 ELSE 0 END) as in_progress, "
        "SUM(CASE WHEN t.status='todo' THEN 1 ELSE 0 END) as todo "
        "FROM categories c "
        "LEFT JOIN todos t ON c.id = t.category_id "
        "GROUP BY c.id HAVING total > 0"
    ).fetchall()

    # 3. Daily Completion (Last 7 days)
    daily = db.execute(
        "SELECT date(completed_at) as completed_at, COUNT(*) as count "
        "FROM todos WHERE status = 'done' AND completed_at IS NOT NULL "
        "GROUP BY date(completed_at) ORDER BY completed_at DESC LIMIT 7"
    ).fetchall()

    db.close()
    return {
        "status": status_map,
        "categories": [dict(c) for c in by_cat],
        "daily_completion": [dict(d) for d in daily]
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
    allowed = {"title", "priority", "status", "remind_daily", "task_level"}
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
