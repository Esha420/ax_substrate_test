# AX & Agent Substrate: Verification Results Report

**Date**: 2026-10-30 04:28:43 UTC  
**Target AX Commit**: `7c0d85b7bde239aab049dad23ecdba86fca8a4be`  
**Target Substrate Commit**: `46b6ea90ca512c236e4e7487612cbde64c857292`  
**Test Suite Duration**: 1.34 seconds  
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
