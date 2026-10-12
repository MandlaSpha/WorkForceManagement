from ninja import Schema


class LoginIn(Schema):
    username: str
    password: str


class MeOut(Schema):
    username: str
    displayName: str  # noqa: N815 - camelCase on the wire
    role: str
