"""Leave rules: blackout periods and the most people away at once (LV-04)."""

from __future__ import annotations

from datetime import date

from django.http import HttpRequest
from ninja import Router, Schema, Status

from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import rules_services as services
from .models import LeaveBlackout, LeaveLimit
from .policy import CONFIG_ROLES, SELF_ROLES

router = Router(tags=["people"])
SELF = RoleSessionAuth(*sorted(SELF_ROLES), feature=Feature.PEOPLE)
CONFIG = RoleSessionAuth(*sorted(CONFIG_ROLES), feature=Feature.PEOPLE)


class BlackoutIn(Schema):
    name: str
    dateFrom: date  # noqa: N815
    dateTo: date  # noqa: N815


class BlackoutOut(Schema):
    id: int
    name: str
    dateFrom: date  # noqa: N815
    dateTo: date  # noqa: N815


class LimitIn(Schema):
    maxConcurrent: int | None  # noqa: N815 - none: no limit


class LimitOut(Schema):
    maxConcurrent: int | None  # noqa: N815


@router.get(
    "/blackouts",
    auth=SELF,
    response=list[BlackoutOut],
    summary="Days on which restricted kinds of leave cannot be asked for",
)
def list_blackouts(request: HttpRequest) -> list[BlackoutOut]:
    return [_blackout(b) for b in LeaveBlackout.objects.all()]


@router.post(
    "/blackouts", auth=CONFIG, response={201: BlackoutOut}, summary="Add a blackout period"
)
def add_blackout(request: HttpRequest, body: BlackoutIn) -> Status[BlackoutOut]:
    found = services.add_blackout(
        user=current_user(request), name=body.name, date_from=body.dateFrom, date_to=body.dateTo
    )
    return Status(201, _blackout(found))


@router.delete(
    "/blackouts/{blackout_id}",
    auth=CONFIG,
    response=dict[str, bool],
    summary="Remove a blackout period",
)
def remove_blackout(request: HttpRequest, blackout_id: int) -> dict[str, bool]:
    services.remove_blackout(user=current_user(request), blackout_id=blackout_id)
    return {"ok": True}


@router.get("/limit", auth=SELF, response=LimitOut, summary="The most people away at once")
def get_limit(request: HttpRequest) -> LimitOut:
    return _limit(services.limit())


@router.put("/limit", auth=CONFIG, response=LimitOut, summary="Set the most people away at once")
def put_limit(request: HttpRequest, body: LimitIn) -> LimitOut:
    return _limit(services.set_limit(user=current_user(request), max_concurrent=body.maxConcurrent))


def _blackout(b: LeaveBlackout) -> BlackoutOut:
    return BlackoutOut(id=b.pk, name=b.name, dateFrom=b.date_from, dateTo=b.date_to)


def _limit(row: LeaveLimit) -> LimitOut:
    return LimitOut(maxConcurrent=row.max_concurrent)
