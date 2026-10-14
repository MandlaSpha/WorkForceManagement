"""What-if scenarios on a forecast (requirement RPT-06): change calls, handling time, shrinkage or
the service-level target, and see what it does to the agents needed. Read-only: nothing is saved,
the forecast itself is never touched.

The base is the forecast's own stored requirement; the scenario is worked out again with the same
staffing function (`staffing.requirement`), so a scenario of "no change" reproduces the base.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from wfm_engine.kpi import INTERVAL_MINUTES

from wfm.core.errors import ApiError

from .staffing import Assumptions, requirement

HOURS_PER_SLOT = INTERVAL_MINUTES / 60

MIN_VOLUME_CHANGE, MAX_VOLUME_CHANGE = -100.0, 500.0
MIN_AHT_CHANGE, MAX_AHT_CHANGE = -90.0, 500.0


@dataclass(frozen=True, slots=True)
class Row:
    """One half-hour of a forecast as stored."""

    day: date
    volume: float
    aht_s: float | None
    required: (
        int | None
    )  # agents to roster, shrinkage included; None when it could not be worked out


@dataclass(frozen=True, slots=True)
class DayFigures:
    day: date
    calls_base: float
    calls_scenario: float
    peak_base: int | None  # most agents to roster at once
    peak_scenario: int | None
    hours_base: float  # agent-hours to roster over the day
    hours_scenario: float
    complete: bool  # false when some half-hour with calls has no requirement: figures are minimums


def check(
    volume_change_pct: float,
    aht_change_pct: float,
    sl_target_pct: float | None,
    shrinkage_pct: float | None,
) -> None:
    def refuse(code: str, detail: str) -> ApiError:
        return ApiError(422, code, "Invalid scenario", detail)

    if not MIN_VOLUME_CHANGE <= volume_change_pct <= MAX_VOLUME_CHANGE:
        raise refuse("scenario.volume_invalid", "Calls can change by -100% to +500%.")
    if not MIN_AHT_CHANGE <= aht_change_pct <= MAX_AHT_CHANGE:
        raise refuse("scenario.aht_invalid", "Handling time can change by -90% to +500%.")
    if sl_target_pct is not None and not 0 < sl_target_pct <= 100:
        raise refuse("scenario.sl_invalid", "The service-level target is above 0 and at most 100%.")
    if shrinkage_pct is not None and not 0 <= shrinkage_pct < 100:
        raise refuse("scenario.shrinkage_invalid", "Shrinkage is 0% or more and under 100%.")


def run(
    rows: Iterable[Row],
    base: Assumptions,
    *,
    volume_change_pct: float = 0.0,
    aht_change_pct: float = 0.0,
    sl_target_pct: float | None = None,
    shrinkage_pct: float | None = None,
) -> tuple[Assumptions, list[DayFigures]]:
    """The scenario's assumptions, and the base against the scenario for each day."""
    check(volume_change_pct, aht_change_pct, sl_target_pct, shrinkage_pct)
    scenario = base.changed(sl_target_pct=sl_target_pct, shrinkage_pct=shrinkage_pct)
    volume_factor = 1 + volume_change_pct / 100
    aht_factor = 1 + aht_change_pct / 100

    by_day: dict[date, list[Row]] = defaultdict(list)
    for row in rows:
        by_day[row.day].append(row)

    figures: list[DayFigures] = []
    for day in sorted(by_day):
        base_required: list[int | None] = []
        scenario_required: list[int | None] = []
        calls_scenario = 0.0
        for row in by_day[day]:
            volume = row.volume * volume_factor
            aht = None if row.aht_s is None else row.aht_s * aht_factor
            calls_scenario += volume
            base_required.append(row.required if row.volume > 0 else 0)
            scenario_required.append(requirement(volume, aht, scenario)[1])
        known_base = [r for r in base_required if r is not None]
        known_scenario = [r for r in scenario_required if r is not None]
        figures.append(
            DayFigures(
                day=day,
                calls_base=sum(r.volume for r in by_day[day]),
                calls_scenario=calls_scenario,
                peak_base=max(known_base, default=None),
                peak_scenario=max(known_scenario, default=None),
                hours_base=sum(known_base) * HOURS_PER_SLOT,
                hours_scenario=sum(known_scenario) * HOURS_PER_SLOT,
                complete=len(known_base) == len(base_required)
                and len(known_scenario) == len(scenario_required),
            )
        )
    return scenario, figures
