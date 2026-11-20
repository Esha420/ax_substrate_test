#!/usr/bin/env bash
# ==============================================================================
# Start Keycard Multi-Agent A2A Environment
# Spawns:
#   1. Keycard STS Server (Port 8088)
#   2. Agent B: Incident Investigator (Port 9002)
#   3. Agent C: Audit Vault Signer (Port 9003)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load environment variables from .env if present
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    . "$SCRIPT_DIR/.env"
    set +a
fi

PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [ ! -f "$PYTHON" ]; then
    echo "Virtual environment not found at $PYTHON"
    exit 1
fi

PID_FILE="$SCRIPT_DIR/.server_pids"

# Check if already running
if [ -f "$PID_FILE" ]; then
    echo "[!] Servers appear to be already running (found $PID_FILE)."
    echo "    Run ./stop_servers.sh first if you want to restart them."
fi

echo -e "\033[1;36m======================================================================\033[0m"
echo -e "\033[1;36m  STARTING KEYCARD A2A MULTI-AGENT ENVIRONMENT                        \033[0m"
echo -e "\033[1;36m======================================================================\033[0m"

# 1. Start Keycard STS
echo -n "• Starting Keycard Local STS on http://127.0.0.1:8088 ... "
nohup "$PYTHON" keycard_server.py 8088 > .sts.log 2>&1 &
PID_STS=$!
disown $PID_STS
echo -e "\033[1;32mPID $PID_STS\033[0m"

# 2. Start Agent C (Audit Vault Signer)
echo -n "• Starting Agent C (Audit Vault) on http://127.0.0.1:9003 ... "
nohup "$PYTHON" agent_c_server.py --port 9003 > .agent_c.log 2>&1 &
PID_AGENT_C=$!
disown $PID_AGENT_C
echo -e "\033[1;32mPID $PID_AGENT_C\033[0m"

# 3. Start Agent B (Incident Investigator)
echo -n "• Starting Agent B (Investigator) on http://127.0.0.1:9002 ... "
nohup "$PYTHON" agent_b_server.py --port 9002 > .agent_b.log 2>&1 &
PID_AGENT_B=$!
disown $PID_AGENT_B
echo -e "\033[1;32mPID $PID_AGENT_B\033[0m"

echo "$PID_STS $PID_AGENT_C $PID_AGENT_B" > "$PID_FILE"

# Wait for all services to become healthy
echo -e "\nWaiting for endpoints to become healthy..."

wait_for_health() {
    local url="$1"
    local name="$2"
    local retries=15
    while [ $retries -gt 0 ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo -e "  \033[1;32m✓\033[0m $name is healthy ($url)"
            return 0
        fi
        sleep 0.4
        retries=$((retries - 1))
    done
    echo -e "  \033[1;31m✗\033[0m Timed out waiting for $name at $url"
    return 1
}

wait_for_health "http://127.0.0.1:8088/health" "Keycard STS"
wait_for_health "http://127.0.0.1:9002/health" "Agent B (Investigator)"
wait_for_health "http://127.0.0.1:9003/health" "Agent C (Audit Vault)"

echo -e "\n\033[1;32m✔ All 3 services are online and ready for live demonstration!\033[0m"
echo -e "  Logs: \033[2m.sts.log, .agent_b.log, .agent_c.log\033[0m"
echo -e "  To stop: \033[1;33m./stop_servers.sh\033[0m\n"
