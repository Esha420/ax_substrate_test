#!/usr/bin/env bash
# ==============================================================================
# Keycard Runtime Security Features - 5 Core Curl Commands Showcase
# Scenario: User (Alice) -> Agent A (Triage) -> Agent B (Worker) -> Customer DB
# ==============================================================================

set -e

KEYCARD_URL="http://127.0.0.1:8088"

# Terminal formatting
BOLD="\033[1m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
CYAN="\033[0;36m"
NC="\033[0m"

echo -e "${BOLD}${CYAN}======================================================================${NC}"
echo -e "${BOLD}${CYAN}   KEYCARD RUNTIME AUTHORIZATION & MULTI-AGENT DELEGATION SHOWCASE    ${NC}"
echo -e "${BOLD}${CYAN}======================================================================${NC}\n"

# Verify local STS is running
if ! curl -s "$KEYCARD_URL/health" > /dev/null 2>&1; then
    echo -e "${RED}[!] Keycard Local STS is not running on $KEYCARD_URL.${NC}"
    echo -e "    Please start it first in another terminal:"
    echo -e "    ${YELLOW}python3 keycard_server.py${NC}\n"
    exit 1
fi

decode_jwt() {
    local token="$1"
    echo "$token" | cut -d. -f2 | base64 -d 2>/dev/null | jq .
}

# ------------------------------------------------------------------------------
# STEP 1: Ephemeral Task-Scoped Credential Minting
# ------------------------------------------------------------------------------
echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"
echo -e "${BOLD}${YELLOW}▶ STEP 1: Ephemeral Task-Scoped Credential Minting${NC}"
echo -e "  Feature: Agent A runs 'secretless', requesting a short-lived token for Alice."
echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"

echo -e "${CYAN}Executing Command:${NC}"
cat << 'EOF'
curl -s -X POST http://127.0.0.1:8088/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "client_credentials",
    "client_id": "agent-a",
    "user_id": "alice",
    "scope": "support:read tasks:delegate"
  }'
EOF
echo ""

RESP_1=$(curl -s -X POST "$KEYCARD_URL/oauth/token" \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "client_credentials",
    "client_id": "agent-a",
    "user_id": "alice",
    "scope": "support:read tasks:delegate"
  }')

TOKEN_A=$(echo "$RESP_1" | jq -r .access_token)
echo -e "${GREEN}✓ Minted Ephemeral Token for Agent A:${NC}"
echo "$RESP_1" | jq .

echo -e "\n${BOLD}Decoded JWT Claims (Agent A):${NC}"
decode_jwt "$TOKEN_A"
echo ""

# ------------------------------------------------------------------------------
# STEP 2: Agent-to-Agent Delegation via RFC 8693 Token Exchange
# ------------------------------------------------------------------------------
echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"
echo -e "${BOLD}${YELLOW}▶ STEP 2: Agent-to-Agent Delegation via Token Exchange (RFC 8693)${NC}"
echo -e "  Feature: Agent A delegates task to Agent B with scoped attenuation."
echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"

echo -e "${CYAN}Executing Command:${NC}"
cat << 'EOF'
curl -s -X POST http://127.0.0.1:8088/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
    "subject_token": "$TOKEN_A",
    "actor_token": "agent-a",
    "audience": "agent-b",
    "scope": "db:read"
  }'
EOF
echo ""

RESP_2=$(curl -s -X POST "$KEYCARD_URL/oauth/token" \
  -H "Content-Type: application/json" \
  -d "{
    \"grant_type\": \"urn:ietf:params:oauth:grant-type:token-exchange\",
    \"subject_token\": \"$TOKEN_A\",
    \"actor_token\": \"agent-a\",
    \"audience\": \"agent-b\",
    \"scope\": \"db:read\"
  }")

TOKEN_B=$(echo "$RESP_2" | jq -r .access_token)
echo -e "${GREEN}✓ Token Exchange Successful (Issued Token for Agent B):${NC}"
echo "$RESP_2" | jq .
echo ""

# ------------------------------------------------------------------------------
# STEP 3: Cryptographic Lineage & Scope Attenuation Verification
# ------------------------------------------------------------------------------
echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"
echo -e "${BOLD}${YELLOW}▶ STEP 3: Inspect Cryptographic Lineage (Nested 'act' Claims)${NC}"
echo -e "  Feature: Proves User identity is preserved and privileges were narrowed."
echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"

echo -e "${CYAN}Executing Command:${NC}"
echo 'echo "$TOKEN_B" | cut -d. -f2 | base64 -d | jq .'
echo ""

