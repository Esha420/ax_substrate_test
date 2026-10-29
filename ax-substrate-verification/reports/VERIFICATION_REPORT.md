# AX & Agent Substrate: Verification Results Report

**Date**: 2026-10-29 05:04:50 UTC  
**Target AX Commit**: `8440ae689d3314954b4f9f91d5b1460bdf5d6120`  
**Target Substrate Commit**: `eaf0e85c7622d021d833c13e8f8911e2854f9794`  
**Test Suite Duration**: 0.56 seconds  
**Verdict**: **ALL PASSED (100%)**

---

## 1. Executive Summary

This report documents the independent verification of features and architecture claims for **Google AX** and **Agent Substrate**, executed non-invasively from an external test workspace without modifying either target repository.

| Platform | Claims Tested | Passed | Failed | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Google AX** | 7 (TC-AX-01 to TC-AX-07) | 7 | 0 | **VERIFIED** |
| **Agent Substrate** | 7 (TC-SUB-01 to TC-SUB-07) | 7 | 0 | **VERIFIED** |
| **Snapshot Lineage** | 1 (TC-LIN-01) | 1 | 0 | **VERIFIED** |
| **Total** | **15 Claims** | **15** | **0** | **100% PASS** |

---

## 2. AX Platform Verification Matrix

| Claim ID | Feature Verified | Verification Method | Outcome | Evidence File |
| :--- | :--- | :--- | :--- | :--- |
| **TC-AX-01** | PostgreSQL Store & Leased Locks | Schema & Store Contract | **PASS** | [`evidence/ax/tc_ax_01_postgres.txt`](../evidence/ax/tc_ax_01_postgres.txt) |
| **TC-AX-02** | Direct Substrate Actor Observation | Live Observation Unit Suite | **PASS** | [`evidence/ax/tc_ax_02_observation.txt`](../evidence/ax/tc_ax_02_observation.txt) |
| **TC-AX-03** | Elimination of Ambient Credentials | AST & Reconciler Contract | **PASS** | [`evidence/ax/tc_ax_03_credentials.txt`](../evidence/ax/tc_ax_03_credentials.txt) |
| **TC-AX-04** | WatchTask RPC Removal | Proto & CLI Contract | **PASS** | [`evidence/ax/tc_ax_04_watch_removal.txt`](../evidence/ax/tc_ax_04_watch_removal.txt) |
| **TC-AX-05** | Gateway CRD Removal | Proto & Commit History | **PASS** | [`evidence/ax/tc_ax_05_gateway.txt`](../evidence/ax/tc_ax_05_gateway.txt) |
| **TC-AX-06** | SSH Signal & Stdin Forwarding | CLI Source Contract | **PASS** | [`evidence/ax/tc_ax_06_ssh.txt`](../evidence/ax/tc_ax_06_ssh.txt) |
| **TC-AX-07** | Single Workspace & Runner Tolerance | Unit Suite & API Contract | **PASS** | [`evidence/ax/tc_ax_07_workspace_runner.txt`](../evidence/ax/tc_ax_07_workspace_runner.txt) |

---

## 3. Agent Substrate Verification Matrix

| Claim ID | Feature Verified | Verification Method | Outcome | Evidence File |
| :--- | :--- | :--- | :--- | :--- |
| **TC-SUB-01** | Worker-Level OOM Isolation | Cgroup Pressure & Unit Suite | **PASS** | [`evidence/substrate/tc_sub_01_oom.txt`](../evidence/substrate/tc_sub_01_oom.txt) |
| **TC-SUB-02** | CNCF DCO Sign-off Governance | Contributing Policy & Commits | **PASS** | [`evidence/substrate/tc_sub_02_dco.txt`](../evidence/substrate/tc_sub_02_dco.txt) |
| **TC-SUB-03** | ECDSA P-256 Workload Identity | Crypto & CA Generation | **PASS** | [`evidence/substrate/tc_sub_03_ecdsa.txt`](../evidence/substrate/tc_sub_03_ecdsa.txt) |
| **TC-SUB-04** | Strict SPIFFE mTLS (Port 443) | Network Security Contract | **PASS** | [`evidence/substrate/tc_sub_04_mtls.txt`](../evidence/substrate/tc_sub_04_mtls.txt) |
| **TC-SUB-05** | Non-Root Control-Plane (UID 65532) | Manifest Security Context | **PASS** | [`evidence/substrate/tc_sub_05_non_root.txt`](../evidence/substrate/tc_sub_05_non_root.txt) |
| **TC-SUB-06** | Actor Mutex Concurrency Guard | Control API Preconditions | **PASS** | [`evidence/substrate/tc_sub_06_mutex.txt`](../evidence/substrate/tc_sub_06_mutex.txt) |
| **TC-SUB-07** | Tag Deletion Lifecycle Safety | ateapi Tag Controller Check | **PASS** | [`evidence/substrate/tc_sub_07_tag_safety.txt`](../evidence/substrate/tc_sub_07_tag_safety.txt) |

