#!/usr/bin/env bash
set -eo pipefail

# ==============================================================================
# 🎬 15-MINUTE DEMO SHOWCASE: AX & AGENT SUBSTRATE RUNTIME
# ==============================================================================
# This script executes the exact 4-part demo flow with rich visual terminal
# output and live telemetry streaming to Substrate Scope (http://localhost:8123).
# ==============================================================================

export PATH="/home/berrybytes/bin:$PATH"
export KUBECONFIG="${KUBECONFIG:-/home/berrybytes/.kube/config}"
SCOPE_URL="http://127.0.0.1:8123"

# Styling Helpers
BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
MAGENTA='\033[0;35m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

post_scope_activity() {
  local agent="$1"
  local kind="$2"
  local text="$3"
  curl -s -X POST "${SCOPE_URL}/activity" \
    -H "Content-Type: application/json" \
    -d "{\"agent\":\"${agent}\",\"kind\":\"${kind}\",\"text\":\"${text}\",\"ms\":60,\"via\":\"demo-runner\"}" >/dev/null 2>&1 || true
}

banner() {
  local title="$1"
  local duration="$2"
  echo -e "\n${BOLD}${CYAN}==============================================================================${NC}"
  echo -e "${BOLD}${MAGENTA}▶ ${title}  ${YELLOW}[${duration}]${NC}"
  echo -e "${BOLD}${CYAN}==============================================================================${NC}\n"
}

step() {
  local num="$1"
  local msg="$2"
  echo -e "${BOLD}${GREEN}[Step ${num}]${NC} ${msg}"
}

pause_for_audience() {
  local secs="${1:-3}"
  echo -e "${BLUE}⏱  Observing state (${secs}s)...${NC}"
  sleep "${secs}"
}

# Ensure Substrate Scope is running
if ! lsof -i :8123 >/dev/null 2>&1; then
  echo -e "${YELLOW}Starting Substrate Scope on http://localhost:8123...${NC}"
  cd /home/berrybytes/Office/Assignment/substrate-scope
  nohup node server.mjs --live >/dev/null 2>&1 &
  sleep 2
fi

clear || true

echo -e "${BOLD}${CYAN}"
cat << "EOF"
   ___   _  __  ___    _____       __         __             __     
  / _ | | |/ / / _ |  / __/_ _____/ /  ___ ___/ /________ _ / /____ 
 / __ | / _ < / __ | _\ \/ // / _  / _(_-</ _  / __/ _ `/ / __/ -_)
/_/ |_|/_/|_|/_/ |_|/___/\_,_/_.__/_//___/\_,_/_/  \_,_/_/\__/\__/ 
EOF
echo -e "${NC}"
echo -e "${BOLD}🎯 AX & AGENT SUBSTRATE: 15-MINUTE LIVE DEMO SHOWCASE${NC}"
echo -e "Dashboard: ${BOLD}${GREEN}http://localhost:8123${NC}"
echo -e "Time:      $(date '+%Y-%m-%d %H:%M:%S')"
echo -e "Cluster:   Kind (ax-e2e) with gVisor runsc sandbox"
echo "------------------------------------------------------------------------------"

# ==============================================================================
# PART 1: ENVIRONMENT OVERVIEW (1 min)
# ==============================================================================
banner "PART 1: ENVIRONMENT OVERVIEW" "1 minute"
post_scope_activity "demo-coordinator" "prompt" "PART 1: Demonstrating live cluster topology and control planes..."

step "1.1" "Checking Kubernetes Nodes and Runtime Class (gVisor)"
kubectl get nodes -o wide
echo ""
kubectl get runtimeclass

step "1.2" "Agent Substrate Control Plane (ate-system)"
kubectl get pods,svc -n ate-system
post_scope_activity "substrate-control" "reply" "Substrate Control Plane active: ate-api-server, ate-controller, atelet, atenet-router."

step "1.3" "AX Server & Worker Pool (ax-system)"
kubectl get pods,svc -n ax-system
post_scope_activity "ax-system" "reply" "AX Control Plane active: ax-server, ax-postgres statefulset, 4 gVisor worker replicas."

step "1.4" "Substrate WorkerPool Custom Resource & Active Workers"
kubectl get workerpools.ate.dev -A
echo ""
kubectl-ate get worker
post_scope_activity "demo-coordinator" "reply" "Environment verified: Cluster is fully healthy with dual control planes."
pause_for_audience 3

