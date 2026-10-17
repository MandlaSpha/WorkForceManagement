"""Workload balance across queues for a day, and suggested moves (requirement WLB-01).

Pure: no Django, no clock, no I/O. A queue's load is what its published forecast needs against
what the roster puts on the phones, over the half-hours where the requirement is known. A queue
well above 1.0 is stretched, well below is slack. A move is only ever a SUGGESTION: a person who is
rostered on a slack queue and has the skill for a stretched one, whose shift would not leave the
slack queue short.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

OVER_RATIO = 1.1  # needs more than 110% of what is scheduled
UNDER_RATIO = 0.8  # needs less than 80% of what is scheduled
STRETCHED, SLACK, BALANCED, UNKNOWN = "stretched", "slack", "balanced", "unknown"


@dataclass(frozen=True, slots=True)
class QueueLoad:
    queue_id: int
    name: str
    required_slots: int  # people-half-hours needed, over half-hours with a known requirement
    scheduled_slots: int  # people-half-hours on the phones over those same half-hours


@dataclass(frozen=True, slots=True)
class Mover:
    """Somebody rostered that day who could work elsewhere."""

    person_id: int
    from_queue_id: int
    skilled_queue_ids: frozenset[int]
    shift_slots: int  # half-hours they put on the phones where they are now


@dataclass(frozen=True, slots=True)
class Suggestion:
    person_id: int
    from_queue_id: int
    to_queue_id: int
    slots: int  # half-hours of cover moved


def load_ratio(load: QueueLoad) -> float | None:
    """Required over scheduled. None when nothing is known to be required; when work is needed and
    nobody is scheduled the ratio is the required half-hours themselves (large, finite)."""
    if load.required_slots <= 0:
        return None
    if load.scheduled_slots <= 0:
        return float(load.required_slots)
    return round(load.required_slots / load.scheduled_slots, 2)


def classify(load: QueueLoad) -> str:
    ratio = load_ratio(load)
    if ratio is None:
        return UNKNOWN
    if ratio > OVER_RATIO:
        return STRETCHED
    if ratio < UNDER_RATIO:
        return SLACK
    return BALANCED


def suggest_moves(loads: Iterable[QueueLoad], movers: Iterable[Mover]) -> list[Suggestion]:
    """Greedy and deterministic: the most stretched queue is helped first, from the sparest slack
    queue's people, and only while the source keeps at least what it needs and the target still
    needs more. Each person is suggested at most once."""
    queues = {q.queue_id: q for q in loads}
    need = {i: q.required_slots - q.scheduled_slots for i, q in queues.items()}  # +short, -spare
    state = {i: classify(q) for i, q in queues.items()}
    pool = sorted(movers, key=lambda m: (m.from_queue_id, m.person_id))
    used: set[int] = set()
    result: list[Suggestion] = []
    stretched = sorted((i for i, s in state.items() if s == STRETCHED), key=lambda i: (-need[i], i))
    for target in stretched:
        candidates = sorted(
            (
                m
                for m in pool
                if m.person_id not in used
                and target in m.skilled_queue_ids
                and state.get(m.from_queue_id) == SLACK
            ),
            key=lambda m: (need[m.from_queue_id], m.person_id),
        )
        for m in candidates:
            if need[target] <= 0:
                break
            if m.shift_slots <= 0 or need[m.from_queue_id] + m.shift_slots > 0:
                continue  # it would leave the source short
            used.add(m.person_id)
            need[target] -= m.shift_slots
            need[m.from_queue_id] += m.shift_slots
            result.append(Suggestion(m.person_id, m.from_queue_id, target, m.shift_slots))
    return result
