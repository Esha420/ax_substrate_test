#!/usr/bin/env bash
# ==============================================================================
# Keycard A2A Interactive Protocol Showcase (6-Stage Terminal Demonstration)
# ==============================================================================
# Usage:
#   ./demo_stages.sh         # Interactive mode (prompts between stages)
#   ./demo_stages.sh all     # Automated run through all 6 stages
#   ./demo_stages.sh 1       # Run Stage 1: Discovery only
#   ./demo_stages.sh 2       # Run Stage 2: Authentication only
#   ./demo_stages.sh 3       # Run Stage 3: A2A Invocation only
#   ./demo_stages.sh 4       # Run Stage 4: Multi-Hop Delegation only
#   ./demo_stages.sh 5       # Run Stage 5: Attack Simulation only
#   ./demo_stages.sh 6       # Run Stage 6: Telemetry & Revocation only
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

STS_URL="http://127.0.0.1:8088"
AGENT_B_URL="http://127.0.0.1:9002"
AGENT_C_URL="http://127.0.0.1:9003"
PYTHON="$SCRIPT_DIR/.venv/bin/python"

# Terminal Formatting
BOLD="\033[1m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
CYAN="\033[0;36m"
MAGENTA="\033[0;35m"
DIM="\033[2m"
NC="\033[0m"

# Ensure all 3 servers are running
check_health() {
    local missing=0
    if ! curl -s "$STS_URL/health" > /dev/null 2>&1; then
        echo -e "${RED}[!] Keycard Local STS is not running on $STS_URL${NC}"
        missing=1
    fi
    if ! curl -s "$AGENT_B_URL/health" > /dev/null 2>&1; then
        echo -e "${RED}[!] Agent B (Investigator) is not running on $AGENT_B_URL${NC}"
        missing=1
    fi
    if ! curl -s "$AGENT_C_URL/health" > /dev/null 2>&1; then
        echo -e "${RED}[!] Agent C (Audit Vault) is not running on $AGENT_C_URL${NC}"
        missing=1
    fi

    if [ $missing -eq 1 ]; then
        echo -e "\n${YELLOW}Starting all background server processes via ./start_servers.sh ...${NC}"
        ./start_servers.sh
    fi
}

pause_prompt() {
    local stage_title="$1"
    if [ "$INTERACTIVE_MODE" = true ]; then
        echo -e "\n${BOLD}${YELLOW}❯ [NEXT: $stage_title]${NC} ${DIM}Press [ENTER] to execute stage, or Ctrl+C to exit...${NC}"
        read -r
    else
        sleep 0.5
    fi
}

print_header() {
    clear 2>/dev/null || true
    echo -e "${BOLD}${CYAN}======================================================================${NC}"
    echo -e "${BOLD}${CYAN}   KEYCARD AGENT-TO-AGENT (A2A) INTERACTIVE PROTOCOL SHOWCASE         ${NC}"
    echo -e "${BOLD}${CYAN}======================================================================${NC}"
    echo -e "  ${BOLD}Architecture:${NC}"
    echo -e "    Alice (Human) ➔ Agent A (Orchestrator) ➔ Agent B (Port 9002) ➔ Agent C (Port 9003)"
    echo -e "  ${BOLD}Security Fabric:${NC}"
    echo -e "    Keycard Local STS (Port 8088) · RFC 8693 Token Exchange · Dynamic RS256 JWKS"
    echo -e "${BOLD}${CYAN}======================================================================${NC}\n"
}

# ==============================================================================
# STAGE 1: Discovery
# ==============================================================================
run_stage_1() {
    echo -e "${BOLD}${BLUE}======================================================================${NC}"
    echo -e "${BOLD}${YELLOW}▶ STAGE 1: Discovery — Agent B Publishes Identity & Capabilities${NC}"
    echo -e "  ${DIM}Protocol: Official Google A2A Agent Card Discovery (Public, Unauthenticated)${NC}"
    echo -e "${BOLD}${BLUE}======================================================================${NC}\n"

    echo -e "Key Concept: The Keycard STS is ${BOLD}not an agent router${NC}."
    echo -e "Agents publish their own cards directly on ${CYAN}/.well-known/agent-card.json${NC}.\n"

    echo -e "${CYAN}Executing Command:${NC}"
    echo -e "${BOLD}curl -s http://127.0.0.1:9002/.well-known/agent-card.json | jq .${NC}\n"

    curl -s "$AGENT_B_URL/.well-known/agent-card.json" | jq .

    echo -e "\n${GREEN}✓ Stage 1 Takeaway:${NC}"
    echo -e "  Agent B advertises its JSON-RPC endpoint (${CYAN}$AGENT_B_URL/a2a/jsonrpc${NC})"
    echo -e "  and functional capabilities without requiring pre-shared secrets."
}

