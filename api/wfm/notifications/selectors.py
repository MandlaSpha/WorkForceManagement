"""Reading notifications. Everything starts from `Notification.objects.for_user(user)`."""

from __future__ import annotations

from wfm.accounts.models import User

from .models import Notification

INBOX_SIZE = 50


def inbox(user: User) -> list[Notification]:
    """The newest notifications, read or not."""
    return list(Notification.objects.for_user(user)[:INBOX_SIZE])


def unread_count(user: User) -> int:
    return Notification.objects.for_user(user).filter(read_at__isnull=True).count()
