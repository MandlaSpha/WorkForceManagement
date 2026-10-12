from __future__ import annotations

from celery import shared_task
from django.db import connection

from . import telemetry


@shared_task(name="wfm.core.ping")  # type: ignore[untyped-decorator]
def ping() -> dict[str, str]:
    """A round trip through the worker that touches the database. Reports the trace id it ran
    under, which must equal the caller's when trace context propagates through the queue."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return {"trace_id": telemetry.trace_id_hex()}
