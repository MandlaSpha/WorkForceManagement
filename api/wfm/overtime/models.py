"""Overtime requests and the pay they are priced from (requirement OT-01).

A salary is a pay figure: it is set only by the customer's admin, is never returned by the API, and
never appears in the audit trail, logs or traces. What a request costs is worked out on the server
and shown only to the roles that approve it.
"""

from __future__ import annotations

from typing import Any, Self

from django.db import models

from wfm.accounts.models import Role, User
from wfm.core.scoping import ScopedQuerySet

from .policy import ALL_SCOPE_ROLES, COST_ROLES, PAY_ROLES


class PayQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        return self if user.role in PAY_ROLES else self.none()

    def for_pricing(self, user: Any) -> Self:
        """For working out a cost on the server: whoever may see a cost, never the salary itself."""
        return self if user.role in COST_ROLES else self.none()


class EmployeePay(models.Model):
    employee = models.OneToOneField(
        "scheduling.Employee", on_delete=models.CASCADE, related_name="pay"
    )
    monthly_salary = models.DecimalField(max_digits=10, decimal_places=2)
    # Somebody who ordinarily works Sundays is paid the ordinary overtime rate for them.
    ordinarily_works_sundays = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = PayQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(monthly_salary__gt=0), name="overtime_salary_positive"
            )
        ]

    def __str__(self) -> str:
        return f"pay of employee {self.employee_id}"


class OvertimeStatus(models.TextChoices):
    PENDING = "pending", "Waiting"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


class OvertimeQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        if user.role in ALL_SCOPE_ROLES:
            return self
        if user.role == Role.LEAD:  # their own team, and their own
            return self.filter(
                models.Q(employee__manager__user=user) | models.Q(employee__user=user)
            )
        return self.none()


class OvertimeRequest(models.Model):
    employee = models.ForeignKey(
        "scheduling.Employee", on_delete=models.PROTECT, related_name="overtime_requests"
    )
    day = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()  # after the start, on the same day
    minutes = models.PositiveSmallIntegerField()
    reason = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=10, choices=OvertimeStatus.choices, default=OvertimeStatus.PENDING
    )
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(
        db_default=models.Func(function="now", output_field=models.DateTimeField())
    )
    decided_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    # What it was priced at the moment it was approved (rands), so a later change of rules or pay
    # does not rewrite what was agreed. Null while waiting, or when no salary was on file.
    approved_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # OT-03: what was really worked, recorded afterwards by somebody other than the person. Paid
    # at most as far as it was approved; the cost is the approved price in proportion.
    worked_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    worked_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    worked_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    worked_at = models.DateTimeField(null=True, blank=True)

    objects = OvertimeQuerySet.as_manager()

    class Meta:
        ordering = ["day", "start_time", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="overtime_times_ordered",
            ),
            models.CheckConstraint(
                condition=models.Q(minutes__gte=1) & models.Q(minutes__lte=720),
                name="overtime_minutes_range",
            ),
            models.CheckConstraint(
                condition=models.Q(worked_minutes__isnull=True) | models.Q(worked_minutes__lte=720),
                name="overtime_worked_range",
            ),
        ]
        indexes = [models.Index(fields=["day"], name="overtime_day")]

    def __str__(self) -> str:
        return f"overtime {self.employee_id} {self.day}"


class OvertimeRates(models.Model):
    """Rates that are not per person: one row. The standby allowance is paid for each day on
    standby, whether or not the person is called out."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    standby_allowance = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    def __str__(self) -> str:
        return "overtime rates"


class OvertimeBudget(models.Model):
    """What the customer set aside for overtime and standby in a month (the first of the month)."""

    month = models.DateField(unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gte=0), name="overtime_budget_nonneg")
        ]

    def __str__(self) -> str:
        return f"overtime budget {self.month:%Y-%m}"


class StandbyStatus(models.TextChoices):
    BOOKED = "booked", "On standby"
    CANCELLED = "cancelled", "Cancelled"


class StandbyQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        if user.role in ALL_SCOPE_ROLES:
            return self
        if user.role == Role.LEAD:
            return self.filter(
                models.Q(employee__manager__user=user) | models.Q(employee__user=user)
            )
        return self.none()


class StandbyShift(models.Model):
    """A day on which somebody is on call (OT-02). The allowance is fixed when it is booked; a
    call-out is the time actually worked while on standby, priced like overtime."""

    employee = models.ForeignKey(
        "scheduling.Employee", on_delete=models.PROTECT, related_name="standby_shifts"
    )
    day = models.DateField()
    status = models.CharField(
        max_length=10, choices=StandbyStatus.choices, default=StandbyStatus.BOOKED
    )
    allowance = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    booked_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(
        db_default=models.Func(function="now", output_field=models.DateTimeField())
    )
    call_out_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    call_out_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    call_out_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    objects = StandbyQuerySet.as_manager()

    class Meta:
        ordering = ["day", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "day"],
                condition=models.Q(status="booked"),
                name="standby_one_booking_a_day",
            ),
            models.CheckConstraint(
                condition=models.Q(call_out_minutes__isnull=True)
                | models.Q(call_out_minutes__lte=720),
                name="standby_callout_range",
            ),
        ]
        indexes = [models.Index(fields=["day"], name="standby_day")]

    def __str__(self) -> str:
        return f"standby {self.employee_id} {self.day}"
