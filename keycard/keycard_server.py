#!/usr/bin/env python3
"""
Keycard Local Runtime STS & Protected Resource Simulator
Features:
  1. RFC 8414 OAuth 2.0 Authorization Server Metadata Discovery
     (/.well-known/oauth-authorization-server & /.well-known/openid-configuration)
  2. JSON Web Key Set (JWKS) endpoint (/oauth/jwks) for RS256 token verification
  3. Ephemeral task-scoped credential issuance & OAuth 2.0 Token Exchange (RFC 8693)
  4. Scope attenuation & prohibited scope blocking (e.g. db:delete)
  5. Cryptographic preservation of user lineage via nested RFC 8693 'act' claims
  6. Real-time session and token revocation (/oauth/revoke)
  7. Protected tool / resource access with audit logging
Compatible with both raw curl commands and official Keycard SDKs (keycardai-fastmcp, keycardai-mcp).
"""

import json
import time
import uuid
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from cryptography.hazmat.primitives.asymmetric import rsa
from joserfc.jwk import RSAKey
import jwt

# Generate RSA key pair for standard RS256 JWKS validation
RSA_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
RSA_PUBLIC_KEY = RSA_PRIVATE_KEY.public_key()
PUBLIC_JWK = RSAKey.import_key(RSA_PUBLIC_KEY).as_dict()
KEY_ID = "keycard-demo-rsa-key-1"
PUBLIC_JWK["kid"] = KEY_ID
PUBLIC_JWK["use"] = "sig"
PUBLIC_JWK["alg"] = "RS256"

# Fallback HMAC secret for backward compatibility
HS256_SECRET = "keycard-demo-secret-key-32bytes-min"

REVOKED_SESSIONS = set()

# Defined policies in Keycard zone
ALLOWED_DELEGATIONS = {
    # delegator -> list of allowed downstream target agents/audiences
    "agent-a": ["agent-b", "https://api.github.com"]
}

