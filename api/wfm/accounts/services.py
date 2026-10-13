"""Commands for authentication. Every outcome is audited (AUD-05, AUD-07)."""

from __future__ import annotations

from collections.abc import Collection
from datetime import timedelta

from django.conf import settings
from django.contrib import auth
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from wfm.audit import services as audit
from wfm.audit.models import Action, Outcome
from wfm.core import request_context

from .models import User


class InvalidCredentialsError(Exception):
    """Deliberately generic: the caller must not learn whether the account exists or is locked."""


def login(
    *,
    request: HttpRequest,
    username: str,
    password: str,
    allowed_roles: Collection[str] = (),
) -> User:
    """Sign in.

    A rejected attempt must still persist its failure counter and audit event, so the
    transaction commits first and the exception is raised only after it has closed. Raising
    inside the atomic block would roll the bookkeeping back and lockout would never trigger.
    """
    with transaction.atomic():
        user = _attempt(
            request=request, username=username, password=password, allowed_roles=allowed_roles
        )
    if user is None:
        raise InvalidCredentialsError
    return user


def _attempt(
    *, request: HttpRequest, username: str, password: str, allowed_roles: Collection[str]
) -> User | None:
    user = User.objects.select_for_update().filter(username=username).first()

    if user is None:
        # Never store the attempted username: people sometimes type their password into it.
        audit.record(
            actor=None, action=Action.LOGIN_FAILED, outcome=Outcome.FAILED, reason="unknown_account"
        )
        return None

    now = timezone.now()
    if user.locked_until and user.locked_until > now:
        audit.record(
            actor=user, action=Action.LOGIN_LOCKED, outcome=Outcome.DENIED, reason="account_locked"
        )
        return None

    authenticated = auth.authenticate(request, username=username, password=password)
    if authenticated is None or not user.is_active:
        user.failed_login_count += 1
        reason = "bad_password"
        if user.failed_login_count >= settings.LOGIN_MAX_FAILURES:
            user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            user.failed_login_count = 0
            reason = "locked_after_repeated_failures"
        user.save(update_fields=["failed_login_count", "locked_until"])
        audit.record(actor=user, action=Action.LOGIN_FAILED, outcome=Outcome.FAILED, reason=reason)
        return None

    if allowed_roles and user.role not in allowed_roles:
        # Local accounts are restricted to break-glass roles; the password was right but this
        # account must sign in through the organisation's identity provider.
        audit.record(
            actor=user,
            action=Action.LOGIN_FAILED,
            outcome=Outcome.DENIED,
            reason="local_login_not_allowed_for_role",
        )
        return None

    user.failed_login_count = 0
    user.locked_until = None
    user.save(update_fields=["failed_login_count", "locked_until"])
    auth.login(request, user)  # rotates the session key (session-fixation defence)
    request_context.refresh_session(request.session.session_key)
    audit.record(actor=user, action=Action.LOGIN_SUCCESS)
    return user


def logout(*, request: HttpRequest, actor: User) -> None:
    with transaction.atomic():
        auth.logout(request)
        audit.record(actor=actor, action=Action.LOGOUT)  # last write: see audit.services
