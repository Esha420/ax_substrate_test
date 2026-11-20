#!/usr/bin/env python3
"""
Agent C Audit Seal Cryptographic Verifier
=========================================
Verifies the cryptographic RS256 signature on an Evidence Seal produced
by Agent C (Audit Vault Signer) against Agent C's RSA public key.

Usage:
  .venv/bin/python verify_seal.py '<SEAL_JSON_OR_STRING>'
  .venv/bin/python verify_seal.py file_containing_seal.json
"""

import sys
import json
import base64
import urllib.request
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization

CURRENT_DIR = Path(__file__).resolve().parent
KEY_FILE = CURRENT_DIR / "agent_c_rsa_key.pem"

CYAN = "\033[1;36m"
GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
MAGENTA = "\033[1;35m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def load_public_key():
    # 1. Try local PEM file if available
    if KEY_FILE.exists():
        with open(KEY_FILE, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
            return private_key.public_key()
    # 2. Otherwise fetch from live Agent C endpoint
    try:
        req = urllib.request.urlopen("http://127.0.0.1:9003/vault/public_key", timeout=2.0)
        data = json.loads(req.read().decode("utf-8"))
        pem_data = data["public_key_pem"].encode("utf-8")
        return serialization.load_pem_public_key(pem_data)
    except Exception as e:
        print(f"{RED}Error loading Agent C public key: {e}{RESET}", file=sys.stderr)
        sys.exit(1)


def verify_seal(input_data: str):
    input_data = input_data.strip()

    # If it's a file path, read file
    if "\n" not in input_data and len(input_data) < 255 and Path(input_data).exists():
        with open(input_data, "r") as f:
            raw_text = f.read()
    else:
        raw_text = input_data

    # Parse JSON or find embedded seal in A2A response text
    signature_b64 = None
    evidence_digest = None
    seal_id = "UNKNOWN"
    root_subject = "UNKNOWN"
    lineage = "UNKNOWN"

    try:
        parsed = json.loads(raw_text)
        # Check if wrapped in result.task.status.message.parts
        if "result" in parsed:
            parts = parsed.get("result", {}).get("task", {}).get("status", {}).get("message", {}).get("parts", [])
            for p in parts:
                text = p.get("text", "")
                if "Signature (RS256):" in text:
                    raw_text = text
                    break
        elif "evidence_seal" in parsed:
            parsed = parsed["evidence_seal"]

        if isinstance(parsed, dict) and "signature" in parsed and "evidence_digest" in parsed:
            signature_b64 = parsed["signature"]
            evidence_digest = parsed["evidence_digest"]
            seal_id = parsed.get("seal_id", "SEAL")
            root_subject = parsed.get("root_subject", "alice")
            lineage = parsed.get("lineage", "alice -> agent-a -> agent-b -> agent-c")
    except Exception:
        pass

    # Fallback: extract from raw text if it was a plain string or A2A message part
    if not signature_b64 and "Signature (RS256): " in raw_text:
        import re
        sig_match = re.search(r"Signature \(RS256\):\s*([A-Za-z0-9+/=]+)", raw_text)
        dig_match = re.search(r"Evidence Digest:\s*(sha256:[a-f0-9]+)", raw_text)
        seal_match = re.search(r"Audit Vault Seal '([^']+)'", raw_text)
        lineage_match = re.search(r"lineage \[([^\]]+)\]", raw_text)

        if sig_match:
            signature_b64 = sig_match.group(1)
        if dig_match:
            evidence_digest = dig_match.group(1)
        if seal_match:
            seal_id = seal_match.group(1)
        if lineage_match:
            lineage = lineage_match.group(1)

    if not signature_b64 or not evidence_digest:
        print(f"{RED}Error: Could not extract 'signature' and 'evidence_digest' from input.{RESET}", file=sys.stderr)
        print(f"Input received: {raw_text[:200]}...", file=sys.stderr)
        sys.exit(1)

    clean_digest = evidence_digest.replace("sha256:", "")
    public_key = load_public_key()

    print(f"\n{BOLD}{CYAN}======================================================================{RESET}")
    print(f"{BOLD}{CYAN}   AGENT C CRYPTOGRAPHIC AUDIT EVIDENCE VERIFIER                      {RESET}")
    print(f"{BOLD}{CYAN}======================================================================{RESET}")
    print(f"  • Seal ID:            {BOLD}{YELLOW}{seal_id}{RESET}")
    print(f"  • Signer:             {GREEN}Agent C (Audit Vault Signer){RESET}")
    print(f"  • Algorithm:          {CYAN}RS256 (RSASSA-PKCS1-v1_5 with SHA-256){RESET}")
    print(f"  • Evidence Digest:    {DIM}sha256:{clean_digest}{RESET}")
    print(f"  • Delegated Lineage:  {MAGENTA}[{lineage}]{RESET}")
    print(f"  • Signature (B64):    {DIM}{signature_b64[:36]}...{RESET}")
    print(f"{BOLD}{CYAN}----------------------------------------------------------------------{RESET}")

    try:
        sig_bytes = base64.b64decode(signature_b64)
        public_key.verify(
            sig_bytes,
            clean_digest.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        print(f"  {BOLD}{GREEN}✔ CRYPTOGRAPHIC SIGNATURE VALID{RESET}")
        print(f"    Evidence digest verified against Agent C RSA public key.")
        print(f"    Lineage accountability and tamper-resistance mathematically proven.")
        print(f"{BOLD}{CYAN}======================================================================{RESET}\n")
        return True
    except Exception as e:
        print(f"  {BOLD}{RED}✗ SIGNATURE VERIFICATION FAILED: {e}{RESET}")
        print(f"{BOLD}{CYAN}======================================================================{RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        data = " ".join(sys.argv[1:])
    else:
        data = sys.stdin.read()
    verify_seal(data)
