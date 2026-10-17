from __future__ import annotations

from typing import Literal
from uuid import UUID

from django.http import HttpRequest
from ninja import Router, Status
from wfm_engine.forecast import Backtest

from wfm.core.errors import not_found
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user
from wfm.jobs import services as jobs
from wfm.jobs.api import JobOut, job_out
from wfm.jobs.runners import FORECAST
from wfm.telephony.models import Queue

from . import event_services, modeling, scenario, selectors, services
from .models import ForecastEvent, ForecastInterval, ForecastVersion
from .policy import READ_ROLES, WRITE_ROLES
from .schemas import (
    AccuracyOut,
    BacktestOut,
    DayAccuracyOut,
    EventIn,
    EventOut,
    ForecastIntervalOut,
    ForecastVersionOut,
    RunForecastIn,
    ScenarioAssumptionsOut,
    ScenarioDayOut,
    ScenarioIn,
    ScenarioOut,
    ScoreOut,
    TuningIn,
    TuningOut,
)
from .staffing import Assumptions

router = Router(tags=["forecasting"])

READ = RoleSessionAuth(*sorted(READ_ROLES), feature=Feature.FORECASTING)
WRITE = RoleSessionAuth(*sorted(WRITE_ROLES), feature=Feature.FORECASTING)


@router.post(
    "/versions",
    auth=WRITE,
    response={201: ForecastVersionOut},
    summary="Run a forecast for a queue and a range of days (a draft)",
)
def run_forecast(request: HttpRequest, body: RunForecastIn) -> Status[ForecastVersionOut]:
    version = services.run_forecast(
        user=current_user(request),
        queue_id=body.queueId,
        date_from=body.dateFrom,
        date_to=body.dateTo,
        label=body.label,
        method=body.method,
    )
    return Status(201, _version_out(version, interval_count=version.intervals.count()))


@router.post(
    "/versions/jobs",
    auth=WRITE,
    response={202: JobOut},
    summary="Run a forecast in the background (a draft when it finishes)",
)
def run_forecast_in_background(request: HttpRequest, body: RunForecastIn) -> Status[JobOut]:
    """Answers at once with a job to ask about. The worker does what the call above does, as this
    person, so their scope and the audit trail apply."""
    user = current_user(request)
    if not Queue.objects.for_user(user).filter(pk=body.queueId).exists():
        raise not_found("No such queue.")
    job = jobs.start(
        user=user,
        kind=FORECAST,
        params={
            "queue_id": body.queueId,
            "date_from": body.dateFrom.isoformat(),
            "date_to": body.dateTo.isoformat(),
            "label": body.label,
            "method": body.method,
        },
    )
    return Status(202, job_out(job))


@router.get(
    "/versions",
    auth=READ,
    response=list[ForecastVersionOut],
    summary="Forecast versions, newest first",
)
def list_versions(request: HttpRequest, queue_id: int | None = None) -> list[ForecastVersionOut]:
    versions = selectors.list_versions(current_user(request), queue_id)
    return [_version_out(v, interval_count=getattr(v, "interval_count", 0)) for v in versions]


@router.post(
    "/versions/{version_id}/publish",
    auth=WRITE,
    response=ForecastVersionOut,
    summary="Make a draft the live forecast of its queue",
)
def publish_version(request: HttpRequest, version_id: UUID) -> ForecastVersionOut:
    version = services.publish_forecast(user=current_user(request), version_id=version_id)
    return _version_out(version, interval_count=version.intervals.count())


@router.get(
    "/versions/{version_id}/intervals",
    auth=READ,
    response=list[ForecastIntervalOut],
    summary="The half-hour forecast and staffing requirement of a version",
)
def version_intervals(request: HttpRequest, version_id: UUID) -> list[ForecastIntervalOut]:
    return [
        _interval_out(i) for i in selectors.version_intervals(current_user(request), version_id)
    ]


