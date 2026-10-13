"""LDAP / Active Directory sign-in (requirement AUTH-09).

The password is verified by binding to the directory *as the user*, never by reading or comparing
a stored hash. Finding the user's DN is done first with a read-only service account.

Safety rules this adapter enforces:
- an empty password is refused before any bind (an empty simple bind succeeds anonymously on many
  servers, which would let anyone in);
- the username is escaped before it goes into a search filter (no LDAP injection);
- TLS with a validated certificate is required unless `allow_insecure` is set for development;
- connections time out rather than hang a web worker;
- zero or several matching users is a refusal, never "pick the first".
"""

from __future__ import annotations

import ssl
from collections.abc import Callable
from typing import Any

from ldap3 import Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import parse_dn

from ..config import LdapConfig, secret_from_env
from ..types import AuthenticationFailedError, Identity, ProviderMisconfiguredError

MAX_CREDENTIAL_LENGTH = 512

# (user DN or None, password or None) -> an unbound ldap3 connection. Tests inject a mock server.
ConnectionFactory = Callable[[str | None, str | None], Connection]


def _default_factory(cfg: LdapConfig) -> ConnectionFactory:
    uri = cfg.server_uri.lower()
    if uri.startswith("ldap://") and not cfg.start_tls and not cfg.allow_insecure:
        raise ProviderMisconfiguredError(
            f"LDAP provider '{cfg.key}' uses plain ldap:// without start_tls: passwords would "
            "travel unencrypted. Use ldaps://, enable start_tls, or set allow_insecure for "
            "development only."
        )
    tls = Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=cfg.ca_certs_file)
    server = Server(
        cfg.server_uri,
        use_ssl=uri.startswith("ldaps://"),
        tls=tls,
        connect_timeout=cfg.connect_timeout_s,
    )

    def factory(user: str | None, password: str | None) -> Connection:
        return Connection(
            server,
            user=user,
            password=password,
            receive_timeout=cfg.receive_timeout_s,
            raise_exceptions=False,
        )

    return factory


class LdapProvider:
    kind = "ldap"

    def __init__(self, cfg: LdapConfig, *, connection_factory: ConnectionFactory | None = None):
        self.cfg = cfg
        self._factory = connection_factory or _default_factory(cfg)

    @property
    def key(self) -> str:
        return self.cfg.key

    def authenticate(self, username: str, password: str) -> Identity:
        # Before anything else: an empty password must never reach a bind.
        if not username or not password:
            raise AuthenticationFailedError("empty_credentials")
        if len(username) > MAX_CREDENTIAL_LENGTH or len(password) > MAX_CREDENTIAL_LENGTH:
            raise AuthenticationFailedError("credentials_too_long")
        try:
            return self._authenticate(username, password)
        except LDAPException as exc:
            # network, TLS, timeout: never expose which, and never let it become a 500
            raise AuthenticationFailedError(f"directory_error:{type(exc).__name__}") from None

    def _authenticate(self, username: str, password: str) -> Identity:
        cfg = self.cfg
        service = self._factory(
            cfg.bind_dn, secret_from_env(cfg.bind_password_env, what="LDAP bind password")
        )
        try:
            if cfg.start_tls and not service.start_tls():
                raise AuthenticationFailedError("directory_error:start_tls")
            if not service.bind():
                raise AuthenticationFailedError("directory_error:service_bind")

            attributes = [
                cfg.subject_attribute,
                cfg.username_attribute,
                cfg.email_attribute,
                cfg.display_name_attribute,
                "memberOf",
            ]
            service.search(
                cfg.user_search_base,
                cfg.user_filter.format(username=escape_filter_chars(username)),
                attributes=attributes,
                size_limit=2,
            )
            if not service.entries:
                raise AuthenticationFailedError("unknown_user")
            if len(service.entries) > 1:
                raise AuthenticationFailedError("ambiguous_user")
            entry = service.entries[0]
            user_dn = entry.entry_dn

            # Verify the password by binding as the user on a separate connection.
            user_conn = self._factory(user_dn, password)
            try:
                if cfg.start_tls and not user_conn.start_tls():
                    raise AuthenticationFailedError("directory_error:start_tls")
                if not user_conn.bind():
                    raise AuthenticationFailedError("bad_credentials")
            finally:
                user_conn.unbind()

            return Identity(
                provider=cfg.key,
                subject=_subject(_first(entry, cfg.subject_attribute)),
                username=_first(entry, cfg.username_attribute) or username,
                email=_first(entry, cfg.email_attribute),
                email_verified=True,  # the directory is the authority on its own addresses
                display_name=_first(entry, cfg.display_name_attribute),
                groups=self._groups(service, user_dn, entry),
            )
        finally:
            service.unbind()

    def _groups(self, service: Connection, user_dn: str, entry: Any) -> tuple[str, ...]:
        cfg = self.cfg
        dns: list[str] = []
        if cfg.group_base:
            service.search(
                cfg.group_base,
                cfg.group_filter.format(user_dn=escape_filter_chars(user_dn)),
                attributes=["cn"],
            )
            dns = [e.entry_dn for e in service.entries]
        elif cfg.groups_from_member_of and "memberOf" in entry.entry_attributes_as_dict:
            dns = [str(v) for v in entry.memberOf.values]
        return tuple(_cn(dn) if cfg.group_format == "cn" else dn for dn in dns)


def _first(entry: Any, attribute: str) -> str:
    """One attribute value as text ("" when the entry lacks it)."""
    if attribute not in entry.entry_attributes_as_dict:
        return ""
    value = entry[attribute].value
    if isinstance(value, list):
        value = value[0] if value else ""
    return "" if value is None else str(value)


def _subject(raw: str) -> str:
    """A stable, comparable id: Active Directory prints objectGUID as {XXXXXXXX-...}."""
    subject = raw.strip().strip("{}").lower()
    if not subject:
        raise AuthenticationFailedError(
            "no_subject"
        )  # without a stable id the account cannot be linked
    return subject


def _cn(dn: str) -> str:
    """The first name component of a DN: "CN=WFM Planners,OU=Groups,DC=x" -> "WFM Planners"."""
    try:
        return str(parse_dn(dn)[0][1])
    except Exception:
        return dn
