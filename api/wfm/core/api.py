from __future__ import annotations

from django.http import HttpRequest
from ninja import Router, Schema

from wfm.accounts.models import Role

from . import telemetry
from .errors import ApiError
from .features import CORE
from .permissions import RoleSessionAuth
from .tasks import ping

router = Router(tags=["system"])


class WorkerPingOut(Schema):
    ok: bool
    apiTraceId: str  # noqa: N815 - camelCase on the wire
    workerTraceId: str  # noqa: N815


@router.post(
    "/ping-worker",
    auth=RoleSessionAuth(Role.ADMIN, feature=CORE),
    response=WorkerPingOut,
    summary="Round trip through the background worker",
)
def ping_worker(request: HttpRequest) -> WorkerPingOut:
    """Is the worker alive, and does trace context survive the queue? Both trace ids should match
    when tracing is on."""
    try:
        result = ping.delay().get(timeout=5)
    except Exception:
        raise ApiError(
            503, "worker.unavailable", "Worker unavailable", "The background worker did not answer."
        ) from None
    return WorkerPingOut(
        ok=True, apiTraceId=telemetry.trace_id_hex(), workerTraceId=result["trace_id"]
    )
