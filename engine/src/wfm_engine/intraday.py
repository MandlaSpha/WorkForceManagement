"""Intraday: re-forecast the rest of the day from the calls so far, and flag half-hours where the
people scheduled fall short of the people needed (requirements INT-02, INT-03).

Pure: no Django, no clock, no I/O. The caller says how many half-hours of the day are over
(`elapsed`) and which of them have call data; a half-hour with no data is unknown, never zero.
"""

from __future__ import annotations

from collections.abc import Collection, Hashable, Mapping, Sequence
from dataclasses import dataclass

from .roster import check_activity

# How many calls of agreement with the forecast the estimate starts from, so a handful of early
# calls cannot swing the rest of the day. 30 means 30 calls of evidence weigh as much as the prior.
PRIOR_CALLS = 30.0
MIN_RATIO, MAX_RATIO = 0.5, 2.0
CRITICAL_SHORT = 2  # this many people short, or a quarter of the requirement, is critical
CRITICAL_SHARE = 0.25


@dataclass(frozen=True, slots=True)
class Reforecast:
    ratio: float | None  # actual over forecast so far, steadied; None with no data to go on
    volumes: list[float]  # per half-hour: actual where it is over, forecast x ratio where it is not
    basis_calls: int  # calls in the half-hours the ratio was learned from


@dataclass(frozen=True, slots=True)
class Alert:
    slot: int
    scheduled: int
    required: int
    short: int
    severity: str  # warning or critical


def reforecast(
    forecast: Sequence[float],
    actual: Sequence[int | None],
    elapsed: int,
    prior_calls: float = PRIOR_CALLS,
) -> Reforecast:
    """Scale what is left of the day by how the day has gone so far.

    The ratio is (actual + prior) / (forecast + prior) over the finished half-hours that have data,
    kept between 0.5 and 2 so a strange morning cannot produce an absurd afternoon.
    """
    if len(forecast) != len(actual):
        raise ValueError("forecast and actual must cover the same half-hours")
    known = [i for i in range(min(elapsed, len(forecast))) if actual[i] is not None]
    seen = float(sum(actual[i] or 0 for i in known))
    expected = float(sum(forecast[i] for i in known))
    if not known:
        return Reforecast(None, list(forecast), 0)
    ratio = max(MIN_RATIO, min(MAX_RATIO, (seen + prior_calls) / (expected + prior_calls)))
    volumes = [
        float(actual[i] or 0) if i < elapsed and actual[i] is not None else forecast[i] * ratio
        for i in range(len(forecast))
    ]
    # A finished half-hour with no data keeps its forecast: unknown is not zero, and not scaled.
    volumes = [
        forecast[i] if i < elapsed and actual[i] is None else volumes[i]
        for i in range(len(volumes))
    ]
    return Reforecast(ratio, volumes, int(seen))


def alerts(scheduled: Sequence[int], required: Sequence[int | None], elapsed: int) -> list[Alert]:
    """The half-hours still to come where fewer people are scheduled than needed. A requirement
    that is not known raises nothing: no claim is made about it."""
    if len(scheduled) != len(required):
        raise ValueError("scheduled and required must cover the same half-hours")
    found: list[Alert] = []
    for slot in range(max(0, elapsed), len(scheduled)):
        need = required[slot]
        if need is None or scheduled[slot] >= need:
            continue
        short = need - scheduled[slot]
        critical = short >= CRITICAL_SHORT or short / need >= CRITICAL_SHARE
        found.append(
            Alert(slot, scheduled[slot], need, short, "critical" if critical else "warning")
        )
    return found


def break_targets[K: Hashable](
    keys: Sequence[K],
    activity: tuple[int, int],
    others: Collection[tuple[int, int]],
    scheduled: Mapping[K, int],
    required: Mapping[K, int | None],
) -> list[int]:
    """Where inside a shift an activity could move so the phones stay covered (INT-04).

    `keys` names each half-hour of the shift in order; `activity` is (offset, length) in those
    half-hours and `others` the shift's other activities. `scheduled` is people on the phones in
    each half-hour NOW, with this person already counted out of their activity's half-hours.
    A new place is offered when it stays inside the shift, overlaps no other activity, and in
    every half-hour it takes the person off the phones the cover afterwards still reaches the
    requirement. A half-hour whose requirement is unknown is never offered (cover cannot be
    shown). Returns offsets, the nearest to the current place first (earlier first on a tie);
    the current place is not offered.
    """
    offset, length = activity
    here = {keys[i] for i in range(offset, offset + length)}
    found: list[int] = []
    for new in range(0, len(keys) - length + 1):
        if new == offset:
            continue
        if check_activity_overlap(len(keys), (new, length), others):
            continue
        ok = True
        for i in range(new, new + length):
            key = keys[i]
            need = required.get(key)
            after = scheduled.get(key, 0) - (0 if key in here else 1)
            if need is None or after < need:
                ok = False
                break
        if ok:
            found.append(new)
    return sorted(found, key=lambda n: (abs(n - offset), n))


def check_activity_overlap(
    shift_length: int, activity: tuple[int, int], others: Collection[tuple[int, int]]
) -> bool:
    """True when the activity does not fit: outside the shift or on top of another one."""
    return check_activity(shift_length, activity, others) is not None