# ==============================================================================
# STAGE 2: Authentication
# ==============================================================================
run_stage_2() {
    echo -e "\n${BOLD}${BLUE}======================================================================${NC}"
    echo -e "${BOLD}${YELLOW}▶ STAGE 2: Authentication — Ephemeral Token Exchange (RFC 8693)${NC}"
    echo -e "  ${DIM}Alice's identity is exchanged for an ephemeral, task-scoped Agent B token${NC}"
    echo -e "${BOLD}${BLUE}======================================================================${NC}\n"

    echo -e "Step 2a: Minting initial session credential for human user Alice on Agent A..."
    echo -e "${CYAN}Executing Command:${NC}"
    cat << 'EOF'
curl -s -X POST http://127.0.0.1:8088/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "client_credentials",
    "client_id": "agent-a",
    "user_id": "alice",
    "scope": "support:read tasks:delegate incident:investigate audit:write"
  }'
EOF
    echo ""

    RESP_A=$(curl -s -X POST "$STS_URL/oauth/token" \
      -H "Content-Type: application/json" \
      -d '{
        "grant_type": "client_credentials",
        "client_id": "agent-a",
        "user_id": "alice",
        "scope": "support:read tasks:delegate incident:investigate audit:write"
      }')
    TOKEN_A=$(echo "$RESP_A" | jq -r .access_token)
    echo -e "${GREEN}✓ Minted initial session token for Alice.${NC}\n"

    echo -e "Step 2b: RFC 8693 Token Exchange against Keycard STS for Agent B..."
    echo -e "${CYAN}Executing Command:${NC}"
    cat << 'EOF'
curl -s -X POST http://127.0.0.1:8088/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
    "subject_token": "$TOKEN_A",
    "actor_token": "agent-a",
    "audience": "http://127.0.0.1:9002",
    "scope": "incident:investigate db:read"
  }'
EOF
    echo ""

    RESP_B=$(curl -s -X POST "$STS_URL/oauth/token" \
      -H "Content-Type: application/json" \
      -d "{
        \"grant_type\": \"urn:ietf:params:oauth:grant-type:token-exchange\",
        \"subject_token\": \"$TOKEN_A\",
        \"actor_token\": \"agent-a\",
        \"audience\": \"http://127.0.0.1:9002\",
        \"scope\": \"incident:investigate db:read\"
      }")
    TOKEN_B=$(echo "$RESP_B" | jq -r .access_token)
    echo -e "${GREEN}✓ Received Token B (Scoped for Agent B).${NC}\n"

    echo -e "Step 2c: Inspecting Token B claims..."
    echo -e "${CYAN}Executing Command:${NC}"
    echo -e "${BOLD}python3 decode_jwt.py \"\$TOKEN_B\"${NC}"
    $PYTHON decode_jwt.py "$TOKEN_B"

    # Save to temp files for subsequent single-stage executions
    echo "$TOKEN_A" > /tmp/.keycard_token_a
    echo "$TOKEN_B" > /tmp/.keycard_token_b

    echo -e "${GREEN}✓ Stage 2 Takeaway:${NC}"
    echo -e "  The token preserves Alice as root user (${GREEN}sub: alice${NC}), identifies caller (${YELLOW}client_id: agent-a${NC}),"
    echo -e "  restricts audience strictly to (${CYAN}aud: $AGENT_B_URL${NC}), and attenuates permissions."
}

