"""Early-warning prompts for overload, and skill-gap checks (requirements WEL-01, WEL-02).

A flag is a prompt for a conversation, never a score: there is no number that ranks people and no
function here returns one. Each flag carries only the plain fact that raised it (days in a row,
overtime days). The thresholds are named constants so a customer can change them in one place and
a test can pin them.

Pure functions: no Django, no clock, no I/O. `today` is passed in.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

# Seven or more days in a row worked (shifts or overtime), counted back from today.
LONG_RUN_DAYS = 7
# Fewer than two days not worked in the last fortnight.
NO_REST_WINDOW_DAYS = 14
MIN_REST_DAYS = 2
# Overtime on four or more different days in the last four weeks.
OVERTIME_WINDOW_DAYS = 28
REPEATED_OVERTIME_DAYS = 4
# Unplanned absence (sick, family responsibility): three or more days in the last four weeks AND
# more than in the four weeks before that.
ABSENCE_WINDOW_DAYS = 28
RISING_ABSENCE_MIN_DAYS = 3

LONG_RUN = "long_run"
NO_REST = "no_rest"
REPEATED_OVERTIME = "repeated_overtime"
RISING_ABSENCE = "rising_absence"
FLAG_CODES = (LONG_RUN, NO_REST, REPEATED_OVERTIME, RISING_ABSENCE)


@dataclass(frozen=True, slots=True)
class Flag:
    code: str
    value: int  # the fact behind it: days in a row, rest days, overtime days, absence days


def _days_back(today: date, days: int) -> set[date]:
    return {today - timedelta(days=n) for n in range(days)}


def current_run_days(worked: Collection[date], today: date) -> int:
    """Days worked in a row up to today. Today itself not being worked yet does not break a run
    that ran up to yesterday."""
    day = today if today in worked else today - timedelta(days=1)
    run = 0
    while day in worked:
        run += 1
        day -= timedelta(days=1)
    return run


def wellbeing_flags(
    *,
    shift_days: Collection[date],
    overtime_days: Collection[date],
    absence_days: Collection[date],
    today: date,
) -> list[Flag]:
    """The prompts that apply to one person today. `shift_days` are days on a shift, `overtime_days`
    days with approved overtime, `absence_days` days of unplanned absence. Days after today are
    ignored, so a roster published ahead cannot raise a flag early."""
    worked = {d for d in shift_days if d <= today} | {d for d in overtime_days if d <= today}
    overtime = {d for d in overtime_days if d <= today}
    flags: list[Flag] = []

    run = current_run_days(worked, today)
    if run >= LONG_RUN_DAYS:
        flags.append(Flag(LONG_RUN, run))

    rest = len(_days_back(today, NO_REST_WINDOW_DAYS) - worked)
    if rest < MIN_REST_DAYS and run > 0:
        flags.append(Flag(NO_REST, rest))

    overtime_count = len(overtime & _days_back(today, OVERTIME_WINDOW_DAYS))
    if overtime_count >= REPEATED_OVERTIME_DAYS:
        flags.append(Flag(REPEATED_OVERTIME, overtime_count))

    recent_window = _days_back(today, ABSENCE_WINDOW_DAYS)
    prior_window = _days_back(today - timedelta(days=ABSENCE_WINDOW_DAYS), ABSENCE_WINDOW_DAYS)
    absent = set(absence_days)
    recent, prior = len(absent & recent_window), len(absent & prior_window)
    if recent >= RISING_ABSENCE_MIN_DAYS and recent > prior:
        flags.append(Flag(RISING_ABSENCE, recent))
    return flags


@dataclass(frozen=True, slots=True)
class Shortfall[K]:
    key: K
    required: int
    present: int

    @property
    def missing(self) -> int:
        return self.required - self.present


def skill_shortfalls[K](
    *, required: int, present: Mapping[K, int], expected: Collection[K]
) -> list[Shortfall[K]]:
    """Every key in `expected` (a shift on a day, say) where fewer than `required` people hold the
    skill. A key nobody holds the skill on counts as zero present: absence is the gap itself."""
    return [
        Shortfall(key, required, present.get(key, 0))
        for key in expected
        if present.get(key, 0) < required
    ]
