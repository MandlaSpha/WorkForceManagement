from __future__ import annotations

from datetime import date

from ninja import Schema

# camelCase on the wire; the noqa comments mark that deliberate choice.


class WorkImportOut(Schema):
    created: int
    updated: int
    unchanged: int
    rejected: dict[str, int]  # reason -> rows; never the rows themselves
    ignoredColumns: list[str]  # noqa: N815 - columns in the file that were not read or stored


class PoolIn(Schema):
    productiveMinutesPerDay: int  # noqa: N815


class PoolDemandOut(Schema):
    poolId: int  # noqa: N815
    pool: str
    productiveMinutesPerDay: int  # noqa: N815
    settingsConfirmed: bool  # noqa: N815 - false while the productive time is the default
    openCount: int  # noqa: N815
    breached: int  # open and past its deadline when the period starts
    backlogMin: int  # noqa: N815 - estimated effort of everything open
    dueMin: int  # noqa: N815 - effort that must be finished within the period
    arrivingMin: float | None  # noqa: N815 - expected new effort in the period; none when unknown
    unestimated: int  # open items with no effort estimate
    noDeadline: int  # noqa: N815 - open items with no deadline
    requiredFte: float | None  # noqa: N815
    complete: bool  # false when an estimate or the arrival rate is missing: a minimum


class DemandOut(Schema):
    asOf: date  # noqa: N815
    days: int
    workingDays: int  # noqa: N815
    pools: list[PoolDemandOut]
    requiredFte: float | None  # noqa: N815 - the pools added up; none when no pool has a figure
    backlogMin: int  # noqa: N815
    arrivingMin: float | None  # noqa: N815
    breached: int
    complete: bool
