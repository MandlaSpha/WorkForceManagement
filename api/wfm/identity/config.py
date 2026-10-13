"""Identity provider configuration (requirement AUTH-03): code, not database rows.

Providers are described in deployment configuration (the WFM_IDENTITY_PROVIDERS setting). Secrets
are never written there: a provider names the environment variable that holds its secret
(`client_secret_env`, `bind_password_env`), so a vault or the platform's secret store can supply it.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from wfm.accounts.models import Role

from .types import ProviderMisconfiguredError


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a typo in a security setting must not be ignored


class RoleRule(_Strict):
    group: str
    role: Role


class Provisioning(_Strict):
    """What happens the first time someone signs in through a provider, and how roles are set."""

    mode: Literal["auto", "linked_only"] = "linked_only"
    """auto: create the user. linked_only: the user must already exist and be matched."""
    default_role: Role | None = None
    """Role for someone who signs in but matches no rule. None means: refuse the sign-in."""
    role_rules: list[RoleRule] = Field(default_factory=list)
    manage_roles: bool = True
    """True: the directory decides the role and it is recomputed at every sign-in, so removing
    someone from a group demotes them. False: the role is set once and managed inside the app."""
    match_existing_by: Literal["email", "username"] | None = None
    """Link a first-time identity to an existing user with the same email/username. Off by default
    because merging accounts on a name the provider does not guarantee is account takeover. Needs
    trust_attributes, and for email a verified address."""
    trust_attributes: bool = False
    """The provider controls usernames and email addresses (a corporate directory), so they may
    be used to link an existing account and email is copied onto the user."""
    case_insensitive_groups: bool = True


class _Provider(_Strict):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")
    label: str
    enabled: bool = True


class LocalConfig(_Provider):
    kind: Literal["local"] = "local"
    key: str = "local"
    label: str = "Username and password"
    allowed_roles: list[Role] = Field(default_factory=list)
    """If set, local accounts may only sign in with these roles (break-glass admin)."""


class LdapConfig(_Provider):
    kind: Literal["ldap"] = "ldap"
    server_uri: str
    """ldaps://dc.example.org:636, or ldap://... together with start_tls."""
    start_tls: bool = False
    allow_insecure: bool = False
    """Permit plain ldap:// without TLS. Development only; sends passwords unencrypted."""
    ca_certs_file: str | None = None
    bind_dn: str
    """Service account used to find the user's DN."""
    bind_password_env: str
    user_search_base: str
    user_filter: str = "(sAMAccountName={username})"
    """{username} is substituted after LDAP-escaping."""
    subject_attribute: str = "objectGUID"
    username_attribute: str = "sAMAccountName"
    email_attribute: str = "mail"
    display_name_attribute: str = "displayName"
    group_base: str | None = None
    group_filter: str = "(member={user_dn})"
    """Used when group_base is set. For nested Active Directory groups use
    (member:1.2.840.113556.1.4.1941:={user_dn})."""
    group_format: Literal["dn", "cn"] = "dn"
    """Match role rules against the group's full DN, or just its CN (the first name component)."""
    groups_from_member_of: bool = True
    """When no group_base is set, read the user's memberOf attribute."""
    connect_timeout_s: float = 5.0
    receive_timeout_s: float = 10.0
    provisioning: Provisioning = Field(default_factory=Provisioning)


class OidcConfig(_Provider):
    kind: Literal["oidc"] = "oidc"
    discovery_url: str
    """The issuer's .well-known/openid-configuration URL."""
    issuer: str | None = None
    """Expected `iss`. Defaults to the issuer in the discovery document; set it explicitly when
    that varies (Entra multi-tenant)."""
    client_id: str
    client_secret_env: str
    scopes: list[str] = Field(default_factory=lambda: ["openid", "profile", "email"])
    subject_claim: str = "sub"
    username_claim: str = "preferred_username"
    email_claim: str = "email"
    name_claim: str = "name"
    groups_claim: str = "groups"
    """Claim holding group ids or names. For Entra, prefer the `roles` claim (app roles) to avoid
    the 200-group overage limit."""
    tenant_id: str | None = None
    """Entra ID: reject tokens whose `tid` differs, so another organisation's accounts cannot
    sign in even if they obtain a token for this client id."""
    allowed_email_domains: list[str] = Field(default_factory=list)
    clock_skew_s: int = 60
    provisioning: Provisioning = Field(default_factory=Provisioning)


ProviderConfig = Annotated[LocalConfig | LdapConfig | OidcConfig, Field(discriminator="kind")]
_adapter: TypeAdapter[list[ProviderConfig]] = TypeAdapter(list[ProviderConfig])


def parse_providers(
    raw: str | Sequence[Mapping[str, object]] | None,
) -> list[LocalConfig | LdapConfig | OidcConfig]:
    """Validate the configured providers. The local provider is always present, because without
    it nobody could recover from a broken SSO configuration."""
    data: Sequence[Mapping[str, object]]
    if raw is None or raw == "":
        data = []
    elif isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderMisconfiguredError(
                f"WFM_IDENTITY_PROVIDERS is not valid JSON: {exc}"
            ) from exc
    else:
        data = raw
    try:
        providers = _adapter.validate_python(data)
    except Exception as exc:
        raise ProviderMisconfiguredError(f"Invalid identity provider configuration: {exc}") from exc
    keys = [p.key for p in providers]
    if len(keys) != len(set(keys)):
        raise ProviderMisconfiguredError("Identity provider keys must be unique")
    if "local" not in keys:
        providers.insert(0, LocalConfig())
    return providers


def secret_from_env(name: str, *, what: str) -> str:
    """Read a secret by reference. A missing secret is a deployment error, not a silent default."""
    value = os.environ.get(name)
    if not value:
        raise ProviderMisconfiguredError(f"Environment variable {name} ({what}) is not set")
    return value
