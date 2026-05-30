#!/usr/bin/env python3
"""
Test script for Marin tools via LangGraph or direct import.
We'll test a few tools to ensure they work.
"""
import os
import sys
import json
import subprocess

# Add marin root to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

print("=== Testing Marin Tools ===\n")

# 1. Test knowledge_hub.create_integrated_hub_map
print("1. Testing knowledge_hub.create_integrated_hub_map")
try:
    from tools.knowledge_hub import create_integrated_hub_map
    result = create_integrated_hub_map(location="Dhaka", query="hospital", limit=3)
    print(f"   Result type: {type(result)}")
    if isinstance(result, dict):
        print(f"   Keys: {list(result.keys())}")
        # Print a snippet
        print(f"   Sample: {json.dumps(result, indent=2)[:200]}...")
    else:
        print(f"   Result: {result}")
except Exception as e:
    print(f"   ERROR: {e}")
    import traceback
    traceback.print_exc()
print()

# 2. Test stock.py via subprocess
print("2. Testing stock.py (AAPL)")
try:
    script = os.path.join(BASE_DIR, "tools", "stock.py")
    proc = subprocess.run(
        [sys.executable, script, "--ticker", "AAPL"],
        capture_output=True,
        text=True,
        timeout=10
    )
    if proc.returncode == 0:
        print(f"   Success: {proc.stdout[:200]}...")
    else:
        print(f"   ERROR: {proc.stderr}")
except Exception as e:
    print(f"   ERROR: {e}")
print()

# 3. Test crypto.py via subprocess
print("3. Testing crypto.py (bitcoin)")
try:
    script = os.path.join(BASE_DIR, "tools", "crypto.py")
    proc = subprocess.run(
        [sys.executable, script, "--coin", "bitcoin"],
        capture_output=True,
        text=True,
        timeout=10
    )
    if proc.returncode == 0:
        print(f"   Success: {proc.stdout[:200]}...")
    else:
        print(f"   ERROR: {proc.stderr}")
except Exception as e:
    print(f"   ERROR: {e}")
print()

# 4. Test read_file (simple)
print("4. Testing read_file on README")
try:
    readme_path = os.path.join(BASE_DIR, "readme.md")
    with open(readme_path, 'r', encoding='utf-8') as f:
        content = f.read(200)  # first 200 chars
    print(f"   Success: read {len(content)} chars")
    print(f"   Preview: {content[:100]}...")
except Exception as e:
    print(f"   ERROR: {e}")
print()

# 5. Test classify from marin_fier
print("5. Testing marin_fier.classify")
try:
    from marin_fier import classify
    result = classify("What is the weather in Dhaka?")
    print(f"   Result: {result}")
except Exception as e:
    print(f"   ERROR: {e}")
print()

# 6. Test a simple tool: alarm.py maybe
print("6. Testing alarm.py (help)")
try:
    script = os.path.join(BASE_DIR, "tools", "alarm.py")
    proc = subprocess.run(
        [sys.executable, script, "--help"],
        capture_output=True,
        text=True,
        timeout=5
    )
    if proc.returncode == 0:
        # Get first two lines of help
        lines = proc.stdout.split('\n')
        first_two_lines = lines[0] + '\n' + lines[1] if len(lines) > 1 else lines[0]
        print(f"   Help output (first 2 lines): {first_two_lines}")
    else:
        print(f"   ERROR: {proc.stderr}")
except Exception as e:
    print(f"   ERROR: {e}")
print()

print("=== Test Complete ===")