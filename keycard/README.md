# Keycard Multi-Agent (A2A) Production Architecture & Governance

This repository implements a production-grade **Autonomous Multi-Agent Authorization Architecture** using the official **Keycard A2A SDK** (`keycardai-a2a`, `keycardai-starlette`) and the **Google Agent-to-Agent (A2A) Protocol** (`a2a-sdk`), reusing open-source executors from [`a2aproject/a2a-samples`](https://github.com/a2aproject/a2a-samples).

Rather than relying on static scripts, mock payloads, or shared root API keys, the system demonstrates **autonomous multi-hop delegation**, **natural-language intent interpretation**, **in-process middleware request interception**, **cryptographic evidence sealing**, and **centralized governance with cascading revocation**.

---

## 1. System Architecture & Component Overview

```mermaid
flowchart TD
    subgraph Human["Human Layer"]
        Alice["Alice (Human Principal)\nRoot Scopes: support:read tasks:delegate incident:investigate db:read audit:write"]
    end

    subgraph Orchestration["Client & Orchestration Layer"]
        AgentA["Agent A: Orchestrator Client (agent_a.py)\n• Natural Language Understanding (NVIDIA Nemotron LLM)\n• Task & Scope Identification\n• Automated Credential Exchange Manager"]
    end

    subgraph SecurityFabric["Keycard Security Fabric (Port 8088)"]
        STS["Keycard Local STS Server\n• RFC 8414 OAuth Metadata (/.well-known/oauth-authorization-server)\n• Dynamic RS256 JWKS (/oauth/jwks)\n• RFC 8693 Token Exchange (/oauth/token)\n• Central Session Revocation (/oauth/revoke)\n• Immutable Delegation Audit Ledger (/audit)"]
    end

    subgraph AgentB_Service["Agent B Microservice (Port 9002)"]
        B_MW["KeycardAuthBackend Middleware\n• Intercepts Every Inbound Request\n• Validates RS256 Signature against STS JWKS\n• Strictly Enforces 'incident:investigate' & 'db:read'\n• Checks Real-Time Revocation (401 if Revoked)"]
        B_EXEC["IncidentInvestigatorExecutor\n• NVIDIA Nemotron LLM Reasoning\n• Findings Synthesis & Containment Planning\n• Autonomous DelegationClient (Hop 2 Exchange)"]
        B_MW -->|Authorized 200 OK| B_EXEC
    end

    subgraph AgentC_Service["Agent C Microservice (Port 9003)"]
        C_MW["KeycardAuthBackend Middleware\n• Intercepts Inbound Requests\n• Validates RS256 Signature against STS JWKS\n• Strictly Enforces 'audit:write' (403 if Missing)\n• Validates Nested Actor Lineage"]
        C_EXEC["AuditVaultSignerExecutor\n• Canonical SHA-256 Evidence Digest\n• RS256 RSA Private Key Signature\n• Public Verification Endpoint (/verify)"]
        C_MW -->|Authorized 200 OK| C_EXEC
    end

    Alice -->|"1. Natural Language Instruction"| AgentA
    AgentA <-->|"2. Mint Root Token & Exchange for Token B"| STS
    AgentA -->|"3. POST /a2a/jsonrpc (Bearer Token B)"| B_MW
    B_EXEC <-->|"4. Autonomous Token Exchange for Token C"| STS
    B_EXEC -->|"5. POST /a2a/jsonrpc (Bearer Token C)"| C_MW
    C_EXEC -->|"6. Verifiable Evidence Seal"| B_EXEC
    B_EXEC -->|"7. Complete Sealed Report"| AgentA
    AgentA -->|"8. Mathematical Signature Verification"| Alice
```

---

## 2. Architectural Clarity: Where Does the Middleware Live?

A common question in multi-agent security is: **"Does all agent-to-agent communication route through an API gateway, or does middleware run on every request?"**

In this architecture:
- **Keycard STS (Port 8088) is OUT-OF-BAND**: It is **not** an in-line proxy. Agent payload traffic never passes through STS. STS only issues, exchanges, and revokes tokens.
- **Keycard Middleware is EMBEDDED IN EACH AGENT**: `KeycardAuthBackend` sits directly inside Agent B and Agent C's HTTP application pipeline. Every incoming HTTP request is intercepted and policed locally by the receiving agent before hitting any business logic.

```mermaid
flowchart LR
    subgraph Agent_A["Agent A (Caller)"]
        A_Out["HTTP Client"]
    end

    subgraph Agent_B["Agent B (Receiver - Port 9002)"]
        B_MW["KeycardAuthBackend Middleware\n[Runs on EVERY incoming request]"]
        B_App["Agent Logic / LLM Executor"]
        B_MW -->|Valid RS256 & Scopes| B_App
        B_MW -->|Invalid Token| Deny401["401 Unauthorized"]
        B_MW -->|Missing Scope| Deny403["403 Forbidden"]
    end

    subgraph OutOfBand["Out-of-Band Authority"]
        STS["Keycard STS (Port 8088)\n• Public JWKS (/oauth/jwks)\n• Revocation Registry"]
    end

    A_Out -->|"Direct HTTP POST /a2a/jsonrpc (Bearer JWT)"| B_MW
    B_MW -.->|"Resolves Public Key via JWKS"| STS
    B_MW -.->|"Checks Session Revocation"| STS
```

---

## 3. Scope Attenuation & Nested Actor Lineage (`act`)

To prevent the **Confused Deputy Problem** and stop agents from escalating privileges, Keycard enforces **permission attenuation** and **RFC 8693 nested actor chaining** at every hop:

```text
Alice (Human Principal)
  └─ Initial Root Scopes: [support:read, tasks:delegate, incident:investigate, db:read, audit:write]
      │
      ▼ (Hop 1: Agent A exchanges Alice's token for Agent B)
Token B:
  • sub:       "alice"
  • aud:       "http://127.0.0.1:9002"
  • client_id: "agent-a"
  • act:       {"sub": "agent-a"}
  • scope:     "incident:investigate db:read audit:write"  <-- Attenuated
      │
      ▼ (Hop 2: Agent B autonomously exchanges Token B for Agent C)
Token C:
  • sub:       "alice"
  • aud:       "http://127.0.0.1:9003"
  • client_id: "agent-b"
  • act:       {"sub": "agent-b", "act": {"sub": "agent-a"}}  <-- Cryptographic Lineage Preserved
  • scope:     "audit:write"                                  <-- Narrowed to least privilege
```

### Delegation Bounds Enforcement:
- **Strict Scope Boundaries**: An agent cannot request or delegate permissions that were not present in its parent token (attempting to escalate results in `HTTP 403 Forbidden`).
- **Registered Delegators**: Only authorized agents (`agent-a`, `agent-b`) are permitted to initiate token exchanges at Keycard STS.

---

## 4. End-to-End Execution Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Alice as Alice (Human User)
    participant A as Agent A (Orchestrator)
    participant STS as Keycard STS (8088)
    participant B_MW as Agent B Middleware
    participant B as Agent B (Investigator: 9002)
    participant C_MW as Agent C Middleware
    participant C as Agent C (Vault Signer: 9003)

    Alice->>A: "Investigate suspicious DB access on production database and save findings to audit vault"
    Note over A: NVIDIA Nemotron LLM parses intent:<br/>Operations: [read_db, investigate, write_vault]<br/>Scopes: [incident:investigate, db:read, audit:write]

    A->>STS: POST /oauth/token (client_credentials for Alice)
    STS-->>A: Token A (Root Scopes, sid: sess_xxxx)

    A->>STS: POST /oauth/token (RFC 8693 Token Exchange for Agent B)
    STS-->>A: Token B (aud: 9002, act: agent-a, scopes: incident:investigate db:read)

    A->>B_MW: POST /a2a/jsonrpc (Bearer Token B)
    Note over B_MW: Middleware validates RS256 signature against STS JWKS<br/>Checks audience=9002, scopes=['incident:investigate', 'db:read']<br/>Status: AUTHORIZED (200 OK)
    B_MW->>B: Execute Investigation

    Note over B: Nemotron LLM reasons on database logs<br/>Identifies anomalous queries & formulates containment

    Note over B: Autonomous Hop 2 Triggered
    B->>STS: POST /oauth/token (RFC 8693 Token Exchange for Agent C)
    STS-->>B: Token C (aud: 9003, act: agent-b -> agent-a, scope: audit:write)

    B->>C_MW: POST /a2a/jsonrpc (Bearer Token C)
    Note over C_MW: Middleware validates RS256 signature<br/>Enforces scope='audit:write' (403 if missing)<br/>Status: AUTHORIZED (200 OK)
    C_MW->>C: Execute Evidence Sealing

    Note over C: Computes SHA-256 digest of findings<br/>Signs digest with RSA RS256 private key
    C-->>B: SEAL-xxxx (Verifiable Evidence Record + Signature)
    B-->>A: Complete Investigation Report with Embedded Seal
    
    Note over A: Verifies signature against Agent C public key (/vault/public_key)<br/>Confirms 6-event chronological STS audit trail
    A-->>Alice: Final Verified Report (Tamper-Proof & Audit-Ready)
```

---

## 5. Natural-Language Entry Point (`agent_a.py`)

Users interact with the system using **plain-English instructions**. No manual `curl` commands or token handling are required.

### Interactive Mode:
```bash
python agent_a.py
```
```text
======================================================================
       KEYCARD MULTI-AGENT (A2A) AUTONOMOUS WORKFLOW
  Natural Language ➔ Orchestrator ➔ Keycard STS ➔ Multi-Hop Agents
======================================================================

Enter your natural-language task (or press Enter for default):
Default: Investigate suspicious database access on the production database. Analyze the access logs, identify the responsible activity, and save the investigation findings in the audit vault.

Alice > 
```

### Direct Command-Line Execution:
```bash
python agent_a.py "Investigate unauthorized database access on production customers table and seal findings"
```

### Real-Time Terminal Output Layout:
```text
── PLANNING ───────────────────────────────────────────────
[Agent A] Interpreting natural-language user intent...
[Agent A] ✓ Intent interpreted via NVIDIA Nemotron LLM:
  • Summary:         Investigate unauthorized database access on production DB
  • Operations:      ['analyze_access_logs', 'identify_responsible_activity', 'save_findings_to_audit_vault']
  • Target Agents:   ['log_analyzer', 'db_access_monitor', 'audit_vault_writer']
  • Required Scopes: ['incident:investigate', 'db:read', 'audit:write']

── AUTHENTICATION & TOKEN EXCHANGE ────────────────────────
[Keycard STS] Minting initial root session token for 'alice' on 'agent-a'...
  • Initial Credential: ISSUED (Session: sess_654dd299b709)
  • Root Scopes:        support:read tasks:delegate incident:investigate db:read audit:write

[Keycard STS] Performing RFC 8693 Token Exchange for Agent B (http://127.0.0.1:9002)...
  • Exchanged Token B:  ACQUIRED
  • Audience:           http://127.0.0.1:9002
  • Attenuated Scopes:  incident:investigate db:read audit:write
  • Actor Lineage:      [alice -> agent-a -> http://127.0.0.1:9002]

── AGENT B: INCIDENT INVESTIGATION ────────────────────────
[Agent A] Invoking Agent B via Google A2A JSON-RPC (Bearer Token B)...
[Agent B] ✓ Investigation Completed in 4.42s
  • Category: Unauthorized Database Access
  • Findings: Log analysis identified 47 anomalous queries from external IP 203.0.113.42 between 02:14–02:38 UTC. Queries targeted sensitive tables (users, payments, credentials) using a decommissioned service account.
  • Containment Action: Immediately revoked compromised service account, blocked source IP at perimeter, set database to read-only, and opened high-priority SOC ticket.

── AGENT C: AUDIT VAULT SEAL & VERIFICATION ───────────────
[Agent A] Retrieving Agent C public key and verifying cryptographic signature...

======================================================================
   AGENT C CRYPTOGRAPHIC AUDIT EVIDENCE VERIFIER                      
======================================================================
  • Seal ID:            SEAL-1795509637-22155B
  • Signer:             Agent C (Audit Vault Signer)
  • Algorithm:          RS256 (RSASSA-PKCS1-v1_5 with SHA-256)
  • Evidence Digest:    sha256:0c7ea7b3b714381e71c2db5313388e1be2df252f558ad688c2b1d15b823320c8
  • Delegated Lineage:  [alice -> agent-a -> agent-b -> agent-b -> agent-c]
  • Signature (B64):    kaD/6P17QjwluX76TtN6C/Oo41zWJgSvTC/0...
----------------------------------------------------------------------
  ✔ CRYPTOGRAPHIC SIGNATURE VALID
    Evidence digest verified against Agent C RSA public key.
    Lineage accountability and tamper-resistance mathematically proven.
======================================================================

── KEYCARD DELEGATION AUDIT LEDGER ────────────────────────
  1. [USER_SESSION_MINTED] decision=AUTHORIZED actor=alice
  2. [TOKEN_EXCHANGE_SUCCESS] decision=AUTHORIZED actor=agent-a target=http://127.0.0.1:9002
  3. [AGENT_AUTHORIZATION] decision=AUTHORIZED actor=Agent B (Incident Investigator) target=/a2a/jsonrpc
  4. [TOKEN_EXCHANGE_SUCCESS] decision=AUTHORIZED actor=agent-b target=http://127.0.0.1:9003
  5. [AGENT_AUTHORIZATION] decision=AUTHORIZED actor=Agent C (Audit Vault Signer) target=/a2a/jsonrpc
  6. [EVIDENCE_SIGNED] decision=AUTHORIZED actor=Agent C (Audit Vault Signer) target=SEAL-1795509637-22155B

── FINAL RESULT ───────────────────────────────────────────
  • Incident Investigation:  COMPLETED
  • Audit Vault Record:      STORED
  • Cryptographic Seal:      VERIFIED (RS256 Signature Valid)
  • Runtime Authorization:   VERIFIED (Least-Privilege Maintained across 2 Hops)
```

---

## 6. Real-Time Middleware Event Logging

Agent B and Agent C's embedded middleware (`KeycardAuthBackend`) emits structured logs in real time as requests are intercepted:

### Agent B Middleware Log (Read Path):
```text
[14:25:32] [AGENT B MIDDLEWARE] ── INCOMING A2A REQUEST ──
  • Endpoint: /a2a/jsonrpc | Method: POST
  • Token Verification: VALID RS256 JWKS SIGNATURE (Keycard STS Port 8088)
  • Caller Identity: client_id='agent-a' | Root Subject: 'alice'
  • Required Scope: 'incident:investigate' | Held Scopes: ['incident:investigate', 'db:read', 'audit:write']
  • Scope Evaluation: GRANTED
  • Middleware Decision: AUTHORIZED (200 OK) ➔ Dispatching to Investigator Executor
```

### Agent C Middleware Log (Write Path):
```text
[14:25:37] [AGENT C MIDDLEWARE] ── INCOMING A2A REQUEST ──
  • Endpoint: /a2a/jsonrpc | Method: POST
  • Token Verification: VALID RS256 JWKS SIGNATURE (Keycard STS Port 8088)
  • Caller Identity: client_id='agent-b' | Root Subject: 'alice'
  • Required Scope: 'audit:write' | Held Scopes: ['audit:write']
  • Scope Evaluation: GRANTED (Permission Attenuation Verified)
  • Middleware Decision: AUTHORIZED (200 OK) ➔ Dispatching to Audit Vault Signer
```

---

## 7. Security Defenses & Attack Testing

The gateway polices both authentication (401) and authorization/scope boundaries (403):

| Test Scenario | Attack Description | Expected Code | Defensive Mechanism |
|---|---|:---:|---|
| **Unauthenticated Request** | Calling Agent B without Authorization header | `401 Unauthorized` | Intercepted by `KeycardAuthBackend` |
| **Tampered Token** | Altering JWT signature bytes | `401 Unauthorized` | Fails RS256 cryptographic signature check |
| **Expired Token** | Presenting token past its TTL | `401 Unauthorized` | Fails timestamp expiration check |
| **Audience Replay** | Replaying Agent B token against Agent C | `401 Unauthorized` | Audience mismatch (`aud != http://127.0.0.1:9003`) |
| **Missing Permission** | Token holds `support:read` but lacks `audit:write` | `403 Forbidden` | Strict scope enforcement |
| **Scope Escalation** | Requesting prohibited scope (`db:delete`) | `403 Forbidden` | Intercepted by Keycard STS delegation policy |
| **Unauthorized Delegator** | Rogue agent attempting token exchange | `403 Forbidden` | Intercepted by registered delegator policy |
| **Session Revocation** | Calling agents after administrator kill switch | `401 Unauthorized` | Real-time session invalidation |

### Run Automated Security Tests via CLI:

#### 1. Unauthorized Operation Test (`db:delete`):
```bash
python agent_a.py --test-unauthorized
```
```text
── SECURITY TEST: UNAUTHORIZED OPERATION ATTEMPT (HTTP 403) 
[Scenario] Agent A attempts to delegate prohibited scope 'db:delete' to Agent B.
  • Keycard STS Response: HTTP 403 Forbidden
  • Policy Interception:  Scope escalation detected. Scope 'db:delete' is prohibited.
  • ✔ SECURITY VERIFIED: Destructive action was blocked at the gateway.
```

#### 2. Central Kill Switch Revocation Test:
```bash
python agent_a.py --test-revocation
```
```text
── SECURITY TEST: CENTRAL REVOCATION & KILL SWITCH (HTTP 401) 
[Scenario] Alice's session is revoked centrally at Keycard STS. Downstream tokens are rejected.
  • Revocation status: Session 'sess_xxxx' has been revoked immediately across all downstream agents.
  • Agent B Middleware: HTTP 401 Unauthorized
  • ✔ SECURITY VERIFIED: Lineage invalidation propagated to downstream agent.
```

---

## 8. Quickstart & Production Runbook

### Prerequisites
- Python 3.10+
- Virtual environment with dependencies installed:
  ```bash
  cd keycard
  source .venv/bin/activate
  ```

### Configuration (`.env`)
Create or verify [.env](file:///home/berrybytes/Office/Assignment/keycard/.env) (template in [.env.example](file:///home/berrybytes/Office/Assignment/keycard/.env.example)):
```bash
NVIDIA_API_KEY="your-nvidia-api-key"
NVIDIA_MODEL="nvidia/nemotron-3.5-lightning-30b-a3b"
STS_URL="http://127.0.0.1:8088"
AGENT_B_URL="http://127.0.0.1:9002"
AGENT_C_URL="http://127.0.0.1:9003"
```

### 1. Start Services
Launch all three microservices in the background:
```bash
./start_servers.sh
```
Check health:
```bash
curl -s http://127.0.0.1:8088/health | jq .
curl -s http://127.0.0.1:9002/health | jq .
curl -s http://127.0.0.1:9003/health | jq .
```

### 2. Run the Workflow (3 Options)

#### Option A: Natural-Language Orchestrator (Recommended)
```bash
python agent_a.py
```
Or with custom input:
```bash
python agent_a.py "Investigate repeated failed authentication attempts on bastion host"
```

#### Option B: Multi-Stage Showcase Runner
```bash
./demo_stages.sh 1 "Custom Incident"   # Run Scenario 1 (Happy Path)
./demo_stages.sh 2                     # Run Scenario 2 (7 Security Attacks)
./demo_stages.sh 3                     # Run Scenario 3 (Kill Switch)
./demo_stages.sh all                   # Run all scenarios
```

#### Option C: Reproduce with Raw `curl` Commands
See [Raw `curl` Reproduction Guide](file:///home/berrybytes/.gemini/antigravity/brain/17def851-2e32-4fc9-bb3f-c894c3764a65/KEYCARD_A2A_ARCHITECTURE_AND_DEMO_GUIDE.md#4-end-to-end-demonstration-playbook) for exact copy-pasteable commands for every step.

---

## 9. 12-Point Verification Matrix

| # | Requirement | Implementation Mechanism | Verified Status |
|:---:|---|---|:---:|
| 1 | Natural-Language Input | `agent_a.py` accepts free-form text input | ✔ PASS |
| 2 | Intent & Agent Identification | NVIDIA Nemotron LLM parses operations, target agents, and scopes | ✔ PASS |
| 3 | Automatic Token Exchange | Agent A handles RFC 8693 token exchange via Keycard STS | ✔ PASS |
| 4 | Agent B Middleware Interception | `KeycardAuthBackend` validates RS256 JWKS independently of STS | ✔ PASS |
| 5 | Live LLM Incident Investigation | Agent B performs live reasoning using `nvidia/nemotron-3.5-lightning-30b-a3b` | ✔ PASS |
| 6 | Autonomous Hop 2 Delegation | Agent B uses `DelegationClient` to exchange Token B for Token C | ✔ PASS |
| 7 | Independent Agent C Validation | Agent C's middleware independently verifies Token C audience and scopes | ✔ PASS |
| 8 | Read vs. Write Scope Separation | `db:read` enforced on Agent B; `audit:write` enforced on Agent C | ✔ PASS |
| 9 | Real-Time Middleware Visibility | High-visibility formatted logs emitted on every inbound request | ✔ PASS |
| 10 | Unauthorized Action Rejection | Attempted `db:delete` or missing scopes return `HTTP 403 Forbidden` | ✔ PASS |
| 11 | Central Session Revocation | Revoking root session causes immediate `HTTP 401` on downstream agents | ✔ PASS |
| 12 | Cryptographic Evidence Verification | Agent C RSA RS256 signature mathematically verified via `verify_seal.py` | ✔ PASS |

---

## 10. File & Component Reference

| File | Role |
|---|---|
| [agent_a.py](file:///home/berrybytes/Office/Assignment/keycard/agent_a.py) | Natural language entry point and workflow orchestrator. |
| [agent_b_server.py](file:///home/berrybytes/Office/Assignment/keycard/agent_b_server.py) | Agent B Incident Investigator (Port 9002), Google A2A server, Nemotron LLM reasoning. |
| [agent_c_server.py](file:///home/berrybytes/Office/Assignment/keycard/agent_c_server.py) | Agent C Audit Vault Signer (Port 9003), RS256 cryptographic evidence signer. |
| [keycard_server.py](file:///home/berrybytes/Office/Assignment/keycard/keycard_server.py) | Keycard Local STS Server (Port 8088), RFC 8414 metadata, JWKS, RFC 8693 exchange. |
| [verify_seal.py](file:///home/berrybytes/Office/Assignment/keycard/verify_seal.py) | Standalone CLI verifier for Agent C RSA digital signatures. |
| [decode_jwt.py](file:///home/berrybytes/Office/Assignment/keycard/decode_jwt.py) | Runtime authorization visibility inspector (`act` claim, scopes, lineage). |
| [start_servers.sh](file:///home/berrybytes/Office/Assignment/keycard/start_servers.sh) | Starts all services in the background and verifies health. |
| [stop_servers.sh](file:///home/berrybytes/Office/Assignment/keycard/stop_servers.sh) | Cleanly terminates all running services. |
| [demo_stages.sh](file:///home/berrybytes/Office/Assignment/keycard/demo_stages.sh) | Interactive terminal showcase runner. |
| [.env](file:///home/berrybytes/Office/Assignment/keycard/.env) | Configuration file for NVIDIA NIM API key and service endpoints. |
