"""The payroll file for a month (RPT-08): what each person did that payroll needs to pay.

One row per person who has anything in the month: rostered hours on published rosters, approved
leave days by kind, overtime (approved, paid and its amount: worked time where reconciled, the
approved amount where not), standby days with their allowance, and call-outs. It holds names and
pay, so only planner and admin may export it, and every export is audited (who, which month, how
many rows; never the contents).
"""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from wfm_engine import leave as leave_rules
from wfm_engine import payroll as fmt

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import not_found
from wfm.people.calendar import public_holidays
from wfm.people.models import LeaveRequest, LeaveStatus, LeaveType
from wfm.scheduling.models import Employee, RosterStatus, ShiftAssignment

from .models import OvertimeRequest, OvertimeStatus, StandbyShift, StandbyStatus
from .policy import COST_ROLES

FIXED = [
    "Employee number",
    "Name",
    "Rostered hours",
]
TAIL = [
    "Overtime approved hours",
    "Overtime paid hours",
    "Overtime amount (R)",
    "Overtime not yet reconciled",
    "Overtime without a salary on file",
    "Standby days",
    "Standby allowance (R)",
    "Call-out hours",
    "Call-out amount (R)",
    "Total extra pay (R)",
]


def build(user: User, month: date) -> tuple[str, int]:
    """The CSV text for the month and the number of people in it."""
    if user.role not in COST_ROLES:
        raise not_found("Not found.")
    first = month.replace(day=1)
    last = first.replace(day=monthrange(first.year, first.month)[1])
    holidays = public_holidays(first, last)
    kinds = list(LeaveType.objects.order_by("code"))

    rostered = {
        r["employee_id"]: r["total"]
        for r in ShiftAssignment.objects.for_user(user)
        .filter(day__gte=first, day__lte=last, roster_week__status=RosterStatus.PUBLISHED)
        .values("employee_id")
        .annotate(total=Sum("template__paid_minutes"))
    }

    leave_days: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for lv in LeaveRequest.objects.for_user(user).filter(
        status=LeaveStatus.APPROVED, start_date__lte=last, end_date__gte=first
    ):
        span = (max(first, lv.start_date), min(last, lv.end_date))
        leave_days[lv.employee_id][lv.leave_type_id] += len(
            leave_rules.working_day_list(*span, holidays)
        )

    overtime: dict[int, dict[str, Decimal | int]] = defaultdict(
        lambda: {"approved": 0, "paid": 0, "amount": Decimal(0), "open": 0, "unpriced": 0}
    )
    for r in OvertimeRequest.objects.for_user(user).filter(
        status=OvertimeStatus.APPROVED, day__gte=first, day__lte=last
    ):
        o = overtime[r.employee_id]
        o["approved"] += r.minutes
        if r.worked_minutes is None:
            o["paid"] += r.minutes
            o["open"] += 1
            amount = r.approved_cost
        else:
            o["paid"] += min(r.worked_minutes, r.minutes)
            amount = r.worked_cost
        if amount is None:
            o["unpriced"] += 1
        else:
            o["amount"] += amount

    standby: dict[int, dict[str, Decimal | int]] = defaultdict(
        lambda: {"days": 0, "allowance": Decimal(0), "minutes": 0, "amount": Decimal(0)}
    )
    for s in StandbyShift.objects.for_user(user).filter(
        status=StandbyStatus.BOOKED, day__gte=first, day__lte=last
    ):
        b = standby[s.employee_id]
        b["days"] += 1
        b["allowance"] += s.allowance
        b["minutes"] += s.call_out_minutes or 0
        b["amount"] += s.call_out_cost or Decimal(0)

    header = [*FIXED, *(f"Leave: {k.name} (days)" for k in kinds), *TAIL]
    rows: list[list[str]] = []
    people = Employee.objects.for_user(user).order_by("emp_no")
    for e in people:
        ot = overtime.get(e.pk)
        sb = standby.get(e.pk)
        days = leave_days.get(e.pk, {})
        if not (rostered.get(e.pk) or ot or sb or any(days.values())):
            continue
        o_amount = Decimal(ot["amount"]) if ot else Decimal(0)
        b_allowance = Decimal(sb["allowance"]) if sb else Decimal(0)
        b_amount = Decimal(sb["amount"]) if sb else Decimal(0)
        rows.append(
            [
                e.emp_no,
                e.name,
                fmt.hours(int(rostered.get(e.pk) or 0)),
                *(str(days.get(k.pk, 0)) for k in kinds),
                fmt.hours(int(ot["approved"])) if ot else "0.00",
                fmt.hours(int(ot["paid"])) if ot else "0.00",
                fmt.rands(o_amount),
                str(ot["open"]) if ot else "0",
                str(ot["unpriced"]) if ot else "0",
                str(sb["days"]) if sb else "0",
                fmt.rands(b_allowance),
                fmt.hours(int(sb["minutes"])) if sb else "0.00",
                fmt.rands(b_amount),
                fmt.rands(o_amount + b_allowance + b_amount),
            ]
        )
    return fmt.to_csv(header, rows), len(rows)


def export(user: User, month: date) -> str:
    """Build the file and record that it was taken, as the LAST write."""
    with transaction.atomic():
        text, count = build(user, month)
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.PAYROLL_EXPORTED,
            entity_type="payroll_export",
            entity_id=f"{month:%Y-%m}",
            changes=[
                audit.FieldChange("payroll_export", f"{month:%Y-%m}", "rows", None, str(count))
            ],
        )
    return text