@router.get(
    "/accuracy",
    auth=READ,
    response=AccuracyOut,
    summary="How well a model would have predicted each past day (backtest)",
)
def accuracy(
    request: HttpRequest, queue_id: int, method: Literal["baseline", "prophet"] = "baseline"
) -> AccuracyOut:
    result = selectors.forecast_accuracy(current_user(request), queue_id, method)
    return AccuracyOut(
        queueId=result.queue.pk,
        queue=result.queue.name,
        overallAccuracyPct=result.overall_pct,
        overallDailyAccuracyPct=result.overall_daily_pct,
        weeks=result.weeks,
        decay=result.decay,
        biasPct=result.bias_pct,
        days=[
            DayAccuracyOut(
                date=d.day,
                accuracyPct=d.accuracy_pct,
                dailyAccuracyPct=d.daily_pct,
                daysUsed=d.days_used,
            )
            for d in result.days
        ],
    )


@router.get("/tuning", auth=READ, response=TuningOut, summary="How a queue's forecast is tuned")
def get_tuning(request: HttpRequest, queue_id: int) -> TuningOut:
    user = current_user(request)
    queue = selectors.queue_for(user, queue_id)
    tuning, saved = selectors.tuning_of(user, queue)
    return _tuning_out(queue.pk, queue.name, tuning, saved)


@router.put(
    "/tuning", auth=WRITE, response=TuningOut, summary="Save how a queue's forecast is tuned"
)
def put_tuning(request: HttpRequest, body: TuningIn) -> TuningOut:
    row = services.set_tuning(
        user=current_user(request),
        queue_id=body.queueId,
        tuning=modeling.Tuning(body.weeks, body.decay, body.volumeMultiplier, body.ahtMultiplier),
    )
    tuning, _ = selectors.tuning_of(current_user(request), row.queue)
    return _tuning_out(row.queue_id, row.queue.name, tuning, True)


@router.get(
    "/tuning/backtest",
    auth=READ,
    response=BacktestOut,
    summary="Score a tuning against what really happened, next to the saved one (nothing is saved)",
)
def backtest_tuning(
    request: HttpRequest,
    queue_id: int,
    weeks: int | None = None,
    decay: float | None = None,
    volume_multiplier: float | None = None,
    aht_multiplier: float | None = None,
) -> BacktestOut:
    user = current_user(request)
    saved, _ = selectors.tuning_of(user, selectors.queue_for(user, queue_id))
    candidate = modeling.Tuning(
        saved.weeks if weeks is None else weeks,
        saved.decay if decay is None else decay,
        saved.volume_multiplier if volume_multiplier is None else volume_multiplier,
        saved.aht_multiplier if aht_multiplier is None else aht_multiplier,
    )
    trial = selectors.try_tuning(user, queue_id, candidate)
    return BacktestOut(
        queueId=trial.queue.pk,
        candidate=_score_out(trial.candidate),
        current=_score_out(trial.current),
        suggestedVolumeMultiplier=trial.suggested_volume_multiplier,
    )


def _tuning_out(queue_id: int, queue: str, tuning: modeling.Tuning, saved: bool) -> TuningOut:
    return TuningOut(
        queueId=queue_id,
        queue=queue,
        weeks=tuning.weeks,
        decay=tuning.decay,
        volumeMultiplier=tuning.volume_multiplier,
        ahtMultiplier=tuning.aht_multiplier,
        saved=saved,
    )


def _score_out(result: Backtest) -> ScoreOut:
    return ScoreOut(
        dailyPct=result.daily_pct,
        intervalPct=result.interval_pct,
        biasPct=result.bias_pct,
        days=len(result.days),
    )


@router.get(
    "/events", auth=READ, response=list[EventOut], summary="The events calendar, soonest first"
)
def list_events(request: HttpRequest, queue_id: int | None = None) -> list[EventOut]:
    return [_event_out(e) for e in selectors.list_events(current_user(request), queue_id)]


@router.post("/events", auth=WRITE, response={201: EventOut}, summary="Add an event")
def create_event(request: HttpRequest, body: EventIn) -> Status[EventOut]:
    event = event_services.create_event(
        user=current_user(request),
        name=body.name,
        queue_id=body.queueId,
        date_from=body.dateFrom,
        date_to=body.dateTo,
        uplift_pct=body.upliftPct,
    )
    return Status(201, _event_out(event))


