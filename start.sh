#!/usr/bin/env bash
set -e

MARIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FREELLM_DIR="$HOME/freellmapi"
VENV="$HOME/marin_venv"
LOG_DIR="$MARIN_DIR/logs"
mkdir -p "$LOG_DIR"

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}     Marin AI — Starting all services${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

pkill -9 -f "uvicorn main:app"   2>/dev/null || true
pkill -9 -f "tsx.*server/src"    2>/dev/null || true
sleep 1

echo -e "Starting ${CYAN}g4f API${NC} on :1337..."
source "$VENV/bin/activate"
nohup python3 -m g4f.cli api --bind 127.0.0.1:1337 > "$LOG_DIR/g4f.log" 2>&1 &
echo $! > "$LOG_DIR/g4f.pid"

echo -e "Starting ${CYAN}freellmapi${NC} on :3001..."
if [ -d "$FREELLM_DIR" ]; then
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
    cd "$MARIN_DIR"
else
    echo -e "  ${YELLOW}⚠ freellmapi not found — skipping${NC}"
fi

echo ""
echo -e "Starting ${CYAN}Marin AI${NC} on :5069..."
source "$VENV/bin/activate"
cd "$MARIN_DIR"

python3 -m uvicorn main:app \
    --host 0.0.0.0 \
    --port 5069 \
    --log-level info \
    2>&1 | tee "$LOG_DIR/marin.log"
