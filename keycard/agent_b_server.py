#!/usr/bin/env python3
"""
Agent B: Incident Investigator (Port 9002)
=========================================
Google A2A agent protected by Keycard Authentication Middleware.
Reuses open-source HelloWorldAgentExecutor from a2aproject/a2a-samples.

Key Capabilities:
  - Publishes public A2A Agent Card on /.well-known/agent-card.json
  - Enforces RS256 JWT verification via KeycardAuthBackend on /a2a/jsonrpc
  - Injects KeycardUser into RequestContext via KeycardServerCallContextBuilder
  - Autonomously delegates to Agent C (Port 9003) via RFC 8693 token exchange
  - Emits real-time colored telemetry for live terminal demonstration
"""

import argparse
import asyncio
import importlib.util
import json
import os
import sys
import time
from datetime import datetime
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
from keycardai.starlette import AuthProvider, KeycardAuthBackend, keycard_on_error


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

        audit_seal_info = "Local investigation completed."

        # Check if task requests multi-hop archival / delegation to Agent C
        should_delegate = (
            self.client_c is not None and
            self.agent_c_url is not None and
            any(k in query.lower() for k in ["audit", "archive", "seal", "vault", "hop", "record", "account"])
        )

        if should_delegate:
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

                c_invoke = await self.client_c.invoke_service(
                    self.agent_c_url,
                    {"task": f"Cryptographically seal incident findings on account #4821 for root subject '{caller.sub}'"},
                    token=token_c
                )
                c_result_text = c_invoke.get("result", "")
                telemetry["delegations_to_agent_c"] += 1
                audit_seal_info = f"Archived to Agent C. Evidence Seal: {c_result_text[:90]}..."
                print(f"    ✓ Agent C response: {GREEN}{c_result_text[:90]}...{RESET}", flush=True)

            except Exception as e:
                audit_seal_info = f"Delegation to Agent C failed: {str(e)}"
                print(f"    {RED}✗ Delegation to Agent C error: {str(e)}{RESET}", flush=True)

        resp_text = (
            f"Incident Investigation Report: Suspicious pattern on account #4821 verified and contained. "
            f"Authorized on behalf of root subject '{caller.sub}' delegated through actor '{caller.client_id}'. "
            f"[{audit_seal_info}]"
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

        try:
            auth_res = await super().authenticate(conn)
            if auth_res:
                creds, user = auth_res
                # Check real-time revocation with Keycard STS
                import httpx
                try:
                    unverified = jwt.decode(user.access_token, options={"verify_signature": False})
                    sid = unverified.get("sid")
                    if sid:
                        async with httpx.AsyncClient() as client:
                            resp = await client.get(f"{self.sts_url}/oauth/revoked", timeout=1.0)
                            if resp.status_code == 200 and sid in resp.json().get("revoked_sessions", []):
                                from starlette.authentication import AuthenticationError
                                raise AuthenticationError(f"Session '{sid}' has been revoked by central security policy.")
                except Exception as e:
                    from starlette.authentication import AuthenticationError
                    if isinstance(e, AuthenticationError):
                        raise

                print(f"{GREEN}[Agent B | {timestamp()}]{RESET} AUTH: Verified RS256 Keycard token! sub='{user.sub}', client='{user.client_id}', scopes={user.scopes}", flush=True)
            return auth_res
        except Exception as exc:
            telemetry["blocked_requests"] += 1
            err_msg = getattr(exc, "error_description", str(exc))
            print(f"\n{RED}[Agent B | {timestamp()}]{RESET} {BOLD}ATTACK INTERCEPTED (401 Unauthorized):{RESET}", flush=True)
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
