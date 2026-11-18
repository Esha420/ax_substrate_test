# Keycard Multi-Agent (A2A) Security & Multi-Hop Delegation Showcase

This workspace provides an implementation of autonomous multi-agent security using the official Keycard A2A SDK (`keycardai-a2a`, `keycardai-starlette`) and official Google Agent-to-Agent SDK (`a2a-sdk`), reusing existing open-source agents from [`a2aproject/a2a-samples`](https://github.com/a2aproject/a2a-samples).

---

### Core Architecture: 2-Hop Multi-Hop Delegation

```text
Human User (Alice)
       │
       ▼ (Initial Session: support:read tasks:delegate incident:investigate audit:write)
Calling Orchestrator (Agent A)
       │
       ├─ 1. Discovers Agent B via /.well-known/agent-card.json
       ├─ 2. RFC 8693 Token Exchange against Keycard STS (Hop 1)
       │     └─ Token B: sub="alice", aud="Agent B", scope="incident:investigate db:read", act={"sub": "agent-a"}
       ▼
Incident Investigator (Agent B) [Reusing HelloWorldAgentExecutor]
       │
       ├─ 3. Verifies Token B via KeycardAuthBackend + TokenVerifier
       ├─ 4. Injects KeycardUser into ServerCallContext via KeycardServerCallContextBuilder
       ├─ 5. Investigates account incident
       ├─ 6. RFC 8693 Token Exchange against Keycard STS (Hop 2)
       │     └─ Token C: sub="alice", aud="Agent C", scope="audit:write", act={"sub": "agent-b", "act": {"sub": "agent-a"}}
       ▼
Audit Vault Signer (Agent C) [Reusing SignedAgentExecutor]
       │
       ├─ 7. Verifies Token C via KeycardAuthBackend + TokenVerifier
       ├─ 8. Cryptographically seals evidence under root user 'alice' with scope 'audit:write'
       └─ 9. Returns verified seal back through the chain: Agent C ➔ Agent B ➔ Agent A ➔ Alice
```

---

### The 5 Presentation Moments

The demonstration script ([showcase_a2a_keycard.py](file:///home/berrybytes/Office/Assignment/keycard/showcase_a2a_keycard.py)) is structured into the 5 core presentation moments:

1. **Moment 1 — The Problem (Ordinary A2A Accepts Anonymous Requests):**
   - Shows an unauthenticated HTTP client executing actions on an unprotected open-source agent.
   - Highlights the baseline security vulnerability: zero caller verification, lost human origin, and absence of authorization boundaries.
2. **Moment 2 — The Integration (Service Discovery & Ephemeral Token Exchange):**
   - Demonstrates official A2A agent card discovery (`/.well-known/agent-card.json`).
   - `DelegationClient` executes RFC 8693 token exchange against Keycard STS to mint task-scoped ephemeral RS256 credentials.
3. **Moment 3 — The Identity (Multi-Hop Cryptographic Lineage & Progressive Attenuation):**
   - Cryptographically preserves human user `alice` across **two autonomous hops** (`alice ➔ agent-a ➔ agent-b ➔ agent-c`).
   - Progressively attenuates permissions:
     - Alice: `support:read tasks:delegate incident:investigate audit:write`
     - Agent B: `incident:investigate db:read` (Attenuated)
     - Agent C: `audit:write` (Narrowest scope)
   - Decodes RFC 8693 nested `act` claims: `{"sub": "agent-b", "act": {"sub": "agent-a"}}`.
   - Masks bearer tokens in logs (`eyJhbGci...[MASKED]...`) while validating RS256 signatures via dynamic JWKS (`/oauth/jwks`).
4. **Moment 4 — The Security (Allowed Operation vs. 3 Blocked Attacks):**
   - **Allowed Delegated Operation:** Authorized multi-hop workflow completes cleanly.
   - **Attack 4A (No Auth):** Rogue direct JSON-RPC call $\rightarrow$ HTTP 401 Unauthorized.
   - **Attack 4B (Audience Replay):** Alice's session token replayed to Agent B $\rightarrow$ HTTP 401 Unauthorized (Audience mismatch).
   - **Attack 4C (Scope Escalation):** Rogue agent requests prohibited `db:delete` scope $\rightarrow$ HTTP 403 Forbidden (Blocked at STS boundary).
5. **Moment 5 — The Evidence (Execution-Level Telemetry & Containment Proof):**
   - Uses `MultiHopAuditTracker` to track execution counters inside `IncidentInvestigatorExecutor` and `AuditVaultSignerExecutor`.
   - **Empirical Proof:** In all 3 attacks, executor execution counters **remain completely unchanged**. Payloads are intercepted *before* agent code execution.
   - **Containment Rate:** 100.0% of unauthorized attempts stopped.

---

### Key Takeaway

> *"Keycard doesn't stop agents from communicating. It ensures that when agents communicate and delegate tasks, their identities, authority and accountability travel with them."*

---

### Running the Showcase

#### 1. Automated Run (Instant Demo)
```bash
cd /home/berrybytes/Office/Assignment/keycard
.venv/bin/python showcase_a2a_keycard.py
```

#### 2. Live Interactive Presentation Mode (Step-by-Step with `[ENTER]`)
```bash
cd /home/berrybytes/Office/Assignment/keycard
.venv/bin/python showcase_a2a_keycard.py --interactive
```

#### 3. Custom Ports or STS URL
```bash
.venv/bin/python showcase_a2a_keycard.py --sts-url http://127.0.0.1:8088 --agent-b-port 9002 --agent-c-port 9003
```
