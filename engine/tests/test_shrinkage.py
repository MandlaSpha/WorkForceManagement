from decimal import Decimal

import pytest

from wfm_engine.shrinkage import Person, summarise


def test_share_is_away_hours_over_contracted_hours() -> None:
    # Failure caught: dividing by days instead of hours, so part-timers count like full-timers.
    s = summarise([Person(Decimal(40), 20, 2), Person(Decimal(20), 20, 0)])
    assert (s.contracted_hours, s.away_hours, s.planned_pct) == (
        Decimal(240),
        Decimal(16),
        Decimal("6.7"),
    )


def test_nobody_employed_has_no_share_not_zero() -> None:
    # Failure caught: 0% reported for a team with no contracted hours.
    assert summarise([Person(Decimal(40), 0, 0)]).planned_pct is None
    assert summarise([]).planned_pct is None


def test_more_days_away_than_employed_is_a_bug_not_a_figure() -> None:
    with pytest.raises(ValueError, match="exceed"):
        summarise([Person(Decimal(40), 2, 3)])
