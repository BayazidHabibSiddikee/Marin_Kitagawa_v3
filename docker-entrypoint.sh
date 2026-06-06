#!/bin/bash
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Marin HS-02 — Docker Entry Point"
echo "  Mode: SECURE SANDBOX (bridge mode, limited caps)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Ensure directories exist
mkdir -p logs static/uploads static/generated static/downloads doc code unique/marin_vault storage/faiss_db

echo "→ Starting services via Supervisord..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Chat UI:    http://localhost:5069"
echo "  RAG:        http://localhost:5080"
echo "  ModuleFlow: http://localhost:5070"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Execute supervisord to manage all processes
exec supervisord -c /app/supervisord.conf
