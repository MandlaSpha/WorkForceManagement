"""Utilisation, billability and cost of engineer time (requirements UTL-01, UTL-02).

Pure: no Django, no clock, no I/O. Hours are worked out from minutes; money is Decimal and rounded
half up to the cent only at the end.

Worked time is the paid time of the shifts on the published roster. Billable time is the part of
it spent on a queue that a contract holds, less the time inside the shift given to anything other
than customer work. That is a MODEL of billing, not a timesheet, and the callers say so (DAT-10).
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
MINUTES_PER_HOUR = Decimal(60)


@dataclass(frozen=True, slots=True)
class Block:
    """A stretch of one person's work: how much was worked, how much of it is billable, and the
    utilisation target of the contract it was done under (None: no contract, so no target)."""

    worked_min: int
    billable_min: int
    target_pct: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Utilisation:
    worked_min: int
    billable_min: int
    utilisation_pct: float | None  # None when nothing was worked
    target_pct: float | None  # weighted by worked time under each contract; None without one
    gap_pct: float | None  # utilisation less target, in percentage points; negative is short


def utilisation(blocks: Iterable[Block]) -> Utilisation:
    """Worked against billable hours for a group. The target is the average of the contract
    targets weighted by the worked time under each, so a team on two contracts has a blend."""
    worked = billable = 0
    weight = 0
    weighted = Decimal(0)
    for block in blocks:
        if block.billable_min < 0 or block.billable_min > block.worked_min:
            raise ValueError("billable time cannot be negative or exceed worked time")
        worked += block.worked_min
        billable += block.billable_min
        if block.target_pct is not None:
            weight += block.worked_min
            weighted += block.target_pct * block.worked_min
    pct = round(100 * billable / worked, 1) if worked else None
    target = round(float(weighted / weight), 1) if weight else None
    gap = round(pct - target, 1) if pct is not None and target is not None else None
    return Utilisation(worked, billable, pct, target, gap)


def billable_minutes(worked_min: int, *, on_contract: bool, non_billable_min: int) -> int:
    """Billable part of a shift: none when the queue is not under a contract, else the paid time
    less activities that are not customer work, never below zero."""
    if worked_min < 0 or non_billable_min < 0:
        raise ValueError("minutes cannot be negative")
    return max(worked_min - non_billable_min, 0) if on_contract else 0


def cost_of(hourly_rate: Decimal, minutes: int) -> Decimal:
    """Rands for `minutes` at an hourly rate, to the cent."""
    if hourly_rate < 0 or minutes < 0:
        raise ValueError("rate and minutes cannot be negative")
    return (hourly_rate * minutes / MINUTES_PER_HOUR).quantize(CENT, rounding=ROUND_HALF_UP)


def allocate[K: Hashable](total: Decimal, shares: Mapping[K, int]) -> dict[K, Decimal]:
    """Split `total` rands across keys in proportion to their minutes so the parts add up to the
    total exactly: each part is rounded down to the cent and the leftover cents go, one each, to
    the largest remainders. No shares means nothing is allocated."""
    weight = sum(shares.values())
    if weight <= 0 or total == 0:
        return {key: Decimal("0.00") for key in shares}
    exact = {key: total * n / weight for key, n in shares.items()}
    parts = {key: value.quantize(CENT, rounding=ROUND_DOWN) for key, value in exact.items()}
    left = round((total - sum(parts.values())) / CENT)
    by_remainder = sorted(shares, key=lambda k: exact[k] - parts[k], reverse=True)
    for key in by_remainder[: max(left, 0)]:
        parts[key] += CENT
    return parts


def blended_hourly_rate(rates: Iterable[Decimal]) -> Decimal | None:
    """The plain average of the hourly rates known; None when none is known."""
    known = list(rates)
    return sum(known, Decimal(0)) / len(known) if known else None


@dataclass(frozen=True, slots=True)
class TicketCost:
    closed: int
    estimated: int  # closed items that carry an effort estimate
    effort_min: int
    cost: Decimal | None  # effort priced at the blended rate; None without a rate or an estimate
    per_ticket: Decimal | None  # over the estimated items only


def ticket_cost(efforts_min: Iterable[int | None], rate: Decimal | None) -> TicketCost:
    """Cost of closed tickets priced from their effort at one blended hourly rate. Items with no
    estimate are counted but cannot be priced, and are left out of the per-ticket average."""
    items = list(efforts_min)
    known = [e for e in items if e is not None]
    effort = sum(known)
    if rate is None or not known:
        return TicketCost(len(items), len(known), effort, None, None)
    cost = cost_of(rate, effort)
    per_ticket = (cost / len(known)).quantize(CENT, rounding=ROUND_HALF_UP)
    return TicketCost(len(items), len(known), effort, cost, per_ticket)


def share_pct(part: Decimal, whole: Decimal | None) -> float | None:
    """`part` as a percentage of `whole`, one decimal; None when there is no whole to compare to."""
    if whole is None or whole <= 0:
        return None
    return round(float(100 * part / whole), 1)
