"""Compliance rules the roster is checked against (CFG-06)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema
from wfm_engine.compliance import Rules, floor_warnings

from wfm.accounts.models import Role
from wfm.core.permissions import RoleSessionAuth, current_user

from . import compliance_services as services
from . import selectors
from .api import FEATURE
from .policy import READ_ROLES

router = Router(tags=["scheduling"])
READ = RoleSessionAuth(*sorted(READ_ROLES), feature=FEATURE)
ADMIN_ONLY = RoleSessionAuth(Role.ADMIN, feature=FEATURE)


class RulesIn(Schema):
    effectiveFrom: date  # noqa: N815
    minRestHours: int  # noqa: N815
    maxConsecutiveDays: int  # noqa: N815
    maxWeeklyHours: int | None = None  # noqa: N815 - none: only each person's contract hours
    overtimeMultiplier: float = 1.5  # noqa: N815
    sundayMultiplier: float = 2  # noqa: N815
    holidayMultiplier: float = 2  # noqa: N815


class RulesOut(Schema):
    effectiveFrom: date | None  # noqa: N815 - none: the built-in defaults
    minRestHours: int  # noqa: N815
    maxConsecutiveDays: int  # noqa: N815
    maxWeeklyHours: int | None  # noqa: N815
    overtimeMultiplier: float  # noqa: N815
    sundayMultiplier: float  # noqa: N815
    holidayMultiplier: float  # noqa: N815


class RulesState(Schema):
    inForce: RulesOut  # noqa: N815
    versions: list[RulesOut]  # newest first, including ones not yet started
    warnings: list[str]  # for the rules in force


class RulesSaved(Schema):
    saved: RulesOut
    warnings: list[str]


def _out(day: date | None, rules: Rules) -> RulesOut:
    return RulesOut(
        effectiveFrom=day,
        minRestHours=rules.min_rest_hours,
        maxConsecutiveDays=rules.max_consecutive_days,
        maxWeeklyHours=rules.max_weekly_hours,
        overtimeMultiplier=float(rules.overtime_multiplier),
        sundayMultiplier=float(rules.sunday_multiplier),
        holidayMultiplier=float(rules.holiday_multiplier),
    )


@router.get("", auth=READ, response=RulesState, summary="The compliance rules, now and by version")
def get_rules(request: HttpRequest, on: date | None = None) -> RulesState:
    day = on or timezone.localdate()
    versions = selectors.rule_versions()
    started = [v for v in versions if v.effective_from <= day]
    in_force = selectors.rules_on(day)
    return RulesState(
        inForce=_out(started[0].effective_from if started else None, in_force),
        versions=[_out(v.effective_from, selectors.rules_of(v)) for v in versions],
        warnings=floor_warnings(in_force),
    )


@router.put("", auth=ADMIN_ONLY, response=RulesSaved, summary="Set the rules from a day onwards")
def put_rules(request: HttpRequest, body: RulesIn) -> RulesSaved:
    rules = Rules(
        min_rest_hours=body.minRestHours,
        max_consecutive_days=body.maxConsecutiveDays,
        max_weekly_hours=body.maxWeeklyHours,
        overtime_multiplier=Decimal(str(body.overtimeMultiplier)),
        sunday_multiplier=Decimal(str(body.sundayMultiplier)),
        holiday_multiplier=Decimal(str(body.holidayMultiplier)),
    )
    version, warnings = services.set_rules(
        user=current_user(request), effective_from=body.effectiveFrom, rules=rules
    )
    return RulesSaved(saved=_out(version.effective_from, rules), warnings=warnings)
