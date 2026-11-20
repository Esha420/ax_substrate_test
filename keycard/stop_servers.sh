#!/usr/bin/env bash
# ==============================================================================
# Stop Keycard Multi-Agent A2A Environment
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/.server_pids"

echo -e "\033[1;33mStopping Keycard A2A environment...\033[0m"

if [ -f "$PID_FILE" ]; then
    PIDS=$(cat "$PID_FILE")
    for pid in $PIDS; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            echo "  Stopped process PID $pid"
        fi
    done
    rm -f "$PID_FILE"
fi

# Fallback: kill by port or process name
fuser -k 8088/tcp 2>/dev/null || true
fuser -k 9002/tcp 2>/dev/null || true
fuser -k 9003/tcp 2>/dev/null || true

echo -e "\033[1;32m✔ All services stopped cleanly.\033[0m"