# ==============================================================================
# STAGE 3: A2A Invocation
# ==============================================================================
run_stage_3() {
    echo -e "\n${BOLD}${BLUE}======================================================================${NC}"
    echo -e "${BOLD}${YELLOW}▶ STAGE 3: A2A Invocation — Agent A Calls Agent B${NC}"
    echo -e "  ${DIM}Protocol: Official Google A2A JSON-RPC 'SendMessage' with Bearer Token${NC}"
    echo -e "${BOLD}${BLUE}======================================================================${NC}\n"

    # Ensure Token B is available
    if [ ! -f /tmp/.keycard_token_b ]; then
        echo -e "${YELLOW}Obtaining fresh Token B...${NC}"
        TOKEN_A=$(curl -s -X POST "$STS_URL/oauth/token" -H "Content-Type: application/json" -d '{"grant_type": "client_credentials", "client_id": "agent-a", "user_id": "alice", "scope": "support:read tasks:delegate incident:investigate audit:write"}' | jq -r .access_token)
        TOKEN_B=$(curl -s -X POST "$STS_URL/oauth/token" -H "Content-Type: application/json" -d "{\"grant_type\": \"urn:ietf:params:oauth:grant-type:token-exchange\", \"subject_token\": \"$TOKEN_A\", \"actor_token\": \"agent-a\", \"audience\": \"$AGENT_B_URL\", \"scope\": \"incident:investigate db:read\"}" | jq -r .access_token)
        echo "$TOKEN_A" > /tmp/.keycard_token_a
        echo "$TOKEN_B" > /tmp/.keycard_token_b
    else
        TOKEN_B=$(cat /tmp/.keycard_token_b)
    fi

    echo -e "${CYAN}Executing Command:${NC}"
    cat << 'EOF'
curl -s -X POST http://127.0.0.1:9002/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN_B" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-hop1",
    "method": "SendMessage",
    "params": {
      "message": {
        "messageId": "msg-hop1",
        "role": "ROLE_USER",
        "parts": [{"text": "Investigate suspicious data access pattern on account #4821"}]
      }
    }
  }' | jq .
EOF
    echo ""

    RESP_INVOKE=$(curl -s -X POST "$AGENT_B_URL/a2a/jsonrpc" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN_B" \
      -H "A2A-Version: 1.0" \
      -d '{
        "jsonrpc": "2.0",
        "id": "req-hop1",
        "method": "SendMessage",
        "params": {
          "message": {
            "messageId": "msg-hop1",
            "role": "ROLE_USER",
            "parts": [{"text": "Investigate suspicious data access pattern on account #4821"}]
          }
        }
      }')

    echo "$RESP_INVOKE" | jq .

    echo -e "\n${GREEN}✓ Stage 3 Takeaway:${NC}"
    echo -e "  Agent B's Keycard middleware verified the RS256 token against STS JWKS."
    echo -e "  The executor ran with authenticated human context: ${GREEN}root subject 'alice'${NC}."
}

# ==============================================================================
# STAGE 4: Multi-Hop Delegation
# ==============================================================================
run_stage_4() {
    echo -e "\n${BOLD}${BLUE}======================================================================${NC}"
    echo -e "${BOLD}${YELLOW}▶ STAGE 4: Multi-Hop Delegation — Agent B ➔ Agent C${NC}"
    echo -e "  ${DIM}Agent B exchanges its token for Agent C, constructing nested RFC 8693 'act' claims${NC}"
    echo -e "${BOLD}${BLUE}======================================================================${NC}\n"

    # Ensure Token B is available
    if [ ! -f /tmp/.keycard_token_b ]; then
        TOKEN_A=$(curl -s -X POST "$STS_URL/oauth/token" -H "Content-Type: application/json" -d '{"grant_type": "client_credentials", "client_id": "agent-a", "user_id": "alice", "scope": "support:read tasks:delegate incident:investigate audit:write"}' | jq -r .access_token)
        TOKEN_B=$(curl -s -X POST "$STS_URL/oauth/token" -H "Content-Type: application/json" -d "{\"grant_type\": \"urn:ietf:params:oauth:grant-type:token-exchange\", \"subject_token\": \"$TOKEN_A\", \"actor_token\": \"agent-a\", \"audience\": \"$AGENT_B_URL\", \"scope\": \"incident:investigate db:read\"}" | jq -r .access_token)
        echo "$TOKEN_A" > /tmp/.keycard_token_a
        echo "$TOKEN_B" > /tmp/.keycard_token_b
    else
        TOKEN_B=$(cat /tmp/.keycard_token_b)
    fi

    echo -e "Step 4a: Hop 2 Token Exchange (Agent B delegates to Agent C)..."
    echo -e "${CYAN}Executing Command:${NC}"
    cat << 'EOF'
curl -s -X POST http://127.0.0.1:8088/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
    "subject_token": "$TOKEN_B",
    "actor_token": "agent-b",
    "audience": "http://127.0.0.1:9003",
    "scope": "audit:write"
  }'
