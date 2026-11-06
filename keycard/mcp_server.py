#!/usr/bin/env python3
"""
Keycard Quickstart FastMCP Server
Reference: https://docs.keycard.ai/guides/quickstart/
Uses the official 'keycardai-fastmcp' package to secure an MCP server
and perform delegated token exchange without static credentials.
"""

from fastmcp import FastMCP
from keycardai.fastmcp import AuthProvider, AccessContext

# 1. Initialize Keycard AuthProvider
# (When live, zone_url will be https://<zone_id>.keycard.cloud)
auth_provider = AuthProvider(
    zone_url="http://127.0.0.1:8088",
    mcp_server_url="http://localhost:8000/",
    mcp_server_name="My GitHub Tools"
)

# 2. Attach Keycard's remote authentication handler to FastMCP
mcp = FastMCP(
    "My GitHub Tools",
    auth=auth_provider.get_remote_auth_provider()
)

# 3. Define the 'list_my_repos' tool with delegated access to GitHub
@mcp.tool()
@auth_provider.grant("https://api.github.com")
async def list_my_repos(
    user_id: str = "alice",
    access: AccessContext = None
) -> dict:
    """Fetch user repositories via Keycard delegated token exchange."""
    if access.has_errors():
        return {
            "status": "error",
            "message": f"Keycard delegation error: {access.get_errors()}"
        }

    # Extract the delegated ephemeral token for GitHub
    token_obj = access.access("https://api.github.com")
    delegated_token = token_obj.access_token if token_obj else None

    # In production, the agent uses this token to query https://api.github.com/user/repos
    return {
        "status": "success",
        "user": user_id,
        "granted_resource": "https://api.github.com",
        "delegated_token_preview": f"{delegated_token[:15]}..." if delegated_token else "injected_token",
        "repositories": [
            {"id": 101, "name": "ai-agent-platform", "private": True, "stars": 34},
            {"id": 102, "name": "keycard-runtime-demo", "private": False, "stars": 18},
            {"id": 103, "name": "secure-mcp-tools", "private": True, "stars": 95}
        ]
    }


if __name__ == "__main__":
    print("Starting Keycard FastMCP Server on http://localhost:8000 ...")
    mcp.run(transport="sse", port=8000)