---

## 4. Key Architectural Discoveries

1. **Storage Decoupling**: AX has completely shed its Redis dependency. In `internal/store/postgres`, task specs and metadata are saved as JSONB, while actor runtime state (phase, worker IP, ready conditions) is queried directly from Substrate without state duplication.
2. **Credential Safety**: The in-sandbox bootstrap (`antigravity_bootstrap.py`) is completely gone, and `GEMINI_API_KEY` is never injected into task sandboxes. The server keeps credentials for itself when proxying model calls.
3. **Multi-Tenant Protection**: Substrate's `memory.high` throttling and active `cgroup.kill` watchdog contain runaway memory-exhaustion actors without killing the parent gVisor worker pod or peer tenants.
4. **Snapshot Lineage Precondition**: While initial implementations allowed tags to be deleted while child actors borrowed them, Substrate commit `006b0af5` (`#3340`) now guards deleting tags with `FAILED_PRECONDITION`.

---

## 5. Live In-Cluster Step 3 & Runtime Security Verification

Following alignment of the Agent Substrate control plane to `v0.6.0` (`d3f2363590a1`), end-to-end task execution and live guest runtime security scenarios were fully verified against the live Kind cluster `ax-e2e`.

### 5.1 Step 3: Golden Task Execution & Phase Tracking
* **Task Submitted**: [`scratch/task-golden.yaml`](../scratch/task-golden.yaml) with digest-pinned image `localhost:5001/ax-task-runner:e2e@sha256:765ac5457c08c58997dcad43db1f727a6d28516bb0dce764998723000036c187`.
* **Substrate gRPC Resolution**: `ax-server` successfully interfaced with Substrate's `ateapi.Control` without `Unimplemented` errors.
* **Phase Progression**:
  1. `apply`: Created with initial phase `Suspended` (template registered in Substrate).
  2. `resume`: Reconciled by `ax-server` into `Running` phase.
  3. `Ready Condition`: `Ready=True`, Reason=`TaskRunning`, `WorkspaceReady=True` on worker IP `10.244.0.41`.

### 5.2 TC-AX-07: Single Workspace & Runner Tolerance
* **Multi-Workspace Enforcement**: Submitting multi-workspace task specs is rejected at schema level (`unknown field "workspaces"`).
* **Unit Contract**: Verified `TestCreateTask_ValidatesWorkspaceBinding` passes (enforces $\le 1$ workspace).

### 5.3 TC-AX-03: Live In-Guest Ambient Credential Minimization
* **Guest Environment Audit**: Executed `ax ssh golden-task -- env`:
  * Zero ambient model API keys (`GEMINI_API_KEY` not found).
  * Zero root or admin tokens (`AX_ROOT_TOKEN`, `SUBSTRATE_ADMIN_KEY` not found).
  * Zero cloud credential variables (`AWS_SECRET_ACCESS_KEY`, `GOOGLE_APPLICATION_CREDENTIALS` not found).
* **Kubernetes SA Tokens**: Checked `/var/run/secrets`: `No such file or directory` (zero projected Kubernetes SA tokens in guest).
* **Network Isolation**: Probed `https://kubernetes.default.svc/api`: connection unreachable (`RC=6`), confirming host & API network isolation.

### 5.4 TC-AX-06: Interactive SSH Signal Passthrough & Stdin Forwarding
* **Sandbox Verification**: Executed `ax ssh golden-task -- uname -a`: confirmed `Linux actor 4.19.0-gvisor`.
* **Bidirectional Stdin Pipe**: Verified stdin stream echo via `printf ... | ax ssh golden-task -- cat` (`AX_LIVE_STDIN_FORWARDING_VERIFIED_2026`).

Evidence file: [`evidence/ax/live_step3_and_security_scenarios.json`](../evidence/ax/live_step3_and_security_scenarios.json).

---

---

## 7. Runtime Feature Verification & Failure Recovery Matrix

Executed live against the running KinD cluster `ax-e2e` via [`scripts/verify_runtime_features.py`](../scripts/verify_runtime_features.py):

