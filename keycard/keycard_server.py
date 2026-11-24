#!/usr/bin/env python3
"""
Keycard Local Runtime STS & Protected Resource Simulator
Features:
  1. RFC 8414 OAuth 2.0 Authorization Server Metadata Discovery
     (/.well-known/oauth-authorization-server & /.well-known/openid-configuration)
  2. JSON Web Key Set (JWKS) endpoint (/oauth/jwks) for RS256 token verification
  3. Ephemeral task-scoped credential issuance & OAuth 2.0 Token Exchange (RFC 8693)
  4. Scope attenuation & prohibited scope blocking (e.g. db:delete)
  5. Strict delegation bounds: agents cannot delegate permissions they never received (HTTP 403)
  6. Registered delegator policy: unauthorized agents cannot delegate (HTTP 403)
  7. Cryptographic preservation of user lineage via nested RFC 8693 'act' claims
  8. Real-time session and token revocation (/oauth/revoke)
  9. Central delegation audit trail (/audit)
"""

import json
import time
import uuid
import urllib.parse
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from joserfc.jwk import RSAKey
import jwt

# Persistent RSA key pair for standard RS256 JWKS validation across restarts
KEY_FILE = Path(__file__).resolve().parent / "keycard_rsa_key.pem"
if KEY_FILE.exists():
    with open(KEY_FILE, "rb") as f:
        RSA_PRIVATE_KEY = serialization.load_pem_private_key(f.read(), password=None)
else:
    RSA_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with open(KEY_FILE, "wb") as f:
        f.write(RSA_PRIVATE_KEY.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))

RSA_PUBLIC_KEY = RSA_PRIVATE_KEY.public_key()
PUBLIC_JWK = RSAKey.import_key(RSA_PUBLIC_KEY).as_dict()
KEY_ID = "keycard-demo-rsa-key-1"
PUBLIC_JWK["kid"] = KEY_ID
PUBLIC_JWK["use"] = "sig"
PUBLIC_JWK["alg"] = "RS256"

# Fallback HMAC secret for backward compatibility
HS256_SECRET = "keycard-demo-secret-key-32bytes-min"

REVOKED_SESSIONS = set()

# Defined policies in Keycard zone: allowed delegators -> permitted downstream targets
ALLOWED_DELEGATIONS = {
    "agent-a": ["agent-b", "http://127.0.0.1:9002", "https://api.github.com"],
    "agent-b": ["agent-c", "http://127.0.0.1:9003"],
}

PROHIBITED_SCOPES = {"db:delete", "admin:access", "system:root"}

# Global in-memory audit trail
AUDIT_TRAIL = []


def record_audit_event(event_type: str, details: dict):
    entry = {
        "event_id": f"evt_{uuid.uuid4().hex[:8]}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        **details
    }
    AUDIT_TRAIL.append(entry)
    return entry


def extract_delegation_chain(claims):
    """Walks the nested 'act' claims to reconstruct the call chain."""
    chain = []
    act = claims.get("act")
    while act and isinstance(act, dict):
        chain.append(act.get("sub"))
        act = act.get("act")
    return list(reversed(chain))


