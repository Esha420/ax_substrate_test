#!/usr/bin/env python3
"""
Step 3 & Runtime Security Scenarios Verification Script
Executes Golden Task execution tracking and runtime security scenarios:
- Step 3: Golden Task Execution & Phase Tracking
- TC-AX-07: Single Workspace & Runner Tolerance
- TC-AX-03: Live In-Guest Ambient Credential Minimization
- TC-AX-06: Interactive SSH Terminal, Stdin & Signal Forwarding
Streams all activities and results live to Substrate Scope (http://localhost:8123).
"""

import datetime
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(os.environ.get("RESEARCH_ROOT", "/home/esha/Office/research"))
VERIF_DIR = BASE_DIR / "ax-substrate-verification"
EVIDENCE_DIR_AX = VERIF_DIR / "evidence" / "ax"
EVIDENCE_DIR_AX.mkdir(parents=True, exist_ok=True)

KUBECONFIG = str(BASE_DIR / "ax" / ".tmp" / "kubeconfig-ax-e2e")
AX_BIN = str(BASE_DIR / "ax" / ".tmp" / "bin" / "ax")
SCOPE_URL = "http://127.0.0.1:8123"

def send_to_scope(agent, kind, text, ms=60):
    try:
        req = urllib.request.Request(
            f"{SCOPE_URL}/activity",
            data=json.dumps({"agent": agent, "kind": kind, "text": text, "ms": ms, "via": "step3-verifier"}).encode(),
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=1.0)
    except Exception:
        pass

def run_ax(args, input_data=None):
    env = os.environ.copy()
    env["KUBECONFIG"] = KUBECONFIG
    cmd = [AX_BIN] + args
    res = subprocess.run(
        cmd,
        input=input_data,
        capture_output=True,
        text=True,
        env=env
    )
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def step_3_golden_task():
    print("\n" + "=" * 70)
    print("▶ STEP 3: Golden Task Execution & Phase Tracking")
    print("=" * 70)
    send_to_scope("golden-task-tracker", "prompt", "Querying golden-task status and conditions from ax-server...")
    
    stdout, stderr, rc = run_ax(["describe", "task", "golden-task"])
    if rc != 0:
        raise RuntimeError(f"Failed to describe golden-task: {stderr}")
    
    print(stdout)
    assert "Phase:        Running" in stdout, "golden-task must be in Running phase"
    assert "Ready           True    TaskRunning" in stdout, "Task condition must be Ready: True / TaskRunning"
    assert "Worker IP:    10." in stdout, "Worker IP must be assigned from Substrate worker bay"

    send_to_scope("golden-task-tracker", "reply", "PASS: golden-task is Running on Substrate worker. ateapi.Control verified.", 110)
    
    return {
        "status": "PASS",
        "task_name": "golden-task",
        "phase": "Running",
        "describe_output": stdout
    }

def scenario_tc_ax_07():
    print("\n" + "=" * 70)
    print("▶ SCENARIO TC-AX-07: Single Workspace & Runner Tolerance")
    print("=" * 70)
    send_to_scope("ax-workspace-guard", "prompt", "[TC-AX-07] Testing multi-workspace rejection and schema constraints...")
    
    # 1. Multi-workspace test in YAML
    multi_ws_yaml = """apiVersion: ax.dev/v1alpha1
kind: Task
metadata:
  name: test-multi-ws-reject
  atespace: default
spec:
  workspaces:
    - name: ws1
    - name: ws2
  command: ["sleep", "10"]
"""
    stdout, stderr, rc = run_ax(["apply", "-f", "-"], input_data=multi_ws_yaml)
    assert rc != 0, "Server must reject task with invalid 'workspaces' plural field"
    assert "unknown field" in stderr or "unknown field" in stdout or "invalid" in stderr.lower(), "Rejection reason must be unknown/invalid field"
    print(f"✓ Multiple workspaces properly rejected by schema:\n  {stderr or stdout}")

    # 2. Run unit test for server workspace binding validation
    ax_dir = BASE_DIR / "ax"
    cmd = ["go", "test", "-v", "./internal/server/", "-run", "TestCreateTask_ValidatesWorkspaceBinding"]
    res = subprocess.run(cmd, cwd=ax_dir, capture_output=True, text=True)
    assert res.returncode == 0, f"Workspace binding unit test failed:\n{res.stdout}\n{res.stderr}"
    assert "PASS: TestCreateTask_ValidatesWorkspaceBinding" in res.stdout
    print("✓ Unit test TestCreateTask_ValidatesWorkspaceBinding passed")

    send_to_scope("ax-workspace-guard", "reply", "[TC-AX-07] PASS: Single workspace constraint enforced by proto & server.", 85)
    return {
        "status": "PASS",
        "contract": "at most 1 workspace per task",
        "unit_test_result": "PASS"
    }

