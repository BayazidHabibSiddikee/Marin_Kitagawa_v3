#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Marin Unified Startup
# Starts freellmapi (port 3001) then Marin FastAPI (port 5069)
# Usage: ./start.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

MARIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FREELLM_DIR="$HOME/freellmapi"
VENV="$HOME/marin_venv"
LOG_DIR="$MARIN_DIR/logs"
mkdir -p "$LOG_DIR"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}     Marin AI — Starting all services${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── 1. Kill any old processes ───────────────────────────────────────────────
pkill -f "uvicorn main:app"   2>/dev/null || true
pkill -f "tsx.*server/src"    2>/dev/null || true
sleep 1

# ── 2. Start freellmapi ─────────────────────────────────────────────────────
echo -e "Starting ${CYAN}freellmapi${NC} on :3001..."

if lsof -i :3001 >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓ freellmapi already running on :3001${NC}"
else
    if [ ! -d "$FREELLM_DIR" ]; then
        echo -e "  ${YELLOW}⚠ freellmapi not found at $FREELLM_DIR — skipping${NC}"
        echo -e "  ${YELLOW}  Marin will use its own provider list as fallback${NC}"
    else
        cd "$FREELLM_DIR"
        nohup npx tsx server/src/index.ts > "$LOG_DIR/freellmapi.log" 2>&1 &
        echo $! > "$LOG_DIR/freellmapi.pid"

        echo -n "  Waiting for freellmapi health check"
        for i in {1..15}; do
            if curl -s http://localhost:3001/api/health >/dev/null 2>&1; then
                echo -e "\n  ${GREEN}✓ freellmapi up on :3001${NC}"
                break
            fi
            echo -n "."
            sleep 1
        done
        if ! curl -s http://localhost:3001/api/health >/dev/null 2>&1; then
            echo -e "\n  ${YELLOW}⚠ freellmapi may still be starting (check logs/freellmapi.log)${NC}"
        fi
        cd "$MARIN_DIR"
    fi
fi

echo ""

# ── 3. Start Marin ──────────────────────────────────────────────────────────
echo -e "Starting ${CYAN}Marin AI${NC} on :5069..."

source "$VENV/bin/activate"
cd "$MARIN_DIR"

# Export freellmapi connection info for llm_manager.py
export FREELLMAPI_URL="http://127.0.0.1:3001/v1"
export FREELLMAPI_KEY="$(grep FREELLMAPI_KEY .env | cut -d "=" -f2)"

python3 -m uvicorn main:app \
    --host 0.0.0.0 \
    --port 5069 \
    --log-level info \
    2>&1 | tee "$LOG_DIR/marin.log"
