#!/bin/bash
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Marin HS-02 — Docker Entry Point"
echo "  Mode: SECURE SANDBOX (bridge mode, limited caps)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Ensure directories exist
mkdir -p logs static/uploads static/generated static/downloads doc code unique/marin_vault storage/faiss_db

# Ollama runs on the HOST machine.
# Verify we can reach it via host.docker.internal before starting services.
echo "→ Checking Ollama on host (http://host.docker.internal:11434)..."
for i in 1 2 3 4 5; do
    if curl -sf http://host.docker.internal:11434/api/tags > /dev/null 2>&1; then
        echo "✅ Ollama reachable on host."
        break
    fi
    echo "  Waiting for Ollama ($i/5)..."
    sleep 3
done

echo "→ Starting services via Supervisord..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Chat UI:    http://localhost:5069"
echo "  RAG:        http://localhost:5080"
echo "  ModuleFlow: http://localhost:5070"
echo "  Ollama:     http://localhost:11434 (internal)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Execute supervisord to manage all processes
exec supervisord -c /app/supervisord.conf
