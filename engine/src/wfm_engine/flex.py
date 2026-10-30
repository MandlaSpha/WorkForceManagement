"""Cross-queue flexing: borrow a multi-skilled person from a queue that can spare them (SCH-09).

Pure: no Django, no clock, no I/O. For one queue that is short, each candidate is someone already
rostered on another queue (the donor) who is also skilled on this one. Moving their shift across
closes the half-hours where this queue is short. A move is only offered when the donor can spare
them for the whole shift: every half-hour of it must have a known requirement and keep at least
that many people without them. Unknown is not spare, so nothing is claimed about it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, time

from .roster import SlotKey, shift_slots


@dataclass(frozen=True)
class Candidate:
    """A shift on a donor queue that someone skilled on the short queue is working."""

    person_id: int
    donor_queue_id: int
    day: date
    template_id: int
    start: time
    end: time


@dataclass(frozen=True)
class Donor:
    required: Mapping[SlotKey, int | None]
    covered: Mapping[SlotKey, int]


@dataclass(frozen=True)
class Flex:
    person_id: int
    donor_queue_id: int
    day: date
    template_id: int
    closes: int  # people-half-hours no longer short on the borrowing queue
    adds_over: int  # half-hours that would then have one person too many there


def _spare(donor: Donor, slots: Sequence[SlotKey]) -> bool:
    for slot in slots:
        need = donor.required.get(slot)
        if need is None or donor.covered.get(slot, 0) - 1 < need:
            return False
    return True


def suggest(
    required: Mapping[SlotKey, int | None],
    covered: Mapping[SlotKey, int],
    donors: Mapping[int, Donor],
    candidates: Sequence[Candidate],
    limit: int = 10,
) -> list[Flex]:
    """Ranked moves that close the short queue's gaps without leaving a donor short."""
    here: Counter[SlotKey] = Counter(covered)
    found: list[Flex] = []
    for c in candidates:
        donor = donors.get(c.donor_queue_id)
        if donor is None:
            continue
        slots = shift_slots(c.day, c.start, c.end)
        if not _spare(donor, slots):
            continue
        closes = adds_over = 0
        for slot in slots:
            need = required.get(slot)
            if need is None:
                continue
            if here.get(slot, 0) < need:
                closes += 1
            else:
                adds_over += 1
        if closes <= 0 or closes <= adds_over:
            continue
        found.append(Flex(c.person_id, c.donor_queue_id, c.day, c.template_id, closes, adds_over))
    found.sort(key=lambda f: (-(f.closes - f.adds_over), f.day, f.template_id, f.person_id))
    return found[:limit]
