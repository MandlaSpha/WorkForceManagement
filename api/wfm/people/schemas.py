from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from ninja import Schema
from pydantic import StringConstraints

# camelCase on the wire; the noqa comments mark that deliberate choice.


class LeaveTypeOut(Schema):
    id: int
    code: str
    name: str
    paid: bool
    daysPerYear: float | None  # noqa: N815 - none means no limit
    confirmed: bool  # false while it is the BCEA default nobody has confirmed
    restricted: bool  # blackout periods and the away-at-once limit apply to it


class EntitlementIn(Schema):
    daysPerYear: Decimal | None  # noqa: N815


class BalanceOut(Schema):
    typeId: int  # noqa: N815
    code: str
    name: str
    entitlement: float | None
    taken: float
    pending: float
    available: float | None


class BalancesOut(Schema):
    employeeId: int  # noqa: N815
    employee: str
    year: int
    balances: list[BalanceOut]


class LeaveRequestIn(Schema):
    leaveTypeId: int  # noqa: N815
    startDate: date  # noqa: N815
    endDate: date  # noqa: N815
    employeeId: int | None = None  # noqa: N815 - on someone's behalf; planners and admins only


class LeaveRequestOut(Schema):
    id: int
    employeeId: int  # noqa: N815
    employee: str
    empNo: str  # noqa: N815
    leaveTypeId: int  # noqa: N815
    leaveType: str  # noqa: N815
    startDate: date  # noqa: N815
    endDate: date  # noqa: N815
    days: int
    status: str
    createdAt: datetime  # noqa: N815
    decidedAt: datetime | None  # noqa: N815
    shiftsCleared: int  # noqa: N815 - shifts taken off the roster when it was approved
    decisionReason: str  # noqa: N815 - why it was rejected; shown to the requester and approvers
    mine: bool  # the request is the signed-in person's own


class RejectIn(Schema):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""


class DecisionOut(Schema):
    request: LeaveRequestOut
    shiftsCleared: int  # noqa: N815
    shiftsRestored: int  # noqa: N815
    shiftsNotRestored: int  # noqa: N815 - cancelling could not put these back


class ImpactOut(Schema):
    shifts: int  # shifts that fall on the leave days
    hours: float  # rostered hours given up
    intervals: int  # half-hours affected
    newlyUnder: int  # noqa: N815 - half-hours that were covered and would no longer be
    alreadyUnder: int  # noqa: N815 - half-hours already short, made shorter
    unknown: int  # half-hours with no known requirement


class ErasurePreviewOut(Schema):
    employeeId: int  # noqa: N815
    employeeNumber: str  # noqa: N815
    removes: dict[str, int]
    keeps: dict[str, int]


class ErasureConfirmIn(Schema):
    employeeNumber: str  # noqa: N815


class ErasureDoneOut(Schema):
    employeeId: int  # noqa: N815
    removes: dict[str, int]
    keeps: dict[str, int]


class RetentionPersonOut(Schema):
    employeeId: int  # noqa: N815
    employeeNumber: str  # noqa: N815
    endDate: date  # noqa: N815


class RetentionOut(Schema):
    months: int
    before: date
    employees: list[RetentionPersonOut]
