import sqlite3
import json
import os
import secrets
from datetime import datetime
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "storage", "marin.db")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT,
            role TEXT DEFAULT 'guest',
            api_key TEXT UNIQUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen DATETIME,
            is_active INTEGER DEFAULT 1
        )
    ''')

    # Chat History Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'USR-00000000',
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
            user_id TEXT DEFAULT 'USR-00000000',
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
    
    # Migration: Add user_id column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE chat_history ADD COLUMN user_id TEXT DEFAULT 'USR-00000000'")
    except sqlite3.OperationalError:
        pass # already exists

    try:
        cursor.execute("ALTER TABLE timers ADD COLUMN user_id TEXT DEFAULT 'USR-00000000'")
    except sqlite3.OperationalError:
        pass # already exists
        
    conn.commit()
    conn.close()

# ── User Management API ──────────────────────────────────────────────────────

def create_user(username: str, display_name: str = None, role: str = 'guest') -> Dict[str, str]:
    conn = get_connection()
    cursor = conn.cursor()
    user_id = f"USR-{secrets.token_hex(4)}"
    api_key = f"MARIN-{secrets.token_hex(16)}"
    
    try:
        cursor.execute(
            "INSERT INTO users (user_id, username, display_name, role, api_key) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, display_name or username, role, api_key)
        )
        conn.commit()
        return {"user_id": user_id, "api_key": api_key, "role": role}
    except sqlite3.IntegrityError:
        # Username already exists
        cursor.execute("SELECT user_id, api_key, role FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()

def get_user_by_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, username, display_name, role FROM users WHERE api_key = ? AND is_active = 1",
        (api_key,)
    )
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE users SET last_seen = CURRENT_TIMESTAMP WHERE user_id = ?", (row["user_id"],))
        conn.commit()
    conn.close()
    return dict(row) if row else None

def promote_user(user_id: str, new_role: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (new_role, user_id))
    conn.commit()
    conn.close()

# ── Chat History API ─────────────────────────────────────────────────────────

def save_message(agent: str, role: str, content: str, user_id: str = 'USR-00000000'):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_history (agent, role, content, user_id) VALUES (?, ?, ?, ?)",
        (agent, role, content, user_id)
    )
    conn.commit()
    conn.close()

def get_history(agent: str, limit: int = 50, user_id: str = 'USR-00000000') -> List[Dict[str, str]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT role, content FROM chat_history
           WHERE id IN (
               SELECT id FROM chat_history 
               WHERE agent = ? AND user_id = ? 
               ORDER BY id DESC LIMIT ?
           )
           ORDER BY id ASC""",
        (agent, user_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in rows]

def clear_history(agent: str, user_id: str = 'USR-00000000'):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_history WHERE agent = ? AND user_id = ?", (agent, user_id))
    conn.commit()
    conn.close()

# ── Timer API ────────────────────────────────────────────────────────────────

def start_timer(task: str, user_id: str = 'USR-00000000'):
    conn = get_connection()
    cursor = conn.cursor()
    start_time = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO timers (task, start_time, status, user_id) VALUES (?, ?, 'active', ?)",
        (task, start_time, user_id)
    )
    timer_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return timer_id

# ... (end_timer and get_timer_stats remain mostly the same but could be scoped)

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

def get_timer_stats(user_id: str = 'USR-00000000'):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM timers WHERE user_id = ? ORDER BY start_time DESC LIMIT 20", (user_id,))
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

def delete_old_news(days: int = 14) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM news WHERE fetched_at < datetime('now', ?)",
        (f"-{days} days",)
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
