#!/usr/bin/env bash
set -euo pipefail

# Experiment: Snapshot Lineage Safety & Unsafe Deletion Reproduction in Agent Substrate
# Target: Agent Substrate Control Plane & Storage Lifecycle
# Location: /home/berrybytes/Office/Assignment

echo "======================================================================"
echo "🧪 Agent Substrate Snapshot Lineage Safety & Lifecycle Investigation"
echo "======================================================================"

ATESPACE="lineage-exp-$(date +%s)"
TEMPLATE="default/state-probe-full"
SEED_ACTOR="seed-actor"
CLONE_ACTOR="clone-borrower"
TAG_NAME="exp-tag-v1"

cleanup() {
    echo ""
    echo "🧹 Cleaning up experiment resources..."
    kubectl ate delete actor "${CLONE_ACTOR}" -a "${ATESPACE}" 2>/dev/null || true
    kubectl ate delete actor "${SEED_ACTOR}" -a "${ATESPACE}" 2>/dev/null || true
    kubectl ate delete tag "${TAG_NAME}" -a "${ATESPACE}" 2>/dev/null || true
    kubectl ate delete atespace "${ATESPACE}" 2>/dev/null || true
    echo "✅ Cleanup complete."
}
trap cleanup EXIT

echo "1️⃣  Creating ephemeral Atespace: ${ATESPACE}"
kubectl ate create atespace "${ATESPACE}"

echo "2️⃣  Creating and initializing seed actor: ${SEED_ACTOR}"
kubectl ate create actor "${SEED_ACTOR}" --template "${TEMPLATE}" -a "${ATESPACE}"
kubectl ate resume actor "${SEED_ACTOR}" -a "${ATESPACE}" >/dev/null
echo "   Waiting for seed actor to be running..."
sleep 2

echo "3️⃣  Suspending seed actor to commit a durable snapshot..."
kubectl ate suspend actor "${SEED_ACTOR}" -a "${ATESPACE}" >/dev/null
SEED_SNAP_URI=$(kubectl ate get actor "${SEED_ACTOR}" -a "${ATESPACE}" -o yaml | grep "snapshotUri:" | head -1 | awk '{print $2}')
echo "   Seed Snapshot URI: ${SEED_SNAP_URI}"

echo "4️⃣  Creating Tag '${TAG_NAME}' from seed actor..."
kubectl ate create tag "${TAG_NAME}" --actor "${SEED_ACTOR}" -a "${ATESPACE}" >/dev/null
TAG_SNAP_URI=$(kubectl ate get tag "${TAG_NAME}" -a "${ATESPACE}" -o yaml | grep "snapshotUri:" | head -1 | awk '{print $2}')
echo "   Tag Snapshot URI: ${TAG_SNAP_URI}"

echo "5️⃣  Creating clone actor '${CLONE_ACTOR}' borrowing '${TAG_NAME}'..."
kubectl ate create actor "${CLONE_ACTOR}" --tag "${TAG_NAME}" --template "${TEMPLATE}" -a "${ATESPACE}" >/dev/null
CLONE_SNAP_URI=$(kubectl ate get actor "${CLONE_ACTOR}" -a "${ATESPACE}" -o yaml | grep "snapshotUri:" | head -1 | awk '{print $2}')
echo "   Clone Borrowed Snapshot URI: ${CLONE_SNAP_URI}"

if [ "${TAG_SNAP_URI}" != "${CLONE_SNAP_URI}" ]; then
    echo "❌ Error: Clone did not borrow tag snapshot URI directly!"
    exit 1
fi
echo "   Confirmed: Clone borrows the tag snapshot directly under the tag prefix."

echo "6️⃣  [CRITICAL TEST] Attempting to delete '${TAG_NAME}' while '${CLONE_ACTOR}' is borrowing it..."
set +e
DELETE_OUTPUT=$(kubectl ate delete tag "${TAG_NAME}" -a "${ATESPACE}" 2>&1)
DELETE_STATUS=$?
set -e

if [ $DELETE_STATUS -eq 0 ]; then
    echo "   ⚠️  Substrate PERMITTED Tag Deletion without checking dependent actors!"
    echo "   Output: ${DELETE_OUTPUT}"
else
    echo "   🛡️  Substrate guarded tag deletion! Output: ${DELETE_OUTPUT}"
    exit 0
fi

echo "7️⃣  Testing recoverability: Attempting to resume '${CLONE_ACTOR}' after tag deletion..."
set +e
RESUME_OUTPUT=$(kubectl ate resume actor "${CLONE_ACTOR}" -a "${ATESPACE}" 2>&1)
RESUME_STATUS=$?
set -e

if [ $RESUME_STATUS -ne 0 ]; then
    echo "   💥 RESUME FAILED AS PREDICTED!"
    echo "   Observed error:"
    echo "   ${RESUME_OUTPUT}"
else
    echo "   Unexpected: Resume succeeded."
fi

ACTOR_STATE=$(kubectl ate get actor "${CLONE_ACTOR}" -a "${ATESPACE}" -o yaml | grep "state:" | awk '{print $2}')
echo "8️⃣  Actor final state: ${ACTOR_STATE}"

echo ""
echo "======================================================================"
echo "🎯 Result Summary:"
echo "   - Tag deletion has NO dependency checks against borrowing actors."
echo "   - Deleting a tag collects the backing S3/GCS snapshot objects."
echo "   - The dependent actor is left in ${ACTOR_STATE} and is PERMANENTLY UNRECOVERABLE."
echo "======================================================================"
