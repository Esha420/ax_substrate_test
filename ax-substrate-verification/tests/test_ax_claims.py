#!/usr/bin/env python3
"""
Test Suite: AX Platform Claims Verification
Tests Google AX repository state, schema, security contracts, and runtime tests
from an external, non-invasive test harness.
"""

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(os.environ.get("RESEARCH_ROOT", "/home/esha/Office/research"))
AX_DIR = REPO_ROOT / "ax"
EVIDENCE_DIR = REPO_ROOT / "ax-substrate-verification" / "evidence" / "ax"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


class TestAXPlatform(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        assert AX_DIR.exists(), f"AX directory not found at {AX_DIR}"
        # Record commit
        rev = subprocess.check_output(["git", "-C", str(AX_DIR), "rev-parse", "HEAD"]).decode().strip()
        (EVIDENCE_DIR / "commit.txt").write_text(f"AX Commit: {rev}\n")

    def test_tc_ax_01_postgres_store_and_redis_removal(self):
        """TC-AX-01: Verify PostgreSQL store migration and total Redis store deletion."""
        evidence = []
        evidence.append("=== TC-AX-01: PostgreSQL Migration Verification ===")

        # 1. Verify Redis store directory is completely deleted
        redis_store = AX_DIR / "internal" / "store" / "redis"
        self.assertFalse(redis_store.exists(), "internal/store/redis must not exist")
        evidence.append("✓ internal/store/redis/ is completely removed")

        # 2. Verify Postgres store exists with required files
        pg_store = AX_DIR / "internal" / "store" / "postgres"
        self.assertTrue(pg_store.exists(), "internal/store/postgres must exist")
        required_files = ["store.go", "schema.sql", "schema.go", "lock.go", "store_test.go"]
        for f in required_files:
            p = pg_store / f
            self.assertTrue(p.exists(), f"Missing {f} in postgres store")
            evidence.append(f"✓ Found postgres store file: {f}")

        # 3. Verify schema.sql table definitions and JSONB columns
        schema_sql = (pg_store / "schema.sql").read_text()
        self.assertIn("CREATE TABLE IF NOT EXISTS tasks", schema_sql)
        self.assertIn("data     jsonb       NOT NULL", schema_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS locks", schema_sql)
        self.assertIn("token      text        NOT NULL", schema_sql)
        self.assertIn("expires_at timestamptz NOT NULL", schema_sql)
        evidence.append("✓ schema.sql defines tasks with jsonb and locks with leased expires_at")

        # 4. Verify Go postgres store uses pgxpool and protojson
        store_go = (pg_store / "store.go").read_text()
        self.assertIn("github.com/jackc/pgx/v5", store_go)
        self.assertIn("protojson", store_go)
        evidence.append("✓ store.go uses pgx/v5 and protojson serialization")

        # Write evidence
        (EVIDENCE_DIR / "tc_ax_01_postgres.txt").write_text("\n".join(evidence) + "\n")

    def test_tc_ax_02_direct_substrate_observation_runtime(self):
        """TC-AX-02: Verify direct Substrate actor observation and runtime unit tests."""
        evidence = []
        evidence.append("=== TC-AX-02: Direct Substrate Actor Observation ===")

        # 1. Run server actor observation unit tests
        cmd = [
            "go", "test", "-v", "./internal/server/",
            "-run", "TestSetActorStatus|TestServer_ReadsActorStateFromSubstrate|TestTasksGoThroughHelpers"
        ]
        res = subprocess.run(cmd, cwd=AX_DIR, capture_output=True, text=True)
        evidence.append("Command: " + " ".join(cmd))
        evidence.append(f"Exit Code: {res.returncode}")
        evidence.append(res.stdout)
        if res.stderr:
            evidence.append("STDERR:\n" + res.stderr)

        self.assertEqual(res.returncode, 0, "Server actor observation tests must pass")
        self.assertIn("PASS: TestSetActorStatus", res.stdout)
        self.assertIn("PASS: TestServer_ReadsActorStateFromSubstrate", res.stdout)
        self.assertIn("PASS: TestTasksGoThroughHelpers", res.stdout)
        evidence.append("✓ Server direct Substrate observation tests passed")

        # 2. Inspect server.go to ensure actor status is queried directly
        server_go = (AX_DIR / "internal" / "server" / "server.go").read_text()
        self.assertIn("s.substrate.GetActor", server_go)
        evidence.append("✓ server.go directly calls Substrate GetActor on retrieval")

        (EVIDENCE_DIR / "tc_ax_02_observation.txt").write_text("\n".join(evidence) + "\n")

    def test_tc_ax_03_credential_isolation(self):
        """TC-AX-03: Verify removal of GEMINI_API_KEY injection and bootstrap script."""
        evidence = []
        evidence.append("=== TC-AX-03: Ambient Credential Isolation ===")

        # 1. Verify antigravity_bootstrap.py is deleted
        bootstrap_file = AX_DIR / "cmd" / "ax-task-runner" / "antigravity_bootstrap.py"
        self.assertFalse(bootstrap_file.exists(), "antigravity_bootstrap.py must be deleted")
        evidence.append("✓ cmd/ax-task-runner/antigravity_bootstrap.py deleted")

        # 2. Verify proto does not have WorkspaceRef goal field
        proto_file = (AX_DIR / "pkg" / "apis" / "v1alpha1" / "ax.proto").read_text()
        self.assertNotIn("string goal", proto_file)
        evidence.append("✓ WorkspaceRef in ax.proto has no 'goal' field")

        # 3. Verify reconciler does not copy GEMINI_API_KEY into task sandbox
        reconciler_go = (AX_DIR / "internal" / "controller" / "reconciler.go").read_text()
        self.assertNotIn("lookupGeminiKey", reconciler_go)
        self.assertNotIn("gemini-api-secret", reconciler_go)
        evidence.append("✓ internal/controller/reconciler.go does not inject GEMINI_API_KEY into task sandbox")

        (EVIDENCE_DIR / "tc_ax_03_credentials.txt").write_text("\n".join(evidence) + "\n")

    def test_tc_ax_04_watch_task_removal(self):
        """TC-AX-04: Verify WatchTask RPC and ax watch command removal."""
        evidence = []
        evidence.append("=== TC-AX-04: WatchTask Removal & Polling Standardization ===")

        # 1. Verify ax.proto does not have WatchTask RPC
        proto_file = (AX_DIR / "pkg" / "apis" / "v1alpha1" / "ax.proto").read_text()
        self.assertNotIn("rpc WatchTask", proto_file)
        self.assertNotIn("message WatchTaskRequest", proto_file)
        evidence.append("✓ WatchTask RPC and request/response messages removed from ax.proto")

        # 2. Verify cmd/ax does not have 'watch' command
        main_go = (AX_DIR / "cmd" / "ax" / "main.go").read_text()
        self.assertNotIn("runWatch", main_go)
        evidence.append("✓ cmd/ax/main.go has no runWatch / watch subcommand")

        (EVIDENCE_DIR / "tc_ax_04_watch_removal.txt").write_text("\n".join(evidence) + "\n")

    def test_tc_ax_05_gateway_crd_removal(self):
        """TC-AX-05: Verify removal of redundant Gateway concept."""
        evidence = []
        evidence.append("=== TC-AX-05: Gateway CRD Removal ===")

        # 1. Verify no gateway proto message
        proto_file = (AX_DIR / "pkg" / "apis" / "v1alpha1" / "ax.proto").read_text()
        self.assertNotIn("message Gateway", proto_file)
        evidence.append("✓ No Gateway message defined in ax.proto")

        # 2. Verify git commit 0b5427c exists in history
        res = subprocess.run(
            ["git", "-C", str(AX_DIR), "log", "-n", "1", "0b5427c", "--oneline"],
            capture_output=True, text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Remove Gateway concept", res.stdout)
        evidence.append(f"✓ Commit 0b5427c verified: {res.stdout.strip()}")

        (EVIDENCE_DIR / "tc_ax_05_gateway.txt").write_text("\n".join(evidence) + "\n")

    def test_tc_ax_06_ssh_signals(self):
        """TC-AX-06: Verify ax ssh stdin and Ctrl-C signal forwarding."""
        evidence = []
        evidence.append("=== TC-AX-06: Interactive SSH Signal Passthrough ===")

        main_go = (AX_DIR / "cmd" / "ax" / "main.go").read_text()
        self.assertIn("ax ssh", main_go)
        # Check signal notification or raw mode terminal setup
        has_signal = "syscall.SIGINT" in main_go or "signal.Notify" in main_go or "term.MakeRaw" in main_go
        self.assertTrue(has_signal, "ax ssh must handle signals or terminal raw mode")
        evidence.append("✓ cmd/ax/main.go includes terminal/signal handling for ax ssh")

        (EVIDENCE_DIR / "tc_ax_06_ssh.txt").write_text("\n".join(evidence) + "\n")

    def test_tc_ax_07_workspace_binding_and_runner(self):
        """TC-AX-07: Verify single workspace limit and runner tolerance."""
        evidence = []
        evidence.append("=== TC-AX-07: Single Workspace & Runner Tolerance ===")

        # Run workspace validation test
        cmd = [
            "go", "test", "-v", "./internal/server/",
            "-run", "TestCreateTask_ValidatesWorkspaceBinding"
        ]
        res = subprocess.run(cmd, cwd=AX_DIR, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("PASS: TestCreateTask_ValidatesWorkspaceBinding", res.stdout)
        evidence.append("✓ TestCreateTask_ValidatesWorkspaceBinding passed (at most 1 workspace enforced)")

        # Verify runner tolerance test in runner package
        cmd2 = ["go", "test", "-v", "./runner/..."]
        res2 = subprocess.run(cmd2, cwd=AX_DIR, capture_output=True, text=True)
        self.assertEqual(res2.returncode, 0)
        evidence.append("✓ runner tests pass with unknown field tolerance")

        (EVIDENCE_DIR / "tc_ax_07_workspace_runner.txt").write_text("\n".join(evidence) + "\n")


if __name__ == "__main__":
    unittest.main()