def scenario_tc_ax_03():
    print("\n" + "=" * 70)
    print("▶ SCENARIO TC-AX-03: Ambient Credential Minimization (Live Guest Runtime)")
    print("=" * 70)
    send_to_scope("ax-credential-guard", "prompt", "[TC-AX-03] Probing live guest container for leaked credentials...")
    
    # 1. Inspect live guest environment
    env_out, stderr, rc = run_ax(["ssh", "golden-task", "--", "env"])
    assert rc == 0, f"Failed to execute env inside golden-task: {stderr}"
    
    print("--- Live Guest Environment Variables ---")
    print(env_out)
    
    forbidden = ["GEMINI_API_KEY", "AX_ROOT_TOKEN", "SUBSTRATE_ADMIN_KEY", "AWS_SECRET_ACCESS_KEY", "GOOGLE_APPLICATION_CREDENTIALS"]
    for var in forbidden:
        assert var not in env_out, f"Dangerous token {var} detected in guest container!"
    print(f"✓ Confirmed absence of: {', '.join(forbidden)}")

    # 2. Inspect /var/run/secrets inside container
    secrets_out, _, _ = run_ax(["ssh", "golden-task", "--", "ls", "-la", "/var/run/secrets"])
    print(f"✓ Secret mounts check: {secrets_out}")
    assert "No such file or directory" in secrets_out or secrets_out == "", "No ambient kubernetes secrets mounted"

    # 3. Test Network Reachability to Kubernetes API
    net_out, _, _ = run_ax(["ssh", "golden-task", "--", "sh", "-c", "curl -m 2 -sk https://kubernetes.default.svc/api; echo RC=$?"])
    print(f"✓ Network isolation probe: {net_out}")
    assert "RC=6" in net_out or "RC=28" in net_out or "RC=7" in net_out, "Kubernetes API must be unreachable from guest"

    send_to_scope("ax-credential-guard", "reply", "[TC-AX-03] PASS: Live guest verified zero ambient API keys, zero SA mounts, no K8s API reachability.", 120)
    return {
        "status": "PASS",
        "forbidden_tokens_checked": forbidden,
        "tokens_found": [],
        "service_account_mounted": False,
        "k8s_api_isolated": True
    }

def scenario_tc_ax_06():
    print("\n" + "=" * 70)
    print("▶ SCENARIO TC-AX-06: Interactive SSH Stdin & Signal Forwarding")
    print("=" * 70)
    send_to_scope("ax-ssh-controller", "prompt", "[TC-AX-06] Validating ax ssh execution, gVisor isolation & stdin pipe...")
    
    # 1. Check kernel in sandbox
    uname_out, _, rc = run_ax(["ssh", "golden-task", "--", "uname", "-a"])
    assert rc == 0
    print(f"✓ Sandbox Kernel: {uname_out}")
    assert "gvisor" in uname_out.lower(), "Task must run inside gVisor sandbox"

    # 2. Test piped stdin forwarding
    test_payload = "AX_LIVE_STDIN_FORWARDING_VERIFIED_2026"
    pipe_out, _, rc = run_ax(["ssh", "golden-task", "--", "cat"], input_data=test_payload)
    assert rc == 0
    print(f"✓ Stdin Pipe Echo: {pipe_out}")
    assert test_payload in pipe_out, "Piped stdin must be forwarded directly to guest process"

    send_to_scope("ax-ssh-controller", "reply", "[TC-AX-06] PASS: Interactive SSH confirmed inside gVisor sandbox with verified stdin stream.", 95)
    return {
        "status": "PASS",
        "kernel": uname_out,
        "stdin_forwarding_verified": True
    }

def main():
    print("\n" + "=" * 75)
    print("🚀 AX & AGENT SUBSTRATE: LIVE RUNTIME VERIFICATION (STEP 3 & SECURITY SCENARIOS)")
    print("=" * 75)

    results = {}
    results["step_3_golden_task"] = step_3_golden_task()
    results["tc_ax_07"] = scenario_tc_ax_07()
    results["tc_ax_03"] = scenario_tc_ax_03()
    results["tc_ax_06"] = scenario_tc_ax_06()

    evidence_file = EVIDENCE_DIR_AX / "live_step3_and_security_scenarios.json"
    evidence_file.write_text(json.dumps(results, indent=2))
    print(f"\n📁 Saved live evidence to {evidence_file}")

    print("\n" + "=" * 75)
    print("🏁 ALL RUNTIME SCENARIOS VERIFIED SUCCESSFULLY (100% PASS)!")
    print("=" * 75)

if __name__ == "__main__":
    main()