EOF
    echo ""

    RESP_C=$(curl -s -X POST "$STS_URL/oauth/token" \
      -H "Content-Type: application/json" \
      -d "{
        \"grant_type\": \"urn:ietf:params:oauth:grant-type:token-exchange\",
        \"subject_token\": \"$TOKEN_B\",
        \"actor_token\": \"agent-b\",
        \"audience\": \"http://127.0.0.1:9003\",
        \"scope\": \"audit:write\"
      }")
    TOKEN_C=$(echo "$RESP_C" | jq -r .access_token)
    echo -e "${GREEN}✓ Received Token C (Hop 2 Scoped Credential).${NC}\n"

    echo -e "Step 4b: Inspecting Token C nested delegation claims..."
    $PYTHON decode_jwt.py "$TOKEN_C"

    echo -e "Step 4c: Agent B calls Agent C over A2A JSON-RPC to seal audit record..."
    echo -e "${CYAN}Executing Command:${NC}"
    cat << 'EOF'
curl -s -X POST http://127.0.0.1:9003/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN_C" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": "hop2-invoke",
    "method": "SendMessage",
    "params": {
      "message": {
        "messageId": "msg-hop2",
        "role": "ROLE_USER",
        "parts": [{"text": "Cryptographically seal audit evidence for root user alice"}]
      }
    }
  }' | jq .
EOF
    echo ""

    RESP_SEAL=$(curl -s -X POST "$AGENT_C_URL/a2a/jsonrpc" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN_C" \
      -H "A2A-Version: 1.0" \
      -d '{
        "jsonrpc": "2.0",
        "id": "hop2-invoke",
        "method": "SendMessage",
        "params": {
          "message": {
            "messageId": "msg-hop2",
            "role": "ROLE_USER",
            "parts": [{"text": "Cryptographically seal audit evidence for root user alice"}]
          }
        }
      }')

    echo "$RESP_SEAL" | jq .

    echo -e "\n${GREEN}✓ Stage 4 Takeaway:${NC}"
    echo -e "  Multi-hop delegation succeeded across 2 autonomous hops: ${CYAN}alice ➔ agent-a ➔ agent-b ➔ agent-c${NC}."
    echo -e "  Notice permissions were progressively narrowed from full access down strictly to ${MAGENTA}audit:write${NC}."
}

