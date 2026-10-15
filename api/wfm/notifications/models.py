"""In-app notifications (CFG-05): short messages to a person about their own matters.

A message says what happened to the RECIPIENT's request or roster ("Your annual leave from 25 May
was approved"). It never names another person and never holds a reason, so a notification is safe
to show on a shared screen and to keep. Email can be added later behind the same `notify` call.
"""

from __future__ import annotations

from typing import Any, Self

from django.db import models

from wfm.accounts.models import User
from wfm.core.scoping import ScopedQuerySet


class NotificationQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        return self.filter(recipient=user)  # everyone sees their own, nobody else's


class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=40)  # "roster.published", "leave.approved", ...
    message = models.CharField(max_length=200)
    link = models.CharField(max_length=100, blank=True)  # an app path such as /leave
    created_at = models.DateTimeField(
        db_default=models.Func(function="now", output_field=models.DateTimeField())
    )
    read_at = models.DateTimeField(null=True, blank=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["recipient", "read_at"], name="notif_by_recipient")]

    def __str__(self) -> str:
        return f"{self.recipient_id} {self.kind}"
