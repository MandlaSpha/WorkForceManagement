"""Leave: types with their yearly entitlements, and requests (requirements LV-01 to LV-03).

A request holds who, what kind, which days and what state it is in. It has no free text: a reason,
and above all a medical reason, is nobody's business here and must not end up in a database that
planners and leads read.
"""

from __future__ import annotations

from typing import Any, Self

from django.db import models

from wfm.accounts.models import Role, User
from wfm.core.scoping import ScopedQuerySet

from .policy import APPROVE_ROLES, SELF_ROLES


class LeaveTypeQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        return self if user.role in SELF_ROLES else self.none()


class LeaveType(models.Model):
    """A kind of leave. The entitlements are South African (BCEA) defaults until an admin confirms
    them: a default is never passed off as the customer's policy (DAT-10)."""

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=60)
    paid = models.BooleanField(default=True)
    days_per_year = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    confirmed = models.BooleanField(default=False)  # a person confirmed the entitlement

    objects = LeaveTypeQuerySet.as_manager()

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.code


class LeaveStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


class LeaveRequestQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        if user.role in APPROVE_ROLES:
            return self
        if user.role == Role.AGENT:
            return self.filter(employee__user=user)  # an agent sees only their own
        return self.none()


class LeaveRequest(models.Model):
    employee = models.ForeignKey(
        "scheduling.Employee", on_delete=models.PROTECT, related_name="leave_requests"
    )
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="+")
    start_date = models.DateField()
    end_date = models.DateField()  # inclusive
    days = models.PositiveSmallIntegerField()  # working days, public holidays and weekends left out
    # The same days split by the calendar year they fall in, as worked out when it was asked for
    # ({"2026": 5}), so a balance does not shift if the holiday calendar changes later.
    days_by_year = models.JSONField(default=dict)
    status = models.CharField(
        max_length=10, choices=LeaveStatus.choices, default=LeaveStatus.PENDING
    )
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(
        db_default=models.Func(function="now", output_field=models.DateTimeField())
    )
    decided_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    # Shifts taken off the roster when it was approved, so cancelling can put them back:
    # [{"queueId": 1, "day": "2026-05-25", "templateId": 3}, ...]
    cleared_shifts = models.JSONField(default=list)

    objects = LeaveRequestQuerySet.as_manager()

    class Meta:
        ordering = ["start_date", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="people_leave_dates_ordered",
            ),
            models.CheckConstraint(
                condition=models.Q(days__gte=1), name="people_leave_has_working_days"
            ),
        ]
        indexes = [
            models.Index(
                fields=["employee", "status", "start_date"], name="people_leave_by_employee"
            )
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.start_date}..{self.end_date} ({self.status})"
