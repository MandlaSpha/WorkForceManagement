"""Role-based endpoint authentication. Every API operation must declare who may call it; a
contract test fails if one does not (tests/contracts)."""

from __future__ import annotations

from django.http import HttpRequest
from ninja.security import SessionAuth

from wfm.accounts.models import Role

from .errors import forbidden, unauthorised


class RoleSessionAuth(SessionAuth):
    """Session login plus a role allow-list. Also enforces CSRF on unsafe methods."""

    def __init__(self, *roles: Role) -> None:
        super().__init__()
        self.roles = frozenset(roles)

    def authenticate(self, request: HttpRequest, key: str | None) -> object:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or not user.is_active:
            raise unauthorised()
        if self.roles and user.role not in self.roles:
            from wfm.audit import services as audit
            from wfm.audit.models import Action, Outcome

            audit.record(
                actor=user,
                action=Action.ACCESS_DENIED,
                outcome=Outcome.DENIED,
                entity_type="endpoint",
                entity_id=request.path[:200],
            )
            raise forbidden()
        return user


ANY_ROLE: tuple[Role, ...] = ()
