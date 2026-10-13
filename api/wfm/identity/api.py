"""Sign-in endpoints that work with any configured identity provider (AUTH-01, AUTH-02).

  GET  /auth/providers                     what the login page may offer
  POST /auth/login                         credentials, checked by the chosen provider
  GET  /auth/sso/{id}/start                send the browser to an OIDC provider
  GET  /auth/sso/{id}/callback             the OIDC provider sends it back here

Users only ever see generic failures (AUTH-11): the reason a provider refused is recorded in the
audit trail, never returned.
"""

from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from ninja import Router, Schema

from wfm.accounts import services as account_services
from wfm.accounts.schemas import LoginIn, MeOut, me_out
from wfm.audit import services as audit
from wfm.audit.models import Action, Outcome
from wfm.core.csrf import enforce_csrf
from wfm.core.errors import ApiError, not_found
from wfm.core.redirects import safe_next

from . import registry
from .config import LdapConfig, LocalConfig, OidcConfig
from .providers.ldap import LdapProvider
from .providers.oidc import OidcProvider
from .services import complete_login
from .types import AuthenticationFailedError, ProviderMisconfiguredError

log = logging.getLogger(__name__)
router = Router(tags=["auth"])

SSO_FAILED_URL = "/login?error=sso_failed"


class ProviderOut(Schema):
    id: str
    kind: str
    label: str
    flow: str
    """"credentials": show a username and password form. "redirect": send the browser away."""
    startUrl: str | None = None  # noqa: N815 - camelCase on the wire
    restricted: bool = False
    """Local accounts limited to certain roles (break-glass): offer them as emergency access."""


@router.get("/providers", auth=None, response=list[ProviderOut], summary="Sign-in methods on offer")
def list_providers(request: HttpRequest) -> list[ProviderOut]:
    out: list[ProviderOut] = []
    for cfg in registry.enabled():
        if isinstance(cfg, OidcConfig):
            out.append(
                ProviderOut(
                    id=cfg.key,
                    kind=cfg.kind,
                    label=cfg.label,
                    flow="redirect",
                    startUrl=f"/api/v1/auth/sso/{cfg.key}/start",
                )
            )
        else:
            out.append(
                ProviderOut(
                    id=cfg.key,
                    kind=cfg.kind,
                    label=cfg.label,
                    flow="credentials",
                    restricted=isinstance(cfg, LocalConfig) and bool(cfg.allowed_roles),
                )
            )
    return out


def _ldap(key: str) -> LdapProvider:
    adapter = registry.adapter(key)
    if not isinstance(adapter, LdapProvider):
        raise ProviderMisconfiguredError(f"Provider '{key}' is not an LDAP provider")
    return adapter


def _oidc(key: str) -> OidcProvider:
    adapter = registry.adapter(key)
    if not isinstance(adapter, OidcProvider):
        raise ProviderMisconfiguredError(f"Provider '{key}' is not an OIDC provider")
    return adapter


def _invalid() -> ApiError:
    return ApiError(
        401, "auth.invalid_credentials", "Invalid credentials", "Username or password is incorrect."
    )


@router.post("/login", auth=None, response=MeOut, summary="Sign in with a username and password")
def login(request: HttpRequest, payload: LoginIn) -> MeOut:
    enforce_csrf(request)
    cfg = registry.config(payload.provider)
    if cfg is None or isinstance(cfg, OidcConfig):
        # unknown, disabled, or a redirect provider: the same answer, so nothing is revealed
        raise _invalid()
    try:
        if isinstance(cfg, LocalConfig):
            user = account_services.login(
                request=request,
                username=payload.username,
                password=payload.password,
                allowed_roles=cfg.allowed_roles,
            )
        else:
            user = _directory_login(request, cfg, payload)
    except (account_services.InvalidCredentialsError, AuthenticationFailedError):
        raise _invalid() from None
    except ProviderMisconfiguredError as exc:
        log.error("Identity provider '%s' is misconfigured: %s", payload.provider, exc)
        raise ApiError(
            503, "auth.provider_unavailable", "Sign-in unavailable", "Please try another method."
        ) from None
    return me_out(user)


def _directory_login(request: HttpRequest, cfg: LdapConfig, payload: LoginIn):  # type: ignore[no-untyped-def]
    adapter = _ldap(cfg.key)
    try:
        identity = adapter.authenticate(payload.username, payload.password)
    except AuthenticationFailedError as exc:
        # The typed username is not stored (people sometimes type their password into it).
        audit.record(
            actor=None,
            action=Action.LOGIN_FAILED,
            outcome=Outcome.FAILED,
            reason=f"{cfg.key}:{exc.reason}"[:300],
        )
        raise
    return complete_login(request=request, provider=cfg, identity=identity)  # audits its refusals


@router.get("/sso/{provider_id}/start", auth=None, url_name="sso_start", summary="Begin SSO")
def sso_start(request: HttpRequest, provider_id: str, next: str = "/") -> HttpResponse:
    cfg = registry.config(provider_id)
    if not isinstance(cfg, OidcConfig):
        raise not_found()
    try:
        adapter = _oidc(provider_id)
        return adapter.start(request, next_path=safe_next(next))
    except ProviderMisconfiguredError as exc:
        log.error("Identity provider '%s' is misconfigured: %s", provider_id, exc)
        return HttpResponseRedirect(SSO_FAILED_URL)
    except Exception as exc:
        log.warning("SSO start failed for %s: %s", provider_id, type(exc).__name__)
        audit.record(
            actor=None,
            action=Action.LOGIN_FAILED,
            outcome=Outcome.FAILED,
            reason=f"{provider_id}:start_failed:{type(exc).__name__}"[:300],
        )
        return HttpResponseRedirect(SSO_FAILED_URL)


@router.get("/sso/{provider_id}/callback", auth=None, url_name="sso_callback", summary="Finish SSO")
def sso_callback(request: HttpRequest, provider_id: str) -> HttpResponse:
    cfg = registry.config(provider_id)
    if not isinstance(cfg, OidcConfig):
        raise not_found()
    try:
        adapter = _oidc(provider_id)
        identity, next_path = adapter.complete(request)
    except AuthenticationFailedError as exc:
        audit.record(
            actor=None,
            action=Action.LOGIN_FAILED,
            outcome=Outcome.FAILED,
            reason=f"{provider_id}:{exc.reason}"[:300],
        )
        return HttpResponseRedirect(SSO_FAILED_URL)
    except ProviderMisconfiguredError as exc:
        log.error("Identity provider '%s' is misconfigured: %s", provider_id, exc)
        return HttpResponseRedirect(SSO_FAILED_URL)
    try:
        complete_login(request=request, provider=cfg, identity=identity)  # audits its refusals
    except AuthenticationFailedError:
        return HttpResponseRedirect(SSO_FAILED_URL)
    return HttpResponseRedirect(safe_next(next_path))
