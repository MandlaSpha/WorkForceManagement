"""Reading overtime. Everything starts from `Model.objects.for_user(user)`.

What a request costs is computed here, from the pay on file and the compliance rules in force on
the day, and only for the roles allowed to see a pay figure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from wfm_engine import overtime as pricing

from wfm.accounts.models import User
from wfm.people.calendar import public_holidays
from wfm.scheduling.models import Employee
from wfm.scheduling.selectors import rules_on

from .models import EmployeePay, OvertimeRequest, OvertimeStatus
from .policy import COST_ROLES, PAY_ROLES

MAX_ROWS = 300


@dataclass(frozen=True, slots=True)
class Row:
    request: OvertimeRequest
    kind: str  # weekday, sunday or holiday
    cost: Decimal | None  # None: not allowed to see it, or no salary on file
    cost_missing: bool  # allowed to see it, but there is no salary on file to price it from


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
        out.append(Row(r, kind, cost, missing))
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
