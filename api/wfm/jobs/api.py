"""Asking how a background job is getting on."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.http import HttpRequest
from ninja import Router, Schema

from wfm.core.features import CORE
from wfm.core.permissions import RoleSessionAuth, current_user

from . import services
from .models import Job

router = Router(tags=["jobs"])
# Any signed-in role may ask; a job is only ever visible to the person who started it.
ANY = RoleSessionAuth(feature=CORE)


class JobOut(Schema):
    id: str
    kind: str
    status: str  # queued, running, done or failed
    result: dict[str, Any] | None
    errorCode: str  # noqa: N815
    errorDetail: str  # noqa: N815
    createdAt: datetime  # noqa: N815
    finishedAt: datetime | None  # noqa: N815


def job_out(job: Job) -> JobOut:
    return JobOut(
        id=str(job.pk),
        kind=job.kind,
        status=job.status,
        result=job.result,
        errorCode=job.error_code,
        errorDetail=job.error_detail,
        createdAt=job.created_at,
        finishedAt=job.finished_at,
    )


@router.get("/{job_id}", auth=ANY, response=JobOut, summary="How a background job is getting on")
def get_job(request: HttpRequest, job_id: str) -> JobOut:
    return job_out(services.get(current_user(request), job_id))
