"""Emailed report schedules (RPT-04, RPT-10).

A schedule belongs to the person who made it. What it sends is built as that person, with the same
scoping as the screen, so a report can never hold more than its owner may see. Recipients must be on
a domain the customer's admin has allowed.
"""

from __future__ import annotations

from typing import Any, Self

from django.db import models

from wfm.accounts.models import Role, User
from wfm.core.scoping import ScopedQuerySet


class ReportKind(models.TextChoices):
    SCORECARD = "scorecard", "Analytics scorecard"
    PEAKS = "peaks", "Peaks and troughs"


class Frequency(models.TextChoices):
    DAILY = "daily", "Every day"
    WEEKLY = "weekly", "Every week"
    MONTHLY = "monthly", "Every month"


class Outcome(models.TextChoices):
    NEVER = "", "Not sent yet"
    SENT = "sent", "Sent"
    FAILED = "failed", "Could not be sent"
    STOPPED = "stopped", "Stopped"


class ScheduleQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        if user.role == Role.ADMIN:  # the customer's admin can see, pause and remove any
            return self
        return self.filter(owner=user)


class ReportSchedule(models.Model):
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    report = models.CharField(max_length=20, choices=ReportKind.choices)
    queue = models.ForeignKey(
        "telephony.Queue", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    recipients = models.JSONField(default=list)
    frequency = models.CharField(max_length=10, choices=Frequency.choices)
    hour = models.PositiveSmallIntegerField()  # local time
    weekday = models.PositiveSmallIntegerField(default=0)  # Monday is 0; weekly only
    day_of_month = models.PositiveSmallIntegerField(default=1)  # 1 to 28; monthly only
    paused = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    last_outcome = models.CharField(max_length=10, choices=Outcome.choices, blank=True)

    objects = ScheduleQuerySet.as_manager()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(hour__lte=23), name="reports_schedule_hour_range"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.report} {self.frequency} for {self.owner_id}"


class ReportSettings(models.Model):
    """One row: the email domains reports may be sent to. Empty means nothing may be sent."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    allowed_domains = models.JSONField(default=list)
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    def __str__(self) -> str:
        return "report settings"
