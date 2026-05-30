#!/usr/bin/env python3
"""
Quick test of Marin tools using the project's venv.
"""
import os
import sys
import subprocess
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.join(BASE_DIR, "tools")

# Activate the project's venv? Actually we are already sourced in the terminal.
# But we can just use the python from the venv if needed.
# We'll assume we are already in the venv.

def test_tool_help(tool_path):
    try:
        proc = subprocess.run(
            [sys.executable, tool_path, "--help"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if proc.returncode == 0:
            return True, proc.stdout[:100]
        else:
            # try -h
            proc2 = subprocess.run(
                [sys.executable, tool_path, "-h"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if proc2.returncode == 0:
                return True, proc2.stdout[:100]
            else:
                return False, f"help failed: {proc.stderr[:50]}"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, f"error: {e}"

# List of tools to test (we'll test a few key ones)
tools_to_test = [
    "knowledge_hub.py",
    "stock.py",
    "crypto.py",
    "translate.py",
    "maps.py",
    "office_tools.py",
    "command_queue.py",
    "vault_manager.py",
    "news.py",
    "youtube_transcript.py",
    "alarm.py",
    "timer.py",
    "vpa.py",
    "image.py",
    "draw.py",
    "wordgame.py",
    "connect4.py",
    "tictactoe.py",
    "email_tool.py",
    "pdf.py",
    "student_tools.py",
    "bangla.py",
    "crypto_data.py",
    "news_harvester.py",
    "app.py",
    "stealth_browser.py",
    "archive_tools.py",
]

print("Testing tools with --help (using project venv)...")
passed = []
failed = []
for tool in tools_to_test:
    path = os.path.join(TOOLS_DIR, tool)
    ok, msg = test_tool_help(path)
    if ok:
        passed.append((tool, msg))
        print(f"✓ {tool}: {msg}")
    else:
        failed.append((tool, msg))
        print(f"✗ {tool}: {msg}")

print(f"\nPassed: {len(passed)}")
print(f"Failed: {len(failed)}")

if failed:
    print("\nFailed tools:")
    for tool, msg in failed:
        print(f"  {tool}: {msg}")