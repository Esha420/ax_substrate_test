#!/usr/bin/env python3
"""
Keycard Token Claim Inspector
=============================
Decodes RS256 / HS256 JWT tokens, displays claims in formatted JSON,
and highlights RFC 8693 nested 'act' delegation lineage.
"""

import sys
import json
import base64

CYAN = "\033[1;36m"
GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
MAGENTA = "\033[1;35m"
BOLD = "\033[1m"
RESET = "\033[0m"

def b64url_decode(s: str) -> bytes:
    padding = '=' * (4 - len(s) % 4) if len(s) % 4 != 0 else ''
    return base64.urlsafe_b64decode(s + padding)

def extract_delegation_chain(claims: dict) -> list:
    chain = []
    act = claims.get("act")
    while act and isinstance(act, dict):
        chain.append(act.get("sub"))
        act = act.get("act")
    return list(reversed(chain))

def inspect_token(token_str: str):
    token_str = token_str.strip()
    parts = token_str.split('.')
    if len(parts) < 2:
        print("Invalid JWT format", file=sys.stderr)
        sys.exit(1)

    header = json.loads(b64url_decode(parts[0]).decode('utf-8'))
    payload = json.loads(b64url_decode(parts[1]).decode('utf-8'))

    print(f"\n{BOLD}{CYAN}=== Keycard Ephemeral Token Decoded Claims ==={RESET}")
    print(f"{BOLD}Header (Algorithm & Key ID):{RESET}")
    print(json.dumps(header, indent=2))

    print(f"\n{BOLD}Payload (OAuth 2.0 & RFC 8693 Claims):{RESET}")
    print(json.dumps(payload, indent=2))

    sub = payload.get("sub")
    aud = payload.get("aud")
    scope = payload.get("scope")
    client_id = payload.get("client_id")
    chain = extract_delegation_chain(payload)

    print(f"\n{BOLD}{GREEN}Cryptographic Lineage Summary:{RESET}")
    print(f"  • Root Principal (sub):      {GREEN}{sub}{RESET} (Originating human user)")
    print(f"  • Immediate Actor (client):  {YELLOW}{client_id}{RESET}")
    print(f"  • Target Audience (aud):     {CYAN}{aud}{RESET}")
    print(f"  • Attenuated Scopes:         {MAGENTA}{scope}{RESET}")
    if chain:
        full_lineage = " -> ".join([str(sub)] + [str(x) for x in chain] + [str(aud)])
        print(f"  • Delegated Lineage (act):   {BOLD}{CYAN}[{full_lineage}]{RESET}")
    else:
        print(f"  • Delegation Level:          Single-hop / direct session")
    print(f"{BOLD}{CYAN}=============================================={RESET}\n")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        token = sys.argv[1]
    else:
        token = sys.stdin.read()
    inspect_token(token)
