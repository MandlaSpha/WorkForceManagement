"""Breaks and activities inside shifts (SCH-03).

An activity is time inside a shift when the person is not on the phones. It can be added to a
shift of a draft or a published week (a break is often moved on the day), by a planner or admin;
each change is one transaction with the audit event as the LAST write. The planner's coverage
(ENG-03) is people on the phones, so adding one can open a gap, and the response says so.
"""

from __future__ import annotations

from datetime import date, time

from django.db import transaction
from wfm_engine.roster import check_activity, shift_length_slots

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError, not_found

from .models import ActivityKind, ShiftActivity, ShiftAssignment

MAX_ACTIVITIES_PER_SHIFT = 12

_WHY = {
    "length": ("activity.no_length", "An activity lasts at least half an hour."),
    "outside": ("activity.outside_shift", "That falls outside the shift."),
    "overlap": ("activity.overlap", "That overlaps another break or activity in the shift."),
}


def _refuse(code: str, detail: str, status: int = 422) -> ApiError:
    return ApiError(status, code, "Activity refused", detail)


def _on_grid(moment: time) -> bool:
    return moment.minute in (0, 30) and moment.second == 0 and moment.microsecond == 0


def _locked(user: User, assignment_id: int) -> ShiftAssignment:
    found: ShiftAssignment | None = (
        ShiftAssignment.objects.select_for_update(no_key=True, of=("self",))
        .for_user(user)
        .select_related("template", "roster_week", "employee")
        .filter(pk=assignment_id)
        .first()
    )
    if found is None:
        raise not_found("No such shift.")
    return found


def add(
    *,
    user: User,
    queue_id: int,
    employee_id: int,
    day: date,
    kind: str,
    start_time: time,
    minutes: int,
) -> ShiftActivity:
    """Put a break or activity in the shift a person has on a day, by clock time. The start must
    be on the half-hour and the length a whole number of half-hours; the place inside the shift is
    worked out here, so an overnight shift needs no special case."""
    if kind not in ActivityKind.values:
        raise _refuse("activity.unknown_kind", "That kind of activity does not exist.")
    if not _on_grid(start_time) or minutes % 30 != 0:
        raise _refuse("activity.not_on_grid", "Start on the hour or half-hour, in half-hours.")
    with transaction.atomic():
        found = (
            ShiftAssignment.objects.for_user(user)
            .filter(roster_week__queue_id=queue_id, employee_id=employee_id, day=day)
            .values_list("pk", flat=True)
            .first()
        )
        if found is None:
            raise not_found("That person has no shift on that day.")
        shift = _locked(user, found)
        began = shift.template.start_time.hour * 60 + shift.template.start_time.minute
        at = start_time.hour * 60 + start_time.minute
        offset_slots = ((at - began) % (24 * 60)) // 30
        slots = minutes // 30
        others = list(shift.activities.values_list("offset_slots", "slots"))
        if len(others) >= MAX_ACTIVITIES_PER_SHIFT:
            raise _refuse(
                "activity.too_many", "That is enough breaks and activities for one shift."
            )
        length = shift_length_slots(shift.template.start_time, shift.template.end_time)
        why = check_activity(length, (offset_slots, slots), others)
        if why is not None:
            code, detail = _WHY[why]
            raise _refuse(code, detail)
        made = ShiftActivity.objects.create(
            assignment=shift, kind=kind, offset_slots=offset_slots, slots=slots, created_by=user
        )
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.ROSTER_ACTIVITY_ADDED,
            entity_type="shift_assignment",
            entity_id=str(shift.pk),
            subject_employee_id=shift.employee_id,
            changes=[
                audit.FieldChange(
                    "shift_assignment", str(shift.pk), "activity", None, f"{kind} x{slots}"
                )
            ],
        )
    return made


def remove(*, user: User, activity_id: int) -> None:
    with transaction.atomic():
        activity = (
            ShiftActivity.objects.select_related("assignment")
            .filter(pk=activity_id, assignment__in=ShiftAssignment.objects.for_user(user))
            .first()
        )
        if activity is None:
            raise not_found("No such break or activity.")
        shift = _locked(user, activity.assignment_id)
        kind, slots = activity.kind, activity.slots
        activity.delete()
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.ROSTER_ACTIVITY_REMOVED,
            entity_type="shift_assignment",
            entity_id=str(shift.pk),
            subject_employee_id=shift.employee_id,
            changes=[
                audit.FieldChange(
                    "shift_assignment", str(shift.pk), "activity", f"{kind} x{slots}", None
                )
            ],
        )


def move(*, user: User, activity_id: int, start_time: time) -> ShiftActivity:
    """Move a break or activity to another start inside the same shift (INT-04): the new one is
    added and the old one removed in ONE transaction, so there is never a moment with both or
    neither, and the audit trail shows the removal and the addition, last."""
    if not _on_grid(start_time):
        raise _refuse("activity.not_on_grid", "Start on the hour or half-hour, in half-hours.")
    with transaction.atomic():
        old = (
            ShiftActivity.objects.select_related("assignment")
            .filter(pk=activity_id, assignment__in=ShiftAssignment.objects.for_user(user))
            .first()
        )
        if old is None:
            raise not_found("No such break or activity.")
        shift = _locked(user, old.assignment_id)
        began = shift.template.start_time.hour * 60 + shift.template.start_time.minute
        at = start_time.hour * 60 + start_time.minute
        offset_slots = ((at - began) % (24 * 60)) // 30
        others = list(shift.activities.exclude(pk=old.pk).values_list("offset_slots", "slots"))
        length = shift_length_slots(shift.template.start_time, shift.template.end_time)
        why = check_activity(length, (offset_slots, old.slots), others)
        if why is not None:
            code, detail = _WHY[why]
            raise _refuse(code, detail)
        kind, slots = old.kind, old.slots
        old.delete()
        made = ShiftActivity.objects.create(
            assignment=shift, kind=kind, offset_slots=offset_slots, slots=slots, created_by=user
        )
        for action, before, after in (
            (Action.ROSTER_ACTIVITY_REMOVED, f"{kind} x{slots}", None),
            (Action.ROSTER_ACTIVITY_ADDED, None, f"{kind} x{slots}"),
        ):
            audit.record(  # the last writes of the transaction
                actor=user,
                action=action,
                entity_type="shift_assignment",
                entity_id=str(shift.pk),
                subject_employee_id=shift.employee_id,
                changes=[
                    audit.FieldChange("shift_assignment", str(shift.pk), "activity", before, after)
                ],
            )
    return made
