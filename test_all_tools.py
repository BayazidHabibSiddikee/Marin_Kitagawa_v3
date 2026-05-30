#!/usr/bin/env python3
"""
Test all Marin tools to see if they can be executed (at least without import errors).
We'll try to run each tool with --help or --version if available, or just import and see if there are import errors.
"""
import os
import sys
import subprocess
import importlib.util

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.join(BASE_DIR, "tools")

# Add BASE_DIR to sys.path so we can import from tools if needed
sys.path.insert(0, BASE_DIR)

results = []

def test_tool(filepath):
    """Test a single tool script."""
    name = os.path.basename(filepath)
    print(f"Testing {name}...", end=' ')
    
    # First, check if it's a Python file
    if not filepath.endswith('.py'):
        return ("SKIP", "Not a Python file")
    
    # Try to run with --help
    try:
        proc = subprocess.run(
            [sys.executable, filepath, "--help"],
            capture_output=True,
            text=True,
            timeout=5
        )
        # If --help works, it's good
        if proc.returncode == 0:
            return ("PASS", f"--help succeeded (stdout length {len(proc.stdout)})")
        else:
            # Maybe --help is not supported, try -h
            proc2 = subprocess.run(
                [sys.executable, filepath, "-h"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if proc2.returncode == 0:
                return ("PASS", f"-h succeeded (stdout length {len(proc2.stdout)})")
            else:
                # Neither helped; maybe the tool doesn't accept help flags.
                # Try to import the module to see if there are import errors.
                # We'll do a simple import check.
                mod_name = name[:-3]  # remove .py
                spec = importlib.util.spec_from_file_location(mod_name, filepath)
                if spec is None:
                    return ("FAIL", "Could not load spec")
                module = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(module)
                    return ("PASS", "Module imports successfully (no --help/-h)")
                except Exception as e:
                    return ("FAIL", f"Import error: {e}")
    except subprocess.TimeoutExpired:
        return ("FAIL", "Timeout on --help/-h")
    except Exception as e:
        return ("FAIL", f"Unexpected error: {e}")

# Get all .py files in tools directory
tool_files = []
for f in os.listdir(TOOLS_DIR):
    if f.endswith('.py'):
        tool_files.append(os.path.join(TOOLS_DIR, f))

print(f"Found {len(tool_files)} tools to test.\n")

for tf in tool_files:
    status, msg = test_tool(tf)
    results.append((os.path.basename(tf), status, msg))
    print(f"{status}: {msg}")

print("\n=== Summary ===")
passed = [r for r in results if r[1] == "PASS"]
failed = [r for r in results if r[1] == "FAIL"]
skipped = [r for r in results if r[1] == "SKIP"]

print(f"PASS: {len(passed)}")
print(f"FAIL: {len(failed)}")
print(f"SKIP: {len(skipped)}")

if failed:
    print("\nFailed tools:")
    for name, status, msg in failed:
        print(f"  {name}: {msg}")

if passed:
    print("\nPassed tools:")
    for name, status, msg in passed:
        print(f"  {name}: {msg}")