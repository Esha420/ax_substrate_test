# AX Platform Verification Test Specifications

This document defines the formal verification test cases for **Google AX (Agent Executor)** based on the latest clean checkout of `main` (`4b7bf6f`). All tests are executed externally without modifying the `ax` repository.

---

## Matrix of Claims

| Test ID | Feature / Claim | Verification Type | Target Component | Expected Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **TC-AX-01** | Migration from Redis to PostgreSQL with leased locks | Architecture & Schema Contract | `internal/store/postgres` | PASS |
| **TC-AX-02** | Direct observation of Substrate Actor state | Runtime Unit & API Contract | `internal/server` | PASS |
| **TC-AX-03** | Elimination of ambient credentials (`GEMINI_API_KEY`) | Security & Isolation Contract | `internal/workspace`, `internal/controller` | PASS |
| **TC-AX-04** | Deprecation/Removal of `WatchTask` and `ax watch` | API & CLI Contract | `pkg/apis/v1alpha1`, `cmd/ax` | PASS |
| **TC-AX-05** | Removal of Gateway CRD in favor of Substrate egress | Architecture & CRD Cleanliness | `pkg/apis/v1alpha1`, `deploy/` | PASS |
| **TC-AX-06** | Interactive SSH terminal with stdin and Ctrl-C forwarding | CLI Execution Contract | `cmd/ax` | PASS |
| **TC-AX-07** | Task runner unknown field tolerance & workspace limits | Runtime Compatibility | `runner/`, `pkg/apis/v1alpha1` | PASS |

---

## Detailed Test Specifications

### TC-AX-01: Migration from Redis to PostgreSQL
* **Claim**: AX replaced Redis-based task storage and distributed locking with PostgreSQL (`pgx`), storing resources as JSONB documents and using leased locks.
* **Prerequisites**: Access to `ax/internal/store/`.
* **Test Procedure**:
  1. Verify total absence of `internal/store/redis/` and `deploy/redis.yaml`.
  2. Inspect `internal/store/postgres/schema.sql` for table definitions: `tasks`, `workspaces`, `models`, and `locks`.
  3. Verify JSONB document columns (`spec`, `metadata`, `status`) and lock lease columns (`lease_id`, `expires_at`).
  4. Verify that `internal/store/postgres/store_test.go` exercises schema creation, newest-first task ordering, and lease renewal/takeover.
* **Expected Result**: Clean PostgreSQL store implementation; zero residual Redis dependencies in `internal/store`.

---

### TC-AX-02: Direct Observation of Substrate Actor State
* **Claim**: AX no longer caches or replicates live actor status in its store. Live actor phase, worker IP, and `Ready` conditions are retrieved live from Substrate.
* **Prerequisites**: Go 1.22+ toolchain.
* **Test Procedure**:
  1. Execute `go test -v ./internal/server/ -run "TestSetActorStatus|TestServer_ReadsActorStateFromSubstrate|TestTasksGoThroughHelpers"`.
  2. Verify that `getTask` calls `client.GetActor` and derives condition reasons directly from actor state.
  3. Verify that when Substrate is temporarily unavailable, AX reports phase `Unknown` rather than fabricating task failure.
* **Expected Result**: Tests pass with 0 failures; actor status dynamically mapped from Substrate `ActorState`.

---

### TC-AX-03: Ambient Credential Elimination
* **Claim**: Neither `GEMINI_API_KEY` nor goal-based bootstrap scripts (`antigravity_bootstrap.py`) are injected into agent task sandboxes.
* **Prerequisites**: AST and file tree analysis of `ax/`.
* **Test Procedure**:
  1. Check for absence of `cmd/ax-task-runner/antigravity_bootstrap.py`.
  2. Verify `pkg/apis/v1alpha1/ax.proto` contains no `goal` field in `WorkspaceRef`.
  3. Scan `internal/controller/reconciler.go` to ensure `lookupGeminiKey` and secret copying are deleted.
  4. Verify the server-side Model client retains its own credentials without forwarding them to the task environment.
* **Expected Result**: No credential injection logic remains in task reconciler.

---

### TC-AX-04: Task Observation API Simplification
* **Claim**: The streaming `WatchTask` RPC and `ax watch` CLI command were removed in favor of polling `GetTask` (`ax describe task`).
* **Prerequisites**: Protobuf and CLI code inspection.
* **Test Procedure**:
  1. Inspect `pkg/apis/v1alpha1/ax.proto` to verify `WatchTask` RPC is absent.
  2. Inspect `cmd/ax/main.go` to confirm the `watch` subcommand is removed.
  3. Verify `ax describe task` is the documented inspection path.
* **Expected Result**: No `WatchTask` definition in proto; CLI cleanly lacks `watch` command.

---

### TC-AX-05: Removal of Gateway CRD
* **Claim**: AX removed its redundant Gateway concept to prevent split-brain networking with Substrate's `atenet-router` and `atenet-egress`.
* **Prerequisites**: Git commit history and manifest check.
* **Test Procedure**:
  1. Verify commit `0b5427c` ("Remove Gateway concept to avoid bifurcation with Substrate").
  2. Verify no `Gateway` protobuf message exists in `pkg/apis/v1alpha1/`.
* **Expected Result**: Zero references to AX Gateway CRD.

---

### TC-AX-06: Interactive SSH Signal Passthrough
* **Claim**: `ax ssh` forwards standard input and propagates Ctrl-C (`SIGINT`) to the running container process.
* **Prerequisites**: Code inspection of `cmd/ax/main.go`.
* **Test Procedure**:
  1. Inspect `ax ssh` implementation in `cmd/ax/main.go`.
  2. Verify SPDY stream setup for stdin forwarding and signal trapping.
* **Expected Result**: Terminal raw mode and signal handling confirmed.
