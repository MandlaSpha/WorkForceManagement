"""Building the roster: assigning shifts, publishing, exporting (SCH-02, SCH-04, SCH-06, SCH-07).

Every assignment is checked before it is written: the person is skilled on the queue and employed
that day, is not already rostered elsewhere that day, keeps the rest between shifts, does
not work more days in a row than the compliance rules (CFG-06) allow, and stays within their
contract hours for the week. The person's row is locked while it is checked, so two planners
cannot each add a shift that is fine alone and wrong together. The audit event is the LAST
write of the transaction.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models.functions import Now
from wfm_engine import availability as rules_availability
from wfm_engine.roster import (
    breaks_rest_rule,
    consecutive_run,
    shift_span,
)

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action, Outcome
from wfm.core.errors import ApiError, not_found
from wfm.notifications import services as notifications
from wfm.people.models import Availability, AvailabilityKind, LeaveRequest, LeaveStatus
from wfm.telephony.models import Queue

from .models import (
    Employee,
    EmployeeSkill,
    RosterStatus,
    RosterWeek,
    ShiftAssignment,
    ShiftTemplate,
)
from .selectors import rules_on

_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def week_start_of(day: date) -> date:
    """The Monday of the week a day is in."""
    return day - timedelta(days=day.weekday())


@dataclass(frozen=True, slots=True)
class AssignResult:
    assignment: ShiftAssignment | None  # None when the shift was cleared
    week: RosterWeek


class _RefusalError(Exception):
    """A rule was broken. Raised inside the transaction, audited after it has rolled back (an
    event written inside would be rolled back with the rest), then turned into an ApiError."""

    def __init__(self, queue: Queue | None, code: str, detail: str, status: int) -> None:
        super().__init__(code)
        self.queue, self.code, self.detail, self.status = queue, code, detail, status


def _refused(
    user: User, queue: Queue | None, code: str, detail: str, status: int = 422
) -> _RefusalError:
    return _RefusalError(queue, code, detail, status)


def _audited(user: User, refusal: _RefusalError) -> ApiError:
    audit.record(
        actor=user,
        action=Action.ROSTER_REFUSED,
        outcome=Outcome.FAILED,
        entity_type="queue" if refusal.queue else "roster",
        entity_id=refusal.queue.name if refusal.queue else "",
        reason=refusal.code,
    )
    return ApiError(refusal.status, refusal.code, "Roster change refused", refusal.detail)


@contextmanager
def _audit_refusals(user: User) -> Iterator[None]:
    """Use as `with _audit_refusals(user), transaction.atomic():`. The transaction rolls back
    first, then the refusal is audited in its own committed write and raised as an ApiError."""
    try:
        yield
    except _RefusalError as refusal:
        raise _audited(user, refusal) from None


def _queue_for(user: User, queue_id: int) -> Queue:
    queue: Queue | None = Queue.objects.for_user(user).filter(pk=queue_id).first()
    if queue is None:
        raise not_found("No such queue.")
    return queue


def _monday(user: User, queue: Queue, week_start: date) -> None:
    if week_start.weekday() != 0:
        raise _refused(user, queue, "roster.not_a_monday", "A roster week starts on a Monday.")


# --- assigning ---------------------------------------------------------------------------------


def assign(
    *, user: User, queue_id: int, employee_id: int, day: date, template_id: int | None
) -> AssignResult:
    """Put a person on a shift on a day, replacing any shift they have that day on this queue, or
    clear it when `template_id` is None. Raises a refusal (audited) when a rule is broken."""
    queue = _queue_for(user, queue_id)
    try:
        with transaction.atomic():
            return _assign(user, queue, employee_id, day, template_id)
    except _RefusalError as refusal:
        raise _audited(user, refusal) from None
    except IntegrityError:
        conflict = _RefusalError(
            queue, "roster.conflict", "Someone changed this at the same moment. Try again.", 409
        )
        raise _audited(user, conflict) from None


def _assign(
    user: User, queue: Queue, employee_id: int, day: date, template_id: int | None
) -> AssignResult:
    week, _ = RosterWeek.objects.select_for_update(no_key=True).get_or_create(
        queue=queue, week_start=week_start_of(day)
    )
    if week.status == RosterStatus.PUBLISHED:
        raise _refused(
            user,
            queue,
            "roster.published",
            "This week is published. Return it to draft before changing it.",
            409,
        )
    # Lock the person's row: every check below reads their other shifts.
    employee = (
        Employee.objects.select_for_update(no_key=True)
        .for_user(user)
        .filter(pk=employee_id)
        .first()
    )
    if employee is None:
        raise not_found("No such employee.")

    existing = (
        ShiftAssignment.objects.filter(employee=employee, day=day)
        .select_related("roster_week", "template")
        .first()
    )
    if existing is not None and existing.roster_week_id != week.pk:
        raise _refused(
            user,
            queue,
            "roster.already_rostered",
            "This person is already rostered on another queue that day.",
        )

    if template_id is None:
        return _clear(user, queue, employee, day, week, existing)

    template = ShiftTemplate.objects.for_user(user).filter(pk=template_id).first()
    if template is None:
        raise not_found("No such shift.")
    _check_rules(user, queue, employee, day, template, existing)

    old_code = existing.template.code if existing else None
    if existing is not None:
        existing.template = template
        existing.save(update_fields=["template"])
        assignment = existing
    else:
        assignment = ShiftAssignment.objects.create(
            roster_week=week, employee=employee, day=day, template=template
        )
    audit.record(  # last write of the transaction
        actor=user,
        action=Action.ROSTER_ASSIGNED,
        entity_type="roster_week",
        entity_id=str(week.pk),
        subject_employee_id=employee.pk,
        changes=[
            audit.FieldChange(
                "assignment", f"{employee.pk}:{day}", "shift", old_code, template.code
            )
        ],
    )
    return AssignResult(assignment, week)


def _clear(
    user: User,
    queue: Queue,
    employee: Employee,
    day: date,
    week: RosterWeek,
    existing: ShiftAssignment | None,
) -> AssignResult:
    if existing is None:
        return AssignResult(None, week)  # nothing there: clearing is idempotent
    old_code = existing.template.code
    existing.delete()
    audit.record(  # last write of the transaction
        actor=user,
        action=Action.ROSTER_CLEARED,
        entity_type="roster_week",
        entity_id=str(week.pk),
        subject_employee_id=employee.pk,
        changes=[audit.FieldChange("assignment", f"{employee.pk}:{day}", "shift", old_code, None)],
    )
    return AssignResult(None, week)


def _check_rules(
    user: User,
    queue: Queue,
    employee: Employee,
    day: date,
    template: ShiftTemplate,
    existing: ShiftAssignment | None,
    also_ignoring: Sequence[int] = (),
) -> None:
    if not EmployeeSkill.objects.filter(employee=employee, queue=queue).exists():
        raise _refused(
            user, queue, "roster.not_skilled", "This person is not skilled on this queue."
        )
    if (employee.start_date and day < employee.start_date) or (
        employee.end_date and day > employee.end_date
    ):
        raise _refused(
            user, queue, "roster.not_employed", "This person is not employed on that day."
        )
    if LeaveRequest.objects.filter(
        employee=employee, status=LeaveStatus.APPROVED, start_date__lte=day, end_date__gte=day
    ).exists():
        raise _refused(user, queue, "roster.on_leave", "This person is on approved leave that day.")

    declared = [
        rules_availability.window_of(w.weekday, w.start_time, w.end_time)
        for w in Availability.objects.filter(employee=employee, kind=AvailabilityKind.UNAVAILABLE)
    ]
    if rules_availability.touches(declared, day, template.start_time, template.end_time):
        raise _refused(
            user,
            queue,
            "roster.unavailable",
            "This person said they cannot work some of those hours.",
        )

    others = ShiftAssignment.objects.filter(
        employee=employee, day__gte=day - timedelta(days=7), day__lte=day + timedelta(days=7)
    ).select_related("template")
    if existing is not None:
        others = others.exclude(pk=existing.pk)
    if also_ignoring:
        others = others.exclude(pk__in=also_ignoring)
    others_list = list(others)

    candidate = shift_span(day, template.start_time, template.end_time)
    spans = [shift_span(a.day, a.template.start_time, a.template.end_time) for a in others_list]
    rules = rules_on(day)
    if breaks_rest_rule(spans, candidate, min_hours=rules.min_rest_hours):
        raise _refused(
            user,
            queue,
            "roster.rest_period",
            f"This would leave less than {rules.min_rest_hours} hours of rest between shifts.",
        )
    if consecutive_run([a.day for a in others_list], day) > rules.max_consecutive_days:
        raise _refused(
            user,
            queue,
            "roster.too_many_days",
            f"This would be more than {rules.max_consecutive_days} days in a row.",
        )

    start = week_start_of(day)
    this_week = sum(
        a.template.paid_minutes for a in others_list if start <= a.day <= start + timedelta(days=6)
    )
    if rules.max_weekly_hours is not None and (
        this_week + template.paid_minutes > rules.max_weekly_hours * 60
    ):
        raise _refused(
            user,
            queue,
            "roster.over_weekly_cap",
            f"This would take the person over the {rules.max_weekly_hours} hour weekly limit.",
        )
    limit = float(employee.weekly_hours) * 60
    if this_week + template.paid_minutes > limit:
        raise _refused(
            user,
            queue,
            "roster.over_hours",
            f"This would take the person over their {employee.weekly_hours} contract hours "
            "for the week.",
        )


# --- exchanging shifts ---------------------------------------------------------------------------


def exchange_refusal(
    user: User, first: ShiftAssignment, second: ShiftAssignment
) -> tuple[str, str] | None:
    """Would the two people swapping these shifts break a roster rule? Each takes the other's
    shift and gives up their own, so each is checked as if their own shift were already gone.
    Returns the (code, plain-language reason) of the first rule broken, or None when it is fine."""
    queue = first.roster_week.queue
    try:
        for mine, theirs in ((first, second), (second, first)):
            person, day, template = mine.employee, theirs.day, theirs.template
            # The incoming day must be free, except for the shift being given up.
            clash = ShiftAssignment.objects.filter(employee=person, day=day).exclude(pk=mine.pk)
            if clash.exists():
                raise _refused(
                    user, queue, "roster.already_rostered", "That person already works that day."
                )
            _check_rules(
                user, queue, person, day, template, mine if mine.day == day else None, [mine.pk]
            )
    except _RefusalError as refusal:
        return refusal.code, refusal.detail
    return None


def exchange(first: ShiftAssignment, second: ShiftAssignment) -> None:
    """Carry out the swap: each person ends up on the other's shift. The caller has checked the
    rules and audits it. Deleting both first keeps the one-shift-a-day constraint happy."""
    plan = [
        (second.employee_id, first.roster_week_id, first.day, first.template_id),
        (first.employee_id, second.roster_week_id, second.day, second.template_id),
    ]
    ShiftAssignment.objects.filter(pk__in=[first.pk, second.pk]).delete()
    for employee_id, week_id, day, template_id in plan:
        ShiftAssignment.objects.create(
            roster_week_id=week_id, employee_id=employee_id, day=day, template_id=template_id
        )


# --- publishing --------------------------------------------------------------------------------


def _week(user: User, queue_id: int, week_start: date) -> tuple[Queue, RosterWeek]:
    queue = _queue_for(user, queue_id)
    _monday(user, queue, week_start)
    week = (
        RosterWeek.objects.for_user(user)
        .select_for_update(no_key=True)
        .filter(queue=queue, week_start=week_start)
        .first()
    )
    if week is None:
        raise not_found("Nobody has been rostered for that week yet.")
    return queue, week


def publish(*, user: User, queue_id: int, week_start: date) -> RosterWeek:
    """Make the week's roster final. An empty roster is refused: publishing nothing is a mistake."""
    with _audit_refusals(user), transaction.atomic():
        queue, week = _week(user, queue_id, week_start)
        if week.status == RosterStatus.PUBLISHED:
            return week
        count = week.assignments.count()
        if count == 0:
            raise _refused(user, queue, "roster.empty", "There are no shifts to publish.")
        week.status = RosterStatus.PUBLISHED
        week.published_at = Now()
        week.published_by = user
        week.save(update_fields=["status", "published_at", "published_by"])
        week.refresh_from_db()
        notifications.notify(
            User.objects.filter(employee__assignments__roster_week=week).distinct(),
            kind="roster.published",
            message=f"Your roster for the week of {week_start:%d %b} is published.",
            link="/my-schedule",
        )
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.ROSTER_PUBLISHED,
            entity_type="roster_week",
            entity_id=str(week.pk),
            changes=[
                audit.FieldChange("roster_week", str(week.pk), "status", "draft", "published"),
                audit.FieldChange("roster_week", str(week.pk), "shifts", None, str(count)),
            ],
        )
        return week


