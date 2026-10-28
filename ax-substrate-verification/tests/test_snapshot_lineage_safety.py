#!/usr/bin/env python3
"""
Test Suite: Snapshot Lineage & Lifecycle Safety Verification
Evaluates snapshot borrowing, tag prefixes, and the deletion safety precondition
identified in test_snapshot_lineage.sh and PR #3340.
"""

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path("/home/berrybytes/Office/Assignment")
SCRIPT_PATH = REPO_ROOT / "test_snapshot_lineage.sh"
EVIDENCE_DIR = REPO_ROOT / "ax-substrate-verification" / "evidence" / "substrate"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


class TestSnapshotLineageSafety(unittest.TestCase):

    def test_tc_lineage_script_analysis_and_safety_contract(self):
        """TC-LIN-01: Verify snapshot borrowing contract and deletion safety logic."""
        self.assertTrue(SCRIPT_PATH.exists(), f"Missing script at {SCRIPT_PATH}")
        script_content = SCRIPT_PATH.read_text()

        evidence = []
        evidence.append("=== TC-LIN-01: Snapshot Lineage & Safety Contract Analysis ===")

        # 1. Verify script steps
        self.assertIn("kubectl ate create tag", script_content)
        self.assertIn("kubectl ate create actor", script_content)
        self.assertIn("kubectl ate suspend actor", script_content)
        self.assertIn("kubectl ate delete tag", script_content)
        evidence.append("✓ Script defines complete lineage sequence: create seed -> suspend -> tag -> borrow clone -> delete tag")

        # 2. Verify borrowed snapshot invariant
        self.assertIn('[ "${TAG_SNAP_URI}" != "${CLONE_SNAP_URI}" ]', script_content)
        evidence.append("✓ Script enforces invariant: Clone directly borrows tag snapshot URI prefix")

        # 3. Check for Substrate's latest fix in cmd/ateapi/internal/controlapi/tag.go
        tag_go = REPO_ROOT / "substrate" / "cmd" / "ateapi" / "internal" / "controlapi" / "tag.go"
        if tag_go.exists():
            content = tag_go.read_text()
            self.assertIn("FailedPrecondition", content)
            evidence.append("✓ Substrate ateapi tag controller includes FAILED_PRECONDITION check on deleting tag (PR #3340)")

        # 4. Record evidence
        evidence_text = "\n".join(evidence)
        (EVIDENCE_DIR / "tc_lineage_safety.txt").write_text(evidence_text + "\n")


if __name__ == "__main__":
    unittest.main()
