"""The Team screen: one aggregate read of a team's week (no writes, so nothing to audit)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.http import HttpRequest
from ninja import Router
from wfm_engine.adherence import ADHERENCE_THRESHOLD_PCT

from wfm.accounts.models import Role
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import team_selectors as selectors
from .team_schemas import (
    TeamLeaveBalanceOut,
    TeamManagerOut,
    TeamOverviewOut,
    TeamPendingLeaveOut,
    TeamPersonOut,
    TeamShiftOut,
    TeamSummaryOut,
)

router = Router(tags=["people"])
READ = RoleSessionAuth(Role.ADMIN, Role.PLANNER, Role.LEAD, feature=Feature.PEOPLE)


def _days(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


@router.get(
    "/team-overview",
    auth=READ,
    response=TeamOverviewOut,
    summary="A team's week: hours, adherence, shifts and waiting requests per person",
)
def team_overview(
    request: HttpRequest, week_start: date | None = None, manager_id: int | None = None
) -> TeamOverviewOut:
    found = selectors.overview(current_user(request), week_start=week_start, manager_id=manager_id)
    s = found.summary
    return TeamOverviewOut(
        weekStart=found.week_start,
        weekEnd=found.week_end,
        adherenceThresholdPct=ADHERENCE_THRESHOLD_PCT,
        summary=TeamSummaryOut(
            headcount=s.headcount,
            withAdherence=s.with_data,
            onTrack=s.on_track,
            rosteredHours=s.rostered_h,
            contractHours=s.contract_h,
            rosteredPct=s.rostered_pct,
        ),
        managers=[TeamManagerOut(id=m.pk, name=m.name) for m in found.managers],
        people=[
            TeamPersonOut(
                employeeId=c.employee.pk,
                empNo=c.employee.emp_no,
                name=c.employee.name,
                contractType=c.employee.contract_type,
                contractHours=float(c.employee.weekly_hours),
                rosteredHours=c.rostered_h,
                shifts=len(c.shifts),
                adherencePct=c.adherence_pct,
                onTrack=c.on_track,
                pendingLeave=c.pending_leave,
                openSwaps=c.open_swaps,
                checkIn=c.check_in,
                shiftList=[
                    TeamShiftOut(
                        day=x.day,
                        shift=x.shift,
                        startTime=x.start_time,
                        endTime=x.end_time,
                        paidHours=x.paid_hours,
                        adherencePct=x.adherence_pct,
                    )
                    for x in c.shifts
                ],
                leaveBalances=[
                    TeamLeaveBalanceOut(
                        leaveType=b.leave_type,
                        entitlementDays=_days(b.entitlement),
                        takenDays=float(b.taken),
                        pendingDays=float(b.pending),
                        availableDays=_days(b.available),
                    )
                    for b in c.balances
                ],
                pendingRequests=[
                    TeamPendingLeaveOut(
                        leaveType=p.leave_type,
                        startDate=p.start_date,
                        endDate=p.end_date,
                        days=p.days,
                    )
                    for p in c.pending
                ],
            )
            for c in found.people
        ],
    )
