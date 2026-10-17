"""The workforce limits capacity is planned against (requirement CAP-01)."""

from __future__ import annotations

from typing import Any, Self

from django.db import models

from wfm.accounts.models import User
from wfm.core.scoping import ScopedQuerySet

from .policy import PLAN_READ_ROLES, READ_ROLES

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


class HiringPlanQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        return self if user.role in PLAN_READ_ROLES else self.none()


class HiringPlan(models.Model):
    """A named monthly hiring plan over 12 to 18 months (CAP-01). Its inputs are stored; the plan
    itself (hires, effective people, gaps) is worked out from them whenever it is read, so it can
    never disagree with the engine."""

    name = models.CharField(max_length=80)
    start_month = models.DateField()  # the first day of the first month
    incumbents = models.DecimalField(max_digits=8, decimal_places=1)
    attrition_pct = models.DecimalField(max_digits=5, decimal_places=2)  # per month
    ramp = models.JSONField(default=list)  # share of full strength by months since hired
    required = models.JSONField(default=list)  # people needed each month
    cost_per_person = models.DecimalField(  # rands per person per month; pay data
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = HiringPlanQuerySet.as_manager()

    class Meta:
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name
