"""The kinds of job there are. Each calls the service a click would, as the job's owner."""

from __future__ import annotations

from datetime import date
from typing import Any

from wfm.accounts.models import User
from wfm.forecasting import services as forecasting
from wfm.scheduling import autoschedule_services as autoschedule

from .registry import register

AUTO_SCHEDULE = "auto_schedule"
FORECAST = "forecast"


@register(AUTO_SCHEDULE)
def auto_schedule(user: User, params: dict[str, Any]) -> dict[str, Any]:
    applied = autoschedule.apply(
        user, int(params["queue_id"]), date.fromisoformat(params["week_start"])
    )
    solution = applied.proposal.solution
    return {  # counts only: no names
        "status": solution.status,
        "placed": applied.placed,
        "skipped": applied.skipped,
        "shortBefore": solution.short_before,
        "shortAfter": solution.short_after,
        "overAfter": solution.over_after,
        "kept": solution.kept,
    }


@register(FORECAST)
def forecast(user: User, params: dict[str, Any]) -> dict[str, Any]:
    version = forecasting.run_forecast(
        user=user,
        queue_id=int(params["queue_id"]),
        date_from=date.fromisoformat(params["date_from"]),
        date_to=date.fromisoformat(params["date_to"]),
        label=str(params.get("label", "")),
        method=str(params.get("method", "baseline")),
    )
    return {"versionId": str(version.pk)}
