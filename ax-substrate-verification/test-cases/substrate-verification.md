# Agent Substrate Platform Verification Test Specifications

This document defines the formal verification test cases for **Agent Substrate** based on the latest clean checkout of `main` (`67c6a6b3`). All tests are executed externally without modifying the `substrate` repository.

---

## Matrix of Claims

| Test ID | Feature / Claim | Verification Type | Target Component | Expected Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **TC-SUB-01** | Worker-Level OOM Isolation via `memory.high` & `cgroup.kill` | Runtime Unit & Cgroup Watch | `cmd/ateworker-gvisor`, `internal/ateworker/cgroup` | PASS |
| **TC-SUB-02** | CNCF Onboarding and DCO Sign-off Governance | Governance & Commit Contract | `CONTRIBUTING.md`, Git History | PASS |
| **TC-SUB-03** | ECDSA P-256 Workload Identity Certificates | Crypto & PKI Contract | `cmd/ateapi`, `internal/ateworker/register` | PASS |
| **TC-SUB-04** | Strict SPIFFE mTLS Networking (port 443 replacing port 80) | Network & Security Contract | `cmd/benchmarking`, `manifests/` | PASS |
| **TC-SUB-05** | Non-Root Control-Plane Execution (UID 65532) | Kubernetes Manifest & Security | `manifests/ate-install/` | PASS |
| **TC-SUB-06** | Actor Operation Concurrency Guard (Mutex Lease) | Lifecycle & API Precondition | `cmd/ateapi/internal/controlapi` | PASS |
| **TC-SUB-07** | Snapshot Lineage Safety & Guarded Tag Deletion | Storage Lifecycle & Lineage | `cmd/ateapi`, `test_snapshot_lineage.sh` | PASS |

---

## Detailed Test Specifications

### TC-SUB-01: Worker-Level OOM Isolation
* **Claim**: A gVisor actor exceeding its memory limit is contained and terminated individually using `memory.high` pressure monitoring and `cgroup.kill`, preventing worker-wide out-of-memory crashes.
* **Prerequisites**: Go 1.22+ toolchain.
* **Test Procedure**:
  1. Inspect `cmd/ateworker-gvisor/memlimit.go` for `memory.high` configuration (replaces `memory.max`).
  2. Inspect `internal/ateworker/cgroup/memwatch.go` for pressure monitoring (`memory.pressure`) and stall threshold detection (> 25% stall over 2s).
  3. Execute `go test -v ./internal/ateworker/cgroup/... -run "TestMemoryWatch|TestCPUMax|TestOpenActorLeaf"`.
* **Expected Result**: Unit tests pass; cgroup memory watcher correctly flags stalled runaway actors for targeted termination without disrupting peer actors.

---

### TC-SUB-02: CNCF Onboarding and DCO Sign-off
* **Claim**: Contributor licensing moved from Google CLA to the CNCF Developer Certificate of Origin (DCO) sign-off process (`git commit -s`).
* **Prerequisites**: Repository inspection.
* **Test Procedure**:
  1. Inspect `CONTRIBUTING.md` for explicit DCO requirement and `-s` flag instructions.
  2. Verify recent commits on `origin/main` (e.g., `#3237`, `#3340`) include `Signed-off-by: Name <email>` trailers.
  3. Confirm removal of Google CLA verification requirements.
* **Expected Result**: DCO policy documented and strictly observed in commit history.

---

### TC-SUB-03: ECDSA P-256 Workload Identity Certificates
* **Claim**: Actor identity CA generation migrated from Ed25519 to ECDSA P-256 to ensure compatibility with enterprise relying parties and x509 validation stacks.
* **Prerequisites**: Source code analysis.
* **Test Procedure**:
  1. Inspect `cmd/ateapi/internal/controlapi/ca.go` and identity certificate generation logic.
  2. Verify ECDSA P-256 curve configuration (`elliptic.P256()`).
* **Expected Result**: Identity CA and actor leaf certificates generated using standard ECDSA P-256.

---

### TC-SUB-04: Strict SPIFFE mTLS Networking
* **Claim**: Plain HTTP on port 80 was eliminated across internal router paths in favor of SPIFFE mutual TLS on port 443.
* **Prerequisites**: Source and manifest inspection.
* **Test Procedure**:
  1. Inspect commit `1756c0f7` ("benchmarking: dial atenet-router over SPIFFE mTLS on port 443").
  2. Verify `atenet-router` configuration enforcing mTLS client certificates.
* **Expected Result**: Clear enforcement of mTLS port 443; port 80 HTTP paths retired.

---

### TC-SUB-05: Non-Root Control-Plane Execution
* **Claim**: Control-plane pods are explicitly configured with `runAsUser: 65532` and `runAsNonRoot: true`.
* **Prerequisites**: Kubernetes manifest inspection.
* **Test Procedure**:
  1. Inspect `manifests/ate-install/` deployment manifests.
  2. Confirm `securityContext` settings specify `runAsNonRoot: true` and `runAsUser: 65532`.
* **Expected Result**: All control plane manifests enforce non-root security context.

---

### TC-SUB-06: Actor Operation Concurrency Guard
* **Claim**: `UpdateActor` fails with status `Aborted` when another lifecycle operation (suspend/resume/revert) is already in progress on the actor.
* **Prerequisites**: Source inspection of `cmd/ateapi/internal/controlapi/actor.go`.
* **Test Procedure**:
  1. Inspect mutex lease handling in `UpdateActor`.
  2. Verify returning `codes.Aborted` upon lease contention.
* **Expected Result**: Explicit rejection of concurrent actor mutations.

---

### TC-SUB-07: Snapshot Lineage & Guarded Tag Deletion
* **Claim**: Tag deletion safety: mutating or deleting a tag returns `FAILED_PRECONDITION` when guarded, addressing unrecoverable state in borrowing actors.
* **Prerequisites**: Analysis of `test_snapshot_lineage.sh` and `cmd/ateapi/internal/controlapi/tag.go`.
* **Test Procedure**:
  1. Inspect commit `006b0af5` (`#3340`).
  2. Verify `UpdateTag` and tag deletion checks return `codes.FailedPrecondition` when tag is in deleting state.
* **Expected Result**: Guard logic prevents race conditions during tag snapshot deletion.
