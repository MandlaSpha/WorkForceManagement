from __future__ import annotations

from celery import shared_task

from . import services


@shared_task(name="wfm.reports.send_due")  # type: ignore[untyped-decorator]
def send_due_reports() -> int:
    """Every fifteen minutes: send the report schedules that have come due."""
    return services.send_due()
