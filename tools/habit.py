#!/usr/bin/env python3
"""
habit.py — CLI wrapper for the unified habit/task tracker.
Uses habit_store.py for all DB operations.
"""
import sys
from habit_store import add_task, complete_task, list_tasks, get_stats, get_reminders_for_today, delete_task

def run(action, args):
    if action == "add":
        return add_task(args[0], "todo", args[1] if len(args) > 1 else "normal")
    elif action == "list":
        return str(list_tasks())
    elif action == "done":
        return complete_task(int(args[0]))
    elif action == "stats":
        return str(get_stats())
    elif action == "today":
        return str(get_reminders_for_today())
    elif action == "del":
        return delete_task(int(args[0]))
    else:
        return "Unknown action"