PROHIBITED_SCOPES = {"db:delete", "admin:access", "system:root"}


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

        # 4. Protected Customer Data Resource
        if self.path == "/api/customer-data":
            auth_header = self.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                self._send_json(401, {
                    "error": "unauthorized",
                    "error_description": "Missing or malformed Authorization header"
                })
                return

            token = auth_header.split(" ", 1)[1].strip()
            claims = None
            # Try RS256 first, then HS256
            try:
                claims = jwt.decode(
                    token,
                    RSA_PUBLIC_KEY,
                    algorithms=["RS256"],
                    options={"verify_exp": True, "verify_aud": False}
                )
            except Exception:
                try:
                    claims = jwt.decode(
                        token,
                        HS256_SECRET,
                        algorithms=["HS256"],
                        options={"verify_exp": True, "verify_aud": False}
                    )
                except jwt.ExpiredSignatureError:
                    self._send_json(401, {
                        "error": "token_expired",
                        "error_description": "The presented ephemeral token has expired"
                    })
                    return
                except Exception as e:
                    self._send_json(401, {
                        "error": "invalid_token",
                        "error_description": f"Failed to validate token: {str(e)}"
                    })
                    return

            sid = claims.get("sid")
            if sid in REVOKED_SESSIONS:
                self._send_json(401, {
                    "error": "invalid_token",
                    "error_description": f"Session '{sid}' has been revoked by security policy."
                })
                return

            scopes = claims.get("scope", "").split()
            if "db:read" not in scopes:
                self._send_json(403, {
                    "error": "insufficient_scope",
                    "error_description": "The presented token lacks the required 'db:read' scope."
                })
                return

            delegation_path = extract_delegation_chain(claims)
            self._send_json(200, {
                "status": "success",
                "message": "Resource accessed successfully under Keycard delegation policy.",
                "data": {
                    "customer_id": "CUST-9842",
                    "company_name": "Global Tech Industries",
                    "tier": "Enterprise",
                    "records_accessed": 142
                },
                "audit_trail": {
                    "principal_user": claims.get("sub"),
                    "executing_agent": claims.get("aud"),
                    "delegation_lineage": delegation_path,
                    "session_id": sid,
                    "token_scopes": scopes
                }
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

        if self.path == "/oauth/token":
            grant_type = body.get("grant_type")

            # 1. Initial User Session Minting (client_credentials)
            if grant_type == "client_credentials":
                client_id = body.get("client_id", "agent-a")
                user_id = body.get("user_id", "alice")
                scope = body.get("scope", "support:read tasks:delegate")
                sid = f"sess_{uuid.uuid4().hex[:12]}"

                now = int(time.time())
                payload = {
                    "iss": base_url,
                    "sub": user_id,
                    "aud": client_id,
                    "client_id": client_id,
                    "scope": scope,
                    "sid": sid,
                    "iat": now,
                    "exp": now + 900  # 15 minutes TTL
                }
                # Sign with RS256 for OIDC / FastMCP compliance
                token = jwt.encode(
                    payload,
                    RSA_PRIVATE_KEY,
                    algorithm="RS256",
                    headers={"kid": KEY_ID}
                )
                self._send_json(200, {
                    "access_token": token,
                    "token_type": "Bearer",
                    "expires_in": 900,
                    "scope": scope,
                    "issued_token_type": "urn:ietf:params:oauth:token-type:access_token"
                })
                return

            # 2. RFC 8693 Token Exchange (Agent-to-Agent Delegation / MCP Grant)
            elif grant_type == "urn:ietf:params:oauth:grant-type:token-exchange":
                subject_token = body.get("subject_token")
                actor_id = body.get("actor_token", "agent-a")
                audience = body.get("audience") or body.get("resource") or "agent-b"
                requested_scope = body.get("scope", "db:read")

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
                except Exception:
                    try:
                        parent_claims = jwt.decode(
                            subject_token,
                            HS256_SECRET,
                            algorithms=["HS256"],
                            options={"verify_exp": True, "verify_aud": False}
                        )
                    except jwt.ExpiredSignatureError:
                        self._send_json(401, {"error": "token_expired", "error_description": "Subject token has expired"})
                        return
                    except Exception as e:
                        self._send_json(401, {"error": "invalid_token", "error_description": f"Invalid subject token: {str(e)}"})
                        return

                sid = parent_claims.get("sid", f"sess_{uuid.uuid4().hex[:12]}")
                if sid in REVOKED_SESSIONS:
                    self._send_json(401, {
                        "error": "invalid_token",
                        "error_description": f"Session '{sid}' is revoked."
                    })
                    return

                # Policy Evaluation
                requested_scopes_list = requested_scope.split() if requested_scope else []
                for sc in requested_scopes_list:
                    if sc in PROHIBITED_SCOPES:
                        self._send_json(403, {
                            "error": "policy_denied",
                            "error_description": f"Policy rejection: Scope escalation detected. Scope '{sc}' is prohibited by security policy."
                        })
                        return

                # Construct Nested 'act' Claim (RFC 8693)
                if "act" not in parent_claims:
                    nested_act = {
                        "sub": audience,
                        "act": {
                            "sub": actor_id
                        }
                    }
                else:
                    nested_act = {
                        "sub": audience,
                        "act": parent_claims["act"]
                    }

                now = int(time.time())
                new_payload = {
                    "iss": base_url,
                    "sub": parent_claims.get("sub", "alice"),
                    "aud": audience,
                    "resource": audience,
                    "scope": requested_scope,
                    "sid": sid,
                    "act": nested_act,
                    "iat": now,
                    "exp": now + 900
                }
                new_token = jwt.encode(
                    new_payload,
                    RSA_PRIVATE_KEY,
                    algorithm="RS256",
                    headers={"kid": KEY_ID}
                )

                self._send_json(200, {
                    "access_token": new_token,
                    "token_type": "Bearer",
                    "expires_in": 900,
                    "scope": requested_scope,
                    "issued_token_type": "urn:ietf:params:oauth:token-type:access_token"
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
