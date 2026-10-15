"""User administration (admin only)."""

from __future__ import annotations

from datetime import datetime

from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema, Status

from wfm.core.features import CORE
from wfm.core.permissions import RoleSessionAuth, current_user

from . import user_services as services
from .models import Role, User

router = Router(tags=["users"])
ADMIN = RoleSessionAuth(Role.ADMIN, feature=CORE)


class UserOut(Schema):
    id: int
    username: str
    name: str
    role: str
    roleFromDirectory: bool  # noqa: N815 - the role comes from the provider's groups
    active: bool
    locked: bool
    hasPassword: bool  # noqa: N815 - false for accounts that only sign in through a provider
    mustChangePassword: bool  # noqa: N815
    employee: str | None  # the linked employee's number, or none
    lastLogin: datetime | None  # noqa: N815


class UserIn(Schema):
    username: str
    firstName: str  # noqa: N815
    lastName: str  # noqa: N815
    role: str
    password: str  # temporary: the person must change it at first sign-in


class RoleIn(Schema):
    role: str


class ActiveIn(Schema):
    active: bool


class PasswordIn(Schema):
    password: str


@router.get("", auth=ADMIN, response=list[UserOut], summary="Users")
def list_users(request: HttpRequest) -> list[UserOut]:
    users = User.objects.select_related("employee").order_by("username")
    return [_out(u) for u in users]


@router.post("", auth=ADMIN, response={201: UserOut}, summary="Create a local user")
def create_user(request: HttpRequest, body: UserIn) -> Status[UserOut]:
    user = services.create_user(
        actor=current_user(request),
        username=body.username,
        first_name=body.firstName,
        last_name=body.lastName,
        role=body.role,
        password=body.password,
    )
    return Status(201, _out(user))


@router.put("/{user_id}/role", auth=ADMIN, response=UserOut, summary="Change a user's role")
def set_role(request: HttpRequest, user_id: int, body: RoleIn) -> UserOut:
    return _out(services.set_role(actor=current_user(request), user_id=user_id, role=body.role))


@router.put(
    "/{user_id}/active", auth=ADMIN, response=UserOut, summary="Switch an account off or on"
)
def set_active(request: HttpRequest, user_id: int, body: ActiveIn) -> UserOut:
    return _out(
        services.set_active(actor=current_user(request), user_id=user_id, active=body.active)
    )


@router.post("/{user_id}/unlock", auth=ADMIN, response=UserOut, summary="Unlock an account")
def unlock(request: HttpRequest, user_id: int) -> UserOut:
    return _out(services.unlock(actor=current_user(request), user_id=user_id))


@router.post(
    "/{user_id}/password",
    auth=ADMIN,
    response=UserOut,
    summary="Give a local account a new temporary password",
)
def reset_password(request: HttpRequest, user_id: int, body: PasswordIn) -> UserOut:
    return _out(
        services.reset_password(
            actor=current_user(request), user_id=user_id, password=body.password
        )
    )


def _out(u: User) -> UserOut:
    employee = getattr(u, "employee", None)
    return UserOut(
        id=u.pk,
        username=u.username,
        name=u.get_full_name() or u.username,
        role=u.role,
        roleFromDirectory=u.role_source == "directory",
        active=u.is_active,
        locked=bool(u.locked_until and u.locked_until > timezone.now()),
        hasPassword=u.has_usable_password(),
        mustChangePassword=u.must_change_password,
        employee=employee.emp_no if employee else None,
        lastLogin=u.last_login,
    )
