from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from ninja import Schema


class QueueOut(Schema):
    id: int
    name: str
    confirmed: bool


class ImportOut(Schema):
    id: UUID
    fileName: str  # noqa: N815 - camelCase on the wire
    createdAt: datetime  # noqa: N815
    uploadedBy: str  # noqa: N815 - display name of the person who imported it
    sourceTimezone: str  # noqa: N815
    periodStart: datetime  # noqa: N815
    periodEnd: datetime  # noqa: N815
    rowsRead: int  # noqa: N815
    rowsInserted: int  # noqa: N815
    rowsDuplicate: int  # noqa: N815
    rowsRejected: int  # noqa: N815
    rejectedSummary: dict[str, int]  # noqa: N815 - reason code to count, never cell values
    warnings: dict[str, int]  # calls kept with one unusable cell cleared, by reason code
    sheetsIgnored: list[str]  # noqa: N815
    reconciles: bool
    reconciliation: dict[str, Any]


class MonthsOut(Schema):
    """The calendar months (`YYYY-MM`, South African time) that have call data, oldest first.
    Empty when nothing has been imported or none of it is visible to the role."""

    months: list[str]


class Coverage(Schema):
    intervalsUsed: int  # noqa: N815
    intervalsTotal: int  # noqa: N815


class Metric(Schema):
    """DAT-10: a figure always says whether it was measured and what it rests on."""

    value: float | None
    basis: Literal["measured"]
    coverage: Coverage


class QueueKpisOut(Schema):
    queueId: int | None  # noqa: N815 - null for the all-queues total
    queue: str
    confirmed: bool
    offered: int
    answered: int
    abandoned: int
    abandonPct: Metric  # noqa: N815
    serviceLevelPct: Metric  # noqa: N815
    asaS: Metric  # noqa: N815
    ahtS: Metric  # noqa: N815


class KpiOut(Schema):
    dateFrom: str  # noqa: N815
    dateTo: str  # noqa: N815
    slThresholdS: int  # noqa: N815
    total: QueueKpisOut
    queues: list[QueueKpisOut]
