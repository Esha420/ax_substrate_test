# Keycard Multi-Agent (A2A) Interactive Protocol Showcase

This workspace provides an implementation of autonomous multi-agent security using the official Keycard A2A SDK (`keycardai-a2a`, `keycardai-starlette`) and Google Agent-to-Agent SDK (`a2a-sdk`), reusing open-source agents from [`a2aproject/a2a-samples`](https://github.com/a2aproject/a2a-samples).

Rather than relying on a hardcoded or simulated scenario, the system is architected as **independent, live agent services** communicating over standard HTTP JSON-RPC and OAuth 2.0 / RFC 8693 protocols with **dynamic task execution**, **runtime authorization visibility**, **cryptographic evidence sealing with verification**, and **strict delegation boundaries**.

---

### Core Architecture: Keycard-Secured Multi-Hop Delegation

```text
Alice — Human User
  │
  │ Initial identity: "alice"
  │ Root Scopes: support:read tasks:delegate incident:investigate db:read audit:write
  ▼
Agent A — Orchestrator (Calling Agent)
  │
  ├─ 1. Discovers Agent B via GET /.well-known/agent-card.json
  ├─ 2. Ephemeral Token Exchange (RFC 8693) against Keycard STS (Hop 1)
  │     └─ Token B: sub="alice", aud="http://127.0.0.1:9002", scope="incident:investigate db:read audit:write", act={"sub": "agent-a"}
  ▼
Agent B — Incident Investigator (Port 9002) [Reuses HelloWorldAgentExecutor]
  │
  ├─ 3. Verifies Token B via KeycardAuthBackend + Dynamic RS256 JWKS
  ├─ 4. Strictly enforces 'incident:investigate' scope (HTTP 403 if missing)
  ├─ 5. Dynamically analyzes incoming incident task & synthesizes real containment
  ├─ 6. Autonomous Token Exchange (RFC 8693) against Keycard STS (Hop 2)
  │     └─ Token C: sub="alice", aud="http://127.0.0.1:9003", scope="audit:write", act={"sub": "agent-b", "act": {"sub": "agent-a"}}
  ▼
Agent C — Audit Vault Signer (Port 9003) [Reuses SignedAgentExecutor]
  │
  ├─ 7. Verifies Token C via KeycardAuthBackend + Dynamic RS256 JWKS
  ├─ 8. Strictly enforces 'audit:write' scope (HTTP 403 if missing)
  ├─ 9. Computes canonical SHA-256 digest of evidence and signs with RSA private key (RS256)
  ├─ 10. Exposes public verification endpoint /verify to mathematically verify RSA signatures
  └─ 11. Returns verified seal through the chain: Agent C ➔ Agent B ➔ Agent A ➔ Alice

                      ▲                          ▲                          ▲
                      │                          │                          │
                      └──────────────────────────┼──────────────────────────┘
                                                 │
                               Keycard Local STS — Port 8088
                                 • RFC 8414 Discovery (/.well-known/oauth-authorization-server)
                                 • RS256 Dynamic JWKS (/oauth/jwks)
                                 • RFC 8693 Token Exchange (/oauth/token)
                                 • Strict Bound Enforcement: Agents cannot delegate unheld scopes (HTTP 403)
                                 • Central Instant Revocation (/oauth/revoke)
                                 • Complete Delegation Audit Trail (/audit)
```

---

### Three Core Showcase Scenarios

The showcase is structured around 3 distinct scenarios:

| Scenario | Objective | What is Demonstrated |
|---|---|---|
| **Scenario 1: Successful Autonomous Delegation** | Collaborative Task Execution | Alice submits a dynamic incident query. Agents A, B, and C collaborate across 2 hops, exchange attenuated credentials, dynamically investigate the incident, and generate cryptographically verifiable evidence. |
| **Scenario 2: Attacker Exploitation Attempts** | Security Boundary Enforcement | 7 distinct real-world attack vectors (Expired, Revoked, Audience Mismatch, Tampered Signature, Missing Permission 403, Scope Escalation 403, Unauthorized Delegation 403) are contained at the gateway. |
| **Scenario 3: Administrator Kill Switch & Audit Trail** | Central Governance | An active session is revoked centrally at Keycard STS; all downstream tokens are rejected immediately. Full chronological delegation audit trail is inspected. |

---

### Service Startup

Start the three services in separate terminals (or run `./start_servers.sh`):

| Window | Service | Command | Description |
|---|---|---|---|
| **Terminal 1** | **Keycard STS** | `.venv/bin/python keycard_server.py 8088` | Authorization server & JWKS on port 8088 |
| **Terminal 2** | **Agent B (Investigator)** | `.venv/bin/python agent_b_server.py --port 9002` | Incident Investigator on port 9002 |
| **Terminal 3** | **Agent C (Audit Vault)** | `.venv/bin/python agent_c_server.py --port 9003` | Audit Signer & Verifier on port 9003 |

#### Health Check
```bash
curl -s http://127.0.0.1:8088/health | jq .
curl -s http://127.0.0.1:9002/health | jq .
curl -s http://127.0.0.1:9003/health | jq .
```

#### Optional: AI Incident Reasoning (NVIDIA NIM)
Agent B supports live LLM reasoning during incident investigations using NVIDIA's `nvidia/nemotron-3.5-lightning-30b-a3b` model. Credentials and model parameters are loaded from `.env` (template in `.env.example`):
```bash
# In .env (or export in shell):
NVIDIA_API_KEY="your-nvapi-key-here"
NVIDIA_MODEL="nvidia/nemotron-3.5-lightning-30b-a3b"
```
*(If `NVIDIA_API_KEY` is omitted or invalid, Agent B automatically falls back to its built-in dynamic security analysis engine without interruption.)*

---

### Interactive Demonstration Runner

```bash
./demo_stages.sh                        # Interactive menu with dynamic task selection
./demo_stages.sh all                    # Automated execution through all 3 scenarios
./demo_stages.sh 1 "Custom Incident"    # Run Scenario 1 with a custom dynamic task
./demo_stages.sh 2                      # Run Scenario 2 (7 Attack Tests)
./demo_stages.sh 3                      # Run Scenario 3 (Kill Switch & Audit Trail)
```

---

### Reproducing with Exact `curl` Commands

---

#### SCENARIO 1: Successful Autonomous Delegation

##### 1. Public Discovery
```bash
curl -s http://127.0.0.1:9002/.well-known/agent-card.json | jq .
```

##### 2. Ephemeral Token Minting & Token Exchange (RFC 8693)
```bash
# 2a. Mint initial session credential for Alice on Agent A
TOKEN_A=$(curl -s -X POST http://127.0.0.1:8088/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "client_credentials",
    "client_id": "agent-a",
    "user_id": "alice",
    "scope": "support:read tasks:delegate incident:investigate db:read audit:write"
  }' | jq -r .access_token)

# 2b. RFC 8693 Token Exchange: Agent A exchanges Alice's token for Agent B
TOKEN_B=$(curl -s -X POST http://127.0.0.1:8088/oauth/token \
  -H "Content-Type: application/json" \
  -d "{
    \"grant_type\": \"urn:ietf:params:oauth:grant-type:token-exchange\",
    \"subject_token\": \"$TOKEN_A\",
    \"actor_token\": \"agent-a\",
    \"audience\": \"http://127.0.0.1:9002\",
    \"scope\": \"incident:investigate db:read audit:write\"
  }" | jq -r .access_token)

# 2c. Inspect Runtime Authorization Visibility
.venv/bin/python decode_jwt.py "$TOKEN_B"
```

**Runtime Authorization Output:**
```text
======================================================================
  RUNTIME AUTHORIZATION VISIBILITY: Agent A ➔ Agent B (Hop 1)
======================================================================
  Status:           Authorized (Policy Verified)
  • Subject:          Alice (Originating Human User)
  • Actor:            agent-a
  • Audience:         Agent B (Incident Investigator - Port 9002)
  • Granted scopes:   incident:investigate, db:read, audit:write
  • Session ID:       sess_04b188b163b9
  • Delegation Lineage: [alice -> agent-a -> http://127.0.0.1:9002]
======================================================================
```

##### 3. A2A JSON-RPC Invocation with Dynamic Task Input
You can supply any dynamic incident task at runtime:
- `"Investigate suspicious activity on account #4821"`
- `"Investigate repeated failed authentication attempts"`
- `"Investigate unauthorized database access"`
- `"Investigate unusual privilege escalation"`

```bash
TASK="Investigate repeated failed authentication attempts"

RESP=$(curl -s -X POST http://127.0.0.1:9002/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN_B" \
  -H "A2A-Version: 1.0" \
  -d "{
    \"jsonrpc\": \"2.0\",
    \"id\": \"req-hop1\",
    \"method\": \"SendMessage\",
    \"params\": {
      \"message\": {
        \"messageId\": \"msg-dyn-01\",
        \"role\": \"ROLE_USER\",
        \"parts\": [{\"text\": \"$TASK\"}]
      }
    }
  }")

echo "$RESP" | jq .
```

##### 4. Autonomous Multi-Hop Lineage & Audit Trail Sequence Verification
Agent B already **autonomously exchanged Token B for Token C** against Keycard STS during invocation in Step 3 (no manual curl token exchange required).

**4a. Inspect Autonomously Issued Token C Received by Agent B:**
```bash
TOKEN_C=$(cat /tmp/.keycard_token_c)
.venv/bin/python decode_jwt.py "$TOKEN_C"
```
**Hop 2 Lineage Claim:** Nested `act: {"sub": "agent-b", "act": {"sub": "agent-a"}}` preserving Alice as root subject with permissions narrowed strictly to `audit:write`.

**4b. Verify the 6-Event Autonomous Sequence in Keycard STS Audit Trail:**
```bash
curl -s http://127.0.0.1:8088/audit | jq .
```
You will observe the exact 6-step autonomous lifecycle produced by that single invocation:
1. `USER_SESSION_MINTED` (Initial human session for Alice)
2. `TOKEN_EXCHANGE_SUCCESS` (Agent A ➔ Agent B Hop 1 exchange)
3. `AGENT_AUTHORIZATION` (Agent B verifies Token B against JWKS)
4. `TOKEN_EXCHANGE_SUCCESS` (Agent B autonomously exchanges Token B for Token C at Keycard STS)
5. `AGENT_AUTHORIZATION` (Agent C verifies Token C against JWKS)
6. `EVIDENCE_SIGNED` (Agent C cryptographically seals evidence under scope `audit:write`)

##### 5. Cryptographic Evidence Signature Verification
Agent C signs the evidence digest using its RSA private key (RS256). Verify the mathematical signature against Agent C's public key:

**Option A: Via Agent C Verification Endpoint (`curl`):**
```bash
LAST_SEAL=$(curl -s http://127.0.0.1:9003/telemetry | jq .last_seal)

curl -s -X POST http://127.0.0.1:9003/verify \
  -H "Content-Type: application/json" \
  -d "$LAST_SEAL" | jq .
```
*Expected Output:*
```json
{
  "valid": true,
  "algorithm": "RS256",
  "signer": "Agent C (Audit Vault Signer)",
  "verified_digest": "sha256:...",
  "message": "✔ Cryptographic signature VALID. Evidence is authentic, untampered, and verified against Agent C RSA public key."
}
```

**Option B: Via Standalone CLI Verifier:**
```bash
RESULT_TEXT=$(echo "$RESP" | jq -r '.result.task.status.message.parts[0].text')
.venv/bin/python verify_seal.py "$RESULT_TEXT"
```

---

#### SCENARIO 2: Attacker Exploitation Attempts (7 Defenses)

##### Attack 1: Expired Token (`HTTP 401 Unauthorized`)
```bash
# Mint an expired token (expires_in: -60)
EXPIRED_TOKEN=$(curl -s -X POST http://127.0.0.1:8088/oauth/token \
  -H "Content-Type: application/json" \
  -d '{"grant_type": "client_credentials", "client_id": "agent-a", "user_id": "alice", "scope": "incident:investigate", "expires_in": -60}' | jq -r .access_token)

curl -i -s -X POST http://127.0.0.1:9002/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $EXPIRED_TOKEN" \
  -H "A2A-Version: 1.0" \
  -d '{"jsonrpc": "2.0", "id": "atk_exp", "method": "SendMessage", "params": {"message": {"messageId": "m1", "role": "ROLE_USER", "parts": [{"text": "Execute expired"}]}}}'
```
*Result:* `HTTP/1.1 401 Unauthorized`

##### Attack 2: Revoked Token (`HTTP 401 Unauthorized`)
```bash
TEMP_TOKEN=$(curl -s -X POST http://127.0.0.1:8088/oauth/token -H "Content-Type: application/json" -d '{"grant_type": "client_credentials", "client_id": "agent-a", "user_id": "alice", "scope": "incident:investigate"}' | jq -r .access_token)
curl -s -X POST http://127.0.0.1:8088/oauth/revoke -H "Content-Type: application/json" -d "{\"token\": \"$TEMP_TOKEN\"}"

curl -i -s -X POST http://127.0.0.1:9002/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TEMP_TOKEN" \
  -H "A2A-Version: 1.0" \
  -d '{"jsonrpc": "2.0", "id": "atk_rev", "method": "SendMessage", "params": {"message": {"messageId": "m2", "role": "ROLE_USER", "parts": [{"text": "Execute revoked"}]}}}'
```
*Result:* `HTTP/1.1 401 Unauthorized`

##### Attack 3: Wrong Audience / Confused Deputy (`HTTP 401 Unauthorized`)
```bash
# Token A (audience: 'agent-a') replayed directly to Agent B
curl -i -s -X POST http://127.0.0.1:9002/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN_A" \
  -H "A2A-Version: 1.0" \
  -d '{"jsonrpc": "2.0", "id": "atk_aud", "method": "SendMessage", "params": {"message": {"messageId": "m3", "role": "ROLE_USER", "parts": [{"text": "Replayed token"}]}}}'
```
*Result:* `HTTP/1.1 401 Unauthorized (Audience Mismatch)`

##### Attack 4: Tampered Token (`HTTP 401 Unauthorized`)
```bash
TAMPERED_TOKEN="${TOKEN_B%???}XYZ"

curl -i -s -X POST http://127.0.0.1:9002/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TAMPERED_TOKEN" \
  -H "A2A-Version: 1.0" \
  -d '{"jsonrpc": "2.0", "id": "atk_tamp", "method": "SendMessage", "params": {"message": {"messageId": "m4", "role": "ROLE_USER", "parts": [{"text": "Tampered token"}]}}}'
```
*Result:* `HTTP/1.1 401 Unauthorized (Signature Verification Failed)`

##### Attack 5: Missing Permission on Agent Endpoint (`HTTP 403 Forbidden`)
```bash
# Valid token for Agent C, but only granted 'support:read' (lacks required 'audit:write')
TOKEN_READ_ONLY=$(curl -s -X POST http://127.0.0.1:8088/oauth/token \
  -H "Content-Type: application/json" \
  -d "{
    \"grant_type\": \"urn:ietf:params:oauth:grant-type:token-exchange\",
    \"subject_token\": \"$TOKEN_A\",
    \"actor_token\": \"agent-b\",
    \"audience\": \"http://127.0.0.1:9003\",
    \"scope\": \"support:read\"
  }" | jq -r .access_token)

curl -i -s -X POST http://127.0.0.1:9003/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN_READ_ONLY" \
  -H "A2A-Version: 1.0" \
  -d '{"jsonrpc": "2.0", "id": "atk_perm", "method": "SendMessage", "params": {"message": {"messageId": "m5", "role": "ROLE_USER", "parts": [{"text": "Seal without permission"}]}}}'
```
*Result:* `HTTP/1.1 403 Forbidden (Insufficient Scope)`

##### Attack 6: Scope Escalation to Prohibited Scope (`HTTP 403 Policy Rejection`)
```bash
# Requesting prohibited destructive scope 'db:delete' from Keycard STS
curl -i -s -X POST http://127.0.0.1:8088/oauth/token \
  -H "Content-Type: application/json" \
  -d "{
    \"grant_type\": \"urn:ietf:params:oauth:grant-type:token-exchange\",
    \"subject_token\": \"$TOKEN_A\",
    \"actor_token\": \"agent-a\",
    \"audience\": \"http://127.0.0.1:9002\",
    \"scope\": \"db:delete\"
  }"
```
*Result:* `HTTP/1.1 403 Forbidden` with `"error": "policy_denied"`

##### Attack 7: Unauthorized Agent Attempting Delegation / Delegating Unheld Permissions (`HTTP 403`)
```bash
# Agent B attempts to delegate 'billing:admin' which was never granted to Agent B
curl -i -s -X POST http://127.0.0.1:8088/oauth/token \
  -H "Content-Type: application/json" \
  -d "{
    \"grant_type\": \"urn:ietf:params:oauth:grant-type:token-exchange\",
    \"subject_token\": \"$TOKEN_B\",
    \"actor_token\": \"agent-b\",
    \"audience\": \"http://127.0.0.1:9003\",
    \"scope\": \"billing:admin payment:execute\"
  }"
```
*Result:* `HTTP/1.1 403 Forbidden` with body:
```json
{
  "error": "invalid_scope",
  "error_description": "Policy rejection: Unauthorized delegation. Requested scope(s) ['billing:admin', 'payment:execute'] exceed permissions held in subject token. Agents cannot delegate permissions they never received."
}
```

---

#### SCENARIO 3: Administrator Kill Switch & Delegation Audit Trail

##### 1. Pull the Kill Switch (Central Session Revocation)
```bash
curl -s -X POST http://127.0.0.1:8088/oauth/revoke \
  -H "Content-Type: application/json" \
  -d "{\"token\": \"$TOKEN_B\"}" | jq .
```

##### 2. Verify Downstream Lineage Invalidation Across Both Agents
Test both Agent B and Agent C with their previously issued downstream tokens:

**2a. Test Agent B with Token B:**
```bash
curl -i -s -X POST http://127.0.0.1:9002/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN_B" \
  -H "A2A-Version: 1.0" \
  -d '{"jsonrpc": "2.0", "id": "post_kill_b", "method": "SendMessage", "params": {"message": {"messageId": "m_kill_b", "role": "ROLE_USER", "parts": [{"text": "Attempt after kill switch"}]}}}'
```
*Result:* `HTTP/1.1 401 Unauthorized (Session Revoked)`

**2b. Test Agent C with Token C (Autonomous Hop 2 Token):**
```bash
TOKEN_C=$(cat /tmp/.keycard_token_c)

curl -i -s -X POST http://127.0.0.1:9003/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN_C" \
  -H "A2A-Version: 1.0" \
  -d '{"jsonrpc": "2.0", "id": "post_kill_c", "method": "SendMessage", "params": {"message": {"messageId": "m_kill_c", "role": "ROLE_USER", "parts": [{"text": "Attempt after kill switch"}]}}}'
```
*Result:* `HTTP/1.1 401 Unauthorized (Session Revoked)`

*Verification:* Revoking the human root session at Keycard STS instantly propagates to all downstream agents, proving that the entire delegation lineage is invalidated simultaneously.

##### 3. Complete Delegation Audit Trail (`Alice ➔ Agent A ➔ Agent B ➔ Agent C`)
```bash
curl -s http://127.0.0.1:8088/audit | jq .
```
Displays all chronological session mints, token exchanges (with subject, actor, previous actor, target audience, granted scopes, and decisions), authorization rejections, and revocation events.

##### 4. Inspect Execution Counters
```bash
curl -s http://127.0.0.1:9002/telemetry | jq .
curl -s http://127.0.0.1:9003/telemetry | jq .
```
Shows execution counters proving that 0 attacks reached the underlying agent logic.
