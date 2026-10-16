from datetime import date

import pytest

from wfm_engine.compliance import (
    DEFAULT_RULES,
    Rules,
    floor_warnings,
    invalid_reason,
    rules_in_force,
)

JAN, MAR, JUN = date(2027, 1, 1), date(2027, 3, 1), date(2027, 6, 1)
LOOSE = Rules(min_rest_hours=8, max_consecutive_days=7)
TIGHT = Rules(min_rest_hours=12, max_consecutive_days=5, max_weekly_hours=45)


def test_defaults_are_the_numbers_the_roster_always_used():
    # Failure caught: changing a default silently changes what every roster accepts.
    assert (DEFAULT_RULES.min_rest_hours, DEFAULT_RULES.max_consecutive_days) == (11, 6)
    assert DEFAULT_RULES.max_weekly_hours is None


def test_no_version_yet_means_the_defaults():
    assert rules_in_force([], JAN) == DEFAULT_RULES


def test_a_version_applies_from_its_own_day_not_before():
    # Failure caught: a new rule rewriting shifts that were rostered under the old one.
    versions = [(MAR, TIGHT)]
    assert rules_in_force(versions, date(2027, 2, 28)) == DEFAULT_RULES
    assert rules_in_force(versions, MAR) == TIGHT


def test_the_latest_version_started_wins_whatever_order_they_come_in():
    # Failure caught: picking the first or last row of a list instead of the right date.
    versions = [(JUN, LOOSE), (JAN, TIGHT), (MAR, DEFAULT_RULES)]
    assert rules_in_force(versions, date(2027, 4, 1)) == DEFAULT_RULES
    assert rules_in_force(versions, JUN) == LOOSE
    assert rules_in_force(versions, date(2027, 2, 1)) == TIGHT


def test_tightening_never_warns():
    assert floor_warnings(TIGHT) == []
    assert floor_warnings(DEFAULT_RULES) == []


@pytest.mark.parametrize(
    ("rules", "mentions"),
    [
        (Rules(min_rest_hours=10), "Rest of 10 hours"),
        (Rules(max_consecutive_days=7), "7 days in a row"),
    ],
)
def test_loosening_below_the_floor_warns_in_words(rules, mentions):
    # Failure caught: a rule loosened past the law with nobody told.
    (only,) = floor_warnings(rules)
    assert mentions in only


def test_loosening_both_gives_two_warnings():
    assert len(floor_warnings(LOOSE)) == 2


@pytest.mark.parametrize(
    "rules",
    [
        Rules(min_rest_hours=0),
        Rules(min_rest_hours=25),
        Rules(max_consecutive_days=0),
        Rules(max_consecutive_days=15),
        Rules(max_weekly_hours=0),
        Rules(max_weekly_hours=91),
    ],
)
def test_nonsense_is_refused_outright(rules):
    # Failure caught: a zero or absurd value making every shift (or none) refused.
    assert invalid_reason(rules) is not None


@pytest.mark.parametrize(
    "rules",
    [
        DEFAULT_RULES,
        TIGHT,
        LOOSE,
        Rules(min_rest_hours=1, max_consecutive_days=14, max_weekly_hours=90),
    ],
)
def test_sensible_values_are_accepted_even_when_loose(rules):
    assert invalid_reason(rules) is None
