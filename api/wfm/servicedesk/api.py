from __future__ import annotations

from datetime import date

from django.http import HttpRequest
from ninja import File, Router, Status
from ninja.files import UploadedFile
from wfm_engine.workload import Demand

from wfm.core.errors import ApiError
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import selectors, services
from .models import ServicePool
from .policy import READ_ROLES, WRITE_ROLES
from .schemas import DemandOut, PoolDemandOut, PoolIn, WorkImportOut

router = Router(tags=["service-desk"])

READ = RoleSessionAuth(*sorted(READ_ROLES), feature=Feature.SERVICE_DESK)
WRITE = RoleSessionAuth(*sorted(WRITE_ROLES), feature=Feature.SERVICE_DESK)

MAX_UPLOAD_MB = 10


@router.get(
    "/demand",
    auth=READ,
    response=DemandOut,
    summary="The people each pool needs: effort due by the deadline over productive time",
)
def get_demand(request: HttpRequest, as_of: date, days: int = 7) -> DemandOut:
    pools, working = selectors.demand(current_user(request), as_of, days)
    known = [p.demand.required_fte for p in pools if p.demand.required_fte is not None]
    arriving = [p.demand.arriving_min for p in pools if p.demand.arriving_min is not None]
    return DemandOut(
        asOf=as_of,
        days=days,
        workingDays=working,
        pools=[_pool_out(p.pool, p.demand) for p in pools],
        requiredFte=sum(known) if known else None,
        backlogMin=sum(p.demand.backlog_min for p in pools),
        arrivingMin=sum(arriving) if arriving else None,
        breached=sum(p.demand.breached for p in pools),
        complete=bool(pools) and all(p.demand.complete for p in pools),
    )


@router.post(
    "/imports",
    auth=WRITE,
    response={201: WorkImportOut},
    summary="Bring in work items from an ITSM export (CSV); known references are updated",
)
def import_items(request: HttpRequest, file: File[UploadedFile]) -> Status[WorkImportOut]:
    if file.size is not None and file.size > MAX_UPLOAD_MB * 1024 * 1024:
        raise ApiError(
            413,
            "workitems.too_large",
            "File too large",
            f"Imports are limited to {MAX_UPLOAD_MB} MB.",
        )
    result = services.import_items(user=current_user(request), content=file.read())
    return Status(
        201,
        WorkImportOut(
            created=result.created,
            updated=result.updated,
            unchanged=result.unchanged,
            rejected=result.rejected,
            ignoredColumns=result.ignored_columns,
        ),
    )


@router.put(
    "/pools/{pool_id}",
    auth=WRITE,
    response=dict[str, int],
    summary="Set how many minutes of a day an engineer in this pool spends on tickets",
)
def set_pool(request: HttpRequest, pool_id: int, body: PoolIn) -> dict[str, int]:
    pool = services.set_productive_minutes(
        user=current_user(request), pool_id=pool_id, minutes=body.productiveMinutesPerDay
    )
    return {"productiveMinutesPerDay": pool.productive_minutes_per_day}


def _pool_out(pool: ServicePool, d: Demand) -> PoolDemandOut:
    return PoolDemandOut(
        poolId=pool.pk,
        pool=pool.name,
        productiveMinutesPerDay=pool.productive_minutes_per_day,
        settingsConfirmed=pool.settings_confirmed,
        openCount=d.open_count,
        breached=d.breached,
        backlogMin=d.backlog_min,
        dueMin=d.due_min,
        arrivingMin=d.arriving_min,
        unestimated=d.unestimated,
        noDeadline=d.no_deadline,
        requiredFte=d.required_fte,
        complete=d.complete,
    )
