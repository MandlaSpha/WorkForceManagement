from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.http import HttpRequest
from django.utils import timezone
from ninja import Field, Router, Schema, Status

from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import selectors, services
from .models import Contract, Customer
from .policy import READ_ROLES, WRITE_ROLES

router = Router(tags=["contracts"])
READ = RoleSessionAuth(*sorted(READ_ROLES), feature=Feature.CAPACITY)
WRITE = RoleSessionAuth(*sorted(WRITE_ROLES), feature=Feature.CAPACITY)


class CustomerIn(Schema):
    name: str


class CustomerOut(Schema):
    id: int
    name: str


class ContractIn(Schema):
    name: str
    slTargetPct: Decimal  # noqa: N815
    slThresholdS: int  # noqa: N815
    queueIds: list[int] = Field(default_factory=list)  # noqa: N815


class ContractChangeIn(ContractIn):
    active: bool = True


class ContractCreateIn(ContractIn):
    customerId: int  # noqa: N815


class QueueRefOut(Schema):
    id: int
    name: str


class ContractOut(Schema):
    id: int
    customerId: int  # noqa: N815
    customer: str
    name: str
    slTargetPct: float  # noqa: N815
    slThresholdS: int  # noqa: N815
    active: bool
    queues: list[QueueRefOut]
    offered: int  # calls in the last 28 days of imported data
    measuredSlPct: float | None  # noqa: N815 - none when there were no calls: never a made-up zero
    intervalsKnown: int  # noqa: N815 - half-hours of the week with a forecast requirement
    underIntervals: int  # noqa: N815
    gap: int
    atRisk: bool  # noqa: N815
    risks: list[str]


@router.get("/customers", auth=READ, response=list[CustomerOut], summary="Customers")
def list_customers(request: HttpRequest) -> list[CustomerOut]:
    return [_customer(c) for c in selectors.customers(current_user(request))]


@router.post("/customers", auth=WRITE, response={201: CustomerOut}, summary="Add a customer")
def create_customer(request: HttpRequest, body: CustomerIn) -> Status[CustomerOut]:
    return Status(
        201, _customer(services.create_customer(user=current_user(request), name=body.name))
    )


@router.get(
    "",
    auth=READ,
    response=list[ContractOut],
    summary="Contracts with their measured service level and the week's coverage",
)
def list_contracts(request: HttpRequest, week_start: date | None = None) -> list[ContractOut]:
    today = timezone.localdate()
    monday = week_start or today - timedelta(days=today.weekday())
    return [_out(r) for r in selectors.contract_rows(current_user(request), monday)]


@router.post("", auth=WRITE, response={201: ContractOut}, summary="Add a contract")
def create_contract(request: HttpRequest, body: ContractCreateIn) -> Status[ContractOut]:
    user = current_user(request)
    created = services.create_contract(
        user=user,
        customer_id=body.customerId,
        name=body.name,
        sl_target_pct=body.slTargetPct,
        sl_threshold_s=body.slThresholdS,
        queue_ids=body.queueIds,
    )
    return Status(201, _one(user, created))


@router.put("/{contract_id}", auth=WRITE, response=ContractOut, summary="Change a contract")
def update_contract(request: HttpRequest, contract_id: int, body: ContractChangeIn) -> ContractOut:
    user = current_user(request)
    changed = services.update_contract(
        user=user,
        contract_id=contract_id,
        name=body.name,
        sl_target_pct=body.slTargetPct,
        sl_threshold_s=body.slThresholdS,
        active=body.active,
        queue_ids=body.queueIds,
    )
    return _one(user, changed)


def _customer(c: Customer) -> CustomerOut:
    return CustomerOut(id=c.pk, name=c.name)


def _one(user: object, contract: Contract) -> ContractOut:
    today = timezone.localdate()
    monday = today - timedelta(days=today.weekday())
    rows = selectors.contract_rows(user, monday)  # type: ignore[arg-type]
    return _out(next(r for r in rows if r.contract.pk == contract.pk))


def _out(r: selectors.ContractRow) -> ContractOut:
    c = r.contract
    return ContractOut(
        id=c.pk,
        customerId=c.customer_id,
        customer=c.customer.name,
        name=c.name,
        slTargetPct=float(c.sl_target_pct),
        slThresholdS=c.sl_threshold_s,
        active=c.active,
        queues=[QueueRefOut(id=q.pk, name=q.name) for q in r.queues],
        offered=r.offered,
        measuredSlPct=r.measured_sl_pct,
        intervalsKnown=r.intervals_known,
        underIntervals=r.under_intervals,
        gap=r.gap,
        atRisk=r.at_risk,
        risks=r.risks,
    )