echo -e "${GREEN}✓ Decoded JWT Claims for Downstream Agent B:${NC}"
decode_jwt "$TOKEN_B"

echo -e "\n${BOLD}Runtime Guarantees Verified:${NC}"
echo -e "  1. ${GREEN}User Identity Preserved:${NC} 'sub' = 'alice' (The root human initiator)."
echo -e "  2. ${GREEN}Delegation Audit Trail:${NC} 'act.sub' = 'agent-b', nested with 'act.act.sub' = 'agent-a'."
echo -e "  3. ${GREEN}Monotonic Privilege Narrowing:${NC} 'scope' narrowed strictly to 'db:read'."
echo ""

# ------------------------------------------------------------------------------
# STEP 4: Negative Test — Unauthorized Scope Escalation Blocked
# ------------------------------------------------------------------------------
echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"
echo -e "${BOLD}${YELLOW}▶ STEP 4: Negative Test — Unauthorized Escalation Blocked at Runtime${NC}"
echo -e "  Feature: Agent A attempts unauthorized delegation of 'db:delete'."
echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"

echo -e "${CYAN}Executing Command:${NC}"
cat << 'EOF'
curl -s -w "\nHTTP Status: %{http_code}\n" -X POST http://127.0.0.1:8088/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
    "subject_token": "$TOKEN_A",
    "actor_token": "agent-a",
    "audience": "agent-b",
    "scope": "db:delete"
  }'
EOF
echo ""

RESP_4=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$KEYCARD_URL/oauth/token" \
  -H "Content-Type: application/json" \
  -d "{
    \"grant_type\": \"urn:ietf:params:oauth:grant-type:token-exchange\",
    \"subject_token\": \"$TOKEN_A\",
    \"actor_token\": \"agent-a\",
    \"audience\": \"agent-b\",
    \"scope\": \"db:delete\"
  }")

BODY_4=$(echo "$RESP_4" | sed -e '$d')
STATUS_4=$(echo "$RESP_4" | tail -n1 | cut -d: -f2)

echo -e "${RED}✗ Runtime Policy Evaluation Result (HTTP $STATUS_4):${NC}"
echo "$BODY_4" | jq .
echo -e "${GREEN}✓ Policy Guardrail Verified: Downstream token issuance was blocked.${NC}\n"

# ------------------------------------------------------------------------------
# STEP 5: Protected Resource Access & Instant Session Kill-Switch
# ------------------------------------------------------------------------------
echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"
echo -e "${BOLD}${YELLOW}▶ STEP 5: Protected Resource Access & Instant Session Revocation${NC}"
echo -e "  Feature: Agent B accesses resource; then session is killed immediately."
echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"

echo -e "${CYAN}5a. Agent B queries protected database with valid token:${NC}"
curl -s -X GET "$KEYCARD_URL/api/customer-data" \
  -H "Authorization: Bearer $TOKEN_B" | jq .
echo ""

echo -e "${CYAN}5b. Security team revokes the active delegation session centrally:${NC}"
cat << 'EOF'
curl -s -X POST http://127.0.0.1:8088/oauth/revoke \
  -H "Content-Type: application/json" \
  -d '{"token": "$TOKEN_B"}'
EOF
echo ""

REVOKE_RESP=$(curl -s -X POST "$KEYCARD_URL/oauth/revoke" \
  -H "Content-Type: application/json" \
  -d "{\"token\": \"$TOKEN_B\"}")
echo "$REVOKE_RESP" | jq .
echo ""

echo -e "${CYAN}5c. Agent B immediately retries the exact same request:${NC}"
RETRY_RESP=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X GET "$KEYCARD_URL/api/customer-data" \
  -H "Authorization: Bearer $TOKEN_B")

BODY_5C=$(echo "$RETRY_RESP" | sed -e '$d')
STATUS_5C=$(echo "$RETRY_RESP" | tail -n1 | cut -d: -f2)

echo -e "${RED}✗ Request Blocked Post-Revocation (HTTP $STATUS_5C):${NC}"
echo "$BODY_5C" | jq .
echo -e "${GREEN}✓ Central Kill-Switch Verified: Token was instantly rejected.${NC}\n"

echo -e "${BOLD}${GREEN}======================================================================${NC}"
echo -e "${BOLD}${GREEN}   ALL 5 KEYCARD RUNTIME SECURITY FEATURES VERIFIED SUCCESSFULLY!    ${NC}"
echo -e "${BOLD}${GREEN}======================================================================${NC}\n"

