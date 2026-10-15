from __future__ import annotations

from django.contrib.auth import update_session_auth_hash
from django.http import HttpRequest
from django.middleware.csrf import get_token
from ninja import Router

from wfm.core.features import CORE
from wfm.core.permissions import ANY_ROLE, RoleSessionAuth

from . import services, user_services
from .models import User
from .schemas import MeOut, OwnPasswordIn, me_out

router = Router(tags=["auth"])
authenticated = RoleSessionAuth(*ANY_ROLE, feature=CORE)

# Signing in lives in wfm.identity.api: it works with any identity provider, local accounts
# included.


@router.get("/csrf", auth=None, summary="Set the CSRF cookie and return the token")
def csrf(request: HttpRequest) -> dict[str, str]:
    # get_token() flags the cookie for update; Django's CsrfViewMiddleware then sets it.
    return {"csrfToken": get_token(request)}


@router.post("/logout", auth=authenticated, summary="Sign out")
def logout(request: HttpRequest) -> dict[str, bool]:
    services.logout(request=request, actor=request.user)  # type: ignore[arg-type]
    return {"ok": True}


@router.get("/me", auth=authenticated, response=MeOut, summary="The signed-in user")
def me(request: HttpRequest) -> MeOut:
    user: User = request.user  # type: ignore[assignment]
    return me_out(user)


@router.post("/change-password", auth=authenticated, summary="Change your own password")
def change_password(request: HttpRequest, body: OwnPasswordIn) -> dict[str, bool]:
    signed_in: User = request.user  # type: ignore[assignment]
    user = user_services.change_own_password(user=signed_in, current=body.current, new=body.new)
    update_session_auth_hash(request, user)  # keep this session; other sessions end
    return {"ok": True}
