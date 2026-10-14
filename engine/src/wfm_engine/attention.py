"""What needs a planner's attention this week (the dashboard's "needs attention" list).

Plain rules over facts about each queue's week; no AI, nothing hidden. Pure functions: no Django, no
clock, no I/O. Each item says what is wrong, for which queue and how bad it is, and carries a
`kind` so the screen can link to where it is fixed.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

CRITICAL_SHARE = 0.25  # a quarter or more of the known half-hours short is critical

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


@dataclass(frozen=True, slots=True)
class QueueWeek:
    """The facts about one queue's week that the rules look at."""

    queue_id: int
    queue: str
    has_forecast: bool  # a published forecast covers (any of) the week
    assumptions_confirmed: bool
    intervals_known: int  # half-hours with a known requirement
    under_intervals: int  # of those, how many are under-staffed
    scheduled_total: int  # people-half-hours rostered
    roster_published: bool


@dataclass(frozen=True, slots=True)
class Item:
    severity: str  # critical, warning or info
    kind: str  # understaffed, no_forecast, assumptions or draft_roster
    queue_id: int
    queue: str
    text: str
    count: int  # the number the text is about (0 when it is not a count)


def attention(weeks: Iterable[QueueWeek]) -> list[Item]:
    """The items worth a planner's time, most serious first, biggest first within a severity."""
    items: list[Item] = []
    for week in weeks:
        if not week.has_forecast:
            items.append(
                Item(
                    "warning",
                    "no_forecast",
                    week.queue_id,
                    week.queue,
                    f"{week.queue}: no published forecast for this week, so nothing to staff to",
                    0,
                )
            )
            continue
        if week.under_intervals > 0:
            share = week.under_intervals / week.intervals_known if week.intervals_known else 0
            noun = "interval" if week.under_intervals == 1 else "intervals"
            items.append(
                Item(
                    "critical" if share >= CRITICAL_SHARE else "warning",
                    "understaffed",
                    week.queue_id,
                    week.queue,
                    f"{week.queue}: {week.under_intervals} under-staffed {noun}",
                    week.under_intervals,
                )
            )
        if not week.assumptions_confirmed:
            items.append(
                Item(
                    "info",
                    "assumptions",
                    week.queue_id,
                    week.queue,
                    f"{week.queue}: the staffing assumptions are unconfirmed defaults",
                    0,
                )
            )
        if not week.roster_published and week.scheduled_total > 0:
            items.append(
                Item(
                    "info",
                    "draft_roster",
                    week.queue_id,
                    week.queue,
                    f"{week.queue}: the roster is still a draft",
                    0,
                )
            )
    return sorted(items, key=lambda i: (SEVERITY_ORDER[i.severity], -i.count, i.queue))