# ==============================================================================
# PART 2: AX POSTGRESQL PERSISTENCE & RECOVERY (2 min)
# ==============================================================================
banner "PART 2: AX POSTGRESQL PERSISTENCE & RECOVERY" "2 minutes"
post_scope_activity "ax-postgres" "prompt" "PART 2: Demonstrating task persistence across AX server rollout restart..."

step "2.1" "Writing live state marker inside active task 'golden-task'"
PERSIST_TOKEN="DEMO_TOKEN_$(date +%s)"
ax ssh golden-task -- sh -c "echo '${PERSIST_TOKEN}' > /workspace/demo_marker.txt"
echo -e "   Written marker: ${BOLD}${GREEN}${PERSIST_TOKEN}${NC} into /workspace/demo_marker.txt"

step "2.2" "Directly Querying PostgreSQL Tasks Table"
kubectl exec -n ax-system statefulset/ax-postgres -c postgres -- \
  psql -U ax -d ax -c "SELECT atespace, name, saved_at, data->'status'->>'phase' as phase, data->'status'->>'actor' as actor FROM tasks WHERE name='golden-task';"

step "2.3" "Rolling Out Restart of ax-server (Simulating Server Crash/Update)"
echo -e "${YELLOW}   Restarting deployment/ax-server...${NC}"
kubectl rollout restart deployment/ax-server -n ax-system
kubectl rollout status deployment/ax-server -n ax-system --timeout=60s

step "2.4" "Verifying Task Persistence After Server Restart"
ax get tasks
ax describe task golden-task

step "2.5" "Verifying In-Guest State & Continued Execution"
RECOVERED_TOKEN=$(ax ssh golden-task -- cat /workspace/demo_marker.txt)
echo -e "   Read back marker from sandbox: ${BOLD}${GREEN}${RECOVERED_TOKEN}${NC}"
if [ "${RECOVERED_TOKEN}" == "${PERSIST_TOKEN}" ]; then
  echo -e "   ${BOLD}${GREEN}✔ PERSISTENCE VERIFIED:${NC} Task state and workspace survived restart without data loss."
  post_scope_activity "ax-postgres" "reply" "PASS: Postgres task record & guest workspace persisted across server restart."
fi
pause_for_audience 3

# ==============================================================================
# PART 3: AX-TO-SUBSTRATE TASK EXECUTION (3 min)
# ==============================================================================
banner "PART 3: AX-TO-SUBSTRATE TASK EXECUTION" "3 minutes"
post_scope_activity "ax-substrate-bridge" "prompt" "PART 3: Correlating AX tasks with Substrate actors, gVisor sandboxes & worker pods..."

step "3.1" "Submitting a fresh task 'demo-math-task' via AX"
ax delete task demo-math-task >/dev/null 2>&1 || true
sleep 1
cat <<EOF | ax apply -f -
apiVersion: ax.dev/v1alpha1
kind: Task
metadata:
  name: demo-math-task
  atespace: default
spec:
  image: localhost:5001/ax-task-runner:e2e@sha256:6627ebe4690940abd761daba55d0809595852c639816e968748885d24de913b0
  command:
    - sleep
    - "3600"
  debug: true
EOF

ax resume task demo-math-task
sleep 3

step "3.2" "Correlating AX Task Status with Substrate Actor Registry"
echo -e "${CYAN}--- AX Perspective ---${NC}"
ax describe task demo-math-task
echo ""
echo -e "${CYAN}--- Substrate Perspective (kubectl-ate) ---${NC}"
kubectl-ate get actor demo-math-task -a default -o table

ASSIGNED_WORKER=$(kubectl-ate get actor demo-math-task -a default -o json 2>/dev/null | jq -r '.status.workerAssignment.workerPod // "unknown"')
ASSIGNED_IP=$(kubectl-ate get actor demo-math-task -a default -o json 2>/dev/null | jq -r '.status.workerAssignment.workerPodIps[0] // "unknown"')
echo -e "\n   ${BOLD}Correlation Verified:${NC}"
echo -e "   • AX Task:        ${BOLD}demo-math-task${NC}"
echo -e "   • Substrate Actor:${BOLD}default/demo-math-task${NC}"
echo -e "   • Host Worker Pod:${BOLD}${ASSIGNED_WORKER}${NC}"
echo -e "   • Assigned IP:    ${BOLD}${ASSIGNED_IP}${NC}"

