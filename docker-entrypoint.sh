#!/bin/bash
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Marin HS-02 — Docker Entry Point"
echo "  Mode: UNRESTRICTED (privileged container)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Ensure storage dirs exist
mkdir -p storage logs static/uploads static/generated static/downloads

# Start RAG server in background
echo "→ Starting RAG server on port 5080..."
python rag_server.py --port 5080 > rag.log 2>&1 &
RAG_PID=$!

# Start ModuleFlow if present
if [ -f "moduleflow/serve.py" ]; then
    echo "→ Starting ModuleFlow on port 5070..."
    python moduleflow/serve.py > moduleflow.log 2>&1 &
    MF_PID=$!
fi

# Start Main App (foreground)
echo "→ Starting Main App on port 5069..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Chat UI:    http://localhost:5069"
echo "  RAG:        http://localhost:5080"
echo "  ModuleFlow: http://localhost:5070"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Trap to kill all sub-processes on exit
trap "kill $RAG_PID ${MF_PID:-} 2>/dev/null; echo 'Services stopped.'; exit" INT TERM

# Run main app in foreground
exec python -m uvicorn main:app --host 0.0.0.0 --port 5069 --log-level info
