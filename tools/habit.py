#!/usr/bin/env python3
"""
habit.py — CLI wrapper for the unified habit/task tracker.
Uses habit_store.py for all DB operations.
"""
from tools.habit_store import add_task, complete_task, delete_task, get_reminders_for_today, get_stats, list_tasks


def run(action, args):
    if action == "add":
        return add_task(args[0], "todo", args[1] if len(args) > 1 else "normal")
    if action == "list":
        return str(list_tasks())
    if action == "done":
        return complete_task(int(args[0]))
    if action == "stats":
        return str(get_stats())
    if action == "today":
        return str(get_reminders_for_today())
    if action == "del":
        return delete_task(int(args[0]))
    return "Unknown action"