| # | Runtime Feature | In-Cluster Test Executed | Verdict | Key Evidence & Telemetry |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **AX State Persistence & Recovery** | Marker written in guest $\rightarrow$ `ax-server` rollout restart $\rightarrow$ task reloaded from PostgreSQL $\rightarrow$ continued execution | **PASS** | [`evidence/ax/runtime_features_verification.json`](../evidence/ax/runtime_features_verification.json) |
| **2** | **AX-to-Substrate Task Execution** | `e2e-feature-task` applied $\rightarrow$ Substrate actor created $\rightarrow$ assigned to worker $\rightarrow$ computation executed in sandbox | **PASS** | gRPC boundary resolved (`ateapi.Control` vs `substrate.ateapi.v1.Control`) |
| **3** | **Worker Failure & Task Recovery** | Host worker pod killed abruptly $\rightarrow$ Substrate detected `ACTOR_STATE_CRASHED` $\rightarrow$ AX flagged `Failed` $\rightarrow$ recovered onto new worker | **PASS** | State recovered on new worker; non-snapshotted volatile disk safely discarded |
| **4** | **Runtime Isolation & Authorization** | Process table (PID virtualization), cross-task workspace denial, CoreDNS blocked, unauthenticated K8s API denied | **PASS** | `RC!=0` on cross-workspace cat, gaierror on cluster DNS, URLError on K8s API |
| **5** | **Suspend, Snapshot & Resume** | State written in guest $\rightarrow$ `ax suspend task` $\rightarrow$ durable snapshot registered $\rightarrow$ `ax resume task` $\rightarrow$ state verified | **PASS** | Checkpoint data intact across suspend/resume lifecycle |
| **6** | **Observability & Scope Dashboard** | Jaeger tracing, Prometheus scraping, and Substrate Scope live dashboard | **PASS** | 9 services in Jaeger, Prometheus targets active, Scope live on `:8123` |

---

## 8. Manual Reproduction Commands Cheatsheet

### 1. AX State Persistence & Server Restart
```bash
export KUBECONFIG="/home/esha/Office/research/ax/.tmp/kubeconfig-ax-e2e"
export AX_BIN="/home/esha/Office/research/ax/.tmp/bin/ax"

# Write marker inside guest
$AX_BIN ssh golden-task -- sh -c "echo 'PERSIST_TEST' > /workspace/persist.txt"

# Restart AX Server deployment
kubectl rollout restart deployment/ax-server -n ax-system
kubectl rollout status deployment/ax-server -n ax-system

# Verify persistence and continued execution
$AX_BIN tunnel stop
$AX_BIN get tasks
$AX_BIN ssh golden-task -- cat /workspace/persist.txt
```

### 2. AX-to-Substrate End-to-End Task Execution
```bash
# Apply a real task spec
$AX_BIN apply -f /home/esha/Office/research/ax_substrate_test/ax-substrate-verification/scratch/task-golden.yaml

# Resume execution onto Substrate worker
$AX_BIN resume task golden-task

# Check Substrate actor assignment
kubectl-ate get actors -a default

# Run command inside container
$AX_BIN ssh golden-task -- python3 -c "print('EXEC_SUCCESS')"
```

### 3. Worker Failure & Recovery
```bash
# Check hosting worker pod
kubectl-ate get actor e2e-feature-task -a default -o yaml | grep workerPod

# Abruptly kill the worker pod
kubectl delete pod <worker-pod-name> -n ax-system --now

# Observe failure detection in Substrate & AX
kubectl-ate get actors -a default
$AX_BIN describe task e2e-feature-task

# Recover actor onto surviving / replacement worker
$AX_BIN resume task e2e-feature-task
$AX_BIN describe task e2e-feature-task
$AX_BIN ssh e2e-feature-task -- uname -a
```

### 4. Runtime Isolation & Security
```bash
# Process isolation (only PID 1 and current command)
$AX_BIN ssh golden-task -- ps aux

# Task-to-task workspace isolation
$AX_BIN ssh golden-task -- sh -c "echo 'SECRET' > /workspace/secret.txt"
$AX_BIN ssh e2e-feature-task -- cat /workspace/secret.txt  # Returns No such file

# Network control plane isolation
$AX_BIN ssh golden-task -- python3 -c "import socket; socket.getaddrinfo('kubernetes.default.svc', 443)" # gaierror
```

### 5. Suspend, Snapshot & Resume
```bash
# Write persistent checkpoint
$AX_BIN ssh golden-task -- sh -c "echo 'CHECKPOINT_V1' > /workspace/ckpt.dat"

# Suspend task
$AX_BIN suspend task golden-task
kubectl-ate get actor golden-task -a default -o yaml | grep -E 'state:|snapshotUri:'

# Resume task and confirm state
$AX_BIN resume task golden-task
$AX_BIN ssh golden-task -- cat /workspace/ckpt.dat
```

### 6. Observability & Substrate Scope
```bash
# Ensure port-forwards for Jaeger and Prometheus
kubectl port-forward -n otel-system svc/jaeger 16686:16686 &
kubectl port-forward -n otel-system svc/prometheus 9090:9090 &

# Start Substrate Scope Visualizer
cd /home/esha/Office/research/substrate-scope
node server.mjs --live --source crd &

# View interfaces in browser
# - Substrate Scope:  http://localhost:8123
# - Jaeger Tracing:   http://localhost:16686
# - Prometheus:       http://localhost:9090
```


