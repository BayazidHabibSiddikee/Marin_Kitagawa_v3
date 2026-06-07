import sqlite3
import json
import os
import secrets
from datetime import datetime
from typing import List, Dict, Any, Optional

from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "storage", "marin.db")

@contextmanager
def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def get_connection():
    # Legacy wrapper for compatibility where needed, but prefer get_db_connection
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
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

    # User API Keys Table (Encrypted)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            provider TEXT NOT NULL,      -- 'binance', 'openrouter', etc.
            api_key TEXT NOT NULL,       -- Encrypted
            api_secret TEXT,             -- Encrypted
            extra_data TEXT,             -- JSON string, encrypted
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            UNIQUE(user_id, provider)
        )
    ''')

    # Trades Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,          -- 'buy' | 'sell'
            amount REAL NOT NULL,
            price REAL NOT NULL,
            status TEXT DEFAULT 'pending', -- 'pending' | 'executed' | 'failed' | 'cancelled'
            order_id TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
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

def set_user_key(user_id: str, provider: str, api_key: str, api_secret: str = None, extra: dict = None):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        extra_str = json.dumps(extra) if extra else None
        cursor.execute(
            """INSERT OR REPLACE INTO user_api_keys (user_id, provider, api_key, api_secret, extra_data) 
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, provider, api_key, api_secret, extra_str)
        )
        conn.commit()

def get_user_key(user_id: str, provider: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT api_key, api_secret, extra_data FROM user_api_keys WHERE user_id = ? AND provider = ?",
            (user_id, provider)
        )
        row = cursor.fetchone()
        if row:
            res = dict(row)
            if res["extra_data"]:
                res["extra_data"] = json.loads(res["extra_data"])
            return res
        return None

def delete_user_key(user_id: str, provider: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_api_keys WHERE user_id = ? AND provider = ?", (user_id, provider))
        conn.commit()

# ── Trades API ───────────────────────────────────────────────────────────────

def save_trade(user_id: str, symbol: str, side: str, amount: float, price: float, order_id: str = None, status: str = 'pending'):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO trades (user_id, symbol, side, amount, price, order_id, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, symbol, side, amount, price, order_id, status)
        )
        conn.commit()
        return cursor.lastrowid

def get_trades(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?", (user_id, limit))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

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
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_history (agent, role, content, user_id) VALUES (?, ?, ?, ?)",
            (agent, role, content, user_id)
        )
        conn.commit()

def get_history(agent: str, limit: int = 50, user_id: str = 'USR-00000000') -> List[Dict[str, str]]:
    with get_db_connection() as conn:
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
        return [{"role": r["role"], "content": r["content"]} for r in rows]

def clear_history(agent: str, user_id: str = 'USR-00000000'):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chat_history WHERE agent = ? AND user_id = ?", (agent, user_id))
        conn.commit()

# ── Timer API ────────────────────────────────────────────────────────────────

def start_timer(task: str, user_id: str = 'USR-00000000'):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        start_time = datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO timers (task, start_time, status, user_id) VALUES (?, ?, 'active', ?)",
            (task, start_time, user_id)
        )
        return cursor.lastrowid

def end_timer(timer_id: int, status: str = 'completed'):
    with get_db_connection() as conn:
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

def get_timer_stats(user_id: str = 'USR-00000000'):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM timers WHERE user_id = ? ORDER BY start_time DESC LIMIT 20", (user_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

# ── User State API ───────────────────────────────────────────────────────────

def set_state(key: str, value: Any):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        val_str = json.dumps(value) if not isinstance(value, str) else value
        cursor.execute(
            "INSERT OR REPLACE INTO user_state (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, val_str)
        )
        conn.commit()

def get_state(key: str, default: Any = None) -> Any:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM user_state WHERE key = ?", (key,))
        row = cursor.fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except:
            return row["value"]

# ── News API ─────────────────────────────────────────────────────────────────

def save_news(items: list, source: str = "AlJazeera"):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for item in items:
            item_source = item.get("source", source)
            cursor.execute(
                "INSERT INTO news (title, summary, analysis, source, fetched_at) VALUES (?, ?, ?, ?, ?)",
                (item.get("title", ""), item.get("summary", ""), item.get("analysis", ""),
                 item_source, item.get("timestamp", datetime.now().isoformat()))
            )
        conn.commit()

def get_latest_news(limit: int = 5) -> list:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT title, summary, analysis, source, fetched_at FROM news ORDER BY fetched_at DESC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def delete_old_news(days: int = 14) -> int:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM news WHERE fetched_at < datetime('now', ?)",
            (f"-{days} days",)
        )
        deleted = cursor.rowcount
        conn.commit()
        return deleted

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
