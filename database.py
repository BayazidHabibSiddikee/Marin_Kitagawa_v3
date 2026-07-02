import sqlite3
import json
import os
import secrets
import logging
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, TypeVar

from vault import encrypt_secret, decrypt_secret

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "storage", "marin.db")

_local = threading.local()
T = TypeVar("T")


def get_db_connection():
    """Return a thread-local SQLite connection (reused per thread)."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        _local.conn = conn
    return conn


def _db_op(fn: Callable[..., T], default: T = None) -> T:
    """Run a DB operation with error logging. Returns `default` on failure."""
    try:
        return fn()
    except sqlite3.Error as e:
        logger.error("Database error in %s: %s", fn.__name__ if hasattr(fn, "__name__") else "op", e)
        return default
    except Exception as e:
        logger.error("Unexpected DB error: %s", e)
        return default


def _table_columns(cursor, table: str) -> set:
    cursor.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def _migrate_schema(cursor):
    """Apply incremental schema migrations for existing databases."""
    if "trades" in {r[0] for r in cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}:
        cols = _table_columns(cursor, "trades")
        if "order_id" not in cols:
            cursor.execute("ALTER TABLE trades ADD COLUMN order_id TEXT")
        if "ts" in cols and "timestamp" not in cols:
            cursor.execute("ALTER TABLE trades RENAME COLUMN ts TO timestamp")
        elif "timestamp" not in cols:
            cursor.execute("ALTER TABLE trades ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP")

    # Encrypt any plaintext API keys still in the DB
    cursor.execute("SELECT id, api_key FROM user_api_keys")
    for row in cursor.fetchall():
        key_val = row["api_key"]
        if key_val and not key_val.startswith("enc:"):
            cursor.execute(
                "UPDATE user_api_keys SET api_key = ? WHERE id = ?",
                (encrypt_secret(key_val), row["id"]),
            )


def init_db():
    def _init():
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT,
                role TEXT DEFAULT 'guest',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                api_key TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                amount REAL,
                price REAL,
                status TEXT DEFAULT 'pending',
                order_id TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                title TEXT UNIQUE,
                summary TEXT,
                analysis TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_history_lookup "
            "ON chat_history(agent, user_id, session_id, id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_timers_user_status "
            "ON timers(user_id, status, start_time)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_news_timestamp ON news(timestamp)"
        )

        _migrate_schema(cursor)
        conn.commit()

    _db_op(_init)


# ── NEWS API ─────────────────────────────────────────────────────────────────

def save_news(news_list: List[Dict[str, Any]]):
    def _save():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for item in news_list:
                cursor.execute('''
                    INSERT OR REPLACE INTO news (source, title, summary, analysis, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    item.get("source"), item.get("title"), item.get("summary"),
                    item.get("analysis"), item.get("timestamp") or datetime.now().isoformat(),
                ))
            conn.commit()
    _db_op(_save)


def get_latest_news(limit: int = 10) -> List[Dict[str, Any]]:
    def _get():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM news ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]
    return _db_op(_get, default=[])


def delete_old_news(days: int = 14) -> int:
    def _delete():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM news WHERE timestamp < date('now', '-' || ? || ' days')", (days,)
            )
            conn.commit()
            return cursor.rowcount
    return _db_op(_delete, default=0)


# ── USER API ─────────────────────────────────────────────────────────────────

def create_user(username: str, role: str = "guest", display_name: str = None) -> dict:
    def _create():
        user_id = f"USR-{secrets.token_hex(4).upper()}"
        if username in ("developer", "admin"):
            user_id = "USR-MASTER"

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO users (user_id, username, role, display_name) VALUES (?, ?, ?, ?)",
                (user_id, username, role, display_name or username),
            )
            conn.commit()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            return dict(row) if row else {}
    return _db_op(_create, default={})


def get_user_by_api_key(api_key: str) -> Optional[dict]:
    return None


def promote_user(user_id: str, role: str):
    def _promote():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
            conn.commit()
    _db_op(_promote)


# ── Chat History API ─────────────────────────────────────────────────────────

def save_message(agent: str, role: str, content: str, user_id: str = "USR-MASTER", session_id: str = "default"):
    def _save():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO chat_history (user_id, session_id, agent, role, content) VALUES (?, ?, ?, ?, ?)",
                (user_id, session_id, agent, role, content),
            )
            conn.commit()
    _db_op(_save)


def get_history(agent: str, limit: int = 50, user_id: str = "USR-MASTER", session_id: str = "default") -> List[Dict[str, str]]:
    def _get():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT role, content FROM chat_history
                   WHERE agent = ? AND user_id = ? AND session_id = ?
                   ORDER BY id DESC LIMIT ?""",
                (agent, user_id, session_id, limit),
            )
            rows = cursor.fetchall()
            return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    return _db_op(_get, default=[])


def clear_history(agent: str, user_id: str = "USR-MASTER", session_id: str = "default"):
    def _clear():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM chat_history WHERE agent = ? AND user_id = ? AND session_id = ?",
                (agent, user_id, session_id),
            )
            conn.commit()
    _db_op(_clear)


# ── API KEY STORAGE (encrypted at rest) ──────────────────────────────────────

def save_user_key(user_id: str, provider: str, key: str):
    def _save():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO user_api_keys (user_id, provider, api_key) VALUES (?, ?, ?)",
                (user_id, provider, encrypt_secret(key)),
            )
            conn.commit()
    _db_op(_save)


