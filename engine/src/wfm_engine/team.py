"""The week of a team at a glance (people screen "Team").

Pure: no Django, no clock, no I/O. Three plain sums, none of which ranks anybody: rostered hours
against contract hours, whether a person's week of adherence is on track, and the same counted for
a whole team. "On track" uses the one adherence threshold the engine already has
(`ADHERENCE_THRESHOLD_PCT`), so the screen and the day-by-day adherence never disagree.

A person with no agent-state data has NO adherence, which is not the same as 0 %: they are not
counted as on track and not counted as off track either.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from wfm_engine.adherence import ADHERENCE_THRESHOLD_PCT


def hours(minutes: int) -> float:
    """Minutes as hours to one decimal place (paid minutes of a shift, summed over a week)."""
    return round(minutes / 60, 1)


def rostered_pct_of_contract(rostered_h: float, contract_h: float) -> float | None:
    """Rostered hours as a percentage of contract hours; None when there are no contract hours to
    compare with."""
    if contract_h <= 0:
        return None
    return round(rostered_h / contract_h * 100, 1)


def is_on_track(
    adherence_pct: float | None, *, threshold_pct: float = ADHERENCE_THRESHOLD_PCT
) -> bool | None:
    """True at or above the threshold, False below it, None when there is no adherence data."""
    if adherence_pct is None:
        return None
    return adherence_pct >= threshold_pct


@dataclass(frozen=True, slots=True)
class PersonWeek:
    rostered_h: float
    contract_h: float
    adherence_pct: float | None


@dataclass(frozen=True, slots=True)
class TeamSummary:
    headcount: int
    with_data: int  # people who have adherence data this week
    on_track: int
    rostered_h: float
    contract_h: float
    rostered_pct: float | None  # of contract hours; None with no contract hours


def summarise(people: Iterable[PersonWeek]) -> TeamSummary:
    rows = list(people)
    verdicts = [is_on_track(p.adherence_pct) for p in rows]
    rostered = round(sum(p.rostered_h for p in rows), 1)
    contract = round(sum(p.contract_h for p in rows), 1)
    return TeamSummary(
        headcount=len(rows),
        with_data=sum(v is not None for v in verdicts),
        on_track=sum(v is True for v in verdicts),
        rostered_h=rostered,
        contract_h=contract,
        rostered_pct=rostered_pct_of_contract(rostered, contract),
    )
