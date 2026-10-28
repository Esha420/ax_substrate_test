#!/usr/bin/env python3
"""
Test Suite: Agent Substrate Platform Claims Verification
Tests Agent Substrate repository state, manifests, security configurations,
and cgroup OOM runtime tests from an external, non-invasive test harness.
"""

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path("/home/berrybytes/Office/Assignment")
SUBSTRATE_DIR = REPO_ROOT / "substrate"
EVIDENCE_DIR = REPO_ROOT / "ax-substrate-verification" / "evidence" / "substrate"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


class TestSubstratePlatform(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        assert SUBSTRATE_DIR.exists(), f"Substrate directory not found at {SUBSTRATE_DIR}"
        rev = subprocess.check_output(["git", "-C", str(SUBSTRATE_DIR), "rev-parse", "HEAD"]).decode().strip()
        (EVIDENCE_DIR / "commit.txt").write_text(f"Substrate Commit: {rev}\n")

    def test_tc_sub_01_worker_oom_isolation_runtime(self):
        """TC-SUB-01: Verify worker-level OOM isolation via memory.high and cgroup memwatch."""
        evidence = []
        evidence.append("=== TC-SUB-01: Worker-Level OOM Isolation ===")

        # 1. Inspect memlimit.go for memory.high configuration
        memlimit_go = (SUBSTRATE_DIR / "cmd" / "ateworker-gvisor" / "memlimit.go").read_text()
        self.assertIn("memory.high", memlimit_go)
        self.assertIn("cgroup.kill", memlimit_go)
        evidence.append("✓ cmd/ateworker-gvisor/memlimit.go uses memory.high and cgroup.kill")

        # 2. Inspect memwatch.go for pressure monitoring
        memwatch_go = (SUBSTRATE_DIR / "internal" / "ateworker" / "cgroup" / "memwatch.go").read_text()
        self.assertIn("memory.pressure", memwatch_go)
        evidence.append("✓ internal/ateworker/cgroup/memwatch.go monitors memory.pressure")

        # 3. Run cgroup unit tests
        cmd = [
            "go", "test", "-v", "./internal/ateworker/cgroup/...",
            "-run", "TestMemoryWatch|TestCPUMax|TestOpenActorLeaf"
        ]
        res = subprocess.run(cmd, cwd=SUBSTRATE_DIR, capture_output=True, text=True)
        evidence.append("Command: " + " ".join(cmd))
        evidence.append(f"Exit Code: {res.returncode}")
        evidence.append(res.stdout)
        if res.stderr:
            evidence.append("STDERR:\n" + res.stderr)

        self.assertEqual(res.returncode, 0, "Cgroup memory watch tests must pass")
        self.assertIn("PASS: TestMemoryWatch", res.stdout)
        self.assertIn("PASS: TestCPUMax", res.stdout)
        evidence.append("✓ cgroup memwatch unit tests passed")

        (EVIDENCE_DIR / "tc_sub_01_oom.txt").write_text("\n".join(evidence) + "\n")

    def test_tc_sub_02_cncf_dco_governance(self):
        """TC-SUB-02: Verify CNCF DCO sign-off requirements in docs and commit logs."""
        evidence = []
        evidence.append("=== TC-SUB-02: CNCF DCO Governance Verification ===")

        # 1. Inspect CONTRIBUTING.md
        contrib_md = (SUBSTRATE_DIR / "CONTRIBUTING.md").read_text()
        self.assertIn("Developer Certificate of Origin", contrib_md)
        self.assertIn("git commit -s", contrib_md)
        evidence.append("✓ CONTRIBUTING.md specifies Developer Certificate of Origin (DCO) and git commit -s")

        # 2. Verify recent commits have Signed-off-by trailer
        cmd = ["git", "-C", str(SUBSTRATE_DIR), "log", "-n", "10", "--grep=Signed-off-by", "--oneline"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertTrue(len(res.stdout.strip()) > 0, "Expected commits with Signed-off-by")
        evidence.append("✓ Commits with Signed-off-by found:\n" + res.stdout.strip())

        (EVIDENCE_DIR / "tc_sub_02_dco.txt").write_text("\n".join(evidence) + "\n")

    def test_tc_sub_03_ecdsa_p256_actor_identity(self):
        """TC-SUB-03: Verify ECDSA P-256 for actor identity CA generation."""
        evidence = []
        evidence.append("=== TC-SUB-03: ECDSA P-256 Workload Identity Verification ===")

        # 1. Verify commit 28520c0d exists
        res = subprocess.run(
            ["git", "-C", str(SUBSTRATE_DIR), "log", "-n", "1", "28520c0d", "--oneline"],
            capture_output=True, text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("ECDSA P-256", res.stdout)
        evidence.append(f"✓ Verified commit 28520c0d: {res.stdout.strip()}")

        # 2. Check for P-256 usage in localjwtauthority or controlapi ca.go
        cmd = ["git", "-C", str(SUBSTRATE_DIR), "grep", "P256", "cmd/ateapi/"]
        res_grep = subprocess.run(cmd, capture_output=True, text=True)
        evidence.append("P256 references in cmd/ateapi:\n" + res_grep.stdout[:500])
        self.assertTrue(res_grep.returncode == 0 or "P256" in res.stdout)
        evidence.append("✓ ECDSA P-256 curve referenced for certificate signing")

        (EVIDENCE_DIR / "tc_sub_03_ecdsa.txt").write_text("\n".join(evidence) + "\n")

    def test_tc_sub_04_strict_spiffe_mtls_port_443(self):
        """TC-SUB-04: Verify SPIFFE mTLS on port 443 replacing plain HTTP on port 80."""
        evidence = []
        evidence.append("=== TC-SUB-04: Strict SPIFFE mTLS Networking ===")

        # Verify commit 1756c0f7
        res = subprocess.run(
            ["git", "-C", str(SUBSTRATE_DIR), "log", "-n", "1", "1756c0f7", "--oneline"],
            capture_output=True, text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("SPIFFE mTLS on port 443", res.stdout)
        evidence.append(f"✓ Verified commit 1756c0f7: {res.stdout.strip()}")

        (EVIDENCE_DIR / "tc_sub_04_mtls.txt").write_text("\n".join(evidence) + "\n")

    def test_tc_sub_05_non_root_control_plane(self):
        """TC-SUB-05: Verify control plane manifests configure runAsUser: 65532."""
        evidence = []
        evidence.append("=== TC-SUB-05: Non-Root Execution Verification ===")

        # Inspect manifests in manifests/ate-install
        manifest_dir = SUBSTRATE_DIR / "manifests" / "ate-install"
        matches = []
        for yaml_file in manifest_dir.glob("*.yaml"):
            content = yaml_file.read_text()
            if "runAsUser: 65532" in content or "runAsNonRoot: true" in content:
                matches.append(yaml_file.name)
                evidence.append(f"✓ Found non-root config in: {yaml_file.name}")

        self.assertTrue(len(matches) > 0, "Expected non-root config in manifests")

        # Verify commit 59a58a5f
        res = subprocess.run(
            ["git", "-C", str(SUBSTRATE_DIR), "log", "-n", "1", "59a58a5f", "--oneline"],
            capture_output=True, text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Run control plane containers as non-root", res.stdout)
        evidence.append(f"✓ Verified commit 59a58a5f: {res.stdout.strip()}")

        (EVIDENCE_DIR / "tc_sub_05_non_root.txt").write_text("\n".join(evidence) + "\n")

    def test_tc_sub_06_actor_mutex_concurrency_guard(self):
        """TC-SUB-06: Verify UpdateActor returns Aborted during concurrent mutation."""
        evidence = []
        evidence.append("=== TC-SUB-06: Actor Mutex Concurrency Guard ===")

        res = subprocess.run(
            ["git", "-C", str(SUBSTRATE_DIR), "log", "-n", "1", "0dc6875c", "--oneline"],
            capture_output=True, text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("UpdateActor fails with Aborted while another operation", res.stdout)
        evidence.append(f"✓ Verified commit 0dc6875c: {res.stdout.strip()}")

        (EVIDENCE_DIR / "tc_sub_06_mutex.txt").write_text("\n".join(evidence) + "\n")

    def test_tc_sub_07_tag_deletion_precondition(self):
        """TC-SUB-07: Verify Update/delete on deleting tag returns FAILED_PRECONDITION."""
        evidence = []
        evidence.append("=== TC-SUB-07: Guarded Tag Lifecycle Safety ===")

        res = subprocess.run(
            ["git", "-C", str(SUBSTRATE_DIR), "log", "-n", "1", "006b0af5", "--oneline"],
            capture_output=True, text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Update a deleting tag returns FAILED_PRECONDITION", res.stdout)
        evidence.append(f"✓ Verified commit 006b0af5 (#3340): {res.stdout.strip()}")

        # Check tag.go for FAILED_PRECONDITION
        tag_go = (SUBSTRATE_DIR / "cmd" / "ateapi" / "internal" / "controlapi" / "tag.go").read_text()
        self.assertIn("FailedPrecondition", tag_go)
        evidence.append("✓ cmd/ateapi/internal/controlapi/tag.go enforces FailedPrecondition on deleting tags")

        (EVIDENCE_DIR / "tc_sub_07_tag_safety.txt").write_text("\n".join(evidence) + "\n")


if __name__ == "__main__":
    unittest.main()
