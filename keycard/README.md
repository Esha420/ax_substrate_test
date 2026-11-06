# Keycard Runtime Security & FastMCP Quickstart Showcase

This directory provides a complete, working implementation of:
1. **The 5 Core Runtime Security Features** via raw `curl` commands.
2. **The Official Keycard FastMCP Quickstart** ([docs.keycard.ai/guides/quickstart](https://docs.keycard.ai/guides/quickstart/)) using the real `keycardai-fastmcp` Python package, runnable immediately without waiting for `console.keycard.ai` console approval.

---

### Key Components

* [`keycard_server.py`](file:///home/berrybytes/Office/Assignment/keycard/keycard_server.py): Standards-compliant Keycard STS with RFC 8414 OAuth 2.0 discovery (`/.well-known/oauth-authorization-server`), JWKS (`/oauth/jwks`), RFC 8693 token exchange, and revocation.
* [`mcp_server.py`](file:///home/berrybytes/Office/Assignment/keycard/mcp_server.py): The official Quickstart FastMCP server using `keycardai.fastmcp.AuthProvider` and `@auth_provider.grant("https://api.github.com")`.
* [`test_quickstart.py`](file:///home/berrybytes/Office/Assignment/keycard/test_quickstart.py): Test script that executes the FastMCP `list_my_repos` tool with automated token exchange.
* [`demo.sh`](file:///home/berrybytes/Office/Assignment/keycard/demo.sh): Automated runner for the 5 core `curl` commands.

---

### Quickstart

#### 1. Start the Local Keycard STS Server
```bash
cd /home/berrybytes/Office/Assignment/keycard
.venv/bin/python keycard_server.py 8088
```
*(Runs on `http://127.0.0.1:8088`)*

#### 2. Test the Official Keycard FastMCP Quickstart Tool
```bash
.venv/bin/python test_quickstart.py
```
**What happens:**
1. Issues an ephemeral token for user `alice`.
2. The `@auth_provider.grant("https://api.github.com")` decorator from `keycardai-fastmcp` intercepts the tool call.
3. Performs an automated RFC 8693 Token Exchange against Keycard STS for `https://api.github.com`.
4. Executes `list_my_repos` using the injected, ephemeral token without static secrets.

#### 3. Run the 5 Core `curl` Commands Showcase
```bash
./demo.sh
```
Shows credential minting, A2A delegation, nested `act` claims inspection, 403 policy blocking, and instant revocation.
