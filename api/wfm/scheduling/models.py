"""Shift templates, employees, and the weekly roster (requirements SCH-01, SCH-02, SCH-06, EMP-01).

Staff names are personal data. They are kept here only because a roster needs them, are shown only
to the roles that plan or read rosters, and never appear in logs, traces or analytics.
"""

from __future__ import annotations

import uuid
from typing import Any, Self

from django.db import models

from wfm.accounts.models import Role, User
from wfm.core.scoping import ScopedQuerySet
from wfm.telephony.models import Queue

from .policy import READ_ROLES


class ReadScopedQuerySet(ScopedQuerySet):
    """Visible to the roles that plan or read rosters, nobody else."""

    def for_user(self, user: Any) -> Self:
        return self if user.role in READ_ROLES else self.none()


class ShiftTemplate(models.Model):
    """A named shift on the half-hour grid, for example D1 09:00-17:30. An end that is not after
    the start means the shift runs overnight."""

    code = models.CharField(max_length=10, unique=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    paid_minutes = models.PositiveSmallIntegerField()  # the clock length less unpaid breaks

    objects = ReadScopedQuerySet.as_manager()

    class Meta:
        ordering = ["start_time", "code"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(paid_minutes__gt=0), name="scheduling_shift_paid_positive"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.start_time:%H:%M}-{self.end_time:%H:%M}"


class ContractType(models.TextChoices):
    PERMANENT = "permanent", "Permanent"
    SEASONAL = "seasonal", "Seasonal"


class WorkMode(models.TextChoices):
    OFFICE = "office", "Office"
    REMOTE = "remote", "Remote"
    HYBRID = "hybrid", "Hybrid"


class EmployeeQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        if user.role in READ_ROLES:
            return self
        if user.role == Role.AGENT:
            return self.filter(user=user)  # an agent sees only their own record
        return self.none()


class Employee(models.Model):
    emp_no = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    contract_type = models.CharField(
        max_length=10, choices=ContractType.choices, default=ContractType.PERMANENT
    )
    weekly_hours = models.DecimalField(max_digits=4, decimal_places=1, default=40)
    # DAT-10: a value nobody entered is visibly a default, not a fact.
    weekly_hours_is_default = models.BooleanField(default=True)
    work_mode = models.CharField(max_length=10, choices=WorkMode.choices, default=WorkMode.OFFICE)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)  # seasonal agents (SCH-11)
    user = models.OneToOneField(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="employee"
    )

    objects = EmployeeQuerySet.as_manager()

    class Meta:
        ordering = ["emp_no"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(weekly_hours__gt=0), name="scheduling_employee_hours_positive"
            ),
        ]

    def __str__(self) -> str:
        return self.emp_no


class EmployeeSkill(models.Model):
    """The queues an employee can work, with a level 1 to 3 (EMP-01)."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="skills")
    queue = models.ForeignKey(Queue, on_delete=models.PROTECT, related_name="skilled")
    level = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["employee", "queue"], name="scheduling_skill_unique"),
            models.CheckConstraint(
                condition=models.Q(level__gte=1, level__lte=3), name="scheduling_skill_level"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.queue_id} L{self.level}"


class RosterStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"


class RosterWeek(models.Model):
    """One queue's roster for one week (Monday to Sunday), draft until published (SCH-06)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    queue = models.ForeignKey(Queue, on_delete=models.PROTECT, related_name="roster_weeks")
    week_start = models.DateField()
    status = models.CharField(
        max_length=10, choices=RosterStatus.choices, default=RosterStatus.DRAFT
    )
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    objects = ReadScopedQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["queue", "week_start"], name="scheduling_week_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.queue_id} {self.week_start} ({self.status})"


class ShiftAssignment(models.Model):
    """A person on a shift on a day. One shift per person per day, across every queue."""

    roster_week = models.ForeignKey(
        RosterWeek, on_delete=models.CASCADE, related_name="assignments"
    )
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="assignments")
    day = models.DateField()
    template = models.ForeignKey(ShiftTemplate, on_delete=models.PROTECT, related_name="+")

    objects = ReadScopedQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "day"], name="scheduling_one_shift_per_person_per_day"
            ),
        ]
        indexes = [models.Index(fields=["day"], name="scheduling_assignment_day")]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.day} {self.template_id}"