def get_user_keys(user_id: str) -> Dict[str, str]:
    def _get():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT provider, api_key FROM user_api_keys WHERE user_id = ?", (user_id,))
            return {r["provider"]: decrypt_secret(r["api_key"]) for r in cursor.fetchall()}
    return _db_op(_get, default={})


def get_user_key(user_id: str, provider: str) -> Optional[str]:
    def _get():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT api_key FROM user_api_keys WHERE user_id = ? AND provider = ?",
                (user_id, provider),
            )
            row = cursor.fetchone()
            return decrypt_secret(row["api_key"]) if row else None
    return _db_op(_get)


def delete_user_key(user_id: str, provider: str):
    def _delete():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM user_api_keys WHERE user_id = ? AND provider = ?",
                (user_id, provider),
            )
            conn.commit()
    _db_op(_delete)


# ── Trades ───────────────────────────────────────────────────────────────────

def save_trade(user_id: str, symbol: str, side: str, amount: float, price: float, status: str, order_id: str = None):
    def _save():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO trades (user_id, symbol, side, amount, price, status, order_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, symbol, side, amount, price, status, order_id),
            )
            conn.commit()
    _db_op(_save)


# ── Timers ───────────────────────────────────────────────────────────────────

def start_timer(task: str, user_id: str = "USR-MASTER") -> int:
    def _start():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute(
                "UPDATE timers SET status = 'interrupted', end_time = ? "
                "WHERE user_id = ? AND status = 'active'",
                (now, user_id),
            )
            cursor.execute(
                "INSERT INTO timers (user_id, task, start_time, status) VALUES (?, ?, ?, 'active')",
                (user_id, task, now),
            )
            conn.commit()
            return cursor.lastrowid
    return _db_op(_start, default=-1)


def clear_active_timers(user_id: str = "USR-MASTER"):
    def _clear():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE timers SET status = 'interrupted', end_time = ? WHERE user_id = ? AND status = 'active'",
                (datetime.now().isoformat(), user_id),
            )
            conn.commit()
    _db_op(_clear)


def end_timer(timer_id: int, status: str = "completed"):
    def _end():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT start_time FROM timers WHERE id = ?", (timer_id,))
            row = cursor.fetchone()
            duration = 0
            if row:
                start = datetime.fromisoformat(row["start_time"])
                duration = int((datetime.now() - start).total_seconds() / 60)

            cursor.execute(
                "UPDATE timers SET end_time = ?, status = ?, duration_minutes = ? WHERE id = ?",
                (datetime.now().isoformat(), status, duration, timer_id),
            )
            conn.commit()
    _db_op(_end)


def get_timer_stats(user_id: str = "USR-MASTER") -> List[Dict[str, Any]]:
    def _get():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM timers WHERE user_id = ? ORDER BY id DESC", (user_id,))
            return [dict(r) for r in cursor.fetchall()]
    return _db_op(_get, default=[])


def get_timer_summary(user_id: str = "USR-MASTER") -> Dict[str, Any]:
    def _get():
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT SUM(duration_minutes) as total_mins
                FROM timers
                WHERE user_id = ? AND date(start_time) = date('now')
            """, (user_id,))
            today_mins = cursor.fetchone()["total_mins"] or 0

            cursor.execute("""
                SELECT * FROM timers
                WHERE user_id = ? AND status = 'active'
                LIMIT 1
            """, (user_id,))
            active = cursor.fetchone()

            cursor.execute("SELECT COUNT(*) as total FROM timers WHERE user_id = ?", (user_id,))
            total_sessions = cursor.fetchone()["total"]

            cursor.execute(
                "SELECT COUNT(*) as total FROM timers WHERE user_id = ? AND date(start_time) = date('now')",
                (user_id,),
            )
            sessions_today = cursor.fetchone()["total"]

            return {
                "today_total_seconds": today_mins * 60,
                "today_seconds": today_mins * 60,
                "active_session": bool(active),
                "current_task": active["task"] if active else None,
                "start_time": active["start_time"] if active else None,
                "total_sessions": total_sessions,
                "sessions_today": sessions_today,
            }
    return _db_op(_get, default={
        "today_total_seconds": 0, "today_seconds": 0,
        "active_session": False, "current_task": None,
        "start_time": None, "total_sessions": 0, "sessions_today": 0,
    })


def get_last_timer(user_id: str = "USR-MASTER") -> Optional[Dict[str, Any]]:
    def _get():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM timers WHERE user_id = ? AND status != 'active' ORDER BY id DESC LIMIT 1",
                (user_id,),
            )
            row = cursor.fetchone()
            if not row:
                cursor.execute(
                    "SELECT * FROM timers WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
                )
                row = cursor.fetchone()
            return dict(row) if row else None
    return _db_op(_get)


# ── App State (KV Store) ─────────────────────────────────────────────────────

def set_state(key: str, value) -> None:
    def _set():
        val_str = json.dumps(value) if not isinstance(value, str) else value
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
                (key, val_str),
            )
            conn.commit()
    _db_op(_set)


def get_state(key: str, default=None):
    def _get():
        with get_db_connection() as conn:
            row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        raw = row["value"]
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw
    return _db_op(lambda: _get(), default=default)


def clear_all_state() -> None:
    def _clear():
        with get_db_connection() as conn:
            conn.execute("DELETE FROM app_state")
            conn.commit()
    _db_op(_clear)
