#!/usr/bin/env bash
# Unified Launcher for Marin HS-02

# 1. Cleanup
echo "Cleaning up existing processes..."
pkill -f "main:app" || true
pkill -f "rag_server.py" || true
pkill -f "moduleflow/serve.py" || true
pkill -f "tools/app.py" || true

# Wait for ports to clear
sleep 1

# 2. Start RAG Server (Port 5080)
echo "Starting RAG server on port 5080..."
python rag_server.py --port 5080 > rag.log 2>&1 &
RAG_PID=$!

# 3. Start ModuleFlow (Port 5070)
if [ -f "moduleflow/serve.py" ]; then
    echo "Starting ModuleFlow on port 5070..."
    python moduleflow/serve.py > moduleflow.log 2>&1 &
    MF_PID=$!
fi

# 4. Start Todo App (Port 5000)
if [ -f "tools/app.py" ]; then
    echo "Starting Todo App on port 5000..."
    python tools/app.py > todo.log 2>&1 &
    TODO_PID=$!
fi

# 5. Start Main App (Port 5069)
echo "Starting Main App on port 5069..."
python -m uvicorn main:app --host 0.0.0.0 --port 5069 --log-level info > uvicorn.log 2>&1 &
MAIN_PID=$!

echo "------------------------------------------------"
echo "✅ All systems launched!"
echo "→ Main App:       http://localhost:5069"
echo "→ RAG Server:     http://localhost:5080"
echo "→ ModuleFlow:     http://localhost:5070"
echo "→ Todo App:       http://localhost:5000"
echo "------------------------------------------------"
echo "Logs: uvicorn.log, rag.log, moduleflow.log, todo.log"
echo "Press Ctrl+C to stop all."

# Trap to kill all sub-processes on exit
trap "kill $MAIN_PID $RAG_PID $MF_PID $TODO_PID 2>/dev/null; echo 'Servers stopped.'; exit" INT TERM

wait
