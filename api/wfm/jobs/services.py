"""Starting, running and reading jobs."""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from wfm.accounts.models import User
from wfm.core.errors import ApiError, not_found

from .models import ACTIVE, Job, JobStatus
from .registry import RUNNERS

log = logging.getLogger(__name__)

# A worker that died mid-job leaves it "running"; after this long another worker may take it over.
STALE_AFTER = timedelta(minutes=20)
KEEP_FOR = timedelta(days=7)


def start(*, user: User, kind: str, params: dict[str, Any]) -> Job:
    """Queue a job for `user`. Asking again for the same work while it is still waiting or running
    returns that job, so a double click does not do it twice."""
    if kind not in RUNNERS:
        raise ValueError(f"unknown job kind {kind!r}")
    from .tasks import run_job

    with transaction.atomic():
        existing: Job | None = (
            Job.objects.for_user(user)
            .select_for_update(no_key=True)
            .filter(kind=kind, params=params, status__in=ACTIVE)
            .first()
        )
        if existing:
            return existing
        job = Job.objects.create(owner=user, kind=kind, params=params)
        transaction.on_commit(lambda: run_job.delay(str(job.pk)))
    return job


def get(user: User, job_id: str) -> Job:
    try:
        found = Job.objects.for_user(user).filter(pk=job_id).first()
    except (ValueError, ValidationError):  # not a UUID
        found = None
    if not isinstance(found, Job):
        raise not_found("No such job.")
    return found


def run(job_id: str) -> None:
    """Do the work of one job, as its owner, and record how it went. Never raises."""
    now = timezone.now()
    with transaction.atomic():
        job = Job.objects.select_for_update(no_key=True).select_related("owner").get(pk=job_id)
        taken_over = (
            job.status == JobStatus.RUNNING
            and job.started_at is not None
            and job.started_at < now - STALE_AFTER
        )
        if job.status != JobStatus.QUEUED and not taken_over:
            return
        job.status, job.started_at = JobStatus.RUNNING, now
        job.save(update_fields=["status", "started_at"])

    result: dict[str, Any] | None = None
    code, detail = "", ""
    try:
        if not job.owner.is_active:  # a deactivated person's work stops
            raise ApiError(403, "job.owner_inactive", "Refused", "The account is not active.")
        produced = RUNNERS[job.kind](job.owner, job.params)
        json.dumps(produced)  # a result that cannot be stored is a failed job, never a stuck one
        result = produced
    except ApiError as refusal:
        code, detail = refusal.code, (refusal.detail or refusal.title)[:300]
    except Exception:
        # The reason goes to the log; the person gets a generic sentence.
        log.exception("job %s (%s) failed", job.pk, job.kind)
        code, detail = "job.failed", "The job failed. Try again, and tell support if it repeats."

    with transaction.atomic():
        finished = Job.objects.select_for_update(no_key=True).get(pk=job_id)
        finished.finished_at = timezone.now()
        if result is None:
            finished.status = JobStatus.FAILED
            finished.error_code, finished.error_detail = code, detail
        else:
            finished.status, finished.result = JobStatus.DONE, result
        finished.save()


def delete_old() -> int:
    """Finished jobs older than a week go; nobody needs the answer any more."""
    cutoff = timezone.now() - KEEP_FOR
    deleted, _ = Job.objects.exclude(status__in=ACTIVE).filter(created_at__lt=cutoff).delete()
    return deleted
