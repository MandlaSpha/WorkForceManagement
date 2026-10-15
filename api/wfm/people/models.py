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

from .policy import ALL_SCOPE_ROLES, SELF_ROLES


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
    # Blackout periods and the limit on people away at once apply to leave that can wait. Sick,
    # family responsibility and maternity leave cannot, so they are never refused for those.
    restricted = models.BooleanField(default=True)

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
        if user.role in ALL_SCOPE_ROLES:
            return self
        if user.role == Role.LEAD:  # their own team, and their own
            return self.filter(
                models.Q(employee__manager__user=user) | models.Q(employee__user=user)
            )
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


class SwapStatus(models.TextChoices):
    OPEN = "open", "Open: waiting for a colleague"
    AWAITING_APPROVAL = "awaiting_approval", "Waiting for approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


OPEN_SWAP_STATUSES = (SwapStatus.OPEN, SwapStatus.AWAITING_APPROVAL)


class SwapRequestQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        if user.role in ALL_SCOPE_ROLES:
            return self
        if user.role == Role.LEAD:  # swaps with someone on their team, or their own
            return self.filter(
                models.Q(from_employee__manager__user=user)
                | models.Q(to_employee__manager__user=user)
                | models.Q(from_employee__user=user)
                | models.Q(to_employee__user=user)
            )
        if user.role == Role.AGENT:  # an agent sees swaps they are a party to, nothing else
            return self.filter(
                models.Q(from_employee__user=user) | models.Q(to_employee__user=user)
            )
        return self.none()

    def open_to(self, employee: Any) -> Self:
        """Requests still waiting for a colleague that `employee` could take: from someone else,
        on a queue they are skilled on. This is the board; it deliberately does not go through
        `for_user`, which shows an agent only the swaps they are in. It carries no names."""
        return self.filter(status=SwapStatus.OPEN, queue__skilled__employee=employee).exclude(
            from_employee=employee
        )


class SwapRequest(models.Model):
    """A person posts one of their shifts (`from_*`). A colleague who could work it takes it by
    offering one of their own (`to_*`, empty while the request is open); a lead then approves and
    the two shifts are exchanged. The shifts are kept as a snapshot (day and shift), because the
    roster rows are replaced when the swap happens; approving checks the roster still matches.
    No free text, like leave. Other agents see an open request without the poster's name."""

    queue = models.ForeignKey("telephony.Queue", on_delete=models.PROTECT, related_name="+")
    from_employee = models.ForeignKey(
        "scheduling.Employee", on_delete=models.PROTECT, related_name="swaps_asked"
    )
    from_day = models.DateField()
    from_template = models.ForeignKey(
        "scheduling.ShiftTemplate", on_delete=models.PROTECT, related_name="+"
    )
    to_employee = models.ForeignKey(
        "scheduling.Employee",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="swaps_offered",
    )
    to_day = models.DateField(null=True, blank=True)
    to_template = models.ForeignKey(
        "scheduling.ShiftTemplate",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    status = models.CharField(max_length=20, choices=SwapStatus.choices, default=SwapStatus.OPEN)
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(
        db_default=models.Func(function="now", output_field=models.DateTimeField())
    )
    colleague_answered_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    objects = SwapRequestQuerySet.as_manager()

    class Meta:
        ordering = ["from_day", "id"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(from_employee=models.F("to_employee")),
                name="people_swap_two_people",
            ),
            models.CheckConstraint(
                condition=models.Q(to_employee__isnull=False)
                | models.Q(status__in=["open", "cancelled", "rejected"]),
                name="people_swap_matched_has_counterpart",
            ),
        ]
        indexes = [models.Index(fields=["status", "from_day"], name="people_swap_by_status")]

    def __str__(self) -> str:
        return f"{self.from_employee_id}<->{self.to_employee_id} ({self.status})"


class AvailabilityKind(models.TextChoices):
    UNAVAILABLE = "unavailable", "Cannot work"  # a constraint: the roster refuses it
    PREFERRED = "preferred", "Would rather work"  # a wish: shown, never enforced


class AvailabilityQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        if user.role in ALL_SCOPE_ROLES:
            return self
        if user.role == Role.LEAD:  # their own team, and their own
            return self.filter(
                models.Q(employee__manager__user=user) | models.Q(employee__user=user)
            )
        if user.role == Role.AGENT:
            return self.filter(employee__user=user)  # an agent sees only their own
        return self.none()


class Availability(models.Model):
    """A weekly window in which a person declares they cannot work, or would rather. Nothing
    declared means nothing is known: it is not the same as available (SCH-08)."""

    employee = models.ForeignKey(
        "scheduling.Employee", on_delete=models.CASCADE, related_name="availability"
    )
    weekday = models.PositiveSmallIntegerField()  # Monday is 0
    start_time = models.TimeField()
    end_time = models.TimeField()  # 00:00 means the end of the day
    kind = models.CharField(max_length=12, choices=AvailabilityKind.choices)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")

    objects = AvailabilityQuerySet.as_manager()

    class Meta:
        ordering = ["weekday", "start_time", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(weekday__gte=0) & models.Q(weekday__lte=6),
                name="people_availability_weekday",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.weekday} {self.start_time}-{self.end_time} {self.kind}"


class LeaveBlackout(models.Model):
    """Days on which leave of a restricted kind cannot be asked for (a year-end close, a launch)."""

    name = models.CharField(max_length=60)
    date_from = models.DateField()
    date_to = models.DateField()
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["date_from", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_to__gte=models.F("date_from")),
                name="people_blackout_dates_ordered",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} {self.date_from}..{self.date_to}"


class LeaveLimit(models.Model):
    """One row for the whole deployment: the most people who may be away at once on restricted
    leave (none: no limit). Locked while a request is approved, so two approvals made at the same
    moment cannot both squeeze under it."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    max_concurrent = models.PositiveSmallIntegerField(null=True, blank=True)
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="people_leave_limit_single_row"),
            models.CheckConstraint(
                condition=models.Q(max_concurrent__isnull=True) | models.Q(max_concurrent__gte=1),
                name="people_leave_limit_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"at most {self.max_concurrent or 'any number'} away at once"
