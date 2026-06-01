#!/usr/bin/env python3
"""
habit_store.py — SQLite habit/task tracker for Marin.
No Flask, no server. Direct DB access.
"""

import os
import sqlite3
from datetime import datetime, date, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "storage", "habits.db")


def _get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    db = _get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'todo',
            remind_daily INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS daily_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            log_date TEXT DEFAULT (date('now','localtime')),
            note TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        );
    """)
    db.commit()
    db.close()


def add_task(title: str, category: str = "general", priority: str = "medium", remind_daily: bool = False) -> dict:
    db = _get_db()
    cur = db.execute(
        "INSERT INTO tasks (title, category, priority, remind_daily) VALUES (?, ?, ?, ?)",
        (title, category, priority, 1 if remind_daily else 0)
    )
    db.commit()
    task_id = cur.lastrowid
    task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    db.close()
    return dict(task)


def complete_task(task_id: int) -> str:
    db = _get_db()
    db.execute(
        "UPDATE tasks SET status = 'done', completed_at = datetime('now','localtime') WHERE id = ?",
        (task_id,)
    )
    db.commit()
    task = db.execute("SELECT title FROM tasks WHERE id = ?", (task_id,)).fetchone()
    db.close()
    if task:
        return f"✅ Task #{task_id} '{task['title']}' marked done."
    return f"Task #{task_id} not found."


def list_tasks(status: str = None, category: str = None) -> list:
    db = _get_db()
    query = "SELECT * FROM tasks WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if category:
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, id DESC"
    tasks = db.execute(query, params).fetchall()
    db.close()
    return [dict(t) for t in tasks]


def get_stats() -> dict:
    db = _get_db()
    total = db.execute("SELECT COUNT(*) as c FROM tasks").fetchone()["c"]
    done = db.execute("SELECT COUNT(*) as c FROM tasks WHERE status='done'").fetchone()["c"]
    todo = db.execute("SELECT COUNT(*) as c FROM tasks WHERE status='todo'").fetchone()["c"]
    in_prog = db.execute("SELECT COUNT(*) as c FROM tasks WHERE status='in-progress'").fetchone()["c"]

    by_cat = db.execute(
        "SELECT category, COUNT(*) as total, "
        "SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done "
        "FROM tasks GROUP BY category"
    ).fetchall()

    by_priority = db.execute(
        "SELECT priority, COUNT(*) as c FROM tasks WHERE status != 'done' GROUP BY priority"
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
        "SELECT t.* FROM tasks t "
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
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    db.close()
    return f"Task #{task_id} deleted."


def update_task(task_id: int, **kwargs) -> str:
    db = _get_db()
    allowed = {"title", "category", "priority", "status", "remind_daily"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        db.close()
        return "Nothing to update."
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [task_id]
    db.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
    if "status" in updates and updates["status"] == "done":
        db.execute("UPDATE tasks SET completed_at = datetime('now','localtime') WHERE id = ?", (task_id,))
    db.commit()
    db.close()
    return f"Task #{task_id} updated."


# Init on import
init_db()
