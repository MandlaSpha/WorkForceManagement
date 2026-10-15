from __future__ import annotations

from datetime import datetime

from django.http import HttpRequest
from ninja import Router, Schema

from wfm.accounts.models import Role
from wfm.core.features import CORE
from wfm.core.permissions import RoleSessionAuth, current_user

from . import selectors, services
from .models import Notification

router = Router(tags=["notifications"])

# Every role has notifications about its own matters; the data is per recipient.
ANY = RoleSessionAuth(*sorted(Role, key=lambda r: r.value), feature=CORE)


class NotificationOut(Schema):
    id: int
    kind: str
    message: str
    link: str
    createdAt: datetime  # noqa: N815
    read: bool


class InboxOut(Schema):
    unread: int
    items: list[NotificationOut]


@router.get("", auth=ANY, response=InboxOut, summary="Your notifications")
def inbox(request: HttpRequest) -> InboxOut:
    user = current_user(request)
    return InboxOut(
        unread=selectors.unread_count(user),
        items=[_out(n) for n in selectors.inbox(user)],
    )


@router.post("/read-all", auth=ANY, response=dict[str, int], summary="Mark all as read")
def read_all(request: HttpRequest) -> dict[str, int]:
    return {"marked": services.mark_all_read(user=current_user(request))}


@router.post("/{notification_id}/read", auth=ANY, response=NotificationOut, summary="Mark one read")
def read_one(request: HttpRequest, notification_id: int) -> NotificationOut:
    return _out(services.mark_read(user=current_user(request), notification_id=notification_id))


def _out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.pk,
        kind=n.kind,
        message=n.message,
        link=n.link,
        createdAt=n.created_at,
        read=n.read_at is not None,
    )
