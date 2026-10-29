#!/usr/bin/env bash
set -euo pipefail

# Showcase Launcher: AX & Agent Substrate Verification + Scope Visualization
RESEARCH_ROOT="${RESEARCH_ROOT:-/home/esha/Office/research}"
VERIF_DIR="${RESEARCH_ROOT}/ax-substrate-verification"
SCOPE_DIR="${RESEARCH_ROOT}/substrate-scope"

echo "======================================================================"
echo "🎯 AX & Agent Substrate Verification & Live Showcase"
echo "======================================================================"

echo ""
echo "Step 1: Running External Verification Test Suite..."
python3 "${VERIF_DIR}/tests/run_all_tests.py"

echo ""
echo "Step 2: Starting Substrate Scope Visualizer (Port 8123)..."
if ! lsof -i :8123 >/dev/null 2>&1; then
    (cd "${SCOPE_DIR}" && nohup node server.mjs > "${VERIF_DIR}/evidence/scope/scope.log" 2>&1 &)
    sleep 2
    echo "   Substrate Scope daemon running on http://localhost:8123"
else
    echo "   Substrate Scope is already running on port 8123."
fi

echo ""
echo "Step 3: Streaming Verification Lifecycle to Substrate Scope..."
node "${VERIF_DIR}/showcase/scope_bridge.mjs"

echo ""
echo "======================================================================"
echo "✨ SHOWCASE READY!"
echo "   - Web Dashboard:     http://localhost:8123"
echo "   - Full Report:       ${VERIF_DIR}/reports/VERIFICATION_REPORT.md"
echo "   - Test Evidence:     ${VERIF_DIR}/evidence/"
echo "======================================================================"