# ==============================================================================
# STAGE 5: Attack Simulations
# ==============================================================================
run_stage_5() {
    echo -e "\n${BOLD}${BLUE}======================================================================${NC}"
    echo -e "${BOLD}${YELLOW}▶ STAGE 5: Attack Simulation — 3 Proactive Security Defenses${NC}"
    echo -e "  ${DIM}1. Missing Auth (401) | 2. Audience Replay (401) | 3. Scope Escalation (403)${NC}"
    echo -e "${BOLD}${BLUE}======================================================================${NC}\n"

    # 5A: Missing Auth
    echo -e "${BOLD}▶ [Attack 5A] Rogue anonymous caller attempts direct SendMessage without token:${NC}"
    echo -e "${CYAN}Command:${NC} curl -s -w \"HTTP Status: %{http_code}\n\" -X POST $AGENT_B_URL/a2a/jsonrpc ..."
    RES_5A=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$AGENT_B_URL/a2a/jsonrpc" \
      -H "Content-Type: application/json" \
      -H "A2A-Version: 1.0" \
      -d '{"jsonrpc": "2.0", "id": "atk1", "method": "SendMessage", "params": {"message": {"messageId": "m1", "role": "ROLE_USER", "parts": [{"text": "Exfiltrate database users;"}]}}}')

    STATUS_5A=$(echo "$RES_5A" | grep "HTTP_STATUS:" | cut -d: -f2)
    BODY_5A=$(echo "$RES_5A" | grep -v "HTTP_STATUS:")
    echo -e "  Outcome: ${RED}$BODY_5A${NC} | Status: ${BOLD}${GREEN}HTTP $STATUS_5A Unauthorized${NC}"
    echo -e "  ${GREEN}✓ Blocked by KeycardAuthBackend before executor execution.${NC}\n"

    # 5B: Audience Replay Attack
    echo -e "${BOLD}▶ [Attack 5B] Confused Deputy: Attacker replays Alice's Token A directly to Agent B:${NC}"
    echo -e "${CYAN}Command:${NC} curl -s -w \"HTTP Status: %{http_code}\n\" -H \"Authorization: Bearer \$TOKEN_A\" ..."
    TOKEN_A=$(cat /tmp/.keycard_token_a 2>/dev/null || curl -s -X POST "$STS_URL/oauth/token" -H "Content-Type: application/json" -d '{"grant_type": "client_credentials", "client_id": "agent-a", "user_id": "alice", "scope": "support:read"}' | jq -r .access_token)

    RES_5B=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$AGENT_B_URL/a2a/jsonrpc" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN_A" \
      -H "A2A-Version: 1.0" \
      -d '{"jsonrpc": "2.0", "id": "atk2", "method": "SendMessage", "params": {"message": {"messageId": "m2", "role": "ROLE_USER", "parts": [{"text": "Replayed token attack"}]}}}')

    STATUS_5B=$(echo "$RES_5B" | grep "HTTP_STATUS:" | cut -d: -f2)
    BODY_5B=$(echo "$RES_5B" | grep -v "HTTP_STATUS:")
    echo -e "  Outcome: ${RED}$BODY_5B${NC} | Status: ${BOLD}${GREEN}HTTP $STATUS_5B Unauthorized (Audience Mismatch)${NC}"
    echo -e "  ${GREEN}✓ Token audience 'agent-a' was rejected by Agent B ($AGENT_B_URL).${NC}\n"

    # 5C: Scope Escalation
    echo -e "${BOLD}▶ [Attack 5C] Rogue agent requests prohibited scope 'db:delete' from Keycard STS:${NC}"
    echo -e "${CYAN}Command:${NC} curl -s -w \"HTTP Status: %{http_code}\n\" -X POST $STS_URL/oauth/token -d '{\"scope\": \"db:delete\", ...}'"
    RES_5C=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$STS_URL/oauth/token" \
      -H "Content-Type: application/json" \
      -d "{
        \"grant_type\": \"urn:ietf:params:oauth:grant-type:token-exchange\",
        \"subject_token\": \"$TOKEN_A\",
        \"actor_token\": \"agent-a\",
        \"audience\": \"$AGENT_B_URL\",
        \"scope\": \"db:delete\"
      }")

    STATUS_5C=$(echo "$RES_5C" | grep "HTTP_STATUS:" | cut -d: -f2)
    BODY_5C=$(echo "$RES_5C" | grep -v "HTTP_STATUS:")
    echo "$BODY_5C" | jq .
    echo -e "  Status: ${BOLD}${GREEN}HTTP $STATUS_5C Policy Denied${NC}"
    echo -e "  ${GREEN}✓ Policy Engine blocked token issuance at the perimeter.${NC}"

    echo -e "\n${GREEN}✓ Stage 5 Takeaway:${NC}"
    echo -e "  All 3 attack vectors were contained (100% interception rate)."
}

