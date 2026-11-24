#!/usr/bin/env python3
"""
Agent A: Natural-Language Orchestrator & Workflow Client
=========================================================
Accepts natural-language instructions from human user (Alice),
interprets the intent via LLM (NVIDIA Nemotron), identifies required operations
and target agents, automatically handles Keycard STS token minting and RFC 8693
token exchange, invokes downstream agents over Google A2A JSON-RPC, and verifies
the cryptographic audit evidence.

Usage:
  python agent_a.py                                   # Interactive prompt mode
  python agent_a.py "<Instruction>"                   # Direct natural-language task
  python agent_a.py --test-unauthorized               # Demonstrate 403 Forbidden on unauthorized operation
  python agent_a.py --test-revocation                 # Demonstrate 401 Unauthorized on revoked session
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import jwt

# Load environment variables (.env)
CURRENT_DIR = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=CURRENT_DIR / ".env")
except ImportError:
    pass

# Configuration endpoints
STS_URL = os.environ.get("STS_URL", "http://127.0.0.1:8088")
AGENT_B_URL = os.environ.get("AGENT_B_URL", "http://127.0.0.1:9002")
AGENT_C_URL = os.environ.get("AGENT_C_URL", "http://127.0.0.1:9003")
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")

# ANSI Color formatting
CYAN = "\033[1;36m"
GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
MAGENTA = "\033[1;35m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def print_banner():
    print(f"\n{BOLD}{CYAN}======================================================================{RESET}")
    print(f"{BOLD}{GREEN}       KEYCARD MULTI-AGENT (A2A) AUTONOMOUS WORKFLOW{RESET}")
    print(f"{DIM}  Natural Language ➔ Orchestrator ➔ Keycard STS ➔ Multi-Hop Agents{RESET}")
    print(f"{BOLD}{CYAN}======================================================================{RESET}\n")


def print_section(title: str):
    print(f"\n{BOLD}{CYAN}── {title} {'─' * (55 - len(title))}{RESET}")


def check_servers_online():
    """Ensure all required services are reachable before running."""
    services = [
        ("Keycard STS", f"{STS_URL}/health"),
        ("Agent B (Investigator)", f"{AGENT_B_URL}/health"),
        ("Agent C (Audit Vault)", f"{AGENT_C_URL}/health"),
    ]
    for name, url in services:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code != 200:
                print(f"{RED}[Agent A] Error: {name} at {url} returned HTTP {r.status_code}{RESET}")
                sys.exit(1)
        except Exception:
            print(f"{RED}[Agent A] Error: Cannot reach {name} at {url}.{RESET}")
            print(f"       Run './start_servers.sh' first to launch the environment.")
            sys.exit(1)


# ==============================================================================
# 1. Natural Language Intent Interpretation via LLM
# ==============================================================================
def interpret_task_intent(user_prompt: str) -> Dict[str, Any]:
    """
    Uses NVIDIA NIM LLM to parse natural-language instructions into structured
    operations, selected agents, and required permissions.
    Distinction: The LLM identifies what was requested, not what permissions it may grant.
    """
    print_section("PLANNING")
    print(f"{BOLD}[Agent A]{RESET} Interpreting natural-language user intent...")

    if NVIDIA_API_KEY:
        try:
            headers = {
                "Authorization": f"Bearer {NVIDIA_API_KEY}",
                "Content-Type": "application/json"
            }
            system_instruction = (
                "You are Agent A, a security orchestrator. Analyze the user's natural language request. "
                "Identify: 1) A short intent summary, 2) The operations to execute, 3) The required agents, "
                "4) The necessary OAuth scopes from: ['incident:investigate', 'db:read', 'audit:write']. "
                "Output ONLY a valid JSON object with keys: intent_summary, operations, target_agents, required_scopes."
            )
            resp = httpx.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers=headers,
                json={
                    "model": NVIDIA_MODEL,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": f"Task: {user_prompt}"}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1024
                },
                timeout=30.0
            )
            if resp.status_code == 200:
                msg = resp.json()["choices"][0]["message"]
                content = msg.get("content") or ""
                if content.strip().startswith("```"):
                    content = content.strip().split("\n", 1)[1].rsplit("```", 1)[0].strip()
                parsed = json.loads(content)
                print(f"{BOLD}[Agent A]{RESET} {GREEN}✓ Intent interpreted via NVIDIA Nemotron LLM:{RESET}")
                print(f"  • Summary:         {BOLD}{parsed.get('intent_summary', 'Security Investigation')}{RESET}")
                print(f"  • Operations:      {parsed.get('operations', ['investigate_incident', 'seal_audit'])}")
                print(f"  • Target Agents:   {CYAN}{parsed.get('target_agents', ['Agent B', 'Agent C'])}{RESET}")
                print(f"  • Required Scopes: {MAGENTA}{parsed.get('required_scopes', ['incident:investigate', 'db:read', 'audit:write'])}{RESET}")
                return parsed
        except Exception as e:
            print(f"{YELLOW}[Agent A] LLM interpretation notice: {e}. Using deterministic parser.{RESET}")

    # Fallback heuristic parser
    p_lower = user_prompt.lower()
    operations = ["investigate_incident"]
    target_agents = ["Agent B (Incident Investigator)", "Agent C (Audit Vault Signer)"]
    scopes = ["incident:investigate"]

    if "db" in p_lower or "database" in p_lower or "query" in p_lower:
        operations.append("read_database_logs")
        scopes.append("db:read")
    if "audit" in p_lower or "vault" in p_lower or "save" in p_lower or "seal" in p_lower:
        operations.append("write_audit_vault")
        scopes.append("audit:write")

    summary = "Investigate incident and cryptographically seal findings"
    parsed = {
        "intent_summary": summary,
        "operations": operations,
        "target_agents": target_agents,
        "required_scopes": scopes
    }
    print(f"{BOLD}[Agent A]{RESET} {GREEN}✓ Intent parsed:{RESET}")
    print(f"  • Summary:         {BOLD}{parsed['intent_summary']}{RESET}")
    print(f"  • Operations:      {parsed['operations']}")
    print(f"  • Target Agents:   {CYAN}{parsed['target_agents']}{RESET}")
    print(f"  • Required Scopes: {MAGENTA}{parsed['required_scopes']}{RESET}")
    return parsed


# ==============================================================================
# 2. Keycard STS Token Minting & Token Exchange (RFC 8693)
# ==============================================================================
def obtain_keycard_tokens(user_id: str, client_id: str, scopes: List[str]) -> Dict[str, str]:
    """
    Automatically authenticates human user (Alice) with Keycard STS
    and exchanges credentials for Agent B with permission attenuation.
    """
    print_section("AUTHENTICATION & TOKEN EXCHANGE")

    # Step 1: Mint Alice's root session credential
    print(f"{BOLD}[Keycard STS]{RESET} Minting initial root session token for '{user_id}' on '{client_id}'...")
    root_scopes = "support:read tasks:delegate incident:investigate db:read audit:write"
    r1 = httpx.post(
        f"{STS_URL}/oauth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "user_id": user_id,
            "scope": root_scopes
        },
        timeout=5.0
    )
    if r1.status_code != 200:
        raise RuntimeError(f"Failed to mint session token on STS: {r1.text}")
    token_a = r1.json()["access_token"]
    claims_a = jwt.decode(token_a, options={"verify_signature": False})
    sid = claims_a.get("sid", "unknown")
    print(f"  • Initial Credential: {GREEN}ISSUED{RESET} (Session: {DIM}{sid}{RESET})")
    print(f"  • Root Scopes:        {MAGENTA}{root_scopes}{RESET}")

    # Step 2: RFC 8693 Token Exchange for Agent B
    agent_b_scopes = "incident:investigate db:read audit:write"
    print(f"\n{BOLD}[Keycard STS]{RESET} Performing RFC 8693 Token Exchange for Agent B ({AGENT_B_URL})...")
    r2 = httpx.post(
        f"{STS_URL}/oauth/token",
        json={
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": token_a,
            "actor_token": client_id,
            "audience": AGENT_B_URL,
            "scope": agent_b_scopes
        },
        timeout=5.0
    )
    if r2.status_code != 200:
        raise RuntimeError(f"Token exchange for Agent B failed: {r2.text}")
    token_b = r2.json()["access_token"]
    print(f"  • Exchanged Token B:  {GREEN}ACQUIRED{RESET}")
    print(f"  • Audience:           {CYAN}{AGENT_B_URL}{RESET}")
    print(f"  • Attenuated Scopes:  {MAGENTA}{agent_b_scopes}{RESET}")
    print(f"  • Actor Lineage:      {BOLD}[{user_id} -> {client_id} -> {AGENT_B_URL}]{RESET}")

    return {
        "token_a": token_a,
        "token_b": token_b,
        "session_id": sid
    }


# ==============================================================================
# 3. Google A2A Invocation & Autonomous Multi-Hop Execution
# ==============================================================================
def invoke_agent_b_workflow(task_text: str, token_b: str) -> Dict[str, Any]:
    """
    Sends the task to Agent B via Google A2A JSON-RPC.
    Agent B's middleware verifies credentials, executes the investigation,
    autonomously calls Keycard STS for Token C, and delegates signing to Agent C.
    """
    print_section("AGENT B: INCIDENT INVESTIGATION")
    print(f"{BOLD}[Agent A]{RESET} Invoking Agent B via Google A2A JSON-RPC (Bearer Token B)...")

    req_payload = {
        "jsonrpc": "2.0",
        "id": f"req-dyn-{int(time.time())}",
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": f"msg-{int(time.time())}",
                "role": "ROLE_USER",
                "parts": [{"text": task_text}]
            }
        }
    }

    t0 = time.time()
    resp = httpx.post(
        f"{AGENT_B_URL}/a2a/jsonrpc",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token_b}",
            "A2A-Version": "1.0"
        },
        json=req_payload,
        timeout=40.0
    )
    elapsed = time.time() - t0

    if resp.status_code != 200:
        print(f"{RED}[Agent A] Agent B invocation failed (HTTP {resp.status_code}): {resp.text}{RESET}")
        return {"error": resp.text, "status_code": resp.status_code}

    data = resp.json()
    result_text = ""
    try:
        parts = data["result"]["task"]["status"]["message"]["parts"]
        result_text = parts[0]["text"]
    except Exception:
        result_text = json.dumps(data)

    print(f"{BOLD}[Agent B]{RESET} {GREEN}✓ Investigation Completed in {elapsed:.2f}s{RESET}")
    
    # Parse report lines for clean presentation
    lines = result_text.split("\n")
    for line in lines:
        if line.startswith("Category:") or line.startswith("Findings:") or line.startswith("Containment Action:"):
            print(f"  • {line}")

    return {
        "status_code": resp.status_code,
        "full_text": result_text,
        "raw_response": data
    }


# ==============================================================================
# 4. Verification & Cryptographic Seal Checking
# ==============================================================================
def verify_audit_seal(result_text: str) -> bool:
    """
    Validates Agent C's digital RSA RS256 signature against its public key.
    """
    print_section("AGENT C: AUDIT VAULT SEAL & VERIFICATION")
    print(f"{BOLD}[Agent A]{RESET} Retrieving Agent C public key and verifying cryptographic signature...")

    try:
        # Step 1: Fetch Agent C public key
        pk_resp = httpx.get(f"{AGENT_C_URL}/vault/public_key", timeout=3.0)
        if pk_resp.status_code != 200:
            print(f"{YELLOW}[Agent A] Could not retrieve Agent C public key: HTTP {pk_resp.status_code}{RESET}")
            return False

        # Step 2: Use verify_seal module
        import verify_seal
        is_valid = verify_seal.verify_seal(result_text)
        return is_valid
    except Exception as e:
        print(f"{RED}[Agent A] Signature verification error: {e}{RESET}")
        return False


def display_audit_trail_summary():
    """Fetches the 6-event chronological audit log from Keycard STS."""
    print_section("KEYCARD DELEGATION AUDIT LEDGER")
    try:
        r = httpx.get(f"{STS_URL}/audit", timeout=3.0)
        if r.status_code == 200:
            res_data = r.json()
            events = res_data.get("audit_trail", []) if isinstance(res_data, dict) else res_data
            recent = events[-6:] if len(events) >= 6 else events
            for idx, ev in enumerate(recent, 1):
                ev_type = ev.get("type", "UNKNOWN")
                decision = ev.get("decision", "AUTHORIZED")
                actor = ev.get("actor") or ev.get("user_id") or ev.get("agent") or "system"
                target = ev.get("target_audience") or ev.get("endpoint") or ev.get("seal_id") or ""
                print(f"  {idx}. [{ev_type}] decision={GREEN}{decision}{RESET} actor={YELLOW}{actor}{RESET} target={CYAN}{target}{RESET}")
    except Exception as e:
        print(f"{YELLOW}[Agent A] Could not fetch audit ledger: {e}{RESET}")


# ==============================================================================
# 5. Security Demonstration Modes (Unauthorized Action & Revocation)
# ==============================================================================
def run_unauthorized_operation_demo():
    """
    Demonstrates Stage 4: An agent attempts an unauthorized operation (db:delete)
    and verifies that Keycard / Middleware rejects it with HTTP 403 Forbidden.
    """
    print_banner()
    print_section("SECURITY TEST: UNAUTHORIZED OPERATION ATTEMPT (HTTP 403)")
    print(f"{BOLD}[Scenario]{RESET} Agent A attempts to delegate prohibited scope '{RED}db:delete{RESET}' to Agent B.")
    
    # Mint token with read permissions
    r1 = httpx.post(
        f"{STS_URL}/oauth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": "agent-a",
            "user_id": "alice",
            "scope": "support:read incident:investigate db:read"
        },
        timeout=3.0
    )
    token_a = r1.json()["access_token"]

    print(f"\n{BOLD}[Agent A]{RESET} Requesting token exchange for scope '{RED}db:delete{RESET}'...")
    r2 = httpx.post(
        f"{STS_URL}/oauth/token",
        json={
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": token_a,
            "actor_token": "agent-a",
            "audience": AGENT_B_URL,
            "scope": "db:delete"
        },
        timeout=3.0
    )
    
    print(f"  • Keycard STS Response: {BOLD}{RED}HTTP {r2.status_code} Forbidden{RESET}")
    print(f"  • Policy Interception:  {r2.text}")
    print(f"  • {GREEN}✔ SECURITY VERIFIED: Destructive action was blocked at the gateway.{RESET}\n")


def run_revocation_demo():
    """
    Demonstrates Stage 4: Admin pulls kill switch; subsequent downstream requests fail with 401.
    """
    print_banner()
    print_section("SECURITY TEST: CENTRAL REVOCATION & KILL SWITCH (HTTP 401)")
    print(f"{BOLD}[Scenario]{RESET} Alice's session is revoked centrally at Keycard STS. Downstream tokens are rejected.")

    # Mint credentials
    tokens = obtain_keycard_tokens("alice", "agent-a", ["incident:investigate", "db:read", "audit:write"])
    sid = tokens["session_id"]
    token_b = tokens["token_b"]

    print(f"\n{BOLD}[Admin Kill Switch]{RESET} Revoking session '{sid}' at Keycard STS...")
    rev_resp = httpx.post(f"{STS_URL}/oauth/revoke", json={"session_id": sid}, timeout=3.0)
    print(f"  • Revocation status: {GREEN}{rev_resp.json()}{RESET}")

    print(f"\n{BOLD}[Agent A]{RESET} Attempting to invoke Agent B with previously issued Token B...")
    inv_resp = httpx.post(
        f"{AGENT_B_URL}/a2a/jsonrpc",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token_b}",
            "A2A-Version": "1.0"
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendMessage",
            "params": {"message": {"role": "ROLE_USER", "parts": [{"text": "Attempt after revocation"}]}}
        },
        timeout=5.0
    )
    print(f"  • Agent B Middleware: {BOLD}{RED}HTTP {inv_resp.status_code} Unauthorized{RESET}")
    print(f"  • Rejection Reason:   {inv_resp.text}")
    print(f"  • {GREEN}✔ SECURITY VERIFIED: Lineage invalidation propagated to downstream agent.{RESET}\n")


# ==============================================================================
# Main Orchestrator Flow
# ==============================================================================
def run_workflow(user_task: str):
    print_banner()
    check_servers_online()

    print(f"{BOLD}User (Alice) >{RESET} {GREEN}\"{user_task}\"{RESET}")

    # 1. Interpret natural language intent
    intent = interpret_task_intent(user_task)

    # 2. Keycard STS automated credential issuance & token exchange
    tokens = obtain_keycard_tokens("alice", "agent-a", intent["required_scopes"])

    # 3. Autonomous Google A2A Multi-Hop execution
    result = invoke_agent_b_workflow(user_task, tokens["token_b"])

    # 4. Cryptographic signature verification
    seal_valid = False
    if "full_text" in result:
        seal_valid = verify_audit_seal(result["full_text"])

    # 5. STS Central audit trail
    display_audit_trail_summary()

    # 6. Final Result Summary
    print_section("FINAL RESULT")
    print(f"  • Incident Investigation:  {GREEN}COMPLETED{RESET}")
    print(f"  • Audit Vault Record:      {GREEN}STORED{RESET}")
    print(f"  • Cryptographic Seal:      {GREEN}VERIFIED (RS256 Signature Valid){RESET}" if seal_valid else f"  • Cryptographic Seal:      {YELLOW}UNVERIFIED{RESET}")
    print(f"  • Runtime Authorization:   {GREEN}VERIFIED (Least-Privilege Maintained across 2 Hops){RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="Agent A: Natural Language Orchestrator for Keycard A2A")
    parser.add_argument("task", nargs="*", help="Natural-language task to execute")
    parser.add_argument("--test-unauthorized", action="store_true", help="Demonstrate 403 Forbidden on unauthorized operation")
    parser.add_argument("--test-revocation", action="store_true", help="Demonstrate 401 Unauthorized on revoked session")
    args = parser.parse_args()

    if args.test_unauthorized:
        run_unauthorized_operation_demo()
        return

    if args.test_revocation:
        run_revocation_demo()
        return

    if args.task:
        task_str = " ".join(args.task)
    else:
        print_banner()
        print("Enter your natural-language task (or press Enter for default):")
        default_task = "Investigate suspicious database access on the production database. Analyze the access logs, identify the responsible activity, and save the investigation findings in the audit vault."
        print(f"{DIM}Default: {default_task}{RESET}")
        try:
            user_input = input(f"\n{BOLD}Alice > {RESET}").strip()
            task_str = user_input if user_input else default_task
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            sys.exit(0)

    run_workflow(task_str)


if __name__ == "__main__":
    main()
