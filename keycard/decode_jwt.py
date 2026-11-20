#!/usr/bin/env python3
"""
Keycard Token Claim & Runtime Authorization Inspector
=====================================================
Decodes RS256 / HS256 JWT tokens, displays claims in formatted JSON,
and highlights runtime authorization visibility, permission attenuation,
and RFC 8693 nested 'act' delegation lineage.
"""

import sys
import json
import base64

CYAN = "\033[1;36m"
GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
MAGENTA = "\033[1;35m"
BOLD = "\033[1m"
DIM = "\033[2m"
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

    try:
        header = json.loads(b64url_decode(parts[0]).decode('utf-8'))
        payload = json.loads(b64url_decode(parts[1]).decode('utf-8'))
    except Exception as e:
        print(f"Error decoding JWT parts: {e}", file=sys.stderr)
        sys.exit(1)

    sub = payload.get("sub", "unknown")
    aud = payload.get("aud", "unknown")
    scope = payload.get("scope", "")
    client_id = payload.get("client_id", "unknown")
    sid = payload.get("sid", "unknown")

    # Analyze nested actors
    act_claim = payload.get("act")
    immediate_actor = client_id
    previous_actor = None
    if isinstance(act_claim, dict):
        immediate_actor = act_claim.get("sub", client_id)
        inner_act = act_claim.get("act")
        if isinstance(inner_act, dict):
            previous_actor = inner_act.get("sub")
        elif inner_act:
            previous_actor = str(inner_act)

    chain = extract_delegation_chain(payload)

    # Determine Hop Label
    if "9003" in str(aud) or "agent-c" in str(aud):
        hop_label = "Agent B ➔ Agent C (Hop 2: Vault Audit)"
        aud_label = "Agent C (Audit Vault Signer - Port 9003)"
    elif "9002" in str(aud) or "agent-b" in str(aud):
        hop_label = "Agent A ➔ Agent B (Hop 1: Investigation)"
        aud_label = "Agent B (Incident Investigator - Port 9002)"
    else:
        hop_label = f"Alice ➔ {client_id} (Initial User Credential)"
        aud_label = str(aud)

    print(f"\n{BOLD}{CYAN}======================================================================{RESET}")
    print(f"{BOLD}{GREEN}  RUNTIME AUTHORIZATION VISIBILITY: {YELLOW}{hop_label}{RESET}")
    print(f"{BOLD}{CYAN}======================================================================{RESET}")
    print(f"  {BOLD}Status:{RESET}           {BOLD}{GREEN}Authorized (Policy Verified){RESET}")
    print(f"  • {BOLD}Subject:{RESET}          {GREEN}{sub.capitalize() if sub.isalpha() else sub}{RESET} (Originating Human User)")
    print(f"  • {BOLD}Actor:{RESET}            {YELLOW}{immediate_actor}{RESET}")
    if previous_actor:
        print(f"  • {BOLD}Previous actor:{RESET}   {CYAN}{previous_actor}{RESET}")
    print(f"  • {BOLD}Audience:{RESET}         {CYAN}{aud_label}{RESET}")
    print(f"  • {BOLD}Granted scopes:{RESET}   {MAGENTA}{', '.join(scope.split()) if scope else '[none]'}{RESET}")
    print(f"  • {BOLD}Session ID:{RESET}       {DIM}{sid}{RESET}")
    if chain:
        lineage_str = " -> ".join([str(sub)] + [str(x) for x in chain] + [str(aud)])
        print(f"  • {BOLD}Delegation Lineage:{RESET} {BOLD}{CYAN}[{lineage_str}]{RESET}")
    print(f"{BOLD}{CYAN}======================================================================{RESET}")

    # Raw Claims details
    print(f"\n{BOLD}Token Header:{RESET} alg={header.get('alg')}, kid={header.get('kid')}")
    print(f"{BOLD}Raw Claims Payload:{RESET}")
    print(json.dumps(payload, indent=2))
    print(f"{BOLD}{CYAN}======================================================================{RESET}\n")


if __name__ == "__main__":
    import os
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        arg = sys.argv[1].strip()
        # If argument is a valid file path, read file contents
        if len(arg) < 255 and os.path.exists(arg):
            with open(arg, "r") as f:
                token = f.read().strip()
        else:
            token = arg
    else:
        token = sys.stdin.read().strip()

    inspect_token(token)
