"""Reading overtime. Everything starts from `Model.objects.for_user(user)`.

What a request costs is computed here, from the pay on file and the compliance rules in force on
the day, and only for the roles allowed to see a pay figure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from wfm_engine import overtime as pricing

from wfm.accounts.models import User
from wfm.people.calendar import public_holidays
from wfm.scheduling.models import Employee
from wfm.scheduling.selectors import rules_on

from .models import (
    EmployeePay,
    OvertimeBudget,
    OvertimeRates,
    OvertimeRequest,
    OvertimeStatus,
    StandbyShift,
    StandbyStatus,
)
from .policy import COST_ROLES, PAY_ROLES

MAX_ROWS = 300


@dataclass(frozen=True, slots=True)
class Row:
    request: OvertimeRequest
    kind: str  # weekday, sunday or holiday
    cost: Decimal | None  # None: not allowed to see it, or no salary on file
    cost_missing: bool  # allowed to see it, but there is no salary on file to price it from
    worked_cost: Decimal | None = None  # OT-03: the paid time at the approved price


def price_of(request: OvertimeRequest, pay: EmployeePay | None) -> Decimal | None:
    """What this request costs at the rules in force on its day; None without a salary."""
    if pay is None:
        return None
    day = request.day
    return pricing.price(
        minutes=request.minutes,
        monthly_salary=pay.monthly_salary,
        weekly_hours=request.employee.weekly_hours,
        kind=pricing.day_kind(day, public_holidays(day, day)),
        ordinarily_works_sundays=pay.ordinarily_works_sundays,
        rules=rules_on(day),
    )


def requests(
    user: User,
    *,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[Row]:
    found = OvertimeRequest.objects.for_user(user).select_related("employee")
    if status:
        found = found.filter(status=status)
    if date_from:
        found = found.filter(day__gte=date_from)
    if date_to:
        found = found.filter(day__lte=date_to)
    rows = list(found.order_by("-day", "-id")[:MAX_ROWS])
    sees_cost = user.role in COST_ROLES
    pay = {p.employee_id: p for p in EmployeePay.objects.for_pricing(user)} if sees_cost else {}
    out: list[Row] = []
    for r in rows:
        day = r.day
        kind = pricing.day_kind(day, public_holidays(day, day))
        if not sees_cost:
            out.append(Row(r, kind, None, False))
            continue
        if r.status == OvertimeStatus.APPROVED and r.approved_cost is not None:
            cost: Decimal | None = r.approved_cost
        elif r.status in (OvertimeStatus.REJECTED, OvertimeStatus.CANCELLED):
            cost = None
        else:
            cost = price_of(r, pay.get(r.employee_id))
        missing = cost is None and r.status in (OvertimeStatus.PENDING, OvertimeStatus.APPROVED)
        out.append(Row(r, kind, cost, missing, r.worked_cost))
    return out


@dataclass(frozen=True, slots=True)
class PayStatus:
    employee: Employee
    has_salary: bool
    ordinarily_works_sundays: bool


def pay_statuses(user: User) -> list[PayStatus]:
    """Who has a salary on file. Never the figure itself."""
    if user.role not in PAY_ROLES:
        return []
    on_file = {p.employee_id: p for p in EmployeePay.objects.for_user(user)}
    return [
        PayStatus(
            e,
            e.pk in on_file,
            on_file[e.pk].ordinarily_works_sundays if e.pk in on_file else False,
        )
        for e in Employee.objects.for_user(user)
    ]


def callout_price(standby: StandbyShift, minutes: int, pay: EmployeePay | None) -> Decimal | None:
    """What a call-out of `minutes` on the standby day costs, priced exactly like overtime."""
    if pay is None:
        return None
    day = standby.day
    return pricing.price(
        minutes=minutes,
        monthly_salary=pay.monthly_salary,
        weekly_hours=standby.employee.weekly_hours,
        kind=pricing.day_kind(day, public_holidays(day, day)),
        ordinarily_works_sundays=pay.ordinarily_works_sundays,
        rules=rules_on(day),
    )


@dataclass(frozen=True, slots=True)
class StandbyRow:
    shift: StandbyShift
    allowance: Decimal | None  # None: not allowed to see money
    call_out_cost: Decimal | None
    call_out_cost_missing: bool  # a call-out is recorded but there is no salary to price it from


def standby_shifts(
    user: User, *, date_from: date | None = None, date_to: date | None = None
) -> list[StandbyRow]:
    found = StandbyShift.objects.for_user(user).select_related("employee")
    if date_from:
        found = found.filter(day__gte=date_from)
    if date_to:
        found = found.filter(day__lte=date_to)
    sees = user.role in COST_ROLES
    return [
        StandbyRow(
            s,
            s.allowance if sees and s.status == StandbyStatus.BOOKED else None,
            s.call_out_cost if sees else None,
            sees and bool(s.call_out_minutes) and s.call_out_cost is None,
        )
        for s in found.order_by("-day", "-id")[:MAX_ROWS]
    ]


def standby_allowance(user: User) -> Decimal | None:
    """The rand amount for a day on standby; only for those who may see money."""
    if user.role not in COST_ROLES:
        return None
    rates = OvertimeRates.objects.filter(pk=1).first()
    return rates.standby_allowance if rates else Decimal(0)


@dataclass(frozen=True, slots=True)
class Summary:
    month: date
    approved: int
    approved_minutes: int
    unreconciled: int  # approved and past, with no worked time recorded yet
    worked_minutes: int  # paid: as far as approved
    extra_minutes: int  # worked beyond what was approved, which is not paid
    overtime_cost: Decimal  # worked where recorded, approved where not
    missing_prices: int  # approved without a salary on file: not in the cost
    standby_days: int
    standby_allowances: Decimal
    call_out_minutes: int
    call_out_cost: Decimal
    total: Decimal
    budget: Decimal | None


def summary(user: User, month: date) -> Summary:
    """Overtime and standby for a calendar month, for the roles that see pay."""
    if user.role not in COST_ROLES:
        raise PermissionError("pay figures are for the roles that approve overtime")
    first = month.replace(day=1)
    last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    today = timezone.localdate()
    approved = list(
        OvertimeRequest.objects.for_user(user).filter(
            status=OvertimeStatus.APPROVED, day__gte=first, day__lte=last
        )
    )
    cost = Decimal(0)
    missing = unreconciled = worked = extra = 0
    for r in approved:
        if r.worked_minutes is None:
            if r.day < today:
                unreconciled += 1
            amount = r.approved_cost
        else:
            worked += min(r.worked_minutes, r.minutes)
            extra += max(0, r.worked_minutes - r.minutes)
            amount = r.worked_cost
        if amount is None:
            missing += 1
        else:
            cost += amount
    booked = list(
        StandbyShift.objects.for_user(user).filter(
            status=StandbyStatus.BOOKED, day__gte=first, day__lte=last
        )
    )
    allowances = sum((s.allowance for s in booked), Decimal(0))
    call_cost = sum((s.call_out_cost or Decimal(0) for s in booked), Decimal(0))
    budget = OvertimeBudget.objects.filter(month=first).first()
    return Summary(
        month=first,
        approved=len(approved),
        approved_minutes=sum(r.minutes for r in approved),
        unreconciled=unreconciled,
        worked_minutes=worked,
        extra_minutes=extra,
        overtime_cost=cost,
        missing_prices=missing,
        standby_days=len(booked),
        standby_allowances=allowances,
        call_out_minutes=sum(s.call_out_minutes or 0 for s in booked),
        call_out_cost=call_cost,
        total=cost + allowances + call_cost,
        budget=budget.amount if budget else None,
    )
