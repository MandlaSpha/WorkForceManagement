"""Capacity against a fixed workforce (requirement CAP-01; tender: up to 350 agents, 100 permanent
and 250 seasonal). Pure functions: no Django, no clock, no I/O.

The question is how many people must be working AT THE SAME TIME at the busiest moment of a day,
and whether the permanent staff, then the seasonal pool, can cover it. Permanent staff fill first;
seasonal agents cover what is left up to their pool; anything beyond both is overflow.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Split:
    permanent: int  # of the peak, how many permanent staff cover it
    seasonal: int  # how many seasonal agents must be brought in
    overflow: int  # what neither pool can cover: needs overtime, another site or an outsourcer


def split_demand(peak: int, permanent_limit: int, seasonal_limit: int) -> Split:
    """Cover `peak` simultaneous agents from the permanent pool first, then the seasonal pool."""
    if peak < 0 or permanent_limit < 0 or seasonal_limit < 0:
        raise ValueError("peak and limits must not be negative")
    permanent = min(peak, permanent_limit)
    seasonal = min(peak - permanent, seasonal_limit)
    return Split(permanent, seasonal, peak - permanent - seasonal)


def combine(per_queue: Sequence[Sequence[int | None]]) -> list[int | None]:
    """Agents required at each moment across queues: the slot-by-slot sum. A slot where any queue's
    requirement is unknown is unknown, never counted as zero (DAT-10)."""
    if not per_queue:
        return []
    width = len(per_queue[0])
    if any(len(queue) != width for queue in per_queue):
        raise ValueError("every queue must cover the same slots")
    totals: list[int | None] = []
    for slot in range(width):
        values = [queue[slot] for queue in per_queue]
        totals.append(None if any(v is None for v in values) else sum(v for v in values if v))
    return totals


def peak(slots: Sequence[int | None]) -> tuple[int | None, bool]:
    """The busiest known moment, and whether every moment was known. With nothing known there is
    no peak (None); with some unknown the peak is at least this much, so `complete` is False."""
    known = [v for v in slots if v is not None]
    return (max(known) if known else None, len(known) == len(slots) and len(slots) > 0)
