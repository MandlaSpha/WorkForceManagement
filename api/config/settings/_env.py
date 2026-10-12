"""Tiny environment helpers (12-factor config, tech spec section 9)."""

from __future__ import annotations

import os
from urllib.parse import unquote, urlparse


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def broker_url_from_env(default: str = "redis://localhost:6379/0") -> str:
    """Celery broker URL. Valkey speaks the Redis protocol, but Aspire hands us `valkey://`
    (and `valkeys://` for TLS), which Celery's transport layer does not know.

    Deliberately not named CELERY_BROKER_URL: the `celery` command line reads that variable
    itself (its --broker option) and would bypass this normalisation."""
    url = os.environ.get("WFM_BROKER_URL", default)
    for valkey_scheme, redis_scheme in (("valkeys://", "rediss://"), ("valkey://", "redis://")):
        if url.startswith(valkey_scheme):
            return redis_scheme + url.removeprefix(valkey_scheme)
    return url


def database_from_env() -> dict[str, object]:
    """Build the Django DATABASES entry from DATABASE_URL or discrete DB_* variables."""
    url = os.environ.get("DATABASE_URL")
    if url:
        parsed = urlparse(url)
        return {
            "NAME": parsed.path.lstrip("/"),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "localhost",
            "PORT": str(parsed.port or 5432),
        }
    return {
        "NAME": env("DB_NAME", "wfm"),
        "USER": env("DB_USER", "wfm"),
        "PASSWORD": env("DB_PASSWORD", "wfm"),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "5432"),
    }
