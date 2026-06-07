import sqlite3
import os

from database import get_db_connection

def init_event_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS market_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,        -- "fomc", "nfp", "cpi", "geopolitical", "leader_statement"
                event_date TEXT NOT NULL,
                description TEXT NOT NULL,
                leader TEXT,                     -- who said/did it
                sentiment_before TEXT,           -- market sentiment pre-event
                sentiment_after TEXT,            -- market sentiment post-event
                btc_change REAL,                 -- % change in BTC within 24h
                sp500_change REAL,               -- % change in S&P 500 within 24h
                gold_change REAL,                -- % change in Gold within 24h
                oil_change REAL,                 -- % change in Oil within 24h
                pattern TEXT,                    -- "dovish_pivot", "hawkish_surprise", "geopolitical_escalation"
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

def log_market_event(event_type: str, date: str, description: str, leader: str, 
                     sentiment_before: str, sentiment_after: str, 
                     btc_change: float, sp500_change: float, pattern: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO market_events 
            (event_type, event_date, description, leader, sentiment_before, sentiment_after, btc_change, sp500_change, pattern)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (event_type, date, description, leader, sentiment_before, sentiment_after, btc_change, sp500_change, pattern))
        conn.commit()

def query_historical_patterns(leader: str, pattern: str) -> list:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT event_date, description, btc_change, sp500_change 
            FROM market_events 
            WHERE leader LIKE ? AND pattern = ?
            ORDER BY event_date DESC LIMIT 5
        ''', (f"%{leader}%", pattern))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

init_event_db()
