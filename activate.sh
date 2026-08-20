#!/bin/bash
# Marin Tools Helper — Start / Stop the Kingdom
# Usage:
#   ./activate.sh          — start
#   ./activate.sh stop     — stop all services
#   ./activate.sh restart  — stop then start

VENV="$HOME/marin_venv"
CONF="./supervisord.local.conf"
PID_FILE="./logs/supervisord.pid"

# ── STOP ──────────────────────────────────────────────────────────────────────
stop_marin() {
    echo "🛑 Stopping Marin..."

    # 1. Supervisord graceful shutdown via PID file
    if [ -f "$PID_FILE" ]; then
        SPID=$(cat "$PID_FILE")
        if kill -0 "$SPID" 2>/dev/null; then
            kill "$SPID"
            # Wait up to 8s for it to exit
            for i in $(seq 1 8); do
                kill -0 "$SPID" 2>/dev/null || break
                sleep 1
            done
            echo "   ✓ Supervisord stopped."
        fi
        rm -f "$PID_FILE"
    fi

    # 2. Kill anything still holding our ports
    for PORT in 5069 5070 5080; do
        PID=$(ss -tlnp "sport = :$PORT" 2>/dev/null \
              | grep -oP 'pid=\K[0-9]+' | head -1)
        if [ -n "$PID" ]; then
            kill "$PID" 2>/dev/null && echo "   ✓ Killed process $PID on port $PORT."
        fi
    done

    echo "✅ Marin is offline."
}

# ── START ──────────────────────────────────────────────────────────────────────
start_marin() {
    echo "🏹 Starting Marin (local venv)..."

    # 1. Check venv
    if [ ! -d "$VENV" ]; then
        echo "❌ Virtual environment not found at $VENV"
        echo "   Create it with: python3 -m venv $VENV && $VENV/bin/pip install -r requirements.txt"
        exit 1
    fi

    # 2. Ensure required directories exist
    mkdir -p logs storage/faiss_db static/uploads static/generated

    # 3. Check for .env
    if [ ! -f ".env" ]; then
        echo "⚠️  .env file missing! Creating a temporary one..."
        echo "MARIN_API_SECRET=$(openssl rand -hex 32)" > .env
        echo "OWNER_USER=Bayazid" >> .env
    fi

    # 4. Check if already running
    if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
        echo "⚠️  Marin is already running (pid $(cat $PID_FILE))."
        echo "   Use './activate.sh restart' to restart."
        exit 0
    fi

    # 5. Activate venv and launch supervisord in background
    source "$VENV/bin/activate"
    nohup supervisord -c "$CONF" > /dev/null 2>&1 &

    # 6. Wait for ports to come up (up to 30s)
    echo "⏳ Waiting for services..."
    for i in $(seq 1 30); do
        if ss -tlnp 2>/dev/null | grep -q ':5069'; then
            break
        fi
        sleep 1
    done

    if ss -tlnp 2>/dev/null | grep -q ':5069'; then
        echo "✨ Marin is ascending..."
    else
        echo "⚠️  Main app took longer than expected. Check logs/main.err.log"
    fi

    echo "🌍 Portal:         http://localhost:5069"
    echo "⌬  Brain Topology: http://localhost:5070"
    echo "📚 RAG Server:     http://localhost:5080"
    echo "------------------------------------------------"
    echo "Run './activate.sh stop' to shut everything down."
}

# ── DISPATCH ──────────────────────────────────────────────────────────────────
case "${1:-start}" in
    stop)    stop_marin ;;
    restart) stop_marin; echo; start_marin ;;
    start|"") start_marin ;;
    *)
        echo "Usage: $0 [start|stop|restart]"
        exit 1
        ;;
esac
