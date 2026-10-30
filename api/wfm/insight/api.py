"""The scorecard for the Analytics screen (RPT-02, RPT-05)."""

from __future__ import annotations

from datetime import date

from django.http import HttpRequest, HttpResponse
from ninja import Router, Schema
from wfm_engine import payroll as fmt

from wfm.accounts.models import Role
from wfm.core.errors import ApiError
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import selectors

router = Router(tags=["insight"])
READ = RoleSessionAuth(
    Role.ADMIN, Role.PLANNER, Role.EXECUTIVE, Role.CUSTOMER_OPS, feature=Feature.INSIGHT
)
MAX_DAYS = 366


class ItemOut(Schema):
    key: str
    label: str
    value: float | None  # null: no data in the range
    unit: str
    basis: str  # measured, modelled or needs_data
    note: str


class ScorecardDayOut(Schema):
    day: date
    offered: int
    serviceLevelPct: float | None  # noqa: N815


class ScorecardOut(Schema):
    dateFrom: date  # noqa: N815
    dateTo: date  # noqa: N815
    items: list[ItemOut]
    days: list[ScorecardDayOut]


def _check_range(date_from: date, date_to: date) -> None:
    if date_to < date_from:
        raise ApiError(422, "range.invalid", "Invalid range", "date_to is before date_from.")
    if (date_to - date_from).days + 1 > MAX_DAYS:
        raise ApiError(
            422, "range.too_long", "Range too long", f"Ask for at most {MAX_DAYS} days at a time."
        )


@router.get(
    "/scorecard",
    auth=READ,
    response=ScorecardOut,
    summary="Service, workload and planning figures for a range, each labelled by its source",
)
def scorecard(request: HttpRequest, date_from: date, date_to: date) -> ScorecardOut:
    _check_range(date_from, date_to)
    found = selectors.scorecard(current_user(request), date_from, date_to)
    return ScorecardOut(
        dateFrom=found.date_from,
        dateTo=found.date_to,
        items=[
            ItemOut(
                key=i.key, label=i.label, value=i.value, unit=i.unit, basis=i.basis, note=i.note
            )
            for i in found.items
        ],
        days=[
            ScorecardDayOut(day=d.day, offered=d.offered, serviceLevelPct=d.service_level_pct)
            for d in found.days
        ],
    )


CSV_HEADER = ["section", "key_or_day", "label", "value", "unit", "basis", "note"]


@router.get(
    "/scorecard.csv",
    auth=READ,
    response={200: None},
    summary="Download the scorecard for a range as CSV (same roles and scoping as the screen)",
)
def scorecard_csv(request: HttpRequest, date_from: date, date_to: date) -> HttpResponse:
    _check_range(date_from, date_to)
    found = selectors.scorecard(current_user(request), date_from, date_to)
    rows = [
        ["figure", i.key, i.label, "" if i.value is None else str(i.value), i.unit, i.basis, i.note]
        for i in found.items
        if i.unit != "R"  # no money figure leaves in a file
    ]
    rows += [
        [
            "day",
            d.day.isoformat(),
            "Calls offered and service level",
            str(d.offered),
            "calls",
            "measured",
            "" if d.service_level_pct is None else f"service level {d.service_level_pct}%",
        ]
        for d in found.days
    ]
    response = HttpResponse(fmt.to_csv(CSV_HEADER, rows), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="scorecard-{date_from}-{date_to}.csv"'
    response["Cache-Control"] = "no-store"
    return response
