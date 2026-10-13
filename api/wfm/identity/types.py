"""The neutral shapes every sign-in method is reduced to. An adapter's only job is to turn a
foreign login (an OIDC token, an LDAP bind) into an `Identity`; everything after that
(linking, provisioning, role mapping, auditing) is shared and lives in services.py."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Identity:
    provider: str
    """Key of the configured provider this identity came from."""
    subject: str
    """Stable, never-reused id at that provider (Entra `oid`, LDAP `objectGUID`/`entryUUID`,
    OIDC `sub`). Accounts are linked by (provider, subject), never by a name that can change."""
    username: str
    email: str = ""
    email_verified: bool = False
    display_name: str = ""
    groups: tuple[str, ...] = ()


class AuthenticationFailedError(Exception):
    """A provider refused the sign-in. `reason` is a short internal code for the audit trail
    (e.g. "bad_credentials", "state_mismatch"); it is never shown to the user, who only ever sees
    a generic message, so the error cannot be used to probe for accounts."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ProviderMisconfiguredError(Exception):
    """The deployment's identity configuration is unusable (missing secret, bad URL)."""
