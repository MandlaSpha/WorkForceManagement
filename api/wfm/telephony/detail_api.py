"""The Call detail screen: ring-no-answer, IVR, transfers, holds, mutes and incident links, as
aggregates for one month (DAT-01, tech spec section 4.31)."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from django.http import HttpRequest
from ninja import Router, Schema
from wfm_engine.call_detail import EventRow

from wfm.accounts.models import Role
from wfm.core.errors import ApiError
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import detail_selectors as selectors

router = Router(tags=["telephony"])

MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
ROLES = (Role.ADMIN, Role.PLANNER, Role.LEAD, Role.EXECUTIVE)


class CallDetailSheetsOut(Schema):
    """True when an import in the month held the sheet; false means NO DATA, not zero."""

    ring: bool
    ivr: bool
    transfers: bool
    holds: bool
    mutes: bool
    incidents: bool


class CallDetailAgentOut(Schema):
    login: str
    employeeNumber: str | None  # noqa: N815
    employeeName: str | None  # noqa: N815
    offers: int
    answered: int
    ringNoAnswer: int  # noqa: N815
    ringNoAnswerPct: Decimal | None  # noqa: N815
    avgRingS: Decimal | None  # noqa: N815


class CallDetailIvrStepOut(Schema):
    step: int
    digit: str
    activity: str
    calls: int
    endedHere: int  # noqa: N815


class CallDetailIvrQueueOut(Schema):
    queue: str
    calls: int
    reachedQueue: int  # noqa: N815
    endedInIvr: int  # noqa: N815
    abandonedAfterIvr: int  # noqa: N815
    steps: list[CallDetailIvrStepOut]


class CallDetailEventOut(Schema):
    """One queue, over the month (`day` is null) or on one day. A count or an average is null when
    its sheet was not in the import."""

    queue: str
    day: date | None
    transfers: int | None
    avgTransferS: Decimal | None  # noqa: N815
    avgTransferAnswerS: Decimal | None  # noqa: N815
    holds: int | None
    avgHoldS: Decimal | None  # noqa: N815
    mutes: int | None
    avgMuteS: Decimal | None  # noqa: N815


class CallDetailIncidentQueueOut(Schema):
    queue: str
    callsWithIncident: int  # noqa: N815
    incidents: list[str]


class CallDetailOut(Schema):
    month: str
    sheets: CallDetailSheetsOut
    scope: str  # "all", "team" or "aggregate"
    agentsAllowed: bool  # noqa: N815
    incidentsAllowed: bool  # noqa: N815
    agents: list[CallDetailAgentOut] | None
    ivr: list[CallDetailIvrQueueOut] | None
    eventsByQueue: list[CallDetailEventOut] | None  # noqa: N815
    eventsByDay: list[CallDetailEventOut] | None  # noqa: N815
    incidents: list[CallDetailIncidentQueueOut] | None


def _event(row: EventRow, sheets: selectors.CallDetail) -> CallDetailEventOut:
    s = sheets.sheets
    return CallDetailEventOut(
        queue=row.queue,
        day=row.day,
        transfers=row.transfers if s["transfers"] else None,
        avgTransferS=row.avg_transfer_s if s["transfers"] else None,
        avgTransferAnswerS=row.avg_transfer_answer_s if s["transfers"] else None,
        holds=row.holds if s["holds"] else None,
        avgHoldS=row.avg_hold_s if s["holds"] else None,
        mutes=row.mutes if s["mutes"] else None,
        avgMuteS=row.avg_mute_s if s["mutes"] else None,
    )


def _flatten(
    grouped: dict[str, list[EventRow]] | None, found: selectors.CallDetail
) -> list[CallDetailEventOut] | None:
    if grouped is None:
        return None
    return [_event(r, found) for rows in grouped.values() for r in rows]


@router.get(
    "/call-detail",
    auth=RoleSessionAuth(*ROLES, feature=Feature.TELEPHONY),
    response=CallDetailOut,
    summary="Ring-no-answer, IVR, transfers, holds, mutes and incident links for a month",
)
def call_detail(request: HttpRequest, month: str) -> CallDetailOut:
    if not MONTH.match(month):
        raise ApiError(422, "call_detail.month_invalid", "Invalid month", "Use YYYY-MM.")
    found = selectors.call_detail(current_user(request), date(int(month[:4]), int(month[5:7]), 1))
    return CallDetailOut(
        month=found.month,
        sheets=CallDetailSheetsOut(**found.sheets),
        scope=found.scope,
        agentsAllowed=found.agents_allowed,
        incidentsAllowed=found.incidents_allowed,
        agents=None
        if found.agents is None
        else [
            CallDetailAgentOut(
                login=a.login,
                employeeNumber=a.employee_number,
                employeeName=a.employee_name,
                offers=a.ring.offers,
                answered=a.ring.answered,
                ringNoAnswer=a.ring.ring_no_answer,
                ringNoAnswerPct=a.ring.ring_no_answer_pct,
                avgRingS=a.ring.avg_ring_s,
            )
            for a in found.agents
        ],
        ivr=None
        if found.ivr is None
        else [
            CallDetailIvrQueueOut(
                queue=q.queue,
                calls=q.calls,
                reachedQueue=q.reached_queue,
                endedInIvr=q.ended_in_ivr,
                abandonedAfterIvr=q.abandoned_after_ivr,
                steps=[
                    CallDetailIvrStepOut(
                        step=s.step,
                        digit=s.digit,
                        activity=s.activity,
                        calls=s.calls,
                        endedHere=s.ended_here,
                    )
                    for s in q.steps
                ],
            )
            for q in found.ivr
        ],
        eventsByQueue=_flatten(found.events_by_queue, found),
        eventsByDay=_flatten(found.events_by_day, found),
        incidents=None
        if found.incidents is None
        else [
            CallDetailIncidentQueueOut(
                queue=q.queue, callsWithIncident=q.calls_with_incident, incidents=q.incidents
            )
            for q in found.incidents
        ],
    )
