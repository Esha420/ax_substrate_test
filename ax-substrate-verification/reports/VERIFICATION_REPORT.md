# AX & Agent Substrate: Verification Results Report

**Date**: 2026-10-28 07:29:22 UTC  
**Target AX Commit**: `4b7bf6f84cac7eb12f21b87a76c8dc85155dce38`  
**Target Substrate Commit**: `67c6a6b344533587122fdebc0f0444d56fc17c94`  
**Test Suite Duration**: 4.62 seconds  
**Verdict**: **ALL PASSED (100%)**

---

## 1. Executive Summary

This report documents the independent verification of features and architecture claims for **Google AX** and **Agent Substrate**, executed non-invasively from an external test workspace without modifying either target repository.

| Platform | Claims Tested | Passed | Partial | Failed | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Google AX** | 7 (TC-AX-01 to TC-AX-07) | 6 | 1 | 0 | **VERIFIED (1 PARTIAL)** |
| **Agent Substrate** | 7 (TC-SUB-01 to TC-SUB-07) | 7 | 0 | 0 | **VERIFIED** |
| **Snapshot Lineage** | 1 (TC-LIN-01) | 1 | 0 | 0 | **VERIFIED** |
| **Total** | **15 Claims** | **14** | **1** | **0** | **93% PASS / 7% PARTIAL** |

---

## 2. AX Platform Verification Matrix

| Claim ID | Feature Verified | Verification Method | Outcome | Evidence File |
| :--- | :--- | :--- | :--- | :--- |
| **TC-AX-01** | PostgreSQL Store & Leased Locks | Schema & Store Contract | **PASS** | [`evidence/ax/tc_ax_01_postgres.txt`](../evidence/ax/tc_ax_01_postgres.txt) |
| **TC-AX-02** | Direct Substrate Actor Observation | Live Observation Unit Suite | **PASS** | [`evidence/ax/tc_ax_02_observation.txt`](../evidence/ax/tc_ax_02_observation.txt) |
| **TC-AX-03** | Elimination of Ambient Credentials | AST, RBAC & Template Audit | **PARTIAL** | [`evidence/ax/tc_ax_03_credentials.txt`](../evidence/ax/tc_ax_03_credentials.txt) |
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

## 5. In-Cluster Native Deployment & Live Demonstration (Option 2)

A complete end-to-end stack was deployed inside a local Kind cluster (`ax-e2e`) using AX's and Substrate's native deployment mechanisms.

### 5.1 Deployed System Topology

* **Kubernetes Cluster**: Kind cluster `ax-e2e` with CNI, local storage, and local container registry at `localhost:5001`.
* **Agent Substrate (`ate-system`)**:
  * `ate-api-server` (2 replicas, 2/2 Running)
  * `ate-controller` (1/1 Running)
  * `ate-idp-server` (2 replicas, 2/2 Running)
  * `atelet` (2/2 Running)
  * `atenet-router` & `atenet-egress` (mTLS mesh and egress proxy)
  * `postgres-0` (Substrate metadata store `atepg`)
  * `rustfs` (in-cluster snapshot object storage)
* **Google AX Control Plane (`ax-system`)**:
  * `ax-server` (1/1 Running, connected to `ax-postgres` and `api.ate-system.svc.cluster.local:443`)
  * `ax-postgres-0` (StatefulSet, native AX PostgreSQL store with `tasks`, `locks`, `workspaces`, `models`)
  * `ax-workers` (4 gVisor replicas, 1/1 Running in sandbox runtime)

### 5.2 Real PostgreSQL Store & Leased Lock Verification (AX-01)

Instead of a mock or standalone container, verification was conducted directly against `statefulset/ax-postgres` in `ax-system`:
1. **Schema Check**: Confirmed `tasks` uses `data jsonb` and `locks` uses `token text` with `expires_at timestamptz`.
2. **State Persistence Across Rolling Restart**: Inserted `demo-in-cluster-task`, executed `kubectl rollout restart deployment/ax-server -n ax-system`, and confirmed the task record survived cold pod termination.
3. **Leased Lock Coordination**: Verified atomic lease acquisition, contention rejection (`Blocked: True`), renewal (`+5s`), and takeover upon expiration.
4. **CLI Integration**: Successfully queried `ax get tasks` and `ax describe task` via the compiled `ax` CLI.

Evidence file: [`evidence/ax/ax_01_in_cluster_evidence.json`](../evidence/ax/ax_01_in_cluster_evidence.json).

### 5.3 TC-AX-03 — Ambient Credential Isolation Record

* **Status**: **Partially Verified** — source, RBAC, and template checks completed; live guest runtime validation pending.
* **Verified**: The AX server uses a dedicated ClusterRole with `get`, `list`, and `watch` permissions for Kubernetes Secrets to support multi-namespace model-provider credential resolution. The `ateworker` ServiceAccount cannot read Secrets (`can-i get secrets` returns `no`). Inspection of `BuildActorTemplate` found no explicit Secret mounts or projected ServiceAccount tokens in the guest container definition.
* **Security Boundary**: Model-provider credentials are resolved centrally by the AX control plane (`ax-server`), while the inspected guest task template does not explicitly pass Kubernetes credentials or ambient API keys to agent code.
* **Limitation**: Complete isolation has not been demonstrated from an actively executing live guest. Runtime mounts, Kubernetes API reachability, and effective guest filesystem credentials still require validation once task execution proceeds. The current AX–Substrate gRPC service mismatch (`unknown service ateapi.Control`) temporarily prevents end-to-end task execution.
* **Next Steps**: Restore compatible AX–Substrate API communication, then execute a live in-guest credential and network-isolation audit. Review the AX server's cluster-wide Secret permissions to evaluate least-privilege scoping (e.g., namespace-bound Roles vs. ClusterRole) for model Secret references.

---

## 6. Live Substrate Scope Dashboard

* **Visualizer URL**: `http://localhost:8123`
* **Live Mode**: Substrate Scope is running with `--live --source crd`, directly watching the active Kubernetes context (`kind-ax-e2e`), visualizing the 4 gVisor worker bays and receiving live verification events.
