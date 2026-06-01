#!/usr/bin/env python3
"""
habit.py — Simple habit tracker.
  CLI:  python habit.py add "Study math" --category study --priority high --remind
        python habit.py list
        python habit.py done 1
        python habit.py stats
        python habit.py today
        
Marin uses habit_store.py directly. This is the CLI wrapper.
"""

import os
import sys
import sqlite3
from datetime import datetime, date

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "storage", "habits.db")


def _db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init():
    db = _db()
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
            note TEXT
        );
    """)
    db.commit()
    db.close()


def add(title, cat="general", pri="medium", remind=False):
    db = _db()
    cur = db.execute(
        "INSERT INTO tasks (title, category, priority, remind_daily) VALUES (?,?,?,?)",
        (title, cat, pri, 1 if remind else 0)
    )
    db.commit()
    tid = cur.lastrowid
    db.close()
    r = "daily reminder ON" if remind else "no reminder"
    print(f"  + #{tid} '{title}' [{pri}] ({cat}) — {r}")


def done(task_id):
    db = _db()
    t = db.execute("SELECT title FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not t:
        print(f"  #{task_id} not found"); db.close(); return
    db.execute("UPDATE tasks SET status='done', completed_at=datetime('now','localtime') WHERE id=?", (task_id,))
    db.commit(); db.close()
    print(f"  done #{task_id} '{t['title']}'")


def ls(status=None, cat=None):
    db = _db()
    q, p = "SELECT * FROM tasks WHERE 1=1", []
    if status: q += " AND status=?"; p.append(status)
    if cat: q += " AND category=?"; p.append(cat)
    q += " ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, id DESC"
    rows = db.execute(q, p).fetchall(); db.close()
    if not rows: print("  no tasks"); return
    icons = {"done": "ok", "in-progress": "~", "todo": ".."}
    for r in rows:
        i = icons.get(r["status"], "..")
        d = " [remind]" if r["remind_daily"] else ""
        print(f"  #{r['id']:>3} {i:>4} [{r['priority']:<6}] {r['title']:<30} ({r['category']}){d}")


def stats():
    db = _db()
    t = db.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"]
    d = db.execute("SELECT COUNT(*) c FROM tasks WHERE status='done'").fetchone()["c"]
    w = db.execute("SELECT COUNT(*) c FROM tasks WHERE status='todo'").fetchone()["c"]
    p = db.execute("SELECT COUNT(*) c FROM tasks WHERE status='in-progress'").fetchone()["c"]
    cats = db.execute("SELECT category, COUNT(*) t, SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) d FROM tasks GROUP BY category").fetchall()
    db.close()
    print(f"  total={t}  done={d}  todo={w}  active={p}")
    for c in cats:
        pct = round(c["d"]/c["t"]*100) if c["t"] else 0
        print(f"    {c['category']}: {c['d']}/{c['t']} ({pct}%)")


def today():
    db = _db()
    today_str = date.today().isoformat()
    rows = db.execute(
        "SELECT * FROM tasks WHERE remind_daily=1 AND status!='done' "
        "AND id NOT IN (SELECT task_id FROM daily_log WHERE log_date=?)",
        (today_str,)
    ).fetchall(); db.close()
    if not rows: print("  no reminders pending"); return
    for r in rows:
        print(f"  #{r['id']} [{r['priority']}] {r['title']} ({r['category']})")


def delete(task_id):
    db = _db()
    db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    db.commit(); db.close()
    print(f"  deleted #{task_id}")


def main():
    init()
    if len(sys.argv) < 2:
        print("usage: habit.py <add|list|done|stats|today|del> [args]")
        return

    cmd = sys.argv[1]

    if cmd == "add" and len(sys.argv) >= 3:
        title = sys.argv[2]
        cat, pri, rem = "general", "medium", False
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == "--category" and i+1 < len(args): cat = args[i+1]; i += 2
            elif args[i] == "--priority" and i+1 < len(args): pri = args[i+1]; i += 2
            elif args[i] == "--remind": rem = True; i += 1
            else: i += 1
        add(title, cat, pri, rem)

    elif cmd == "list":
        status = sys.argv[2] if len(sys.argv) > 2 else None
        cat = sys.argv[3] if len(sys.argv) > 3 else None
        ls(status, cat)

    elif cmd == "done" and len(sys.argv) >= 3:
        done(int(sys.argv[2]))

    elif cmd == "stats":
        stats()

    elif cmd == "today":
        today()

    elif cmd == "del" and len(sys.argv) >= 3:
        delete(int(sys.argv[2]))

    else:
        print("usage: habit.py <add|list|done|stats|today|del> [args]")


if __name__ == "__main__":
    main()
