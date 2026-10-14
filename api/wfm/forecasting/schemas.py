from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from ninja import Field, Schema


class RunForecastIn(Schema):
    queueId: int  # noqa: N815 - camelCase on the wire
    dateFrom: date  # noqa: N815
    dateTo: date  # noqa: N815
    label: str = Field("", max_length=100)
    # "prophet" is used only where it beats the baseline on past days (ADR 0002).
    method: Literal["baseline", "prophet"] = "baseline"


class ForecastVersionOut(Schema):
    id: UUID
    queueId: int  # noqa: N815
    queue: str
    label: str
    status: str
    method: str
    dateFrom: date  # noqa: N815
    dateTo: date  # noqa: N815
    createdAt: datetime  # noqa: N815
    createdBy: str  # noqa: N815
    publishedAt: datetime | None  # noqa: N815
    intervalCount: int  # noqa: N815
    assumptionsConfirmed: bool  # noqa: N815 - false while the staffing settings are defaults
    fallback: dict[str, Any] | None  # why Prophet was asked for but not used
    daysWithoutHistory: list[str]  # noqa: N815 - days that could not be forecast
    historyThrough: str | None  # noqa: N815 - newest day of call data the forecast could use
    params: dict[str, Any]


class ForecastIntervalOut(Schema):
    start: datetime
    volume: float
    volumeLower: float | None  # noqa: N815 - bottom of the 80% range, Prophet only
    volumeUpper: float | None  # noqa: N815
    ahtS: float | None  # noqa: N815
    requiredRaw: int | None  # noqa: N815 - agents on the phone
    required: int | None  # agents to roster, shrinkage included
    daysUsed: int  # noqa: N815 - how many past days this interval rests on


class DayAccuracyOut(Schema):
    date: date
    accuracyPct: float | None  # noqa: N815 - per half-hour
    dailyAccuracyPct: float | None  # noqa: N815 - the day's total calls
    daysUsed: int  # noqa: N815


class AccuracyOut(Schema):
    queueId: int  # noqa: N815
    queue: str
    overallAccuracyPct: float | None  # noqa: N815 - per half-hour
    overallDailyAccuracyPct: float | None  # noqa: N815 - per day total
    weeks: int
    decay: float
    days: list[DayAccuracyOut]


class EventIn(Schema):
    name: str = Field(..., max_length=100)
    queueId: int | None = None  # noqa: N815 - none means every queue
    dateFrom: date  # noqa: N815
    dateTo: date  # noqa: N815
    upliftPct: Decimal  # noqa: N815 - +20 is a fifth more calls, -100 is none


class EventOut(Schema):
    id: int
    name: str
    queueId: int | None  # noqa: N815
    queue: str | None
    dateFrom: date  # noqa: N815
    dateTo: date  # noqa: N815
    upliftPct: float  # noqa: N815


class ScenarioIn(Schema):
    versionId: UUID  # noqa: N815 - the forecast to ask "what if" about
    volumeChangePct: float = 0  # noqa: N815 - +20 is a fifth more calls
    ahtChangePct: float = 0  # noqa: N815 - +10 is calls taking a tenth longer
    shrinkagePct: float | None = None  # noqa: N815 - none keeps the forecast's own
    slTargetPct: float | None = None  # noqa: N815


class ScenarioAssumptionsOut(Schema):
    slTargetPct: float  # noqa: N815
    slThresholdS: int  # noqa: N815
    occupancyCeilingPct: float  # noqa: N815
    shrinkagePct: float  # noqa: N815


class ScenarioDayOut(Schema):
    day: date
    callsBase: float  # noqa: N815
    callsScenario: float  # noqa: N815
    peakBase: int | None  # noqa: N815 - most agents to roster at once
    peakScenario: int | None  # noqa: N815
    hoursBase: float  # noqa: N815 - agent-hours to roster over the day
    hoursScenario: float  # noqa: N815
    complete: bool  # false: some half-hour with calls could not be staffed, figures are minimums


class ScenarioOut(Schema):
    versionId: UUID  # noqa: N815
    queue: str
    base: ScenarioAssumptionsOut
    scenario: ScenarioAssumptionsOut
    days: list[ScenarioDayOut]
