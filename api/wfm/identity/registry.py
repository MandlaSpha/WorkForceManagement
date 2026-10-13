"""The configured identity providers, read once from settings (requirement AUTH-02/AUTH-03).

Configuration is validated on first use, not at import, so a broken configuration is reported with
its reason instead of stopping Django from starting, and tests can change settings and call
`reset()`. Adapters are built lazily because they read secrets from the environment.
"""

from __future__ import annotations

from django.conf import settings

from .config import LdapConfig, LocalConfig, OidcConfig, parse_providers
from .providers.ldap import LdapProvider
from .providers.oidc import OidcProvider
from .types import ProviderMisconfiguredError

Config = LocalConfig | LdapConfig | OidcConfig
Adapter = LdapProvider | OidcProvider

_configs: dict[str, Config] | None = None
_adapters: dict[str, Adapter] = {}


def reset() -> None:
    """Forget everything read so far (tests, or after configuration changes)."""
    global _configs
    _configs = None
    _adapters.clear()


def configs() -> dict[str, Config]:
    global _configs
    if _configs is None:
        _configs = {c.key: c for c in parse_providers(settings.WFM_IDENTITY_PROVIDERS)}
    return _configs


def enabled() -> list[Config]:
    return [c for c in configs().values() if c.enabled]


def config(key: str) -> Config | None:
    """The enabled provider with this key, or None. A disabled provider is indistinguishable from
    one that does not exist."""
    cfg = configs().get(key)
    return cfg if cfg is not None and cfg.enabled else None


def adapter(key: str) -> Adapter:
    cfg = config(key)
    if cfg is None or isinstance(cfg, LocalConfig):
        raise ProviderMisconfiguredError(f"No directory provider '{key}'")
    if key not in _adapters:
        _adapters[key] = LdapProvider(cfg) if isinstance(cfg, LdapConfig) else OidcProvider(cfg)
    return _adapters[key]
