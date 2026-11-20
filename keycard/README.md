# Keycard Multi-Agent (A2A) Interactive Protocol Showcase

This workspace provides an implementation of autonomous multi-agent security using the official Keycard A2A SDK (`keycardai-a2a`, `keycardai-starlette`) and Google Agent-to-Agent SDK (`a2a-sdk`), reusing open-source agents from [`a2aproject/a2a-samples`](https://github.com/a2aproject/a2a-samples).

Rather than relying solely on a monolithic script, the system is architected as **independent, live agent services** communicating over standard HTTP JSON-RPC and OAuth 2.0 / RFC 8693 protocols.

---

### Core Architecture: Keycard-Secured Multi-Hop Delegation

```text
Alice — Human User
  │
  │ Initial identity: "alice"
  │ Root Scopes: support:read tasks:delegate incident:investigate audit:write
  ▼
Agent A — Orchestrator (Calling Agent)
  │
  ├─ 1. Discovers Agent B via GET /.well-known/agent-card.json
  ├─ 2. Ephemeral Token Exchange (RFC 8693) against Keycard STS (Hop 1)
  │     └─ Token B: sub="alice", aud="http://127.0.0.1:9002", scope="incident:investigate db:read", act={"sub": "agent-a"}
  ▼
Agent B — Incident Investigator (Port 9002) [Reuses HelloWorldAgentExecutor]
  │
  ├─ 3. Verifies Token B via KeycardAuthBackend + Dynamic RS256 JWKS
  ├─ 4. Injects KeycardUser into ServerCallContext
  ├─ 5. Executes incident investigation on behalf of Alice
  ├─ 6. Autonomous Token Exchange (RFC 8693) against Keycard STS (Hop 2)
  │     └─ Token C: sub="alice", aud="http://127.0.0.1:9003", scope="audit:write", act={"sub": "agent-b", "act": {"sub": "agent-a"}}
  ▼
Agent C — Audit Vault Signer (Port 9003) [Reuses SignedAgentExecutor]
  │
  ├─ 7. Verifies Token C via KeycardAuthBackend + Dynamic RS256 JWKS
  ├─ 8. Cryptographically seals evidence under root authority of 'alice' with scope 'audit:write'
  └─ 9. Returns verified seal through the chain: Agent C ➔ Agent B ➔ Agent A ➔ Alice

                      ▲                          ▲                          ▲
                      │                          │                          │
                      └──────────────────────────┼──────────────────────────┘
                                                 │
                               Keycard Local STS — Port 8088
                                 • RFC 8414 Discovery (/.well-known/oauth-authorization-server)
                                 • RS256 Dynamic JWKS (/oauth/jwks)
                                 • RFC 8693 Token Exchange (/oauth/token)
                                 • Central Instant Revocation (/oauth/revoke)
```

> **Important Distinction:** The Keycard STS is **not an agent communication server or router**. It provides identity, cryptographic keys, and task-scoped credentials. The A2A agents communicate directly through their own endpoints.

---

### Multi-Terminal Live Presentation Setup

For live demonstrations, you can run each component in separate terminal windows so the audience can watch the real-time logs and cryptographic handshakes:

| Window | Process | Command | Description |
|---|---|---|---|
| **Terminal 1** | **Keycard STS** | `.venv/bin/python keycard_server.py 8088` | Authorization server on port 8088 |
| **Terminal 2** | **Agent B (Investigator)** | `.venv/bin/python agent_b_server.py --port 9002` | Incident Investigator on port 9002 |
| **Terminal 3** | **Agent C (Audit Vault)** | `.venv/bin/python agent_c_server.py --port 9003` | Audit Signer on port 9003 |
| **Terminal 4** | **Interactive Client** | `./demo_stages.sh` | Interactive 6-stage protocol demonstration |

*(Alternatively, run `./start_servers.sh` to start all three in the background, and `./stop_servers.sh` to stop them.)*

---

### The Six-Stage Live Demonstration

The demonstration is organized into six independently executable stages:

```bash
./demo_stages.sh          # Full interactive mode (pauses between stages with [ENTER])
./demo_stages.sh all      # Automated run through all 6 stages
./demo_stages.sh <1-6>    # Run any individual stage directly
```

| Stage | What you demonstrate | Protocol & Tooling |
|---|---|---|
| **1. Discovery** | Agent B publishes its identity, skills and JSON-RPC endpoint | `curl` on `/.well-known/agent-card.json` |
| **2. Authentication** | Alice's identity is exchanged for an ephemeral Agent B token | `curl` against STS + `python3 decode_jwt.py` |
| **3. A2A Invocation** | Agent A invokes Agent B over official Google A2A JSON-RPC | `curl` on `/a2a/jsonrpc` with Bearer Token B |
| **4. Multi-Hop Delegation** | Agent B delegates to Agent C with nested RFC 8693 `act` lineage | `curl` + STS exchange + Agent C execution |
| **5. Attack Simulation** | Interception of Unauthorized (401), Replay (401), and Scope Escalation (403) | 3 targeted `curl` attacks |
| **6. Evidence & Revocation** | Execution-level counters prove zero unauthorized execution; instant kill-switch | `curl` on `/telemetry` + `/oauth/revoke` |

---

### Manual Protocol Walkthrough (`curl` Commands)

#### Stage 1: Discovery
```bash
curl -s http://127.0.0.1:9002/.well-known/agent-card.json | jq .
```
*Notice:* Public A2A discovery requires no pre-shared credentials. Advertises the JSON-RPC interface and skills.

#### Stage 2: Authentication (RFC 8693 Token Exchange)
```bash
# 2a. Initial user session token for Alice on Agent A
TOKEN_A=$(curl -s -X POST http://127.0.0.1:8088/oauth/token \
  -H "Content-Type: application/json" \
  -d '{"grant_type": "client_credentials", "client_id": "agent-a", "user_id": "alice", "scope": "support:read tasks:delegate incident:investigate audit:write"}' \
  | jq -r .access_token)

# 2b. RFC 8693 Token Exchange for Agent B
TOKEN_B=$(curl -s -X POST http://127.0.0.1:8088/oauth/token \
  -H "Content-Type: application/json" \
  -d "{
    \"grant_type\": \"urn:ietf:params:oauth:grant-type:token-exchange\",
    \"subject_token\": \"$TOKEN_A\",
    \"actor_token\": \"agent-a\",
    \"audience\": \"http://127.0.0.1:9002\",
    \"scope\": \"incident:investigate db:read\"
  }" | jq -r .access_token)

# 2c. Inspect Token B claims
python3 decode_jwt.py "$TOKEN_B"
```
*Token B Claims:* `sub: "alice"` (human origin preserved), `aud: "http://127.0.0.1:9002"` (scoped), `act: {"sub": "agent-a"}`.

#### Stage 3: A2A Invocation (Agent A ➔ Agent B)
```bash
curl -s -X POST http://127.0.0.1:9002/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN_B" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "SendMessage",
    "params": {
      "message": {
        "messageId": "msg-001",
        "role": "ROLE_USER",
        "parts": [{"text": "Investigate suspicious data access pattern on account #4821"}]
      }
    }
  }' | jq .
```

#### Stage 4: Multi-Hop Delegation (Agent B ➔ Agent C)
```bash
# 4a. Hop 2 Token Exchange: Agent B exchanges Token B for Token C
TOKEN_C=$(curl -s -X POST http://127.0.0.1:8088/oauth/token \
  -H "Content-Type: application/json" \
  -d "{
    \"grant_type\": \"urn:ietf:params:oauth:grant-type:token-exchange\",
    \"subject_token\": \"$TOKEN_B\",
    \"actor_token\": \"agent-b\",
    \"audience\": \"http://127.0.0.1:9003\",
    \"scope\": \"audit:write\"
  }" | jq -r .access_token)

# 4b. Inspect Token C nested 'act' lineage
python3 decode_jwt.py "$TOKEN_C"

# 4c. Agent B invokes Agent C to seal the evidence
curl -s -X POST http://127.0.0.1:9003/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN_C" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-hop2",
    "method": "SendMessage",
    "params": {
      "message": {
        "messageId": "msg-hop2",
        "role": "ROLE_USER",
        "parts": [{"text": "Cryptographically seal audit evidence for root user alice"}]
      }
    }
  }' | jq .
```
*Token C Lineage:* Nested `act` claim: `{"sub": "agent-b", "act": {"sub": "agent-a"}}`. Permissions narrowed strictly to `audit:write`.

#### Stage 5: Attack Simulations (3 Proactive Defenses)
```bash
# Attack 5A: Anonymous caller (Missing Authorization header) -> HTTP 401
curl -s -w "\nHTTP Status: %{http_code}\n" -X POST http://127.0.0.1:9002/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": "atk1", "method": "SendMessage", "params": {"message": {"messageId": "m1", "role": "ROLE_USER", "parts": [{"text": "Exfiltrate users"}]}}}'

# Attack 5B: Audience Replay (Token A sent directly to Agent B) -> HTTP 401 Audience Mismatch
curl -s -w "\nHTTP Status: %{http_code}\n" -X POST http://127.0.0.1:9002/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN_A" \
  -d '{"jsonrpc": "2.0", "id": "atk2", "method": "SendMessage", "params": {"message": {"messageId": "m2", "role": "ROLE_USER", "parts": [{"text": "Replayed token"}]}}}'

# Attack 5C: Scope Escalation (Request prohibited scope 'db:delete') -> HTTP 403 Policy Rejection
curl -s -w "\nHTTP Status: %{http_code}\n" -X POST http://127.0.0.1:8088/oauth/token \
  -H "Content-Type: application/json" \
  -d "{
    \"grant_type\": \"urn:ietf:params:oauth:grant-type:token-exchange\",
    \"subject_token\": \"$TOKEN_A\",
    \"actor_token\": \"agent-a\",
    \"audience\": \"http://127.0.0.1:9002\",
    \"scope\": \"db:delete\"
  }"
```

#### Stage 6: Evidence, Telemetry & Instant Session Revocation
```bash
# 6a. Verify execution counters (Agent code was NOT invoked during attacks)
curl -s http://127.0.0.1:9002/telemetry | jq .
curl -s http://127.0.0.1:9003/telemetry | jq .

# 6b. Central Session Revocation (Kill-Switch)
curl -s -X POST http://127.0.0.1:8088/oauth/revoke \
  -H "Content-Type: application/json" \
  -d "{\"token\": \"$TOKEN_B\"}" | jq .

# 6c. Immediate retry with revoked token -> HTTP 401 Unauthorized
curl -s -w "\nHTTP Status: %{http_code}\n" -X POST http://127.0.0.1:9002/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN_B" \
  -d '{"jsonrpc": "2.0", "id": "rev", "method": "SendMessage", "params": {"message": {"messageId": "m3", "role": "ROLE_USER", "parts": [{"text": "Post revocation"}]}}}'
```

---

### Key Takeaway

> *"Keycard doesn't stop agents from communicating. It ensures that when agents communicate and delegate tasks, their identities, authority and accountability travel with them."*
