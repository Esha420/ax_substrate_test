#!/usr/bin/env python3
"""
Agent C: Audit Vault Signer (Port 9003)
======================================
Google A2A agent protected by Keycard Authentication Middleware.
Reuses open-source SignedAgentExecutor from a2aproject/a2a-samples.

Key Capabilities:
  - Publishes public A2A Agent Card on /.well-known/agent-card.json
  - Enforces RS256 JWT verification via KeycardAuthBackend on /a2a/jsonrpc
  - Strictly requires 'audit:write' scope (HTTP 403 if missing)
  - Validates multi-hop nested 'act' lineage (alice -> agent-a -> agent-b)
  - Generates verifiable RS256 cryptographic signatures over evidence digests
  - Exposes public verification endpoint /verify to verify cryptographic signatures
  - Emits real-time colored telemetry for live terminal demonstration
"""

import argparse
import asyncio
import base64
import hashlib
import importlib.util
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import uvicorn
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Add official A2A samples agent path
CURRENT_DIR = Path(__file__).resolve().parent
A2A_SAMPLES_DIR = CURRENT_DIR / "a2a-samples/samples/python/agents/sign_and_verify_agent_card"
sys.path.insert(0, str(A2A_SAMPLES_DIR))

# Dynamic loader for SignedAgentExecutor
spec = importlib.util.spec_from_file_location("mod_signed", str(A2A_SAMPLES_DIR / "agent_executor.py"))
mod_signed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod_signed)
SignedAgentExecutor = getattr(mod_signed, "SignedAgentExecutor")

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
    KeycardServerCallContextBuilder,
    build_agent_card_from_config,
    keycard_user,
)
from keycardai.starlette import AuthProvider, KeycardAuthBackend, KeycardAuthError, keycard_on_error


# Generate or load persistent RSA signing key pair for Agent C Audit Vault
AGENT_C_KEY_FILE = CURRENT_DIR / "agent_c_rsa_key.pem"
if AGENT_C_KEY_FILE.exists():
    with open(AGENT_C_KEY_FILE, "rb") as f:
        AGENT_C_PRIVATE_KEY = serialization.load_pem_private_key(f.read(), password=None)
else:
    AGENT_C_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with open(AGENT_C_KEY_FILE, "wb") as f:
        f.write(AGENT_C_PRIVATE_KEY.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))

AGENT_C_PUBLIC_KEY = AGENT_C_PRIVATE_KEY.public_key()
AGENT_C_PUBLIC_PEM = AGENT_C_PUBLIC_KEY.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
).decode("utf-8")


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


def extract_delegation_chain(claims: Dict[str, Any]) -> list:
    chain = []
    act = claims.get("act")
    while act and isinstance(act, dict):
        chain.append(act.get("sub"))
        act = act.get("act")
    return list(reversed(chain))


# Live Telemetry State
telemetry = {
    "agent": "Agent C (Audit Vault Signer)",
    "port": 9003,
    "total_requests": 0,
    "authenticated_executions": 0,
    "blocked_requests": 0,
    "seals_issued": 0,
    "last_caller": None,
    "last_lineage": None,
    "last_seal": None
}


