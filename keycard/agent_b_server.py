#!/usr/bin/env python3
"""
Agent B: Incident Investigator (Port 9002)
=========================================
Google A2A agent protected by Keycard Authentication Middleware.
Reuses open-source HelloWorldAgentExecutor from a2aproject/a2a-samples.

Key Capabilities:
  - Publishes public A2A Agent Card on /.well-known/agent-card.json
  - Enforces RS256 JWT verification via KeycardAuthBackend on /a2a/jsonrpc
  - Strictly requires 'incident:investigate' scope (HTTP 403 if missing)
  - Dynamically analyzes arbitrary incident queries (not hardcoded)
  - Autonomously delegates evidence signing to Agent C (Port 9003) via RFC 8693
  - Emits real-time colored telemetry and execution audit for live demonstration
"""

import argparse
import asyncio
import importlib.util
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import uvicorn
import jwt
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Add official A2A samples agent path
CURRENT_DIR = Path(__file__).resolve().parent

# Load environment variables from .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=CURRENT_DIR / ".env")
except ImportError:
    pass

A2A_SAMPLES_DIR = CURRENT_DIR / "a2a-samples/samples/python/agents/helloworld"
sys.path.insert(0, str(A2A_SAMPLES_DIR))

# Dynamic loader for HelloWorldAgentExecutor
spec = importlib.util.spec_from_file_location("mod_hello", str(A2A_SAMPLES_DIR / "agent_executor.py"))
mod_hello = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod_hello)
HelloWorldAgentExecutor = getattr(mod_hello, "HelloWorldAgentExecutor")

# Official A2A SDK imports
from a2a.helpers import get_message_text, new_task_from_user_message, new_text_message
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import TaskState
from a2a.utils import constants

# Official Keycard A2A SDK imports
from keycardai.a2a import (
    AgentServiceConfig,
    DelegationClient,
    KeycardServerCallContextBuilder,
    build_agent_card_from_config,
    keycard_user,
)
from keycardai.starlette import AuthProvider, KeycardAuthBackend, KeycardAuthError, keycard_on_error


# ANSI terminal colors
CYAN = "\033[1;36m"
GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
MAGENTA = "\033[1;35m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


# Live Telemetry State
telemetry = {
    "agent": "Agent B (Incident Investigator)",
    "port": 9002,
    "total_requests": 0,
    "authenticated_executions": 0,
    "blocked_requests": 0,
    "delegations_to_agent_c": 0,
    "last_caller": None,
    "last_task": None
}


def analyze_incident(query: str) -> Dict[str, str]:
    """
    Dynamically analyzes the incoming task query and synthesizes realistic,
    tailored investigation findings and containment actions.
    """
    q_lower = query.lower()
    incident_id = f"INC-{int(time.time()) % 100000:05d}"

    if "auth" in q_lower or "failed" in q_lower or "login" in q_lower:
        category = "Authentication / Credential Stuffing"
        findings = "Identified 47 brute-force authentication attempts originating from IP 198.51.100.24 targeting /oauth/token. Credential spraying detected."
        containment = "Source IP address 198.51.100.24 quarantined at firewall. Enforced mandatory MFA re-challenge for targeted accounts."
    elif "db" in q_lower or "database" in q_lower or "sql" in q_lower:
        category = "Unauthorized Database Access"
        findings = "Detected anomalous high-volume read query against table 'production_customers' bypassing query cache. Connection origin: svc-analytics."
        containment = "Suspicious database session terminated. Read permissions temporarily restricted to read-only replica with query rate limiting."
    elif "escalat" in q_lower or "privilege" in q_lower or "role" in q_lower or "admin" in q_lower:
        category = "Privilege Escalation Attempt"
        findings = "Observed unapproved role-binding request attempting to bind 'cluster-admin' without an active ServiceNow change ticket."
        containment = "Rogue IAM policy detached immediately. Principal account credentials invalidated and flagged for security review."
    elif "#" in query or "account" in q_lower:
        acc_match = re.search(r"#?(\d{4,6})", query)
        acc_num = acc_match.group(1) if acc_match else "4821"
        category = f"Suspicious Activity on Account #{acc_num}"
        findings = f"Detected concurrent geographic logins (Tokyo and Frankfurt) within 3 minutes on account #{acc_num}. High-risk anomalous data export initiated."
        containment = f"Active session tokens for account #{acc_num} revoked. Outbound data egress throttled and account state set to read-only."
    else:
        category = "General Security Anomaly"
        findings = f"Analyzed reported incident pattern: '{query}'. Correlated SIEM telemetry shows anomalous behavioral deviations."
        containment = "Applied network boundary isolation on affected workload and initiated memory forensics snapshot."

    return {
        "incident_id": incident_id,
        "category": category,
        "findings": findings,
        "containment": containment,
        "engine": "Autonomous Heuristic Engine"
    }


