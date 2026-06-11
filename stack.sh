#!/usr/bin/env bash
# Marin Sentinel Stack (Unified & Minimal)

# Kill existing processes
echo "Stopping existing services..."
pkill -f "sentinel_engine.py" || true
pkill -f "main:app" || true

# 1. Start Sentinel Engine Brain (Port 3001)
# This handles Uncensoring, Persona, and LLM Routing
echo "Starting Sentinel Engine Brain (3001)..."
python3 sentinel_engine.py > logs/sentinel.log 2>&1 &

# 2. Start Marin UI / Agent (Port 5069)
echo "Starting Marin Agent (5069)..."
python3 -m uvicorn main:app --host 0.0.0.0 --port 5069 --log-level info