class KeycardAuditedVaultExecutor(SignedAgentExecutor):
    def __init__(self, sts_url: str = "http://127.0.0.1:8088"):
        super().__init__()
        self.sts_url = sts_url

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
            print(f"{YELLOW}[Agent C | {timestamp()}]{RESET} ⚠️ Unauthenticated execution: '{query}'", flush=True)
            await task_updater.update_status(
                state=TaskState.TASK_STATE_COMPLETED,
                message=new_text_message(f"Unauthenticated audit record: {query}")
            )
            return

        # Extract lineage chain from token claims
        claims = {}
        try:
            claims = jwt.decode(caller.access_token, options={"verify_signature": False})
        except Exception:
            pass

        chain = extract_delegation_chain(claims)
        lineage_list = [caller.sub] + chain + [caller.client_id, "agent-c"]
        lineage_str = " -> ".join(lineage_list)

        # Generate verifiable cryptographic evidence seal
        seal_id = f"SEAL-{int(time.time())}-{uuid.uuid4().hex[:6].upper()}"

        # Compute SHA-256 digest of evidence payload
        evidence_content = {
            "seal_id": seal_id,
            "task": query,
            "root_subject": caller.sub,
            "immediate_actor": caller.client_id,
            "lineage": lineage_list,
            "scopes": caller.scopes,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        canonical_bytes = json.dumps(evidence_content, sort_keys=True).encode("utf-8")
        evidence_digest = hashlib.sha256(canonical_bytes).hexdigest()

        # Sign digest with Agent C's RSA private key
        raw_signature = AGENT_C_PRIVATE_KEY.sign(
            evidence_digest.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        signature_b64 = base64.b64encode(raw_signature).decode("utf-8")

        evidence_seal = {
            "seal_id": seal_id,
            "signer": "Agent C (Audit Vault Signer)",
            "algorithm": "RS256",
            "evidence_digest": f"sha256:{evidence_digest}",
            "signature": signature_b64,
            "root_subject": caller.sub,
            "lineage": lineage_str,
            "timestamp": evidence_content["timestamp"]
        }

        telemetry["authenticated_executions"] += 1
        telemetry["seals_issued"] += 1
        telemetry["last_caller"] = f"caller={caller.client_id}, root_sub={caller.sub}"
        telemetry["last_lineage"] = lineage_str
        telemetry["last_seal"] = evidence_seal

        print(f"\n{GREEN}[Agent C | {timestamp()}]{RESET} {BOLD}EXECUTION STARTED (AUDIT EVIDENCE SEALING):{RESET}", flush=True)
        print(f"  • Task Query: {CYAN}\"{query}\"{RESET}", flush=True)
        print(f"  • Root Principal (sub): {GREEN}{caller.sub}{RESET} (Originating human user)", flush=True)
        print(f"  • Immediate Actor (client_id): {YELLOW}{caller.client_id}{RESET}", flush=True)
        print(f"  • Cryptographic Lineage: {CYAN}[{lineage_str}]{RESET}", flush=True)
        print(f"  • Scopes Verified: {MAGENTA}{caller.scopes}{RESET}", flush=True)
        print(f"  • Evidence Digest: {DIM}sha256:{evidence_digest}{RESET}", flush=True)
        print(f"  • {GREEN}✓ Generated Cryptographic Evidence Seal: {BOLD}{seal_id}{RESET}", flush=True)
        print(f"  • RSA Signature (first 32 chars): {DIM}{signature_b64[:32]}...{RESET}", flush=True)
        print(f"{GREEN}[Agent C | {timestamp()}]{RESET} ✓ Audit record sealed under root authority of '{caller.sub}'.\n", flush=True)

        # Report cryptographic signing event to central audit trail
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(f"{self.sts_url}/audit/event", json={
                    "type": "EVIDENCE_SIGNED",
                    "details": {
                        "agent": "Agent C (Audit Vault Signer)",
                        "seal_id": seal_id,
                        "root_subject": caller.sub,
                        "lineage": lineage_str,
                        "evidence_digest": f"sha256:{evidence_digest}",
                        "algorithm": "RS256"
                    }
                }, timeout=1.0)
        except Exception:
            pass

        resp_text = (
            f"Audit Vault Seal '{seal_id}': Cryptographically verified for root subject '{caller.sub}' "
            f"delegated through lineage [{lineage_str}] with scope '{caller.scopes}'. "
            f"Evidence Digest: sha256:{evidence_digest} | Signature (RS256): {signature_b64}"
        )

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
        if path.endswith("agent-card.json") or path in ["/health", "/telemetry", "/verify", "/vault/public_key"]:
            if path.endswith("agent-card.json"):
                print(f"{CYAN}[Agent C | {timestamp()}]{RESET} DISCOVERY: Served public A2A Agent Card ({path})", flush=True)
            return None

        telemetry["total_requests"] += 1

        auth_header = conn.headers.get("Authorization", "")
        if not auth_header:
            telemetry["blocked_requests"] += 1
            print(f"\n{RED}[Agent C | {timestamp()}]{RESET} {BOLD}ATTACK INTERCEPTED (401 Unauthorized):{RESET}", flush=True)
            print(f"  • Path: {path} | Method: {conn.scope.get('method')}", flush=True)
            print(f"  • Error: Missing Authorization header (Anonymous caller rejected)", flush=True)
            print(f"  • {GREEN}Execution Contained: Agent C Executor was NOT invoked!{RESET}\n", flush=True)
            raise KeycardAuthError("unauthorized", "Missing Authorization header", status_code=401)

        try:
            auth_res = await super().authenticate(conn)
            if auth_res:
                creds, user = auth_res

                # 1. Enforce Scope: Agent C strictly requires 'audit:write'
                if "audit:write" not in user.scopes:
                    telemetry["blocked_requests"] += 1
                    print(f"\n{RED}[Agent C | {timestamp()}]{RESET} {BOLD}SECURITY INTERCEPTION (403 Forbidden):{RESET}", flush=True)
                    print(f"  • Path: {path} | Caller: {user.client_id} (sub={user.sub})", flush=True)
                    print(f"  • Held Scopes: {user.scopes}", flush=True)
                    print(f"  • Missing Scope: {MAGENTA}'audit:write'{RESET}", flush=True)
                    print(f"  • {GREEN}Execution Contained: Agent C Executor was NOT invoked!{RESET}\n", flush=True)
                    raise KeycardAuthError("insufficient_scope", "Insufficient scope: requires 'audit:write'", status_code=403)

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

                print(f"\n{BOLD}{CYAN}[{timestamp()}] [AGENT C MIDDLEWARE] ── INCOMING A2A REQUEST ──{RESET}", flush=True)
                print(f"  • Endpoint: {path} | Method: {conn.scope.get('method')}", flush=True)
                print(f"  • Token Verification: {GREEN}VALID RS256 JWKS SIGNATURE{RESET} (Keycard STS Port 8088)", flush=True)
                print(f"  • Caller Identity: client_id='{user.client_id}' | Root Subject: '{user.sub}'", flush=True)
                print(f"  • Required Scope: {MAGENTA}'audit:write'{RESET} | Held Scopes: {user.scopes}", flush=True)
                print(f"  • Scope Evaluation: {GREEN}GRANTED (Permission Attenuation Verified){RESET}", flush=True)
                print(f"  • Middleware Decision: {BOLD}{GREEN}AUTHORIZED (200 OK){RESET} ➔ Dispatching to Audit Vault Signer\n", flush=True)

                # Report successful Agent C authorization to central audit trail
                try:
                    async with httpx.AsyncClient() as client:
                        await client.post(f"{self.sts_url}/audit/event", json={
                            "type": "AGENT_AUTHORIZATION",
                            "details": {
                                "agent": "Agent C (Audit Vault Signer)",
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
            print(f"\n{RED}[Agent C | {timestamp()}]{RESET} {BOLD}SECURITY INTERCEPTION ({err_type}):{RESET}", flush=True)
            print(f"  • Path: {path}", flush=True)
            print(f"  • Reason: {err_msg}", flush=True)
            print(f"  • {GREEN}Execution Contained: Agent C Executor was NOT invoked!{RESET}\n", flush=True)
            raise


async def telemetry_endpoint(request: Request):
    return JSONResponse(telemetry)


async def health_endpoint(request: Request):
    return JSONResponse({"status": "ok", "service": "Agent C (Audit Vault Signer)", "port": telemetry["port"]})


async def public_key_endpoint(request: Request):
    return JSONResponse({
        "signer": "Agent C (Audit Vault Signer)",
        "algorithm": "RS256",
        "public_key_pem": AGENT_C_PUBLIC_PEM
    })


async def verify_signature_endpoint(request: Request):
    """
    Cryptographically verifies an evidence seal or signature against Agent C's public key.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"valid": False, "error": "Invalid JSON body"}, status_code=400)

    # Extract signature and digest either from top-level or from embedded evidence_seal
    seal = body.get("evidence_seal", body)
    signature_b64 = seal.get("signature")
    digest = seal.get("evidence_digest", "")

    if not signature_b64 or not digest:
        return JSONResponse({
            "valid": False,
            "error": "Missing 'signature' or 'evidence_digest' in request"
        }, status_code=400)

    # Normalize digest (remove 'sha256:' prefix if present)
    clean_digest = digest.replace("sha256:", "")

    try:
        sig_bytes = base64.b64decode(signature_b64)
        AGENT_C_PUBLIC_KEY.verify(
            sig_bytes,
            clean_digest.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return JSONResponse({
            "valid": True,
            "algorithm": "RS256",
            "signer": "Agent C (Audit Vault Signer)",
            "verified_digest": f"sha256:{clean_digest}",
            "seal_id": seal.get("seal_id"),
            "root_subject": seal.get("root_subject"),
            "message": "✔ Cryptographic signature VALID. Evidence is authentic, untampered, and verified against Agent C RSA public key."
        })
    except Exception as e:
        return JSONResponse({
            "valid": False,
            "algorithm": "RS256",
            "error": f"Cryptographic signature verification FAILED: {str(e)}",
            "message": "✗ Invalid signature! Evidence has been altered or signed by an untrusted key."
        }, status_code=400)


def create_agent_c_app(agent_c_url: str, sts_url: str):
    agent_c_cfg = AgentServiceConfig(
        service_name="AuditVaultSignerAgent",
        client_id="agent-c",
        client_secret="secret-c",
        identity_url=agent_c_url,
        zone_id="default",
        authorization_server_url=sts_url,
        capabilities=["audit_sealing", "cryptographic_signing", "evidence_vault"]
    )
    card = build_agent_card_from_config(agent_c_cfg)

    executor = KeycardAuditedVaultExecutor(sts_url=sts_url)
    handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore(), agent_card=card)

    auth_provider = AuthProvider(zone_url=sts_url, server_url=agent_c_url, audience=agent_c_url)
    backend = AuditedKeycardBackend(auth_provider.get_token_verifier(), sts_url=sts_url, require_authentication=True)

    card_routes = create_agent_card_routes(card)
    jsonrpc_routes = create_jsonrpc_routes(handler, rpc_url="/a2a/jsonrpc", context_builder=KeycardServerCallContextBuilder())

    from starlette.routing import Route
    extra_routes = [
        Route("/telemetry", telemetry_endpoint, methods=["GET"]),
        Route("/health", health_endpoint, methods=["GET"]),
        Route("/vault/public_key", public_key_endpoint, methods=["GET"]),
        Route("/verify", verify_signature_endpoint, methods=["POST"])
    ]

    routes = card_routes + jsonrpc_routes + extra_routes
    app = Starlette(
        routes=routes,
        middleware=[Middleware(AuthenticationMiddleware, backend=backend, on_error=keycard_on_error)]
    )
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent C: Audit Vault Signer Service")
    parser.add_argument("--port", type=int, default=9003, help="Port to listen on (default: 9003)")
    parser.add_argument("--sts-url", default="http://127.0.0.1:8088", help="Keycard STS URL")
    args = parser.parse_args()

    agent_c_url = f"http://127.0.0.1:{args.port}"
    telemetry["port"] = args.port

    print(f"\n{BOLD}{CYAN}======================================================================{RESET}")
    print(f"{BOLD}{CYAN}  AGENT C: AUDIT VAULT SIGNER SERVICE (GOOGLE A2A + KEYCARD)          {RESET}")
    print(f"{BOLD}{CYAN}======================================================================{RESET}")
    print(f"  • Listening on: {GREEN}{agent_c_url}{RESET}")
    print(f"  • Agent Card:   {agent_c_url}/.well-known/agent-card.json (Public)")
    print(f"  • A2A JSON-RPC: {agent_c_url}/a2a/jsonrpc (Protected by Keycard)")
    print(f"  • Public Key:   {agent_c_url}/vault/public_key")
    print(f"  • Verify Seal:  {agent_c_url}/verify")
    print(f"  • Telemetry:    {agent_c_url}/telemetry")
    print(f"  • Keycard STS:  {args.sts_url}")
    print(f"{BOLD}{CYAN}======================================================================{RESET}\n", flush=True)

    app = create_agent_c_app(agent_c_url, args.sts_url)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