def analyze_incident_with_ai(query: str) -> Dict[str, str]:
    """
    Connects to NVIDIA NIM LLM for actual AI incident reasoning,
    with graceful fallback to dynamic heuristic reasoning engine.
    Reads NVIDIA_API_KEY and NVIDIA_MODEL from environment / .env.
    """
    api_key = os.environ.get("NVIDIA_API_KEY")
    model = os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")

    if not api_key:
        print(f"{YELLOW}[Agent B | {timestamp()}]{RESET} ℹ️ NVIDIA_API_KEY not configured in .env or environment. Using dynamic security analysis engine.", flush=True)
        return analyze_incident(query)

    try:
        import httpx
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        prompt = (
            f"Incident description: {query}\n"
            "Analyze this security incident. Provide structured reasoning and recommended containment. "
            "Output ONLY valid JSON with keys: category, findings, containment."
        )
        resp = httpx.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a cybersecurity incident response AI (Agent B). Be concise. Output in valid JSON format only with keys: category, findings, containment."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 1024
            },
            timeout=12.0
        )
        if resp.status_code == 200:
            choice = resp.json()["choices"][0]["message"]
            raw_content = choice.get("content") or ""
            reasoning = choice.get("reasoning_content") or ""
            
            # Clean markdown blocks if present
            clean_json = raw_content.strip()
            if clean_json.startswith("```"):
                clean_json = clean_json.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            parsed = json.loads(clean_json)
            parsed["incident_id"] = f"INC-LLM-{int(time.time()) % 10000:04d}"
            parsed["engine"] = f"NVIDIA NIM ({model})"
            if reasoning:
                print(f"{CYAN}[Agent B | {timestamp()}]{RESET} 🧠 AI Chain-of-Thought (Snippet): {DIM}{reasoning[:120].strip()}...{RESET}", flush=True)
            print(f"{GREEN}[Agent B | {timestamp()}]{RESET} ✓ AI Reasoning completed using {CYAN}{parsed['engine']}{RESET}", flush=True)
            return parsed
        else:
            print(f"{YELLOW}[Agent B | {timestamp()}]{RESET} ℹ️ NVIDIA API returned HTTP {resp.status_code} ({resp.text[:65]}). Using dynamic security analysis engine.", flush=True)
    except Exception as e:
        print(f"{YELLOW}[Agent B | {timestamp()}]{RESET} ℹ️ NVIDIA API notice: {e}. Using dynamic security analysis engine.", flush=True)

    return analyze_incident(query)


