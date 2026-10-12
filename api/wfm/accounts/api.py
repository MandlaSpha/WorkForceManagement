from __future__ import annotations

from django.http import HttpRequest
from django.middleware.csrf import get_token
from ninja import Router

from wfm.core.csrf import enforce_csrf
from wfm.core.errors import ApiError
from wfm.core.permissions import ANY_ROLE, RoleSessionAuth

from . import services
from .models import User
from .schemas import LoginIn, MeOut

router = Router(tags=["auth"])
authenticated = RoleSessionAuth(*ANY_ROLE)


def _me(user: User) -> MeOut:
    return MeOut(
        username=user.username,
        displayName=user.get_full_name() or user.username,
        role=user.role,
    )


@router.get("/csrf", auth=None, summary="Set the CSRF cookie and return the token")
def csrf(request: HttpRequest) -> dict[str, str]:
    # get_token() flags the cookie for update; Django's CsrfViewMiddleware then sets it.
    return {"csrfToken": get_token(request)}


@router.post("/login", auth=None, response=MeOut, summary="Sign in")
def login(request: HttpRequest, payload: LoginIn) -> MeOut:
    enforce_csrf(request)
    try:
        user = services.login(request=request, username=payload.username, password=payload.password)
    except services.InvalidCredentialsError:
        raise ApiError(
            401,
            "auth.invalid_credentials",
            "Invalid credentials",
            "Username or password is incorrect.",
        ) from None
    return _me(user)


@router.post("/logout", auth=authenticated, summary="Sign out")
def logout(request: HttpRequest) -> dict[str, bool]:
    services.logout(request=request, actor=request.user)  # type: ignore[arg-type]
    return {"ok": True}


@router.get("/me", auth=authenticated, response=MeOut, summary="The signed-in user")
def me(request: HttpRequest) -> MeOut:
    return _me(request.user)  # type: ignore[arg-type]
