#!/bin/bash
# Marin Tools Helper — Start the Kingdom
# Usage: ./activate.sh

echo "🏹 Starting Marin Tools (Docker-First)..."

# 1. Ensure required directories exist
mkdir -p logs storage/faiss_db static/uploads static/generated

# 2. Check for .env
if [ ! -f ".env" ]; then
    echo "⚠️ .env file missing! Creating a temporary one..."
    echo "MARIN_API_SECRET=$(openssl rand -hex 32)" > .env
    echo "OWNER_USER=Bayazid" >> .env
fi

# 3. Start the containers
docker compose up -d --build

echo "✨ Marin is ascending..."
echo "🌍 Portal: http://localhost:5069"
echo "⌬ Brain Topology: http://localhost:5070"
echo "📚 RAG Server: http://localhost:5080"
echo "------------------------------------------------"
echo "Use 'docker compose logs -f' to watch her thoughts."