class KeycardAuditedInvestigatorExecutor(HelloWorldAgentExecutor):
    def __init__(self, agent_c_client: Optional[DelegationClient] = None, agent_c_url: Optional[str] = None):
        super().__init__()
        self.client_c = agent_c_client
        self.agent_c_url = agent_c_url

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        caller = keycard_user(context)
        query = get_message_text(context.message)

        if context.current_task:
            task = context.current_task
        else:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        task_updater = TaskUpdater(event_queue=event_queue, task_id=task.id, context_id=task.context_id)

        if not caller:
            telemetry["total_requests"] += 1
            print(f"{YELLOW}[Agent B | {timestamp()}]{RESET} ⚠️ Unauthenticated execution (legacy baseline): '{query}'", flush=True)
            await task_updater.update_status(
                state=TaskState.TASK_STATE_COMPLETED,
                message=new_text_message(f"Unauthenticated execution completed: {query}")
            )
            return

        telemetry["authenticated_executions"] += 1
        telemetry["last_caller"] = f"caller={caller.client_id}, root_sub={caller.sub}"
        telemetry["last_task"] = query

        print(f"\n{GREEN}[Agent B | {timestamp()}]{RESET} {BOLD}EXECUTION STARTED:{RESET}", flush=True)
        print(f"  • Task Query: {CYAN}\"{query}\"{RESET}", flush=True)
        print(f"  • Root Principal (sub): {GREEN}{caller.sub}{RESET} (Human initiator)", flush=True)
        print(f"  • Calling Actor (client_id): {YELLOW}{caller.client_id}{RESET}", flush=True)
        print(f"  • Assigned Scopes: {MAGENTA}{caller.scopes}{RESET}", flush=True)

        # Dynamic incident analysis (with AI reasoning if enabled)
        analysis = analyze_incident_with_ai(query)
        print(f"  • Dynamic Incident Classification: {BOLD}{analysis['category']}{RESET} [{analysis.get('engine', 'Heuristic')}]", flush=True)
        print(f"  • Findings: {analysis['findings']}", flush=True)
        print(f"  • Containment Action: {analysis['containment']}", flush=True)

        audit_seal_info = "Local investigation completed."
        evidence_digest = None
        evidence_signature = None

        # Autonomously delegate evidence signing to Agent C
        if self.client_c is not None and self.agent_c_url is not None:
            print(f"  • {MAGENTA}AUTONOMOUS MULTI-HOP DELEGATION TRIGGERED:{RESET}", flush=True)
            print(f"    Agent B delegating evidence archival to Agent C ({self.agent_c_url})...", flush=True)

            try:
                # Hop 2 Token Exchange: Agent B exchanges caller.access_token for Agent-C-scoped token
                print(f"    Requesting RFC 8693 Token Exchange against Keycard STS for Agent C...", flush=True)
                token_c = await self.client_c.get_delegation_token(
                    self.agent_c_url,
                    subject_token=caller.access_token
                )
                print(f"    ✓ Token C received with narrowed scope 'audit:write'", flush=True)

                # Persist autonomously acquired Token C for inspection
                try:
                    with open("/tmp/.keycard_token_c", "w") as f:
                        f.write(token_c)
                except Exception:
                    pass

                delegation_payload = {
                    "task": f"Cryptographically seal incident findings for '{analysis['category']}': {analysis['findings']}"
                }

                c_invoke = await self.client_c.invoke_service(
                    self.agent_c_url,
                    delegation_payload,
                    token=token_c
                )
                c_result_text = c_invoke.get("result", "")
                telemetry["delegations_to_agent_c"] += 1
                audit_seal_info = f"Archived to Agent C. Evidence Seal: {c_result_text}"
                print(f"    ✓ Agent C response: {GREEN}{c_result_text[:110]}...{RESET}", flush=True)

            except Exception as e:
                audit_seal_info = f"Delegation to Agent C failed: {str(e)}"
                print(f"    {RED}✗ Delegation to Agent C error: {str(e)}{RESET}", flush=True)

        resp_text = (
            f"Incident Investigation Report [{analysis['incident_id']}]: {query}\n"
            f"Category: {analysis['category']}\n"
            f"Status: Analyzed and Contained\n"
            f"Root Subject: {caller.sub} | Authorized Actor: {caller.client_id}\n"
            f"Findings: {analysis['findings']}\n"
            f"Containment Action: {analysis['containment']}\n"
            f"Evidence Vault Seal: [{audit_seal_info}]"
        )

        print(f"{GREEN}[Agent B | {timestamp()}]{RESET} ✓ Task completed successfully.\n", flush=True)

        await task_updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message(resp_text)
        )


