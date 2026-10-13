"""Service KPIs from interval totals (tech spec section 4.1).

Definitions, pinned by reconciling the real May and July reports to the deck:
- Only INBOUND calls count. Outbound calls and transfers legs are other work.
- Offered = inbound calls; Answered = status "Agent"; Abandoned = status "Abandoned".
- Service level = answered within the threshold / OFFERED (not / answered).
- ASA = mean queue wait of answered calls.
- AHT = mean of (agent talk time + disposition/wrap time) of answered calls.

Totals add up, so the same formulas serve one call, one 30-minute interval, a queue, or a month.
A ratio with nothing to divide by is None, never 0: "no data" must not read as "perfect".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .cdr import INBOUND, STATUS_ABANDONED, STATUS_ANSWERED

DEFAULT_SL_THRESHOLD_S = 20
INTERVAL_MINUTES = 30


@dataclass(frozen=True, slots=True)
class Totals:
    offered: int = 0
    answered: int = 0
    abandoned: int = 0
    answered_in_sl: int = 0
    sum_wait_s: int = 0  # queue wait of answered calls
    sum_handle_s: int = 0  # talk + wrap of answered calls

    def __add__(self, other: Totals) -> Totals:
        return Totals(
            self.offered + other.offered,
            self.answered + other.answered,
            self.abandoned + other.abandoned,
            self.answered_in_sl + other.answered_in_sl,
            self.sum_wait_s + other.sum_wait_s,
            self.sum_handle_s + other.sum_handle_s,
        )


@dataclass(frozen=True, slots=True)
class Kpis:
    offered: int
    answered: int
    abandoned: int
    abandon_pct: float | None
    service_level_pct: float | None
    asa_s: float | None
    aht_s: float | None


def totals_for_call(
    *,
    call_type: str,
    status: str,
    wait_s: int | None,
    handle_s: int | None,
    sl_threshold_s: int = DEFAULT_SL_THRESHOLD_S,
) -> Totals:
    """What one call adds to the totals. Anything that is not an inbound call adds nothing."""
    if call_type != INBOUND:
        return Totals()
    if status == STATUS_ANSWERED:
        wait = wait_s or 0
        return Totals(
            offered=1,
            answered=1,
            answered_in_sl=1 if wait <= sl_threshold_s else 0,
            sum_wait_s=wait,
            sum_handle_s=handle_s or 0,
        )
    if status == STATUS_ABANDONED:
        return Totals(offered=1, abandoned=1)
    # An inbound call that was neither answered nor abandoned (for example a failover) was still
    # offered to the queue.
    return Totals(offered=1)


def _ratio(numerator: float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def kpis(totals: Totals) -> Kpis:
    return Kpis(
        offered=totals.offered,
        answered=totals.answered,
        abandoned=totals.abandoned,
        abandon_pct=_scaled(_ratio(totals.abandoned, totals.offered)),
        service_level_pct=_scaled(_ratio(totals.answered_in_sl, totals.offered)),
        asa_s=_ratio(totals.sum_wait_s, totals.answered),
        aht_s=_ratio(totals.sum_handle_s, totals.answered),
    )


def _scaled(ratio: float | None) -> float | None:
    return None if ratio is None else ratio * 100


def interval_start(moment: datetime, minutes: int = INTERVAL_MINUTES) -> datetime:
    """The start of the interval a moment falls in (30-minute grid by default)."""
    if minutes <= 0 or 60 % minutes != 0:
        raise ValueError("interval length must divide an hour")
    floored = moment.minute - moment.minute % minutes
    return moment.replace(minute=floored, second=0, microsecond=0)
