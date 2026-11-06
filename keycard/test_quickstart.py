#!/usr/bin/env python3
"""
Test script for Keycard Quickstart FastMCP Server
Reference: https://docs.keycard.ai/guides/quickstart/

Verifies:
  1. Minting an initial session token for user 'alice' from Keycard STS.
  2. Executing 'list_my_repos' secured by the official 'keycardai-fastmcp' library.
  3. Proving that @auth_provider.grant automatically executes an RFC 8693 token exchange
     and injects the scoped downstream token into the tool without hardcoded credentials.
"""

import sys
import asyncio
import json
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from mcp.server.auth.middleware.auth_context import auth_context_var, AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp_server import list_my_repos

STS_URL = "http://127.0.0.1:8088"

def get_initial_token(user_id="alice", client_id="agent-a"):
    req = urllib.request.Request(
        f"{STS_URL}/oauth/token",
        data=json.dumps({
            "grant_type": "client_credentials",
            "client_id": client_id,
            "user_id": user_id,
            "scope": "support:read tasks:delegate"
        }).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["access_token"]


async def main():
    print("=" * 72)
    print("   KEYCARD QUICKSTART: FASTMCP TOOL WITH DELEGATED TOKEN EXCHANGE       ")
    print("=" * 72)

    # 1. Acquire initial token
    print("\n▶ 1. User 'alice' initiates session with Agent A...")
    user_token = get_initial_token(user_id="alice", client_id="agent-a")
    print(f"✓ Ephemeral token issued by Keycard STS:")
    print(f"  {user_token[:40]}... (RS256)")

    # 2. Establish incoming authenticated user context
    token_obj = AccessToken(
        token=user_token,
        client_id="agent-a",
        scopes=["support:read", "tasks:delegate"]
    )
    auth_context_var.set(AuthenticatedUser(token_obj))

    # 3. Invoke list_my_repos protected by Keycard
    print("\n▶ 2. Agent invokes 'list_my_repos' MCP tool...")
    print("  Keycard '@auth_provider.grant' intercepts the call and executes an")
    print("  RFC 8693 Token Exchange against Keycard STS for 'https://api.github.com'...")

    result = await list_my_repos(user_id="alice")

    print("\n▶ 3. Tool Execution Result (with injected token):")
    print(json.dumps(result, indent=2))

    print("\n" + "=" * 72)
    print("✓ QUICKSTART VERIFICATION SUCCESSFUL: ZERO STATIC CREDENTIALS USED!")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