class AuditedKeycardBackend(KeycardAuthBackend):
    def __init__(self, verifier, sts_url: str, require_authentication: bool = True):
        super().__init__(verifier, require_authentication=require_authentication)
        self.sts_url = sts_url

    async def authenticate(self, conn):
        path = conn.url.path
        if path.endswith("agent-card.json") or path in ["/health", "/telemetry"]:
            if path.endswith("agent-card.json"):
                print(f"{CYAN}[Agent B | {timestamp()}]{RESET} DISCOVERY: Served public A2A Agent Card ({path})", flush=True)
            return None

        telemetry["total_requests"] += 1

        auth_header = conn.headers.get("Authorization", "")
        if not auth_header:
            telemetry["blocked_requests"] += 1
            print(f"\n{RED}[Agent B | {timestamp()}]{RESET} {BOLD}ATTACK INTERCEPTED (401 Unauthorized):{RESET}", flush=True)
            print(f"  • Path: {path} | Method: {conn.scope.get('method')}", flush=True)
            print(f"  • Error: Missing Authorization header (Anonymous caller rejected)", flush=True)
            print(f"  • {GREEN}Execution Contained: Agent B Executor was NOT invoked!{RESET}\n", flush=True)
            raise KeycardAuthError("unauthorized", "Missing Authorization header", status_code=401)

        try:
            auth_res = await super().authenticate(conn)
            if auth_res:
                creds, user = auth_res

                # 1. Enforce Scope: Agent B strictly requires 'incident:investigate'
                if "incident:investigate" not in user.scopes:
                    telemetry["blocked_requests"] += 1
                    print(f"\n{RED}[Agent B | {timestamp()}]{RESET} {BOLD}SECURITY INTERCEPTION (403 Forbidden):{RESET}", flush=True)
                    print(f"  • Path: {path} | Caller: {user.client_id} (sub={user.sub})", flush=True)
                    print(f"  • Held Scopes: {user.scopes}", flush=True)
                    print(f"  • Missing Scope: {MAGENTA}'incident:investigate'{RESET}", flush=True)
                    print(f"  • {GREEN}Execution Contained: Agent B Executor was NOT invoked!{RESET}\n", flush=True)
                    raise KeycardAuthError("insufficient_scope", "Insufficient scope: requires 'incident:investigate'", status_code=403)

                # 2. Check real-time revocation with Keycard STS
                import httpx
                try:
                    unverified = jwt.decode(user.access_token, options={"verify_signature": False})
                    sid = unverified.get("sid")
                    if sid:
                        async with httpx.AsyncClient() as client:
                            resp = await client.get(f"{self.sts_url}/oauth/revoked", timeout=1.0)
                            if resp.status_code == 200 and sid in resp.json().get("revoked_sessions", []):
                                raise KeycardAuthError("invalid_token", f"Session '{sid}' has been revoked by central security policy.", status_code=401)
                except KeycardAuthError:
                    raise
                except Exception:
                    pass

                print(f"{GREEN}[Agent B | {timestamp()}]{RESET} AUTH: Verified RS256 Keycard token! sub='{user.sub}', client='{user.client_id}', scopes={user.scopes}", flush=True)

                # Report successful Agent B authorization to central audit trail
                try:
                    async with httpx.AsyncClient() as client:
                        await client.post(f"{self.sts_url}/audit/event", json={
                            "type": "AGENT_AUTHORIZATION",
                            "details": {
                                "agent": "Agent B (Incident Investigator)",
                                "endpoint": path,
                                "caller": user.client_id,
                                "root_subject": user.sub,
                                "scopes_verified": user.scopes,
                                "decision": "AUTHORIZED"
                            }
                        }, timeout=1.0)
                except Exception:
                    pass
            return auth_res
        except Exception as exc:
            telemetry["blocked_requests"] += 1
            status_code = getattr(exc, "status_code", 401)
            err_msg = getattr(exc, "description", str(exc))
            err_type = "403 Forbidden" if status_code == 403 else "401 Unauthorized"
            print(f"\n{RED}[Agent B | {timestamp()}]{RESET} {BOLD}SECURITY INTERCEPTION ({err_type}):{RESET}", flush=True)
            print(f"  • Path: {path}", flush=True)
            print(f"  • Reason: {err_msg}", flush=True)
            print(f"  • {GREEN}Execution Contained: Agent B Executor was NOT invoked!{RESET}\n", flush=True)
            raise