class KeycardHandler(BaseHTTPRequestHandler):
    def _get_base_url(self):
        host = self.headers.get("Host", "127.0.0.1:8088")
        return f"http://{host}"

    def _send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def do_GET(self):
        base_url = self._get_base_url()

        # 1. Health check
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "service": "keycard-local-sts"})
            return

        # 2. RFC 8414 OAuth 2.0 Authorization Server Discovery
        if self.path in ["/.well-known/oauth-authorization-server", "/.well-known/openid-configuration"]:
            metadata = {
                "issuer": base_url,
                "authorization_endpoint": f"{base_url}/oauth/authorize",
                "token_endpoint": f"{base_url}/oauth/token",
                "jwks_uri": f"{base_url}/oauth/jwks",
                "revocation_endpoint": f"{base_url}/oauth/revoke",
                "audit_endpoint": f"{base_url}/audit",
                "response_types_supported": ["code", "token"],
                "grant_types_supported": [
                    "client_credentials",
                    "urn:ietf:params:oauth:grant-type:token-exchange"
                ],
                "token_endpoint_auth_methods_supported": [
                    "none",
                    "client_secret_post",
                    "client_secret_basic"
                ],
                "code_challenge_methods_supported": ["S256"]
            }
            self._send_json(200, metadata)
            return

        # 3. JWKS Endpoint for RemoteAuthProvider / JWTVerifier
        if self.path == "/oauth/jwks":
            self._send_json(200, {"keys": [PUBLIC_JWK]})
            return

        # 4. Revocation Status Endpoint for Downstream Agents
        if self.path.startswith("/oauth/revoked"):
            self._send_json(200, {"revoked_sessions": list(REVOKED_SESSIONS)})
            return

        # 5. Delegation Audit Trail Endpoint
        if self.path == "/audit":
            self._send_json(200, {
                "total_events": len(AUDIT_TRAIL),
                "audit_trail": AUDIT_TRAIL
            })
            return

        self._send_json(404, {"error": "not_found", "path": self.path})

    def do_POST(self):
        base_url = self._get_base_url()
        content_len = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_len) if content_len > 0 else b""
        content_type = self.headers.get("Content-Type", "")

        # Parse body either as JSON or as application/x-www-form-urlencoded
        body = {}
        if "application/json" in content_type:
            try:
                body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            except json.JSONDecodeError:
                self._send_json(400, {"error": "invalid_request", "error_description": "Malformed JSON"})
                return
        elif "application/x-www-form-urlencoded" in content_type:
            parsed = urllib.parse.parse_qs(body_bytes.decode("utf-8"))
            body = {k: v[0] for k, v in parsed.items()}
        else:
            try:
                body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            except Exception:
                parsed = urllib.parse.parse_qs(body_bytes.decode("utf-8"))
                body = {k: v[0] for k, v in parsed.items()}

        # Audit Trail Reset Endpoint
        if self.path == "/audit/reset":
            AUDIT_TRAIL.clear()
            self._send_json(200, {"status": "reset", "message": "Audit trail cleared."})
            return

        # Audit Event Ingestion Endpoint (from Agent B and Agent C)
        if self.path == "/audit/event":
            event_type = body.get("type", "AGENT_EVENT")
            details = body.get("details", {})
            entry = record_audit_event(event_type, details)
            self._send_json(200, {"status": "ok", "event_id": entry["event_id"]})
            return

        # Keycard IdP: Human User Authentication Endpoint (OIDC / User Login)
        if self.path == "/idp/login":
            username = body.get("username", "alice")
            client_id = body.get("client_id", "agent-a")
            scope = body.get("scope", "support:read tasks:delegate incident:investigate db:read audit:write")
            expires_in = int(body.get("expires_in", 900))
            sid = f"sess_{uuid.uuid4().hex[:12]}"

            now = int(time.time())
            payload = {
                "iss": base_url,
                "sub": username,
                "sub_profile": "user",  # Keycard claim designating genuine human user
                "keycard_app_id": "app_agent_a",
                "aud": client_id,
                "client_id": client_id,
                "scope": scope,
                "sid": sid,
                "iat": now,
                "exp": now + expires_in
            }
            token = jwt.encode(
                payload,
                RSA_PRIVATE_KEY,
                algorithm="RS256",
                headers={"kid": KEY_ID}
            )

            record_audit_event("USER_AUTHENTICATED_IDP", {
                "user_id": username,
                "sub_profile": "user",
                "client_id": client_id,
                "keycard_app_id": "app_agent_a",
                "scope": scope,
                "session_id": sid,
                "expires_in": expires_in,
                "decision": "AUTHORIZED"
            })

            print(f"\033[1;36m[Keycard IdP]\033[0m LOGIN: Human user '{username}' authenticated via IdP on client '{client_id}' (sub_profile: 'user', sid: {sid})", flush=True)
            self._send_json(200, {
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": expires_in,
                "scope": scope,
                "sub": username,
                "sub_profile": "user",
                "issued_token_type": "urn:ietf:params:oauth:token-type:access_token"
            })
            return

        if self.path == "/oauth/token":
            grant_type = body.get("grant_type")

            # 1a. User Authentication via Authorization Code Grant (RFC 6749 §4.1)
            if grant_type == "authorization_code":
                client_id = body.get("client_id", "agent-a")
                user_id = body.get("user_id", "alice")
                scope = body.get("scope", "support:read tasks:delegate incident:investigate db:read audit:write")
                expires_in = int(body.get("expires_in", 900))
                sid = f"sess_{uuid.uuid4().hex[:12]}"

                now = int(time.time())
                payload = {
                    "iss": base_url,
                    "sub": user_id,
                    "sub_profile": "user",
                    "keycard_app_id": "app_agent_a",
                    "aud": client_id,
                    "client_id": client_id,
                    "scope": scope,
                    "sid": sid,
                    "iat": now,
                    "exp": now + expires_in
                }
                token = jwt.encode(
                    payload,
                    RSA_PRIVATE_KEY,
                    algorithm="RS256",
                    headers={"kid": KEY_ID}
                )

                record_audit_event("USER_AUTHENTICATED_OIDC", {
                    "user_id": user_id,
                    "sub_profile": "user",
                    "client_id": client_id,
                    "keycard_app_id": "app_agent_a",
                    "scope": scope,
                    "session_id": sid,
                    "expires_in": expires_in,
                    "decision": "AUTHORIZED"
                })

                print(f"\033[1;36m[Keycard STS]\033[0m AUTH CODE: Issued User Token for user='{user_id}' on client='{client_id}' (sub_profile: 'user', sid: {sid})", flush=True)
                self._send_json(200, {
                    "access_token": token,
                    "token_type": "Bearer",
                    "expires_in": expires_in,
                    "scope": scope,
                    "sub": user_id,
                    "sub_profile": "user",
                    "issued_token_type": "urn:ietf:params:oauth:token-type:access_token"
                })
                return

            # 1b. Application Machine-to-Machine Authentication (client_credentials)
            elif grant_type == "client_credentials":
                client_id = body.get("client_id", "agent-a")
                # When client credentials are used, identity is the application itself (RFC 6749)
                scope = body.get("scope", "support:read tasks:delegate incident:investigate db:read audit:write")
                expires_in = int(body.get("expires_in", 900))
                sid = f"sess_{uuid.uuid4().hex[:12]}"

                now = int(time.time())
                payload = {
                    "iss": base_url,
                    "sub": client_id,  # Application itself is subject
                    "sub_profile": "app",
                    "keycard_app_id": f"app_{client_id}",
                    "aud": client_id,
                    "client_id": client_id,
                    "scope": scope,
                    "sid": sid,
                    "iat": now,
                    "exp": now + expires_in
                }
                token = jwt.encode(
                    payload,
                    RSA_PRIVATE_KEY,
                    algorithm="RS256",
                    headers={"kid": KEY_ID}
                )

                record_audit_event("APP_CREDENTIALS_MINTED", {
                    "client_id": client_id,
                    "sub_profile": "app",
                    "scope": scope,
                    "session_id": sid,
                    "expires_in": expires_in,
                    "decision": "AUTHORIZED"
                })

                print(f"\033[1;36m[Keycard STS]\033[0m M2M: Issued Application Token for client='{client_id}' (sub_profile: 'app', sid: {sid})", flush=True)
                self._send_json(200, {
                    "access_token": token,
                    "token_type": "Bearer",
                    "expires_in": expires_in,
                    "scope": scope,
                    "sub": client_id,
                    "sub_profile": "app",
                    "issued_token_type": "urn:ietf:params:oauth:token-type:access_token"
                })
                return

            # 2. RFC 8693 Token Exchange (Agent-to-Agent Delegation / Multi-Hop)
            elif grant_type == "urn:ietf:params:oauth:grant-type:token-exchange":
                subject_token = body.get("subject_token")

                # Extract actor_id from HTTP Basic Auth, body.actor_token, or body.client_id
                auth_header = self.headers.get("Authorization", "")
                if auth_header.startswith("Basic "):
                    import base64
                    try:
                        cred = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
                        actor_id = cred.split(":", 1)[0]
                    except Exception:
                        actor_id = body.get("actor_token", "agent-a")
                elif "actor_token" in body:
                    actor_id = body["actor_token"]
                elif "client_id" in body:
                    actor_id = body["client_id"]
                else:
                    actor_id = "agent-a"

                audience = body.get("audience") or body.get("resource") or "agent-b"

                if not subject_token:
                    self._send_json(400, {
                        "error": "invalid_request",
                        "error_description": "Missing subject_token parameter"
                    })
                    return

                parent_claims = None
                try:
                    parent_claims = jwt.decode(
                        subject_token,
                        RSA_PUBLIC_KEY,
                        algorithms=["RS256"],
                        options={"verify_exp": True, "verify_aud": False}
                    )
                except jwt.ExpiredSignatureError:
                    record_audit_event("TOKEN_EXCHANGE_REJECTED", {
                        "actor_id": actor_id,
                        "audience": audience,
                        "reason": "EXPIRED_SUBJECT_TOKEN",
                        "decision": "DENIED_401"
                    })
                    self._send_json(401, {"error": "token_expired", "error_description": "Subject token has expired"})
                    return
                except Exception as e:
                    record_audit_event("TOKEN_EXCHANGE_REJECTED", {
                        "actor_id": actor_id,
                        "audience": audience,
                        "reason": f"INVALID_TOKEN: {str(e)}",
                        "decision": "DENIED_401"
                    })
                    self._send_json(401, {"error": "invalid_token", "error_description": f"Invalid subject token: {str(e)}"})
                    return

                sid = parent_claims.get("sid", f"sess_{uuid.uuid4().hex[:12]}")
                if sid in REVOKED_SESSIONS:
                    record_audit_event("TOKEN_EXCHANGE_REJECTED", {
                        "actor_id": actor_id,
                        "audience": audience,
                        "session_id": sid,
                        "reason": "SESSION_REVOKED",
                        "decision": "DENIED_401"
                    })
                    self._send_json(401, {
                        "error": "invalid_token",
                        "error_description": f"Session '{sid}' is revoked."
                    })
                    return

                # Policy Enforcement 1: Unauthorized Agent attempting delegation
                if actor_id not in ALLOWED_DELEGATIONS:
                    print(f"\033[1;31m[Keycard STS]\033[0m POLICY REJECTION: Unauthorized agent '{actor_id}' attempted delegation (HTTP 403)", flush=True)
                    record_audit_event("TOKEN_EXCHANGE_REJECTED", {
                        "actor_id": actor_id,
                        "audience": audience,
                        "session_id": sid,
                        "reason": "UNAUTHORIZED_DELEGATOR",
                        "decision": "DENIED_403"
                    })
                    self._send_json(403, {
                        "error": "unauthorized_client",
                        "error_description": f"Policy rejection: Agent '{actor_id}' is not an authorized delegator in this security zone."
                    })
                    return

                # Scope attenuation defaults based on audience
                requested_scope = body.get("scope")
                if not requested_scope:
                    if "9003" in audience or "agent-c" in audience:
                        requested_scope = "audit:write"
                    elif "9002" in audience or "agent-b" in audience:
                        requested_scope = "incident:investigate db:read"
                    else:
                        requested_scope = "db:read"

                requested_scopes_list = requested_scope.split() if requested_scope else []
                parent_scopes_list = parent_claims.get("scope", "").split()

                # Policy Enforcement 2: Prohibited Scopes (e.g. db:delete, admin:access)
                for sc in requested_scopes_list:
                    if sc in PROHIBITED_SCOPES:
                        print(f"\033[1;31m[Keycard STS]\033[0m POLICY REJECTION: Prohibited scope '{sc}' requested by actor='{actor_id}' (HTTP 403)", flush=True)
                        record_audit_event("TOKEN_EXCHANGE_REJECTED", {
                            "actor_id": actor_id,
                            "audience": audience,
                            "session_id": sid,
                            "prohibited_scope": sc,
                            "reason": "PROHIBITED_SCOPE",
                            "decision": "DENIED_403"
                        })
                        self._send_json(403, {
                            "error": "policy_denied",
                            "error_description": f"Policy rejection: Scope escalation detected. Scope '{sc}' is prohibited by security policy."
                        })
                        return

                # Policy Enforcement 3: Cannot delegate permissions never received
                unheld_scopes = [s for s in requested_scopes_list if s not in parent_scopes_list]
                if unheld_scopes:
                    print(f"\033[1;31m[Keycard STS]\033[0m POLICY REJECTION: Scope escalation: actor '{actor_id}' requested {unheld_scopes} but parent token only holds {parent_scopes_list} (HTTP 403)", flush=True)
                    record_audit_event("TOKEN_EXCHANGE_REJECTED", {
                        "actor_id": actor_id,
                        "audience": audience,
                        "session_id": sid,
                        "requested_scopes": requested_scopes_list,
                        "held_scopes": parent_scopes_list,
                        "unheld_scopes": unheld_scopes,
                        "reason": "UNHELD_SCOPES_DELEGATION",
                        "decision": "DENIED_403"
                    })
                    self._send_json(403, {
                        "error": "invalid_scope",
                        "error_description": f"Policy rejection: Unauthorized delegation. Requested scope(s) {unheld_scopes} exceed permissions held in subject token ({parent_scopes_list}). Agents cannot delegate permissions they never received."
                    })
                    return

                # Construct Nested 'act' Claim (RFC 8693 Chained Lineage)
                previous_actor = None
                if "act" in parent_claims and isinstance(parent_claims["act"], dict):
                    previous_actor = parent_claims["act"].get("sub")
                    nested_act = {
                        "sub": actor_id,
                        "act": parent_claims["act"]
                    }
                else:
                    nested_act = {
                        "sub": actor_id
                    }

                now = int(time.time())
                expires_in = int(body.get("expires_in", 900))
                new_payload = {
                    "iss": base_url,
                    "sub": parent_claims.get("sub", "alice"),
                    "sub_profile": parent_claims.get("sub_profile", "user"),
                    "keycard_app_id": f"app_{actor_id}",
                    "aud": audience,
                    "client_id": actor_id,
                    "resource": audience,
                    "scope": requested_scope,
                    "sid": sid,
                    "act": nested_act,
                    "iat": now,
                    "exp": now + expires_in
                }
                new_token = jwt.encode(
                    new_payload,
                    RSA_PRIVATE_KEY,
                    algorithm="RS256",
                    headers={"kid": KEY_ID}
                )

                lineage_list = [parent_claims.get("sub", "user")] + extract_delegation_chain(new_payload) + [audience]
                chain_str = " -> ".join(lineage_list)

                record_audit_event("TOKEN_EXCHANGE_SUCCESS", {
                    "subject": parent_claims.get("sub", "alice"),
                    "actor": actor_id,
                    "previous_actor": previous_actor,
                    "target_audience": audience,
                    "granted_scopes": requested_scopes_list,
                    "parent_scopes": parent_scopes_list,
                    "lineage": lineage_list,
                    "session_id": sid,
                    "decision": "AUTHORIZED"
                })

                print(f"\033[1;32m[Keycard STS]\033[0m RFC 8693 TOKEN-EXCHANGE: actor='{actor_id}' -> target='{audience}' | Lineage: [{chain_str}] | scope='{requested_scope}'", flush=True)

                self._send_json(200, {
                    "access_token": new_token,
                    "token_type": "Bearer",
                    "expires_in": expires_in,
                    "scope": requested_scope,
                    "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
                    "delegation_info": {
                        "subject": parent_claims.get("sub", "alice"),
                        "actor": actor_id,
                        "previous_actor": previous_actor,
                        "audience": audience,
                        "granted_scopes": requested_scopes_list
                    }
                })
                return

            else:
                self._send_json(400, {
                    "error": "unsupported_grant_type",
                    "error_description": f"Unsupported grant_type '{grant_type}'"
                })
                return

        elif self.path == "/oauth/revoke":
            token = body.get("token")
            sid = body.get("session_id")

            if token:
                try:
                    unverified = jwt.decode(token, options={"verify_signature": False})
                    sid = unverified.get("sid", sid)
                except Exception:
                    pass

            if not sid:
                self._send_json(400, {
                    "error": "invalid_request",
                    "error_description": "Must provide 'token' or 'session_id' to revoke"
                })
                return

            REVOKED_SESSIONS.add(sid)

            record_audit_event("SESSION_REVOKED", {
                "session_id": sid,
                "status": "REVOKED",
                "message": "Session revoked centrally at Keycard STS"
            })

            print(f"\033[1;33m[Keycard STS]\033[0m REVOCATION: Session '{sid}' revoked across all downstream agents.", flush=True)
            self._send_json(200, {
                "status": "revoked",
                "session_id": sid,
                "message": f"Session '{sid}' has been revoked immediately across all downstream agents."
            })
            return

        self._send_json(404, {"error": "not_found", "path": self.path})


def run_server(port=8088):
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, KeycardHandler)
    print(f"Keycard Runtime STS running on http://127.0.0.1:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8088
    run_server(port)
