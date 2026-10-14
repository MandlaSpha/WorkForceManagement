"""The workforce limits capacity is planned against (requirement CAP-01)."""

from __future__ import annotations

from typing import Any, Self

from django.db import models

from wfm.accounts.models import User
from wfm.core.scoping import ScopedQuerySet

from .policy import READ_ROLES

# The UIF tender: up to 350 agents, 100 permanent and 250 seasonal.
TENDER_PERMANENT = 100
TENDER_SEASONAL = 250


class CapacityLimitsQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        return self if user.role in READ_ROLES else self.none()


class CapacityLimits(models.Model):
    """One row for the whole deployment. Until an admin confirms it, the figures are the tender's
    and the screen says so (DAT-10: a default is never passed off as a fact)."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    permanent_limit = models.PositiveSmallIntegerField(default=TENDER_PERMANENT)
    seasonal_limit = models.PositiveSmallIntegerField(default=TENDER_SEASONAL)
    confirmed = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = CapacityLimitsQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="capacity_limits_single_row"),
        ]

    def __str__(self) -> str:
        return f"{self.permanent_limit} permanent + {self.seasonal_limit} seasonal"