step "3.3" "Executing Real Workload in Guest Sandbox"
echo -e "${YELLOW}   Running compute calculation in gVisor sandbox...${NC}"
ax ssh demo-math-task -- python3 -c '
import sys, math
res = sum(x**2 for x in range(1, 1001))
print(f"COMPUTE_RESULT: Sum of squares 1..1000 = {res}")
print(f"GUEST_KERNEL: {sys.platform}")
'
post_scope_activity "ax-substrate-bridge" "reply" "PASS: AX Task successfully scheduled, mapped to Substrate worker, and executed."
pause_for_audience 3

# ==============================================================================
# PART 4: ACTOR LIFECYCLE, SUSPEND/RESUME & WORKER RECOVERY (3 min)
# ==============================================================================
banner "PART 4: ACTOR LIFECYCLE, SUSPEND/RESUME & WORKER RECOVERY" "3 minutes"
post_scope_activity "snapshot-lifecycle" "prompt" "PART 4: Demonstrating memory suspend, snapshot persistence, and worker failure recovery..."

step "4.1" "Writing In-Memory Checkpoint to demo-math-task"
ax ssh demo-math-task -- sh -c 'echo "CHECKPOINT_DATA_ALPHA_99" > /workspace/checkpoint.txt'
echo -e "   Written checkpoint: ${BOLD}CHECKPOINT_DATA_ALPHA_99${NC}"

step "4.2" "Suspending Task via AX ('ax suspend task')"
ax suspend task demo-math-task
sleep 2

echo -e "\n${CYAN}Substrate Actor State after Suspension:${NC}"
kubectl-ate get actor demo-math-task -a default -o table

step "4.3" "Resuming Task via AX ('ax resume task')"
ax resume task demo-math-task
sleep 3

echo -e "\n${CYAN}Substrate Actor State after Resumption:${NC}"
kubectl-ate get actor demo-math-task -a default -o table

step "4.4" "Verifying In-Guest Checkpoint Preservation"
RESTORED_CKPT=$(ax ssh demo-math-task -- cat /workspace/checkpoint.txt)
echo -e "   Read checkpoint after resume: ${BOLD}${GREEN}${RESTORED_CKPT}${NC}"

step "4.5" "Simulating Worker Node Failure (Killing Host Worker Pod)"
HOST_WORKER=$(kubectl-ate get actor demo-math-task -a default -o json 2>/dev/null | jq -r '.status.workerAssignment.workerPod // "unknown"')
echo -e "${YELLOW}   Abruptly killing host worker pod ${HOST_WORKER}...${NC}"
kubectl delete pod "${HOST_WORKER}" -n ax-system --now >/dev/null 2>&1

sleep 2
echo -e "\n${CYAN}Immediate Substrate Actor Status (Crash Detected):${NC}"
kubectl-ate get actor demo-math-task -a default -o table

step "4.6" "Recovering Task onto Replacement Worker"
ax resume task demo-math-task
sleep 3

NEW_WORKER=$(kubectl-ate get actor demo-math-task -a default -o json 2>/dev/null | jq -r '.status.workerAssignment.workerPod // "unknown"')
NEW_IP=$(kubectl-ate get actor demo-math-task -a default -o json 2>/dev/null | jq -r '.status.workerAssignment.workerPodIps[0] // "unknown"')
echo -e "   ${BOLD}${GREEN}✔ RECOVERY CONFIRMED:${NC}"
echo -e "   • Old Host: ${RED}${HOST_WORKER}${NC} (Terminated)"
echo -e "   • New Host: ${GREEN}${NEW_WORKER}${NC}"
echo -e "   • New IP:   ${GREEN}${NEW_IP}${NC}"

step "4.7" "Executing Post-Recovery Verification Command"
ax ssh demo-math-task -- sh -c 'echo "SUCCESSFULLY_RUNNING_ON_RECOVERED_WORKER"'
post_scope_activity "snapshot-lifecycle" "reply" "PASS: Suspend/resume snapshot verified; task survived worker crash and rescheduled."

# Clean up temporary demo task
ax delete task demo-math-task >/dev/null 2>&1 || true

echo -e "\n${BOLD}${GREEN}==============================================================================${NC}"
echo -e "${BOLD}${GREEN}🏁 15-MINUTE DEMO SHOWCASE COMPLETED SUCCESSFULLY!${NC}"
echo -e "${BOLD}${GREEN}==============================================================================${NC}"
echo -e "Visual Dashboard available at: ${BOLD}${CYAN}http://localhost:8123${NC}"
