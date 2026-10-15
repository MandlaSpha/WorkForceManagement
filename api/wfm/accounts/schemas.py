from ninja import Schema

from wfm.core.features import REGISTRY, Feature, enabled_features

from .models import User


class LoginIn(Schema):
    username: str
    password: str
    provider: str = "local"
    """Which identity provider to check the credentials with (GET /auth/providers lists them)."""


class OwnPasswordIn(Schema):
    current: str
    new: str


class MeOut(Schema):
    username: str
    displayName: str  # noqa: N815 - camelCase on the wire
    role: str
    mustChangePassword: bool  # noqa: N815 - an admin set a temporary password
    features: list[Feature]
    """The features switched on in this deployment. The UI hides what is missing; the API
    refuses it regardless (FEAT-01)."""


def me_out(user: User) -> MeOut:
    return MeOut(
        username=user.username,
        displayName=user.get_full_name() or user.username,
        role=user.role,
        mustChangePassword=user.must_change_password,
        features=[f for f in REGISTRY if f in enabled_features()],
    )