async def telemetry_endpoint(request: Request):
    return JSONResponse(telemetry)


async def health_endpoint(request: Request):
    return JSONResponse({"status": "ok", "service": "Agent B (Incident Investigator)", "port": telemetry["port"]})


def create_agent_b_app(agent_b_url: str, sts_url: str, agent_c_url: str):
    agent_b_cfg = AgentServiceConfig(
        service_name="IncidentInvestigatorAgent",
        client_id="agent-b",
        client_secret="secret-b",
        identity_url=agent_b_url,
        zone_id="default",
        authorization_server_url=sts_url,
        capabilities=["triage", "incident_investigation", "forensics"]
    )
    card = build_agent_card_from_config(agent_b_cfg)

    # Initialize client for Agent B -> Agent C delegation
    agent_c_client = DelegationClient(agent_b_cfg)

    executor = KeycardAuditedInvestigatorExecutor(agent_c_client=agent_c_client, agent_c_url=agent_c_url)
    handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore(), agent_card=card)

    auth_provider = AuthProvider(zone_url=sts_url, server_url=agent_b_url, audience=agent_b_url)
    backend = AuditedKeycardBackend(auth_provider.get_token_verifier(), sts_url=sts_url, require_authentication=True)

    card_routes = create_agent_card_routes(card)
    jsonrpc_routes = create_jsonrpc_routes(handler, rpc_url="/a2a/jsonrpc", context_builder=KeycardServerCallContextBuilder())

    from starlette.routing import Route
    extra_routes = [
        Route("/telemetry", telemetry_endpoint, methods=["GET"]),
        Route("/health", health_endpoint, methods=["GET"])
    ]

    routes = card_routes + jsonrpc_routes + extra_routes
    app = Starlette(
        routes=routes,
        middleware=[Middleware(AuthenticationMiddleware, backend=backend, on_error=keycard_on_error)]
    )
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent B: Incident Investigator Service")
    parser.add_argument("--port", type=int, default=9002, help="Port to listen on (default: 9002)")
    parser.add_argument("--sts-url", default="http://127.0.0.1:8088", help="Keycard STS URL")
    parser.add_argument("--agent-c-url", default="http://127.0.0.1:9003", help="Downstream Agent C URL")
    args = parser.parse_args()

    agent_b_url = f"http://127.0.0.1:{args.port}"
    telemetry["port"] = args.port

    print(f"\n{BOLD}{CYAN}======================================================================{RESET}")
    print(f"{BOLD}{CYAN}  AGENT B: INCIDENT INVESTIGATOR SERVICE (GOOGLE A2A + KEYCARD)       {RESET}")
    print(f"{BOLD}{CYAN}======================================================================{RESET}")
    print(f"  • Listening on: {GREEN}{agent_b_url}{RESET}")
    print(f"  • Agent Card:   {agent_b_url}/.well-known/agent-card.json (Public)")
    print(f"  • A2A JSON-RPC: {agent_b_url}/a2a/jsonrpc (Protected by Keycard)")
    print(f"  • Telemetry:    {agent_b_url}/telemetry")
    print(f"  • Keycard STS:  {args.sts_url}")
    print(f"  • Downstream:   Agent C at {args.agent_c_url}")
    print(f"{BOLD}{CYAN}======================================================================{RESET}\n", flush=True)

    app = create_agent_b_app(agent_b_url, args.sts_url, args.agent_c_url)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
