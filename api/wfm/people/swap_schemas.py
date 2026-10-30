from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated

from ninja import Schema
from pydantic import StringConstraints

# camelCase on the wire; the noqa comments mark that deliberate choice.


class SwapShiftOut(Schema):
    assignmentId: int  # noqa: N815
    queueId: int  # noqa: N815
    queue: str
    day: date
    shift: str  # the shift code, e.g. D1
    startTime: time  # noqa: N815
    endTime: time  # noqa: N815
    employeeId: int  # noqa: N815
    employee: str  # always the signed-in person's own shift


class SwapIn(Schema):
    giveAssignmentId: int  # noqa: N815 - your shift, posted for a colleague to take
    employeeId: int | None = None  # noqa: N815 - on someone's behalf; planners and admins only


class TakeIn(Schema):
    assignmentId: int  # noqa: N815 - your own shift, offered in return
    employeeId: int | None = None  # noqa: N815 - on someone's behalf; planners and admins only


class SwapOut(Schema):
    id: int
    queue: str
    status: str
    fromEmployee: str  # noqa: N815 - the poster
    fromDay: date  # noqa: N815
    fromShift: str  # noqa: N815
    toEmployee: str | None  # noqa: N815 - none while the request is open
    toDay: date | None  # noqa: N815
    toShift: str | None  # noqa: N815
    createdAt: datetime  # noqa: N815
    decidedAt: datetime | None  # noqa: N815
    decisionReason: str  # noqa: N815 - only the two people in the swap and approvers get this
    asker: bool  # the signed-in person posted it
    colleague: bool  # the signed-in person took it


class SwapRejectIn(Schema):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""


class BoardOut(Schema):
    """An open request as other agents see it: the shift and queue, never the poster."""

    id: int
    queue: str
    day: date
    shift: str
    startTime: time  # noqa: N815
    endTime: time  # noqa: N815
    createdAt: datetime  # noqa: N815
