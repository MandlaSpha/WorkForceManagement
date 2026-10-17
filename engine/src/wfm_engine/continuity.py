"""Business continuity: who can cover a queue when a site fails or an outbreak removes people
(requirement BCP-01).

Two scenarios. A SITE failure takes out everybody who can only work from the office; people who
work remotely or hybrid carry on. An OUTBREAK takes out a share of the people rostered, whatever
their work mode. A named backup person is USABLE when they are not already on the roster that day,
not on approved leave, not declared unavailable for most of the day, and (for a site failure) able
to work away from the office. Someone already rostered on another queue is usable but flagged,
because pulling them leaves a gap elsewhere.

Pure functions: no Django, no clock, no I/O.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

SITE = "site"
OUTBREAK = "outbreak"
SCENARIOS = (SITE, OUTBREAK)

REMOTE_CAPABLE = frozenset({"remote", "hybrid"})

# A person who has declared this much of the day as "cannot work" is not counted as cover.
ALL_DAY_UNAVAILABLE_MIN = 12 * 60

ALREADY_ROSTERED = "already_rostered"
ON_LEAVE = "on_leave"
UNAVAILABLE = "unavailable"
NEEDS_OFFICE = "needs_office"
ROSTERED_ELSEWHERE = "rostered_elsewhere"
FREE = "free"
USABLE = frozenset({FREE, ROSTERED_ELSEWHERE})


@dataclass(frozen=True, slots=True)
class Candidate:
    work_mode: str
    on_leave: bool
    unavailable_min: int  # minutes of "cannot work" windows declared for that weekday
    rostered_here: bool  # already on this queue's roster that day
    rostered_elsewhere: bool  # on another queue's roster that day


@dataclass(frozen=True, slots=True)
class Impact:
    rostered: int  # people on the queue's roster that day
    lost: int  # people the scenario takes away
    remaining: int
    recovered: int  # lost people replaced by usable backups
    covered_after: int
    shortfall: int  # still missing after the backups
    coverage_pct: float | None  # covered_after as a share of rostered; None with nobody rostered


def classify(candidate: Candidate, scenario: str) -> str:
    """Why a backup person can or cannot cover. The first reason that applies wins."""
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    if candidate.rostered_here:
        return ALREADY_ROSTERED
    if candidate.on_leave:
        return ON_LEAVE
    if candidate.unavailable_min >= ALL_DAY_UNAVAILABLE_MIN:
        return UNAVAILABLE
    if scenario == SITE and candidate.work_mode not in REMOTE_CAPABLE:
        return NEEDS_OFFICE
    if candidate.rostered_elsewhere:
        return ROSTERED_ELSEWHERE
    return FREE


def roster_impact(
    rostered_work_modes: Sequence[str], usable_backups: int, scenario: str, lost_pct: int
) -> Impact:
    """What the scenario does to the day's roster and how far the backups close the gap.
    `lost_pct` (0-100) only matters for an outbreak."""
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    if not 0 <= lost_pct <= 100:
        raise ValueError("lost_pct must be 0 to 100")
    if usable_backups < 0:
        raise ValueError("usable_backups cannot be negative")
    rostered = len(rostered_work_modes)
    if scenario == SITE:
        lost = sum(1 for mode in rostered_work_modes if mode not in REMOTE_CAPABLE)
    else:
        lost = math.ceil(rostered * lost_pct / 100)
    recovered = min(usable_backups, lost)
    covered_after = rostered - lost + recovered
    return Impact(
        rostered=rostered,
        lost=lost,
        remaining=rostered - lost,
        recovered=recovered,
        covered_after=covered_after,
        shortfall=lost - recovered,
        coverage_pct=round(100 * covered_after / rostered, 1) if rostered else None,
    )
