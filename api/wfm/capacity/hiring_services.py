"""Making, changing and deleting hiring plans (CAP-01). Writes are one transaction with the audit
event as the LAST write; the event names the plan and never a rand figure."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from wfm_engine import hiring

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError, not_found

from .models import HiringPlan
from .policy import PLAN_WRITE_ROLES

MAX_PLANS = 20
MAX_COST = Decimal("10000000")


def _refuse(code: str, detail: str, status: int = 422) -> ApiError:
    return ApiError(status, code, "Hiring plan refused", detail)


def _check(
    user: User,
    name: str,
    start_month: date,
    incumbents: Decimal,
    attrition_pct: Decimal,
    ramp: list[float],
    required: list[float],
    cost_per_person: Decimal | None,
) -> str:
    if user.role not in PLAN_WRITE_ROLES:
        raise _refuse("auth.forbidden", "Your role may not change hiring plans.", 403)
    name = name.strip()
    if not 1 <= len(name) <= 80:
        raise _refuse("hiring.bad_name", "Give the plan a name of up to 80 letters.")
    if start_month.day != 1:
        raise _refuse("hiring.bad_start", "A plan starts on the first day of a month.")
    if cost_per_person is not None and not Decimal(0) <= cost_per_person <= MAX_COST:
        raise _refuse("hiring.bad_cost", "That is not a sensible cost for a person-month.")
    try:
        hiring.validate(required, float(incumbents), float(attrition_pct) / 100, ramp)
    except ValueError as why:
        raise _refuse("hiring.invalid", str(why).capitalize() + ".") from why
    return name


def create(
    *,
    user: User,
    name: str,
    start_month: date,
    incumbents: Decimal,
    attrition_pct: Decimal,
    ramp: list[float],
    required: list[float],
    cost_per_person: Decimal | None,
) -> HiringPlan:
    name = _check(
        user, name, start_month, incumbents, attrition_pct, ramp, required, cost_per_person
    )
    with transaction.atomic():
        if HiringPlan.objects.count() >= MAX_PLANS:
            raise _refuse("hiring.too_many", "That is enough plans; delete one first.", 409)
        made = HiringPlan.objects.create(
            name=name,
            start_month=start_month,
            incumbents=incumbents,
            attrition_pct=attrition_pct,
            ramp=ramp,
            required=required,
            cost_per_person=cost_per_person,
            created_by=user,
        )
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.HIRING_PLAN_CREATED,
            entity_type="hiring_plan",
            entity_id=str(made.pk),
            changes=[audit.FieldChange("hiring_plan", str(made.pk), "name", None, name)],
        )
    return made


def update(
    *,
    user: User,
    plan_id: int,
    name: str,
    start_month: date,
    incumbents: Decimal,
    attrition_pct: Decimal,
    ramp: list[float],
    required: list[float],
    cost_per_person: Decimal | None,
) -> HiringPlan:
    name = _check(
        user, name, start_month, incumbents, attrition_pct, ramp, required, cost_per_person
    )
    with transaction.atomic():
        row = (
            HiringPlan.objects.select_for_update(no_key=True)
            .for_user(user)
            .filter(pk=plan_id)
            .first()
        )
        if not isinstance(row, HiringPlan):
            raise not_found("No such hiring plan.")
        found = row
        found.name, found.start_month = name, start_month
        found.incumbents, found.attrition_pct = incumbents, attrition_pct
        found.ramp, found.required, found.cost_per_person = ramp, required, cost_per_person
        found.save()
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.HIRING_PLAN_CHANGED,
            entity_type="hiring_plan",
            entity_id=str(found.pk),
            changes=[audit.FieldChange("hiring_plan", str(found.pk), "name", None, name)],
        )
    return found


def delete(*, user: User, plan_id: int) -> None:
    if user.role not in PLAN_WRITE_ROLES:
        raise _refuse("auth.forbidden", "Your role may not change hiring plans.", 403)
    with transaction.atomic():
        found = (
            HiringPlan.objects.select_for_update(no_key=True)
            .for_user(user)
            .filter(pk=plan_id)
            .first()
        )
        if found is None:
            raise not_found("No such hiring plan.")
        name = found.name
        found.delete()
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.HIRING_PLAN_DELETED,
            entity_type="hiring_plan",
            entity_id=str(plan_id),
            changes=[audit.FieldChange("hiring_plan", str(plan_id), "name", name, None)],
        )
