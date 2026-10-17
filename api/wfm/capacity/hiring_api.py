"""Monthly hiring plans over 12 to 18 months (CAP-01)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.http import HttpRequest
from ninja import Router, Schema, Status
from wfm_engine import hiring

from wfm.core.errors import not_found
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import hiring_services as services
from .models import HiringPlan
from .policy import PLAN_READ_ROLES, PLAN_WRITE_ROLES

router = Router(tags=["capacity"])
READ = RoleSessionAuth(*sorted(PLAN_READ_ROLES), feature=Feature.CAPACITY)
WRITE = RoleSessionAuth(*sorted(PLAN_WRITE_ROLES), feature=Feature.CAPACITY)


class HiringPlanIn(Schema):
    name: str
    startMonth: date  # noqa: N815 - the first of a month
    incumbents: Decimal
    attritionPctPerMonth: Decimal  # noqa: N815
    ramp: list[float]  # share of full strength by months since hired; ends at 1
    required: list[float]  # people needed each month, 12 to 18 of them
    costPerPersonMonth: Decimal | None = None  # noqa: N815 - rands; planner and admin only


class HiringRowOut(Schema):
    month: date
    required: float
    headcount: float
    hires: int
    effective: float
    gap: float  # negative is a shortfall
    unavoidable: bool  # a shortfall no hire could have prevented
    costRands: float | None  # noqa: N815 - null for roles that do not see pay


class HiringPlanOut(Schema):
    id: int
    name: str
    startMonth: date  # noqa: N815
    incumbents: float
    attritionPctPerMonth: float  # noqa: N815
    ramp: list[float]
    costPerPersonMonth: float | None  # noqa: N815 - null for roles that do not see pay
    totalHires: int  # noqa: N815
    shortfallMonths: int  # noqa: N815
    unavoidableMonths: int  # noqa: N815
    totalCostRands: float | None  # noqa: N815
    rows: list[HiringRowOut]


class HiringPlanSummaryOut(Schema):
    id: int
    name: str
    startMonth: date  # noqa: N815
    months: int


def _month(start: date, offset: int) -> date:
    index = start.year * 12 + start.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def _out(plan: HiringPlan, user_sees_pay: bool) -> HiringPlanOut:
    attrition = float(plan.attrition_pct) / 100
    rows = hiring.plan(plan.required, float(plan.incumbents), attrition, plan.ramp)
    cost = (
        float(plan.cost_per_person)
        if (user_sees_pay and plan.cost_per_person is not None)
        else None
    )
    out_rows = [
        HiringRowOut(
            month=_month(plan.start_month, r.index),
            required=r.required,
            headcount=round(r.headcount, 2),
            hires=r.hires,
            effective=round(r.effective, 2),
            gap=round(r.gap, 2),
            unavoidable=r.unavoidable,
            costRands=round(r.headcount * cost, 2) if cost is not None else None,
        )
        for r in rows
    ]
    return HiringPlanOut(
        id=plan.pk,
        name=plan.name,
        startMonth=plan.start_month,
        incumbents=float(plan.incumbents),
        attritionPctPerMonth=float(plan.attrition_pct),
        ramp=list(plan.ramp),
        costPerPersonMonth=cost,
        totalHires=sum(r.hires for r in rows),
        shortfallMonths=sum(1 for r in rows if r.gap < -1e-6),
        unavoidableMonths=sum(1 for r in rows if r.unavoidable),
        totalCostRands=round(sum(r.costRands or 0 for r in out_rows), 2)
        if cost is not None
        else None,
        rows=out_rows,
    )


def _sees_pay(request: HttpRequest) -> bool:
    return current_user(request).role in PLAN_WRITE_ROLES


@router.get("/hiring-plans", auth=READ, response=list[HiringPlanSummaryOut], summary="Hiring plans")
def list_plans(request: HttpRequest) -> list[HiringPlanSummaryOut]:
    return [
        HiringPlanSummaryOut(id=p.pk, name=p.name, startMonth=p.start_month, months=len(p.required))
        for p in HiringPlan.objects.for_user(current_user(request))
    ]


@router.get(
    "/hiring-plans/{plan_id}", auth=READ, response=HiringPlanOut, summary="One plan, worked out"
)
def get_plan(request: HttpRequest, plan_id: int) -> HiringPlanOut:
    found = HiringPlan.objects.for_user(current_user(request)).filter(pk=plan_id).first()
    if found is None:
        raise not_found("No such hiring plan.")
    return _out(found, _sees_pay(request))


@router.post("/hiring-plans", auth=WRITE, response={201: HiringPlanOut}, summary="Make a plan")
def create_plan(request: HttpRequest, body: HiringPlanIn) -> Status[HiringPlanOut]:
    made = services.create(
        user=current_user(request),
        name=body.name,
        start_month=body.startMonth,
        incumbents=body.incumbents,
        attrition_pct=body.attritionPctPerMonth,
        ramp=body.ramp,
        required=body.required,
        cost_per_person=body.costPerPersonMonth,
    )
    return Status(201, _out(made, True))


@router.put("/hiring-plans/{plan_id}", auth=WRITE, response=HiringPlanOut, summary="Change a plan")
def change_plan(request: HttpRequest, plan_id: int, body: HiringPlanIn) -> HiringPlanOut:
    changed = services.update(
        user=current_user(request),
        plan_id=plan_id,
        name=body.name,
        start_month=body.startMonth,
        incumbents=body.incumbents,
        attrition_pct=body.attritionPctPerMonth,
        ramp=body.ramp,
        required=body.required,
        cost_per_person=body.costPerPersonMonth,
    )
    return _out(changed, True)


@router.delete("/hiring-plans/{plan_id}", auth=WRITE, response={204: None}, summary="Delete a plan")
def delete_plan(request: HttpRequest, plan_id: int) -> Status[None]:
    services.delete(user=current_user(request), plan_id=plan_id)
    return Status(204, None)