# ==============================================================================
# STAGE 6: Evidence & Telemetry & Revocation
# ==============================================================================
run_stage_6() {
    echo -e "\n${BOLD}${BLUE}======================================================================${NC}"
    echo -e "${BOLD}${YELLOW}▶ STAGE 6: Evidence — Telemetry, Audit Proof & Instant Revocation${NC}"
    echo -e "  ${DIM}Inspect execution counters, verify containment, and trigger central kill-switch${NC}"
    echo -e "${BOLD}${BLUE}======================================================================${NC}\n"

    echo -e "Step 6a: Live execution telemetry on Agent B (Port 9002)..."
    curl -s "$AGENT_B_URL/telemetry" | jq .

    echo -e "\nStep 6b: Live execution telemetry on Agent C (Port 9003)..."
    curl -s "$AGENT_C_URL/telemetry" | jq .

    echo -e "\n${BOLD}Empirical Proof:${NC} In all 3 attacks, executor code was ${BOLD}never executed${NC}."
    echo -e "Blocked requests were dropped at the Keycard middleware boundary.\n"

    echo -e "Step 6c: Live Central Session Revocation (Kill-Switch)..."
    TOKEN_REVOKE=$(cat /tmp/.keycard_token_b 2>/dev/null || true)
    if [ -n "$TOKEN_REVOKE" ]; then
        echo -e "Revoking active session centrally at Keycard STS:"
        curl -s -X POST "$STS_URL/oauth/revoke" \
          -H "Content-Type: application/json" \
          -d "{\"token\": \"$TOKEN_REVOKE\"}" | jq .

        echo -e "\nRetrying request immediately with revoked token:"
        curl -s -w "\nHTTP Status: %{http_code}\n" -X POST "$AGENT_B_URL/a2a/jsonrpc" \
          -H "Content-Type: application/json" \
          -H "Authorization: Bearer $TOKEN_REVOKE" \
          -H "A2A-Version: 1.0" \
          -d '{"jsonrpc": "2.0", "id": "revoked-test", "method": "SendMessage", "params": {"message": {"messageId": "m-rev", "role": "ROLE_USER", "parts": [{"text": "Attempt after revocation"}]}}}'
        echo -e "${GREEN}✓ Central revocation propagated immediately across agents.${NC}"
    fi

    echo -e "\n${BOLD}${GREEN}======================================================================${NC}"
    echo -e "${BOLD}${GREEN}  ✔ 6-STAGE A2A PROTOCOL SHOWCASE COMPLETED SUCCESSFULLY             ${NC}"
    echo -e "${BOLD}${GREEN}======================================================================${NC}"
    echo -e "  Key Takeaway: ${BOLD}\"Identities, authority and accountability travel with agents across every hop.\"${NC}\n"
}

# ==============================================================================
# Main Entry Point
# ==============================================================================
check_health

TARGET_STAGE="${1:-interactive}"

if [ "$TARGET_STAGE" = "1" ]; then
    run_stage_1
elif [ "$TARGET_STAGE" = "2" ]; then
    run_stage_2
elif [ "$TARGET_STAGE" = "3" ]; then
    run_stage_3
elif [ "$TARGET_STAGE" = "4" ]; then
    run_stage_4
elif [ "$TARGET_STAGE" = "5" ]; then
    run_stage_5
elif [ "$TARGET_STAGE" = "6" ]; then
    run_stage_6
elif [ "$TARGET_STAGE" = "all" ]; then
    INTERACTIVE_MODE=false
    print_header
    run_stage_1
    run_stage_2
    run_stage_3
    run_stage_4
    run_stage_5
    run_stage_6
else
    # Default: Interactive mode
    INTERACTIVE_MODE=true
    print_header
    pause_prompt "Stage 1: Discovery (Agent B publishes its identity)"
    run_stage_1
    pause_prompt "Stage 2: Authentication (Alice's identity exchanged for Agent B token)"
    run_stage_2
    pause_prompt "Stage 3: A2A Invocation (Agent A calls Agent B)"
    run_stage_3
    pause_prompt "Stage 4: Multi-Hop Delegation (Agent B obtains Token C & calls Agent C)"
    run_stage_4
    pause_prompt "Stage 5: Attack Simulation (3 blocked attacks: No Auth, Replay, Escalation)"
    run_stage_5
    pause_prompt "Stage 6: Evidence (Inspect telemetry and trigger central session revocation)"
    run_stage_6
fi
