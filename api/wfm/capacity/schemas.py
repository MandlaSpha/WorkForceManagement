from __future__ import annotations

from datetime import date

from ninja import Schema

# camelCase on the wire; the noqa comments mark that deliberate choice.


class LimitsIn(Schema):
    permanentLimit: int  # noqa: N815
    seasonalLimit: int  # noqa: N815


class LimitsOut(Schema):
    permanentLimit: int  # noqa: N815
    seasonalLimit: int  # noqa: N815
    confirmed: bool  # false while they are the tender's figures nobody has confirmed


class CapacityDayOut(Schema):
    day: date
    queuesCovered: int  # noqa: N815 - queues with a published forecast for this day
    queuesTotal: int  # noqa: N815
    peak: int | None  # most agents needed at the same moment; none when nothing is forecast
    complete: bool  # false when a queue or a half-hour is missing, so the peak is a minimum
    permanent: int | None
    seasonal: int | None
    overflow: int | None
    permanentOnBooks: int  # noqa: N815 - permanent staff employed that day
    seasonalOnBooks: int  # noqa: N815 - seasonal agents already engaged for that day
    seasonalToHire: int | None  # noqa: N815 - seasonal agents still to find


class CapacityWeekOut(Schema):
    weekStart: date  # noqa: N815
    peak: int | None
    peakDay: date | None  # noqa: N815
    seasonalPeak: int | None  # noqa: N815
    overflowDays: int  # noqa: N815
    daysForecast: int  # noqa: N815 - days of the week that have any forecast
    daysIncomplete: int  # noqa: N815
    days: list[CapacityDayOut]


class CapacityOut(Schema):
    limits: LimitsOut
    weeks: list[CapacityWeekOut]
