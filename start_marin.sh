#!/bin/bash
set -e

# Load the virtual environment
if [ ! -d "$HOME/marin_venv" ]; then
    echo "❌ Virtual environment not found at ~/marin_venv"
    echo "Please create it first and install requirements."
    exit 1
fi

source "$HOME/marin_venv/bin/activate"

# Ensure directories exist
mkdir -p logs static/uploads static/generated static/downloads doc code unique/marin_vault storage/faiss_db

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Marin HS-02 — Local Venv Start"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "→ Starting services via Supervisord..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Chat UI:    http://localhost:5069"
echo "  RAG:        http://localhost:5080"
echo "  ModuleFlow: http://localhost:5070"
echo "  Ollama:     http://localhost:11434"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Run supervisord in the foreground
supervisord -c ./supervisord.local.conf
