"""Per-request facts every audit event needs (AUD-01, AUD-04), held in a context variable so
services cannot forget to pass them."""

from __future__ import annotations

import hashlib
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str = field(default_factory=lambda: uuid4().hex)
    ip: str | None = None
    user_agent: str = ""
    session_hash: str = ""
    trace_id: str = ""


_current: ContextVar[RequestContext | None] = ContextVar("wfm_request_context", default=None)


def current() -> RequestContext:
    """The context of the request being handled, or a fresh one outside a request (jobs, shell)."""
    return _current.get() or RequestContext()


def refresh_session(session_key: str | None) -> None:
    """Re-capture the session hash after the session changed mid-request (sign-in rotates it),
    so the audit event for that action records the session the user now holds."""
    _current.set(replace(current(), session_hash=hash_session_key(session_key)))


def activate(ctx: RequestContext) -> object:
    return _current.set(ctx)


def deactivate(token: object) -> None:
    _current.reset(token)  # type: ignore[arg-type]


def hash_session_key(session_key: str | None) -> str:
    """Audit stores a one-way hash, never the live session key."""
    if not session_key:
        return ""
    return hashlib.sha256(session_key.encode()).hexdigest()[:32]
