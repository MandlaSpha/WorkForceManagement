"""A monthly hiring plan over 12 to 18 months (requirement CAP-01).

Pure: no Django, no clock, no I/O. Given the people needed each month, the people employed now, a
monthly attrition rate and how fast a new hire becomes productive, work out how many to hire each
month so that enough people are fully productive when they are needed.

A hire made in month `h` is paid from `h` but works at `ramp[0]` of full strength in month `h`,
`ramp[1]` the next, and so on until the last ramp value, which must be 1. So a cohort hired for a
month `t` must be hired `len(ramp) - 1` months before it (the "lead time"): months sooner than that
cannot be helped by hiring and are reported as unavoidable shortfalls. Attrition takes the same
share of every group each month. Hires are whole people, rounded up, and planned in the order of
the month they are for, each counting only the groups already planned (a later group that is
partly productive earlier is not counted, so the plan can be slightly generous in ramp-up months).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass

MIN_MONTHS, MAX_MONTHS = 12, 18
_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class Month:
    index: int  # 0 is the first month of the plan
    required: float  # people needed, fully productive
    headcount: float  # people employed this month, new hires included
    hires: int  # people hired this month
    effective: float  # people's worth of work, with new hires part-way up the ramp
    gap: float  # effective minus required: negative is a shortfall
    unavoidable: bool  # a shortfall no hire could have prevented (inside the lead time)


def validate(
    required: Sequence[float], incumbents: float, attrition: float, ramp: Sequence[float]
) -> None:
    if not MIN_MONTHS <= len(required) <= MAX_MONTHS:
        raise ValueError("a plan covers 12 to 18 months")
    if any(r < 0 for r in required):
        raise ValueError("people needed cannot be negative")
    if incumbents < 0:
        raise ValueError("incumbents cannot be negative")
    if not 0 <= attrition < 1:
        raise ValueError("attrition is a share between 0 and under 1")
    if not ramp or any(not 0 <= r <= 1 for r in ramp) or abs(ramp[-1] - 1) > _EPS:
        raise ValueError("the ramp runs from 0 to 1 and ends at 1")
    if any(b < a for a, b in itertools.pairwise(ramp)):
        raise ValueError("a new hire does not get less productive with time")
    if len(ramp) - 1 >= len(required):
        raise ValueError("the ramp is longer than the plan")


def plan(
    required: Sequence[float],
    incumbents: float,
    attrition: float,
    ramp: Sequence[float],
) -> list[Month]:
    validate(required, incumbents, attrition, ramp)
    months = len(required)
    lead = len(ramp) - 1
    keep = 1 - attrition
    hires = [0] * months

    def survivors(size: float, hired: int, month: int) -> float:
        return size * keep ** (month - hired)

    def effective_at(month: int, upto: int) -> float:
        total = incumbents * keep**month
        for h in range(min(upto, month + 1)):
            if hires[h]:
                total += survivors(hires[h], h, month) * ramp[min(month - h, lead)]
        return total

    for h in range(months):
        target = h + lead
        if target >= months:
            break  # it would only be productive after the plan ends
        shortfall = required[target] - effective_at(target, h)
        if shortfall > _EPS:
            hires[h] = math.ceil(shortfall / keep**lead - _EPS)

    rows: list[Month] = []
    for m in range(months):
        headcount = incumbents * keep**m + sum(
            survivors(hires[h], h, m) for h in range(m + 1) if hires[h]
        )
        eff = effective_at(m, m + 1)
        gap = eff - required[m]
        rows.append(Month(m, required[m], headcount, hires[m], eff, gap, gap < -_EPS and m < lead))
    return rows
