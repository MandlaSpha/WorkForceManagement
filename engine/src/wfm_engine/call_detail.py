"""Adding up the per-call detail of the Call Detail Report (DAT-01, tech spec section 4.31).

Pure functions: no Django, no clock, no I/O. The caller (the telephony selectors) reads the rows
the role may see and passes plain facts in; nothing here knows a name, a number or a role.

Honesty rules the figures follow:
- a rate or an average with nothing to rest on is `None`, never zero;
- nothing is ranked: agents come back in login order, queues and days in name and date order;
- ties and ordering never depend on the order of the input.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

_TENTH = Decimal("0.1")
_HUNDRED = Decimal(100)

KIND_TRANSFER = "transfer"
KIND_HOLD = "hold"
KIND_MUTE = "mute"


def _tenth(value: Decimal) -> Decimal:
    return value.quantize(_TENTH, rounding=ROUND_HALF_UP)


def _average(total: int, count: int) -> Decimal | None:
    return _tenth(Decimal(total) / Decimal(count)) if count else None


# --- Ring-no-answer by agent login ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Offer:
    login: str
    answered: bool
    ring_s: int | None


@dataclass(frozen=True, slots=True)
class AgentRing:
    login: str
    offers: int
    answered: int
    ring_no_answer: int
    ring_no_answer_pct: Decimal | None  # of offers; None when there were none
    avg_ring_s: Decimal | None  # over offers whose ring time is known; None when none are


def ring_by_agent(offers: Iterable[Offer]) -> list[AgentRing]:
    """One row per login, in login order (not ranked)."""
    count: dict[str, int] = defaultdict(int)
    answered: dict[str, int] = defaultdict(int)
    ring_sum: dict[str, int] = defaultdict(int)
    ring_n: dict[str, int] = defaultdict(int)
    for o in offers:
        count[o.login] += 1
        if o.answered:
            answered[o.login] += 1
        if o.ring_s is not None:
            ring_sum[o.login] += o.ring_s
            ring_n[o.login] += 1
    rows: list[AgentRing] = []
    for login in sorted(count):
        missed = count[login] - answered[login]
        rows.append(
            AgentRing(
                login=login,
                offers=count[login],
                answered=answered[login],
                ring_no_answer=missed,
                ring_no_answer_pct=_tenth(Decimal(missed) * _HUNDRED / Decimal(count[login])),
                avg_ring_s=_average(ring_sum[login], ring_n[login]),
            )
        )
    return rows


# --- IVR: calls per menu step and where callers dropped off ---------------------------------------


@dataclass(frozen=True, slots=True)
class IvrStep:
    step: int
    digit: str
    activity: str


@dataclass(frozen=True, slots=True)
class IvrCall:
    queue: str
    steps: tuple[IvrStep, ...]
    reached_queue: bool  # the call was put in the queue after the IVR
    abandoned: bool  # the call ended as abandoned


@dataclass(frozen=True, slots=True)
class IvrStepTotal:
    step: int
    digit: str
    activity: str
    calls: int  # calls that went through this step
    ended_here: int  # calls whose last step was this one and that never reached the queue


@dataclass(frozen=True, slots=True)
class IvrQueue:
    queue: str
    calls: int  # calls with at least one IVR step
    reached_queue: int
    ended_in_ivr: int  # never reached the queue: dropped off inside the IVR
    abandoned_after_ivr: int  # reached the queue and were abandoned there
    steps: list[IvrStepTotal]


def ivr_by_queue(calls: Iterable[IvrCall]) -> list[IvrQueue]:
    """One row per queue (name order) with its menu steps in step order. Calls with no IVR step
    are not IVR calls and are left out."""
    by_queue: dict[str, list[IvrCall]] = defaultdict(list)
    for c in calls:
        if c.steps:
            by_queue[c.queue].append(c)
    result: list[IvrQueue] = []
    for queue in sorted(by_queue):
        group = by_queue[queue]
        seen: dict[tuple[int, str, str], int] = defaultdict(int)
        ended: dict[tuple[int, str, str], int] = defaultdict(int)
        for c in group:
            for key in {(s.step, s.digit, s.activity) for s in c.steps}:
                seen[key] += 1
            if not c.reached_queue:
                last = max(c.steps, key=lambda s: s.step)
                ended[(last.step, last.digit, last.activity)] += 1
        result.append(
            IvrQueue(
                queue=queue,
                calls=len(group),
                reached_queue=sum(1 for c in group if c.reached_queue),
                ended_in_ivr=sum(1 for c in group if not c.reached_queue),
                abandoned_after_ivr=sum(1 for c in group if c.reached_queue and c.abandoned),
                steps=[
                    IvrStepTotal(k[0], k[1], k[2], seen[k], ended[k])
                    for k in sorted(seen, key=lambda k: (k[0], k[1], k[2]))
                ],
            )
        )
    return result


# --- Transfers, holds and mutes -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EventFact:
    queue: str
    day: date
    kind: str  # KIND_TRANSFER, KIND_HOLD or KIND_MUTE
    duration_s: int | None  # talk time of a transfer, length of a hold or a mute
    answer_s: int | None = None  # transfers only: seconds until the other end answered


@dataclass(frozen=True, slots=True)
class EventRow:
    queue: str
    day: date | None  # None on a per-queue total
    transfers: int
    avg_transfer_s: Decimal | None
    avg_transfer_answer_s: Decimal | None
    holds: int
    avg_hold_s: Decimal | None
    mutes: int
    avg_mute_s: Decimal | None


def event_summary(
    facts: Iterable[EventFact], *, by_day: bool, queues: Iterable[str] = ()
) -> list[EventRow]:
    """Counts and average durations per queue (and per day when `by_day`). `queues` are always
    listed on a per-queue total, with zero counts, so "none happened" is not a missing row."""
    groups: dict[tuple[str, date | None], list[EventFact]] = defaultdict(list)
    for fact in facts:
        groups[(fact.queue, fact.day if by_day else None)].append(fact)
    if not by_day:
        for q in queues:
            groups.setdefault((q, None), [])

    def avg(rows: list[EventFact], kind: str, field: str = "duration_s") -> Decimal | None:
        values = [
            getattr(r, field) for r in rows if r.kind == kind and getattr(r, field) is not None
        ]
        return _average(sum(values), len(values))

    out: list[EventRow] = []
    for queue, day in sorted(groups, key=lambda k: (k[0], k[1] or date.min)):
        rows = groups[(queue, day)]
        out.append(
            EventRow(
                queue=queue,
                day=day,
                transfers=sum(1 for r in rows if r.kind == KIND_TRANSFER),
                avg_transfer_s=avg(rows, KIND_TRANSFER),
                avg_transfer_answer_s=avg(rows, KIND_TRANSFER, "answer_s"),
                holds=sum(1 for r in rows if r.kind == KIND_HOLD),
                avg_hold_s=avg(rows, KIND_HOLD),
                mutes=sum(1 for r in rows if r.kind == KIND_MUTE),
                avg_mute_s=avg(rows, KIND_MUTE),
            )
        )
    return out


# --- Incident links -------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IncidentFact:
    queue: str
    call_key: int  # identifies the call, so two dispositions of one call count it once
    incident_ref: str


@dataclass(frozen=True, slots=True)
class IncidentQueue:
    queue: str
    calls_with_incident: int
    incidents: list[str]  # distinct, upper case, sorted


def incident_links(facts: Iterable[IncidentFact]) -> list[IncidentQueue]:
    """Per queue: how many calls carried an incident number, and which numbers. A blank reference
    is no link. A number seen on several calls is listed once."""
    calls: dict[str, set[int]] = defaultdict(set)
    refs: dict[str, set[str]] = defaultdict(set)
    for f in facts:
        ref = f.incident_ref.strip().upper()
        if not ref:
            continue
        calls[f.queue].add(f.call_key)
        refs[f.queue].add(ref)
    return [IncidentQueue(q, len(calls[q]), sorted(refs[q])) for q in sorted(calls)]
