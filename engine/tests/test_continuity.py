from __future__ import annotations

import pytest

from wfm_engine import continuity as c


def cand(**kw: object) -> c.Candidate:
    base: dict[str, object] = {
        "work_mode": "remote",
        "on_leave": False,
        "unavailable_min": 0,
        "rostered_here": False,
        "rostered_elsewhere": False,
    }
    return c.Candidate(**{**base, **kw})  # type: ignore[arg-type]


def test_free_remote_person_covers_a_site_failure() -> None:
    assert c.classify(cand(), c.SITE) == c.FREE


def test_office_only_person_cannot_cover_a_site_failure_but_can_cover_an_outbreak() -> None:
    assert c.classify(cand(work_mode="office"), c.SITE) == c.NEEDS_OFFICE
    assert c.classify(cand(work_mode="office"), c.OUTBREAK) == c.FREE


def test_hybrid_counts_as_remote_capable() -> None:
    assert c.classify(cand(work_mode="hybrid"), c.SITE) == c.FREE


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        ({"rostered_here": True, "on_leave": True}, c.ALREADY_ROSTERED),
        ({"on_leave": True}, c.ON_LEAVE),
        ({"unavailable_min": 720}, c.UNAVAILABLE),
        ({"unavailable_min": 719}, c.FREE),
        ({"rostered_elsewhere": True}, c.ROSTERED_ELSEWHERE),
    ],
)
def test_first_reason_wins(kw: dict[str, object], expected: str) -> None:
    assert c.classify(cand(**kw), c.OUTBREAK) == expected


def test_usable_set_is_free_and_rostered_elsewhere_only() -> None:
    assert {c.FREE, c.ROSTERED_ELSEWHERE} == c.USABLE


def test_site_impact_loses_office_people_and_backups_close_the_gap() -> None:
    modes = ["office", "office", "office", "remote", "hybrid"]
    impact = c.roster_impact(modes, 2, c.SITE, 0)
    assert (impact.lost, impact.remaining, impact.recovered) == (3, 2, 2)
    assert (impact.covered_after, impact.shortfall, impact.coverage_pct) == (4, 1, 80.0)


def test_backups_beyond_the_gap_are_not_counted_twice() -> None:
    impact = c.roster_impact(["office", "remote"], 5, c.SITE, 0)
    assert (impact.lost, impact.recovered, impact.covered_after, impact.shortfall) == (1, 1, 2, 0)


def test_outbreak_rounds_the_loss_up_whatever_the_work_mode() -> None:
    impact = c.roster_impact(["remote"] * 7, 0, c.OUTBREAK, 30)
    assert (impact.lost, impact.remaining, impact.coverage_pct) == (3, 4, 57.1)


def test_empty_roster_has_no_coverage_figure() -> None:
    impact = c.roster_impact([], 3, c.OUTBREAK, 50)
    assert impact.coverage_pct is None
    assert impact.shortfall == 0


@pytest.mark.parametrize("pct", [-1, 101])
def test_bad_percentage_is_refused(pct: int) -> None:
    with pytest.raises(ValueError, match="lost_pct"):
        c.roster_impact(["office"], 0, c.OUTBREAK, pct)


def test_unknown_scenario_is_refused() -> None:
    with pytest.raises(ValueError, match="scenario"):
        c.classify(cand(), "flood")
    with pytest.raises(ValueError, match="scenario"):
        c.roster_impact([], 0, "flood", 0)
