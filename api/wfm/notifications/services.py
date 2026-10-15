"""Sending and reading notifications. `notify` is called inside the transaction of the change it
reports, BEFORE that change's audit event (the audit insert must stay the last write)."""

from __future__ import annotations

from collections.abc import Iterable

from django.db.models.functions import Now

from wfm.accounts.models import User
from wfm.core.errors import not_found

from .models import Notification

MAX_MESSAGE = 200


def notify(recipients: Iterable[User | None], *, kind: str, message: str, link: str = "") -> int:
    """Tell each person (None and duplicates are skipped). Returns how many were told."""
    seen: dict[int, User] = {u.pk: u for u in recipients if u is not None and u.is_active}
    Notification.objects.bulk_create(
        Notification(recipient=u, kind=kind, message=message[:MAX_MESSAGE], link=link)
        for u in seen.values()
    )
    return len(seen)


def mark_read(*, user: User, notification_id: int) -> Notification:
    found: Notification | None = (
        Notification.objects.for_user(user).filter(pk=notification_id).first()
    )
    if found is None:
        raise not_found("No such notification.")
    if found.read_at is None:
        found.read_at = Now()
        found.save(update_fields=["read_at"])
        found.refresh_from_db()
    return found


def mark_all_read(*, user: User) -> int:
    return Notification.objects.for_user(user).filter(read_at__isnull=True).update(read_at=Now())
