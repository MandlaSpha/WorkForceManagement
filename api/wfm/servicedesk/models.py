"""Ticket and task workload by resource pool (requirement SD-01).

A work item is a reference, a pool, dates and an effort estimate. It never holds a person: no
requester, no assignee, no free text. The ITSM tool keeps those; this system only needs to know
how much work is due when.
"""

from __future__ import annotations

from typing import Any, Self

from django.db import models

from wfm.core.scoping import ScopedQuerySet

from .policy import READ_ROLES

DEFAULT_PRODUCTIVE_MINUTES = 360  # six productive hours of an eight-hour day


class ScopedByRole(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        return self if user.role in READ_ROLES else self.none()


class ServicePool(models.Model):
    """A group of engineers who work the same kind of tickets: Service Desk, NOC, SOC, Field
    Services... Created the first time an import names it."""

    name = models.CharField(max_length=100, unique=True)
    # How many minutes of a working day an engineer really spends on tickets (the rest is
    # meetings, breaks, training, admin). An assumption until someone confirms it (DAT-10).
    productive_minutes_per_day = models.PositiveSmallIntegerField(
        default=DEFAULT_PRODUCTIVE_MINUTES
    )
    settings_confirmed = models.BooleanField(default=False)

    objects = ScopedByRole.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(productive_minutes_per_day__gte=30)
                & models.Q(productive_minutes_per_day__lte=600),
                name="servicedesk_productive_minutes",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class WorkItem(models.Model):
    ref = models.CharField(max_length=40, unique=True)  # the ITSM reference, e.g. INC0000123
    pool = models.ForeignKey(ServicePool, on_delete=models.PROTECT, related_name="items")
    priority = models.CharField(max_length=10, blank=True)
    opened_at = models.DateTimeField()
    due_at = models.DateTimeField(null=True, blank=True)  # the deadline; none when it has none
    effort_minutes = models.PositiveIntegerField(null=True, blank=True)  # none: not estimated
    closed_at = models.DateTimeField(null=True, blank=True)  # none: still open
    # Survey answers and the first-contact flag, as the ITSM tool exports them (KPI-01). None: the
    # export did not say, which is not the same as "no" or "0".
    first_contact_resolved = models.BooleanField(null=True, blank=True)
    csat = models.PositiveSmallIntegerField(null=True, blank=True)  # 1 to 5
    nps = models.PositiveSmallIntegerField(null=True, blank=True)  # 0 to 10

    objects = ScopedByRole.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["pool", "closed_at", "due_at"], name="sd_open_by_pool"),
            models.Index(fields=["opened_at"], name="sd_opened"),
            models.Index(fields=["closed_at"], name="sd_closed"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(csat__isnull=True) | models.Q(csat__gte=1, csat__lte=5),
                name="servicedesk_csat_range",
            ),
            models.CheckConstraint(
                condition=models.Q(nps__isnull=True) | models.Q(nps__lte=10),
                name="servicedesk_nps_range",
            ),
        ]

    def __str__(self) -> str:
        return self.ref
