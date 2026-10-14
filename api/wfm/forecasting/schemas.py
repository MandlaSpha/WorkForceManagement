from __future__ import annotations

from datetime import date, datetime
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
