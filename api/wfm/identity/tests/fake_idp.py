"""A fake OpenID Connect provider for tests: real RSA keys, real signed id tokens, served through
`responses` so Authlib talks to it exactly as it would to Entra ID or Keycloak."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import responses
from authlib.jose import JsonWebKey, jwt
from django.test import Client

ISSUER = "https://idp.example.org/tenant-1/v2.0"
CLIENT_ID = "wfm-client-id"
TENANT = "tenant-1"
CALLBACK = "/api/v1/auth/sso/entra/callback"
START = "/api/v1/auth/sso/entra/start"


class FakeIdp:
    def __init__(self, *, kid: str = "key-1") -> None:
        self.kid = kid
        self.key = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": kid})
        self.claims: dict[str, Any] = {}  # overrides for the next id token
        self.token_requests: list[dict[str, list[str]]] = []
        self.token_status = 200

    # --- documents the provider publishes -------------------------------------------------
    def discovery(self) -> dict[str, Any]:
        return {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/authorize",
            "token_endpoint": f"{ISSUER}/token",
            "jwks_uri": f"{ISSUER}/keys",
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "code_challenge_methods_supported": ["S256"],
        }

    def jwks(self) -> dict[str, Any]:
        return {"keys": [self.key.as_dict(is_private=False)]}

    # --- tokens ------------------------------------------------------------------------------
    def id_token(self, *, key: Any = None, **overrides: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "sub": "pairwise-sub-1",
            "oid": "object-id-1",
            "aud": CLIENT_ID,
            "iat": now,
            "exp": now + 3600,
            "tid": TENANT,
            "preferred_username": "pat@example.org",
            "email": "pat@example.org",
            "name": "Pat Planner",
            "groups": ["WFM Planners"],
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}  # None removes a claim
        header = {"alg": "RS256", "kid": self.kid}
        return str(jwt.encode(header, claims, key or self.key).decode())

    def install(self, rsps: responses.RequestsMock, *, nonce: dict[str, str]) -> None:
        """Serve discovery, keys and the token endpoint. The token endpoint signs an id token whose
        nonce is whatever the browser's start request carried (read from `nonce`)."""
        rsps.add(responses.GET, f"{ISSUER}/.well-known/openid-configuration", json=self.discovery())
        rsps.add(responses.GET, f"{ISSUER}/keys", json=self.jwks())

        def token(request: Any) -> tuple[int, dict[str, str], str]:
            self.token_requests.append(parse_qs(request.body))
            if self.token_status != 200:
                return self.token_status, {}, json.dumps({"error": "server_error"})
            body = {
                "access_token": "access-token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "id_token": self.pending_id_token(nonce),
            }
            return 200, {}, json.dumps(body)

        rsps.add_callback(responses.POST, f"{ISSUER}/token", callback=token)

    # set by tests: how to build the id token once the nonce is known
    def pending_id_token(self, nonce: dict[str, str]) -> str:
        return self.id_token(**{"nonce": nonce["value"], **self.claims})


class Flow:
    """Drives the browser side of an authorisation-code flow against the app and a FakeIdp."""

    def __init__(self, client: Client, idp: FakeIdp, rsps: responses.RequestsMock) -> None:
        self.client, self.idp = client, idp
        self.nonce: dict[str, str] = {"value": ""}
        idp.install(rsps, nonce=self.nonce)
        self.state = ""
        self.challenge = ""
        self.location = ""

    def start(self, next_path: str = "/") -> Any:
        response = self.client.get(START, {"next": next_path})
        if response.status_code == 302 and response["Location"].startswith(ISSUER):
            self.location = response["Location"]
            query = parse_qs(urlparse(self.location).query)
            self.state = query["state"][0]
            self.nonce["value"] = query["nonce"][0]
            self.challenge = query["code_challenge"][0]
        return response

    def callback(self, **overrides: str) -> Any:
        params = {"code": "auth-code", "state": self.state, **overrides}
        return self.client.get(CALLBACK, params)

    def verifier_matches_challenge(self) -> bool:
        verifier = self.idp.token_requests[-1]["code_verifier"][0]
        digest = hashlib.sha256(verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == self.challenge
