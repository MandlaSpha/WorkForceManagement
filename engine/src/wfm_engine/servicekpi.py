"""Service metrics from imported ticket data (requirement KPI-01).

Pure: no Django, no clock, no I/O. Cost per ticket is NOT computed here: it is priced from pay and
lives in `wfm_engine.utilisation.ticket_cost`, so the money rules exist once.

Definitions, shown on the screen as well:
- The period's tickets are those CLOSED inside it (`closed_at` in [start, end)).
- MTTR = mean hours from opened to closed of those tickets.
- FCR % = tickets flagged resolved at first contact over those that carry a flag.
- CSAT = mean of the 1 to 5 ratings, and the share rated 4 or 5 ("satisfied").
- NPS = share of promoters (9 or 10) less share of detractors (0 to 6) among the 0 to 10 answers,
  from -100 to 100.
- Backlog = tickets open at `as_of` (opened by then, not yet closed). Age is in days from opening.
A ratio with nothing to divide by is None, never 0, so "no survey answers" never reads as "0".
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

PROMOTER_MIN = 9
DETRACTOR_MAX = 6
SATISFIED_MIN = 4
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86_400


@dataclass(frozen=True, slots=True)
class Ticket:
    opened_at: datetime
    closed_at: datetime | None
    first_contact_resolved: bool | None
    csat: int | None
    nps: int | None


@dataclass(frozen=True, slots=True)
class ServiceKpis:
    closed: int
    mttr_h: float | None
    fcr_known: int
    fcr_pct: float | None
    csat_count: int
    csat_average: float | None
    csat_satisfied_pct: float | None
    nps_count: int
    nps: float | None
    backlog_count: int
    backlog_avg_age_days: float | None
    backlog_median_age_days: float | None
    backlog_oldest_age_days: float | None


def _pct(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def kpis(
    tickets: Iterable[Ticket], *, period_start: datetime, period_end: datetime, as_of: datetime
) -> ServiceKpis:
    items = list(tickets)
    done = [
        t for t in items if t.closed_at is not None and period_start <= t.closed_at < period_end
    ]
    spans = [(t.closed_at - t.opened_at).total_seconds() for t in done if t.closed_at]
    flagged = [t.first_contact_resolved for t in done if t.first_contact_resolved is not None]
    ratings = [t.csat for t in done if t.csat is not None]
    answers = [t.nps for t in done if t.nps is not None]
    promoters = sum(1 for a in answers if a >= PROMOTER_MIN)
    detractors = sum(1 for a in answers if a <= DETRACTOR_MAX)
    ages = [
        (as_of - t.opened_at).total_seconds() / SECONDS_PER_DAY
        for t in items
        if t.opened_at <= as_of and (t.closed_at is None or t.closed_at > as_of)
    ]
    return ServiceKpis(
        closed=len(done),
        mttr_h=round(sum(spans) / len(spans) / SECONDS_PER_HOUR, 1) if spans else None,
        fcr_known=len(flagged),
        fcr_pct=_pct(sum(flagged), len(flagged)),
        csat_count=len(ratings),
        csat_average=round(sum(ratings) / len(ratings), 2) if ratings else None,
        csat_satisfied_pct=_pct(sum(1 for r in ratings if r >= SATISFIED_MIN), len(ratings)),
        nps_count=len(answers),
        nps=round(100 * (promoters - detractors) / len(answers), 1) if answers else None,
        backlog_count=len(ages),
        backlog_avg_age_days=round(sum(ages) / len(ages), 1) if ages else None,
        backlog_median_age_days=round(statistics.median(ages), 1) if ages else None,
        backlog_oldest_age_days=round(max(ages), 1) if ages else None,
    )
