import sqlite3
import json
import os
import secrets
from datetime import datetime
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "storage", "marin.db")

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Users Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT,
                role TEXT DEFAULT 'guest',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 2. User API Keys
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                api_key TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        # 3. Chat History (Updated with user_id)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'USR-MASTER',
                session_id TEXT DEFAULT 'default',
                agent TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 4. Trades Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                amount REAL,
                price REAL,
                status TEXT DEFAULT 'pending',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 5. Timers (Updated with user_id)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS timers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'USR-MASTER',
                task TEXT NOT NULL,
                start_time DATETIME NOT NULL,
                end_time DATETIME,
                duration_minutes INTEGER,
                status TEXT DEFAULT 'active'
            )
        ''')
        
        conn.commit()

# ── USER API ─────────────────────────────────────────────────────────────────

def create_user(username: str, role: str = "guest", display_name: str = None) -> dict:
    user_id = f"USR-{secrets.token_hex(4).upper()}"
    if username == "developer" or username == "admin": user_id = "USR-MASTER"
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, role, display_name) VALUES (?, ?, ?, ?)",
            (user_id, username, role, display_name or username)
        )
        conn.commit()
        
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        return dict(cursor.fetchone())

def get_user_by_api_key(api_key: str) -> Optional[dict]:
    # For now, we use a simple header check in middleware, 
    # but this allows per-user API keys for external access
    return None # Implementation pending

def promote_user(user_id: str, role: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
        conn.commit()

# ── Chat History API ─────────────────────────────────────────────────────────

def save_message(agent: str, role: str, content: str, user_id: str = "USR-MASTER", session_id: str = "default"):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_history (user_id, session_id, agent, role, content) VALUES (?, ?, ?, ?, ?)",
            (user_id, session_id, agent, role, content)
        )
        conn.commit()

def get_history(agent: str, limit: int = 50, user_id: str = "USR-MASTER", session_id: str = "default") -> List[Dict[str, str]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT role, content FROM chat_history
               WHERE agent = ? AND user_id = ? AND session_id = ?
               ORDER BY id DESC LIMIT ?""",
            (agent, user_id, session_id, limit)
        )
        rows = cursor.fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

def clear_history(agent: str, user_id: str = "USR-MASTER", session_id: str = "default"):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM chat_history WHERE agent = ? AND user_id = ? AND session_id = ?", 
            (agent, user_id, session_id)
        )
        conn.commit()

# ── API KEY STORAGE ──────────────────────────────────────────────────────────

def save_user_key(user_id: str, provider: str, key: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO user_api_keys (user_id, provider, api_key) VALUES (?, ?, ?)",
            (user_id, provider, key)
        )
        conn.commit()

def get_user_keys(user_id: str) -> Dict[str, str]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT provider, api_key FROM user_api_keys WHERE user_id = ?", (user_id,))
        return {r["provider"]: r["api_key"] for r in cursor.fetchall()}

def get_user_key(user_id: str, provider: str) -> Optional[str]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT api_key FROM user_api_keys WHERE user_id = ? AND provider = ?", (user_id, provider))
        row = cursor.fetchone()
        return row["api_key"] if row else None

def save_trade(user_id: str, symbol: str, side: str, amount: float, price: float, status: str, order_id: str = None):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Ensure the table exists or just skip if simple. For now, creating dynamically if needed is better,
        # but let's assume it exists or create it.
        cursor.execute('''CREATE TABLE IF NOT EXISTS trades 
                          (id INTEGER PRIMARY KEY, user_id TEXT, symbol TEXT, side TEXT, 
                           amount REAL, price REAL, status TEXT, order_id TEXT, ts DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute("INSERT INTO trades (user_id, symbol, side, amount, price, status, order_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (user_id, symbol, side, amount, price, status, order_id))
        conn.commit()

def start_timer(task: str, user_id: str = "USR-MASTER") -> int:
    # Clear any previously active timers first
    clear_active_timers(user_id)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO timers (user_id, task, start_time, status) VALUES (?, ?, ?, 'active')",
            (user_id, task, datetime.now().isoformat())
        )
        conn.commit()
        return cursor.lastrowid

def clear_active_timers(user_id: str = "USR-MASTER"):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE timers SET status = 'interrupted', end_time = ? WHERE user_id = ? AND status = 'active'", 
                       (datetime.now().isoformat(), user_id))
        conn.commit()

def end_timer(timer_id: int, status: str = "completed"):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Calculate duration
        cursor.execute("SELECT start_time FROM timers WHERE id = ?", (timer_id,))
        row = cursor.fetchone()
        duration = 0
        if row:
            start = datetime.fromisoformat(row["start_time"])
            duration = int((datetime.now() - start).total_seconds() / 60)
            
        cursor.execute(
            "UPDATE timers SET end_time = ?, status = ?, duration_minutes = ? WHERE id = ?",
            (datetime.now().isoformat(), status, duration, timer_id)
        )
        conn.commit()

def get_timer_stats(user_id: str = "USR-MASTER") -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM timers WHERE user_id = ? ORDER BY id DESC", (user_id,))
        return [dict(r) for r in cursor.fetchall()]

def get_last_timer(user_id: str = "USR-MASTER") -> Optional[Dict[str, Any]]:
    """Find the last session that isn't the currently active one (if any)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Find the last completed or stopped task
        cursor.execute("SELECT * FROM timers WHERE user_id = ? AND status != 'active' ORDER BY id DESC LIMIT 1", (user_id,))
        row = cursor.fetchone()
        if not row:
            # Fallback to the very last one regardless of status
            cursor.execute("SELECT * FROM timers WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
            row = cursor.fetchone()
        return dict(row) if row else None

def delete_user_key(user_id: str, provider: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_api_keys WHERE user_id = ? AND provider = ?", (user_id, provider))
        conn.commit()
