"""OpenID Connect sign-in (requirement AUTH-08): Microsoft Entra ID / Azure AD, Okta, Keycloak,
Google, Auth0 and any other OIDC provider.

Authorisation-code flow with PKCE. Authlib creates and checks `state`, `nonce` and the PKCE
verifier (kept in the server-side session) and validates the id token's signature against the
provider's published keys, plus issuer, audience and expiry. On top of that this adapter pins the
Entra tenant, applies an optional email-domain allow-list and turns the claims into an `Identity`.
"""

from __future__ import annotations

import logging
from typing import Any

from authlib.integrations.django_client import OAuth, OAuthError
from authlib.jose.errors import JoseError
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from joserfc.errors import JoseError as JoseRfcError

from ..config import OidcConfig, secret_from_env
from ..types import AuthenticationFailedError, Identity

log = logging.getLogger(__name__)

SESSION_NEXT = "wfm_sso_next"


def _as_list(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(str(v) for v in value)
    return ()


class OidcProvider:
    kind = "oidc"

    def __init__(self, cfg: OidcConfig) -> None:
        self.cfg = cfg
        self._oauth = OAuth()
        self._oauth.register(
            name=cfg.key,
            client_id=cfg.client_id,
            client_secret=secret_from_env(cfg.client_secret_env, what="OIDC client secret"),
            server_metadata_url=cfg.discovery_url,
            client_kwargs={"scope": " ".join(cfg.scopes), "code_challenge_method": "S256"},
        )

    @property
    def key(self) -> str:
        return self.cfg.key

    def _client(self) -> Any:
        return self._oauth.create_client(self.cfg.key)

    def _redirect_uri(self, request: HttpRequest) -> str:
        path = reverse("api-v1:sso_callback", kwargs={"provider_id": self.cfg.key})
        base = getattr(settings, "WFM_PUBLIC_BASE_URL", "")
        # Behind a proxy the request's own host can differ from the public one the identity
        # provider has registered, so a deployment can pin the public base URL.
        return f"{base.rstrip('/')}{path}" if base else request.build_absolute_uri(path)

    def start(self, request: HttpRequest, *, next_path: str) -> HttpResponse:
        request.session[SESSION_NEXT] = next_path
        response: HttpResponse = self._client().authorize_redirect(
            request, self._redirect_uri(request)
        )
        return response

    def complete(self, request: HttpRequest) -> tuple[Identity, str]:
        """Validate the provider's callback and return who signed in and where to send them."""
        next_path = str(request.session.pop(SESSION_NEXT, "/"))
        try:
            claims_options: dict[str, Any] = {}
            if self.cfg.issuer:
                claims_options["iss"] = {"essential": True, "values": [self.cfg.issuer]}
            token = self._client().authorize_access_token(
                request, claims_options=claims_options or None, leeway=self.cfg.clock_skew_s
            )
        except OAuthError as exc:
            raise AuthenticationFailedError(f"oauth_error:{exc.error or 'unknown'}") from None
        except (JoseError, JoseRfcError) as exc:  # Authlib 1.8 raises joserfc's errors
            raise AuthenticationFailedError(f"token_invalid:{type(exc).__name__}") from None
        except Exception as exc:
            log.warning("OIDC callback failed for %s: %s", self.cfg.key, type(exc).__name__)
            raise AuthenticationFailedError(f"provider_error:{type(exc).__name__}") from None

        claims = token.get("userinfo")
        if not claims:
            raise AuthenticationFailedError("no_id_token")
        return self._identity(dict(claims)), next_path

    def _identity(self, claims: dict[str, Any]) -> Identity:
        cfg = self.cfg
        if cfg.tenant_id and claims.get("tid") != cfg.tenant_id:
            raise AuthenticationFailedError("wrong_tenant")

        subject = claims.get(cfg.subject_claim)
        if not subject:
            raise AuthenticationFailedError("no_subject")
        email = str(claims.get(cfg.email_claim) or "")
        if cfg.allowed_email_domains:
            domain = email.rpartition("@")[2].casefold()
            if domain not in {d.casefold() for d in cfg.allowed_email_domains}:
                raise AuthenticationFailedError("email_domain_not_allowed")

        # Entra sends no email_verified claim. With the tenant pinned (above), the address is one
        # the organisation's own directory administrators control, so it counts as verified.
        verified = claims.get("email_verified")
        email_verified = bool(verified) if verified is not None else bool(cfg.tenant_id)

        if cfg.groups_claim not in claims and cfg.groups_claim in (
            claims.get("_claim_names") or {}
        ):
            # Entra "group overage": over 200 groups, so they are not in the token. Use app roles
            # (groups_claim: "roles") instead; until then this user has no groups.
            log.warning("OIDC provider %s: group claim overage for a user; groups unknown", cfg.key)

        return Identity(
            provider=cfg.key,
            subject=str(subject),
            username=str(claims.get(cfg.username_claim) or email or subject),
            email=email,
            email_verified=email_verified,
            display_name=str(claims.get(cfg.name_claim) or ""),
            groups=_as_list(claims.get(cfg.groups_claim)),
        )
