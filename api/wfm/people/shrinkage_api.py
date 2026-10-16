"""Planned shrinkage measured from approved leave, by team (SHR-01)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema

from wfm.accounts.models import Role
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import shrinkage_selectors as selectors

router = Router(tags=["people"])
READ = RoleSessionAuth(Role.ADMIN, Role.PLANNER, Role.LEAD, feature=Feature.PEOPLE)


class TeamShrinkageOut(Schema):
    team: str
    people: int
    contractedHours: Decimal  # noqa: N815
    awayHours: Decimal  # noqa: N815
    plannedPct: Decimal | None  # noqa: N815 - none: nobody had contracted hours
    assumedPct: Decimal | None  # noqa: N815 - the queues' planning assumption, planned + unplanned


class ShrinkageOut(Schema):
    month: date
    teams: list[TeamShrinkageOut]
    unplannedMeasured: bool  # noqa: N815 - false until an attendance feed exists


@router.get(
    "/shrinkage",
    auth=READ,
    response=ShrinkageOut,
    summary="Planned shrinkage per team for a month, from approved leave",
)
def shrinkage(request: HttpRequest, month: date | None = None) -> ShrinkageOut:
    first = (month or timezone.localdate()).replace(day=1)
    rows = selectors.monthly(current_user(request), first)
    return ShrinkageOut(
        month=first,
        teams=[
            TeamShrinkageOut(
                team=r.team,
                people=r.summary.people,
                contractedHours=r.summary.contracted_hours,
                awayHours=r.summary.away_hours,
                plannedPct=r.summary.planned_pct,
                assumedPct=r.assumed_pct,
            )
            for r in rows
        ],
        unplannedMeasured=False,
    )