@router.put("/events/{event_id}", auth=WRITE, response=EventOut, summary="Change an event")
def update_event(request: HttpRequest, event_id: int, body: EventIn) -> EventOut:
    event = event_services.update_event(
        user=current_user(request),
        event_id=event_id,
        name=body.name,
        queue_id=body.queueId,
        date_from=body.dateFrom,
        date_to=body.dateTo,
        uplift_pct=body.upliftPct,
    )
    return _event_out(event)


@router.delete(
    "/events/{event_id}", auth=WRITE, response=dict[str, bool], summary="Remove an event"
)
def delete_event(request: HttpRequest, event_id: int) -> dict[str, bool]:
    event_services.delete_event(user=current_user(request), event_id=event_id)
    return {"ok": True}


@router.post(
    "/scenarios",
    auth=READ,
    response=ScenarioOut,
    summary="What if: the agents needed if calls, handling time, shrinkage or the target change",
)
def run_scenario(request: HttpRequest, body: ScenarioIn) -> ScenarioOut:
    version, rows = selectors.scenario_source(current_user(request), body.versionId)
    base = Assumptions.of_params(version.params, Assumptions.of_queue(version.queue))
    changed, days = scenario.run(
        rows,
        base,
        volume_change_pct=body.volumeChangePct,
        aht_change_pct=body.ahtChangePct,
        sl_target_pct=body.slTargetPct,
        shrinkage_pct=body.shrinkagePct,
    )
    return ScenarioOut(
        versionId=version.id,
        queue=version.queue.name,
        base=_assumptions_out(base),
        scenario=_assumptions_out(changed),
        days=[
            ScenarioDayOut(
                day=d.day,
                callsBase=d.calls_base,
                callsScenario=d.calls_scenario,
                peakBase=d.peak_base,
                peakScenario=d.peak_scenario,
                hoursBase=d.hours_base,
                hoursScenario=d.hours_scenario,
                complete=d.complete,
            )
            for d in days
        ],
    )


def _assumptions_out(a: Assumptions) -> ScenarioAssumptionsOut:
    return ScenarioAssumptionsOut(
        slTargetPct=a.sl_target_pct,
        slThresholdS=a.sl_threshold_s,
        occupancyCeilingPct=a.occupancy_ceiling_pct,
        shrinkagePct=a.shrinkage_pct,
    )


def _event_out(event: ForecastEvent) -> EventOut:
    return EventOut(
        id=event.pk,
        name=event.name,
        queueId=event.queue_id,
        queue=event.queue.name if event.queue else None,
        dateFrom=event.date_from,
        dateTo=event.date_to,
        upliftPct=float(event.uplift_pct),
    )


def _version_out(version: ForecastVersion, *, interval_count: int) -> ForecastVersionOut:
    return ForecastVersionOut(
        id=version.id,
        queueId=version.queue_id,
        queue=version.queue.name,
        label=version.label,
        status=version.status,
        method=version.method,
        dateFrom=version.date_from,
        dateTo=version.date_to,
        createdAt=version.created_at,
        createdBy=version.created_by.get_full_name() or version.created_by.username,
        publishedAt=version.published_at,
        intervalCount=interval_count,
        assumptionsConfirmed=bool(version.params.get("assumptionsConfirmed")),
        fallback=version.params.get("fallback"),
        daysWithoutHistory=version.params.get("daysWithoutHistory", []),
        historyThrough=version.params.get("historyThrough"),
        params=version.params,
    )


def _interval_out(interval: ForecastInterval) -> ForecastIntervalOut:
    return ForecastIntervalOut(
        start=interval.interval_start,
        volume=interval.volume,
        volumeLower=interval.volume_lower,
        volumeUpper=interval.volume_upper,
        ahtS=interval.aht_s,
        requiredRaw=interval.required_raw,
        required=interval.required,
        daysUsed=interval.days_used,
    )
