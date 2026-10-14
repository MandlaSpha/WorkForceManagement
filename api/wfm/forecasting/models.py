"""Forecast versions and their intervals (requirements FC-01 to FC-03).

A version is one run of a forecast model (Prophet, or the baseline) for a queue and a range of
days, with the staffing requirement worked out from it. This app depends on `wfm.telephony`
(queues and the measured intervals) and never the other way round.
"""

from __future__ import annotations

import uuid
from typing import Any, Self

from django.db import models

from wfm.accounts.models import User
from wfm.core.scoping import ScopedQuerySet
from wfm.telephony.models import Queue

from .policy import READ_ROLES


class ForecastVersionQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        return self if user.role in READ_ROLES else self.none()


class ForecastStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class ForecastVersion(models.Model):
    """One run of the forecast for a queue and a range of days (FC-03). Exactly one version per
    queue is published at a time; publishing another archives it and keeps it as history."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    queue = models.ForeignKey(Queue, on_delete=models.PROTECT, related_name="forecasts")
    label = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=10, choices=ForecastStatus.choices, default=ForecastStatus.DRAFT
    )
    method = models.CharField(max_length=40)
    # The settings this run used, so a version can always be explained later: weeks, decay and
    # the staffing assumptions, including whether they were still assumed defaults.
    params = models.JSONField(default=dict)
    date_from = models.DateField()
    date_to = models.DateField()
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    # clock_timestamp(), not now(): now() is the start of the transaction, so two versions made in
    # one transaction would tie and "newest first" would be a coin toss.
    created_at = models.DateTimeField(
        db_default=models.Func(function="clock_timestamp", output_field=models.DateTimeField())
    )
    published_at = models.DateTimeField(null=True, blank=True)

    objects = ForecastVersionQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["queue"],
                condition=models.Q(status="published"),
                name="forecasting_one_published_per_queue",
            ),
            models.CheckConstraint(
                condition=models.Q(date_to__gte=models.F("date_from")),
                name="forecasting_dates_ordered",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.queue_id} {self.date_from}..{self.date_to} ({self.status})"


class ForecastIntervalQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        return self if user.role in READ_ROLES else self.none()


class ForecastInterval(models.Model):
    version = models.ForeignKey(ForecastVersion, on_delete=models.CASCADE, related_name="intervals")
    interval_start = models.DateTimeField()
    volume = models.FloatField()
    # The 80% range around `volume`, from the model's range for the whole day. Only Prophet gives
    # one; the baseline has none and says so with null.
    volume_lower = models.FloatField(null=True)
    volume_upper = models.FloatField(null=True)
    aht_s = models.FloatField(null=True)
    required_raw = models.PositiveSmallIntegerField(null=True)  # agents on the phone
    required = models.PositiveSmallIntegerField(null=True)  # with shrinkage: agents to roster
    days_used = models.PositiveSmallIntegerField()

    objects = ForecastIntervalQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["version", "interval_start"], name="forecasting_interval_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.version_id} {self.interval_start:%Y-%m-%d %H:%M}"
