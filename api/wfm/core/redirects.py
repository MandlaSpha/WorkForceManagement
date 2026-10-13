"""Where a user may be sent after signing in (requirement AUTH-12)."""

from __future__ import annotations


def safe_next(target: object, default: str = "/") -> str:
    """Accept only a same-site path, so a crafted link cannot send a freshly signed-in user to
    another origin (open redirect). Mirrors the check the web app applies."""
    if not isinstance(target, str):
        return default
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        return default
    if any(ord(c) < 32 for c in target):  # no header-splitting control characters
        return default
    if target.startswith("/login"):
        return default
    return target
