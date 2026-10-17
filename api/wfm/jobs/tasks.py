from __future__ import annotations

from celery import shared_task

from . import services


@shared_task(name="wfm.jobs.run")  # type: ignore[untyped-decorator]
def run_job(job_id: str) -> None:
    services.run(job_id)


@shared_task(name="wfm.jobs.delete_old")  # type: ignore[untyped-decorator]
def delete_old_jobs() -> int:
    return services.delete_old()
