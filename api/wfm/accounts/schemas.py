from ninja import Schema

from .models import User


class LoginIn(Schema):
    username: str
    password: str
    provider: str = "local"
    """Which identity provider to check the credentials with (GET /auth/providers lists them)."""


class MeOut(Schema):
    username: str
    displayName: str  # noqa: N815 - camelCase on the wire
    role: str


def me_out(user: User) -> MeOut:
    return MeOut(
        username=user.username,
        displayName=user.get_full_name() or user.username,
        role=user.role,
    )
