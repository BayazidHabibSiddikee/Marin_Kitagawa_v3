#!/usr/bin/env bash
# Unified Launcher for Marin HS-02

# 1. Cleanup
echo "Cleaning up existing processes..."
pkill -f "main:app" || true
pkill -f "sentinel_engine" || true
pkill -f "rag_server.py" || true
pkill -f "moduleflow/serve.py" || true
pkill -f "tools/app.py" || true

sleep 1

PY_PATH="/home/sword/miniconda3/bin/python3"

# 2. Start Sentinel Engine (Port 5071) — LLM brain
echo "Starting Sentinel Engine on port 5071..."
$PY_PATH sentinel_engine.py > logs/sentinel.log 2>&1 &
SENTINEL_PID=$!

# 3. Start RAG Server (Port 5080)
echo "Starting RAG server on port 5080..."
$PY_PATH rag_server.py --port 5080 > logs/rag.log 2>&1 &
RAG_PID=$!

# 4. Start ModuleFlow (Port 5070)
if [ -f "moduleflow/serve.py" ]; then
    echo "Starting ModuleFlow on port 5070..."
    $PY_PATH moduleflow/serve.py > logs/moduleflow.log 2>&1 &
    MF_PID=$!
fi

# 5. Start Main App (Port 5069)
echo "Starting Main App on port 5069..."
$PY_PATH -m uvicorn main:app --host 0.0.0.0 --port 5069 --log-level info > logs/uvicorn.log 2>&1 &
MAIN_PID=$!

echo "------------------------------------------------"
echo "✅ All systems launched!"
echo "→ Sentinel Engine: http://localhost:5071"
echo "→ Main App:        http://localhost:5069"
echo "→ RAG Server:      http://localhost:5080"
echo "→ ModuleFlow:      http://localhost:5070"
echo "------------------------------------------------"
echo "Press Ctrl+C to stop all."

# Run in background to let the script finish but keep servers alive
disown $SENTINEL_PID $MAIN_PID $RAG_PID $MF_PID 2>/dev/null
