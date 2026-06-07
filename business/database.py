import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "storage", "bayazid_marin.db")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Chat History Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Timers Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS timers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT NOT NULL,
            start_time DATETIME NOT NULL,
            end_time DATETIME,
            duration_minutes INTEGER,
            status TEXT DEFAULT 'active'
        )
    ''')
    
    # User Settings / State Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # News Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            summary TEXT,
            analysis TEXT,
            source TEXT DEFAULT 'AlJazeera',
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# ── Chat History API ─────────────────────────────────────────────────────────

def save_message(agent: str, role: str, content: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_history (agent, role, content) VALUES (?, ?, ?)",
        (agent, role, content)
    )
    conn.commit()
    conn.close()

def get_history(agent: str, limit: int = 50) -> List[Dict[str, str]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content FROM chat_history WHERE agent = ? ORDER BY timestamp DESC LIMIT ?",
        (agent, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    # Reverse to get chronological order
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

def clear_history(agent: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_history WHERE agent = ?", (agent,))
    conn.commit()
    conn.close()

# ── Timer API ────────────────────────────────────────────────────────────────

def start_timer(task: str):
    conn = get_connection()
    cursor = conn.cursor()
    start_time = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO timers (task, start_time, status) VALUES (?, ?, 'active')",
        (task, start_time)
    )
    timer_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return timer_id

def end_timer(timer_id: int, status: str = 'completed'):
    conn = get_connection()
    cursor = conn.cursor()
    end_time = datetime.now()
    
    cursor.execute("SELECT start_time FROM timers WHERE id = ?", (timer_id,))
    row = cursor.fetchone()
    if row:
        start_time = datetime.fromisoformat(row["start_time"])
        duration = int((end_time - start_time).total_seconds() / 60)
        cursor.execute(
            "UPDATE timers SET end_time = ?, duration_minutes = ?, status = ? WHERE id = ?",
            (end_time.isoformat(), duration, status, timer_id)
        )
    conn.commit()
    conn.close()

def get_timer_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM timers ORDER BY start_time DESC LIMIT 20")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── User State API ───────────────────────────────────────────────────────────

def set_state(key: str, value: Any):
    conn = get_connection()
    cursor = conn.cursor()
    val_str = json.dumps(value) if not isinstance(value, str) else value
    cursor.execute(
        "INSERT OR REPLACE INTO user_state (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
        (key, val_str)
    )
    conn.commit()
    conn.close()

def get_state(key: str, default: Any = None) -> Any:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM user_state WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except:
        return row["value"]

# ── News API ─────────────────────────────────────────────────────────────────

def save_news(items: list, source: str = "AlJazeera"):
    conn = get_connection()
    cursor = conn.cursor()
    for item in items:
        # Use source from item if available, else use the provided default
        item_source = item.get("source", source)
        cursor.execute(
            "INSERT INTO news (title, summary, analysis, source, fetched_at) VALUES (?, ?, ?, ?, ?)",
            (item.get("title", ""), item.get("summary", ""), item.get("analysis", ""),
             item_source, item.get("timestamp", datetime.now().isoformat()))
        )
    conn.commit()
    conn.close()

def get_latest_news(limit: int = 5) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT title, summary, analysis, source, fetched_at FROM news ORDER BY fetched_at DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Migration Helper ──────────────────────────────────────────────────────────

def migrate_from_json():
    storage_dir = os.path.join(BASE_DIR, "storage")
    if not os.path.exists(storage_dir):
        return

    # Migrate Histories
    for agent in ['bayazid', 'marin', 'arena']:
        json_path = os.path.join(storage_dir, f"{agent}_history.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r") as f:
                    history = json.load(f)
                    for msg in history:
                        save_message(agent, msg["role"], msg["content"])
                print(f"Migrated {agent} history.")
                os.remove(json_path)
            except Exception as e:
                print(f"Error migrating {agent} history: {e}")

    # Migrate Vibe State
    vibe_path = os.path.join(storage_dir, "vibe_state.json")
    if os.path.exists(vibe_path):
        try:
            with open(vibe_path, "r") as f:
                vibe = json.load(f)
                set_state("vibe", vibe)
            print("Migrated vibe state.")
            os.remove(vibe_path)
        except Exception as e:
            print(f"Error migrating vibe state: {e}")

    # Migrate Timers
    timer_path = os.path.join(storage_dir, "timer_sessions.json")
    if os.path.exists(timer_path):
        try:
            with open(timer_path, "r") as f:
                sessions = json.load(f)
                conn = get_connection()
                cursor = conn.cursor()
                for s in sessions:
                    cursor.execute(
                        "INSERT INTO timers (task, start_time, end_time, duration_minutes, status) VALUES (?, ?, ?, ?, ?)",
                        (s.get("task", "Unknown"), s.get("start_time"), s.get("end_time"), s.get("duration"), s.get("status", "completed"))
                    )
                conn.commit()
                conn.close()
            print("Migrated timers.")
            os.remove(timer_path)
        except Exception as e:
            print(f"Error migrating timers: {e}")

if __name__ == "__main__":
    init_db()
    migrate_from_json()
    print("Database initialized and migrated.")