def reopen(*, user: User, queue_id: int, week_start: date) -> RosterWeek:
    """Return a published week to draft so it can be changed. Audited like publishing."""
    with _audit_refusals(user), transaction.atomic():
        _, week = _week(user, queue_id, week_start)
        if week.status == RosterStatus.DRAFT:
            return week
        week.status = RosterStatus.DRAFT
        week.published_at = None
        week.published_by = None
        week.save(update_fields=["status", "published_at", "published_by"])
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.ROSTER_REOPENED,
            entity_type="roster_week",
            entity_id=str(week.pk),
            changes=[
                audit.FieldChange("roster_week", str(week.pk), "status", "published", "draft")
            ],
        )
        return week


# --- export ------------------------------------------------------------------------------------


def _safe(value: Any) -> str:
    """A spreadsheet runs a cell that starts with = + - or @ as a formula. A name or code typed by
    a person must not be able to, so such cells are prefixed with an apostrophe."""
    text = str(value)
    return "'" + text if text.startswith(_FORMULA_STARTS) else text


def export_csv(*, user: User, queue_id: int, week_start: date) -> tuple[str, str]:
    """The week's roster as CSV text, and a file name. Exporting a list of staff and their shifts
    is audited."""
    with _audit_refusals(user), transaction.atomic():
        queue = _queue_for(user, queue_id)
        _monday(user, queue, week_start)
        week = RosterWeek.objects.for_user(user).filter(queue=queue, week_start=week_start).first()
        rows = (
            ShiftAssignment.objects.for_user(user)
            .filter(roster_week=week)
            .select_related("employee", "template")
            .order_by("employee__emp_no", "day")
            if week
            else []
        )
        out = io.StringIO(newline="")
        writer = csv.writer(out)
        writer.writerow(["Employee no", "Name", "Date", "Shift", "Start", "End", "Paid minutes"])
        count = 0
        for a in rows:
            writer.writerow(
                [
                    _safe(a.employee.emp_no),
                    _safe(a.employee.name),
                    a.day.isoformat(),
                    _safe(a.template.code),
                    f"{a.template.start_time:%H:%M}",
                    f"{a.template.end_time:%H:%M}",
                    a.template.paid_minutes,
                ]
            )
            count += 1
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.ROSTER_EXPORTED,
            entity_type="roster_week",
            entity_id=str(week.pk) if week else f"{queue.pk}:{week_start}",
            reason=f"{count} rows",
        )
    return f"roster-{queue.pk}-{week_start.isoformat()}.csv", out.getvalue()
