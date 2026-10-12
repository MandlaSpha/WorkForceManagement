from __future__ import annotations

from django.http import HttpRequest
from django.middleware.csrf import CsrfViewMiddleware

from .errors import ApiError


def enforce_csrf(request: HttpRequest) -> None:
    """CSRF check for endpoints that have no session auth yet (login). Ninja marks its views
    csrf-exempt, so we run Django's own check explicitly."""
    reason = CsrfViewMiddleware(lambda r: None).process_view(request, lambda r: None, (), {})  # type: ignore[arg-type, return-value]
    if reason is not None:
        raise ApiError(403, "auth.csrf", "CSRF check failed", "Missing or invalid CSRF token.")
