# AX & Agent Substrate Verification & Showcase Workspace

This directory is an **independent, external verification workspace** built alongside the clean clones of **Google AX** and **Agent Substrate**.

> **Design Principle**: `ax/` and `substrate/` remain 100% untouched and read-only. All test cases, harnesses, evidence collectors, and visualization bridges reside strictly inside this workspace.

---

## Directory Structure

```
ax-substrate-verification/
├── README.md                          # Workspace documentation
├── test-cases/                        # Formal test specifications
│   ├── ax-verification.md             # TC-AX-01 to TC-AX-07 specifications
│   └── substrate-verification.md      # TC-SUB-01 to TC-SUB-07 specifications
├── tests/                             # External test runners & harnesses
│   ├── run_all_tests.py               # Master test runner & report compiler
│   ├── test_ax_claims.py              # AX claim verification tests
│   ├── test_substrate_claims.py       # Substrate claim verification tests
│   └── test_snapshot_lineage_safety.py# Snapshot lineage & tag safety tests
├── evidence/                          # Captured test outputs & execution logs
│   ├── ax/                            # Logs and proofs for AX claims
│   ├── substrate/                     # Logs and proofs for Substrate claims
│   ├── scope/                         # Substrate Scope server logs
│   └── summary.json                   # Machine-readable test summary
├── reports/                           # Generated audit reports
│   └── VERIFICATION_REPORT.md         # Full verified technical report
└── showcase/                          # Live showcase launcher & visualization bridge
    ├── start_showcase.sh              # One-command showcase launcher
    └── scope_bridge.mjs               # Real-time event bridge to Substrate Scope
```

---

## Running the Verification Suite

To run all 15 test cases independently:
```bash
python3 /home/berrybytes/Office/Assignment/ax-substrate-verification/tests/run_all_tests.py
```

## Running the Live Showcase with Substrate Scope

To run the verification suite and showcase the real-time lifecycle on the **Substrate Scope** visualizer:
```bash
/home/berrybytes/Office/Assignment/ax-substrate-verification/showcase/start_showcase.sh
```
Open **`http://localhost:8123`** in your browser to view:
* **WorkerPool Bays**: gVisor sandbox slots and active test agents.
* **Restore Queue**: Waiting and queued borrow sessions.
* **Object Storage Shelf**: Snapshots and tag lineage.
* **Activity Drawer**: Live prompt, reply, error, and verification event stream.
