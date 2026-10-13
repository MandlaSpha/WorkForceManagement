"""Role-based endpoint authentication. Every API operation must declare who may call it; a
contract test fails if one does not (tests/contracts)."""

from __future__ import annotations

from django.http import HttpRequest
from ninja.security import SessionAuth

from wfm.accounts.models import Role, User

from .errors import feature_disabled, forbidden, unauthorised
from .features import FeatureOrCore, is_enabled


class RoleSessionAuth(SessionAuth):
    """Session login plus a role allow-list. Also enforces CSRF on unsafe methods."""

    def __init__(self, *roles: Role, feature: FeatureOrCore) -> None:
        # `feature` has no default on purpose: every protected operation must say which sellable
        # feature it belongs to (or CORE), so a new endpoint cannot slip outside the switch.
        super().__init__()
        self.roles = frozenset(roles)
        self.feature = feature

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
        if not is_enabled(self.feature):
            raise feature_disabled()
        return user


def current_user(request: HttpRequest) -> User:
    """The signed-in user of a request that passed `RoleSessionAuth` (the one place that knows the
    authenticated user lives on `request.auth`)."""
    return request.auth  # type: ignore[attr-defined, no-any-return]


ANY_ROLE: tuple[Role, ...] = ()
