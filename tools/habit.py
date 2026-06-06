#!/usr/bin/env python3
"""
habit.py — CLI wrapper for the unified habit/task tracker.
Uses habit_store.py for all DB operations.
"""

import sys
from habit_store import add_task, complete_task, list_tasks, get_stats, get_reminders_for_today, delete_task


def add(title, cat="general", pri="medium", remind=False):
    t = add_task(title, category=cat, priority=pri, remind_daily=remind)
    r = "daily reminder ON" if remind else "no reminder"
    print(f"  + #{t['id']} '{t['title']}' [{t['priority']}] ({t['category']}) — {r}")


def done(task_id):
    res = complete_task(task_id)
    print(f"  {res}")


def ls(status=None, cat=None):
    tasks = list_tasks(status=status, category=cat)
    if not tasks:
        print("  no tasks")
        return
    icons = {"done": "ok", "in-progress": "~", "todo": ".."}
    for r in tasks:
        i = icons.get(r["status"], "..")
        d = " [remind]" if r["remind_daily"] else ""
        print(f"  #{r['id']:>3} {i:>4} [{r['priority']:<6}] {r['title']:<30} ({r['category']}){d}")


def stats():
    s = get_stats()
    print(f"  total={s['total']}  done={s['done']}  todo={s['todo']}  active={s['in_progress']}")
    for c in s["categories"]:
        pct = round(c["done"]/c["total"]*100) if c["total"] else 0
        print(f"    {c['category']}: {c['done']}/{c['total']} ({pct}%)")


def today():
    tasks = get_reminders_for_today()
    if not tasks:
        print("  no reminders pending")
        return
    for r in tasks:
        print(f"  #{r['id']} [{r['priority']}] {r['title']} ({r['category']})")


def delete(task_id):
    res = delete_task(task_id)
    print(f"  {res}")


def main():
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
