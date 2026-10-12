from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from django.http import HttpRequest, HttpResponse

from . import request_context

MAX_UA_LENGTH = 300


class RequestContextMiddleware:
    """Captures request id, IP, user agent, session hash and trace id for the audit trail."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        ctx = request_context.RequestContext(
            request_id=request.headers.get("X-Request-ID") or uuid4().hex,
            ip=self._client_ip(request),
            user_agent=request.headers.get("User-Agent", "")[:MAX_UA_LENGTH],
            session_hash=request_context.hash_session_key(request.session.session_key),
            trace_id=self._trace_id(request),
        )
        token = request_context.activate(ctx)
        try:
            response = self.get_response(request)
        finally:
            request_context.deactivate(token)
        response["X-Request-ID"] = ctx.request_id
        return response

    @staticmethod
    def _client_ip(request: HttpRequest) -> str | None:
        return request.META.get("REMOTE_ADDR")

    @staticmethod
    def _trace_id(request: HttpRequest) -> str:
        # W3C traceparent: version-traceid-spanid-flags
        parts = request.headers.get("traceparent", "").split("-")
        return parts[1] if len(parts) == 4 else ""
