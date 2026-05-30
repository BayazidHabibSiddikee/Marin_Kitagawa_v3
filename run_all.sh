#!/usr/bin/env bash
set -e

# Kill any existing process on port 5069
pkill -f "uvicorn main:app" 2>/dev/null || true
sleep 1

echo "Starting unified server..."
echo "  RAG server auto-starts on first teach/code/ask — no manual launch needed."
echo "  Arena served at / on the same port."
echo ""

# Run with reload for development
uvicorn main:app --host 0.0.0.0 --port 5069 &

SERVER_PID=$!
echo "→ Unified Chat + Arena @ http://localhost:5069 (PID $SERVER_PID)"
echo ""
echo "Press Ctrl+C to stop."

trap "kill $SERVER_PID 2>/dev/null; exit" INT TERM
wait
