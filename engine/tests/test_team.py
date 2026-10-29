import pytest

from wfm_engine import adherence
from wfm_engine import team as t


def test_threshold_is_the_one_adherence_uses() -> None:
    # Failure caught: a second, drifting "on track" number beside the adherence one.
    assert t.ADHERENCE_THRESHOLD_PCT == adherence.ADHERENCE_THRESHOLD_PCT == 90.0


def test_hours_round_to_one_decimal() -> None:
    assert t.hours(2400) == 40.0
    assert t.hours(450) == 7.5
    assert t.hours(0) == 0.0


@pytest.mark.parametrize(
    ("rostered", "contract", "expected"),
    [
        (36.0, 40.0, 90.0),
        (40.0, 40.0, 100.0),
        (44.0, 40.0, 110.0),
        (0.0, 40.0, 0.0),
        (8.0, 0.0, None),
    ],
)
def test_rostered_against_contract(
    rostered: float, contract: float, expected: float | None
) -> None:
    assert t.rostered_pct_of_contract(rostered, contract) == expected


@pytest.mark.parametrize(
    ("pct", "expected"),
    [(None, None), (89.9, False), (90.0, True), (100.0, True), (0.0, False)],
)
def test_on_track_is_at_or_above_the_threshold(pct: float | None, expected: bool | None) -> None:
    # Failure caught: > instead of >=, or no data treated as 0 % (off track).
    assert t.is_on_track(pct) is expected


def test_summary_counts_only_people_with_data() -> None:
    people = [
        t.PersonWeek(40.0, 40.0, 95.0),
        t.PersonWeek(32.0, 40.0, 80.0),
        t.PersonWeek(40.0, 40.0, None),
    ]
    s = t.summarise(people)
    assert (s.headcount, s.with_data, s.on_track) == (3, 2, 1)
    assert (s.rostered_h, s.contract_h, s.rostered_pct) == (112.0, 120.0, 93.3)


def test_summary_of_nobody() -> None:
    s = t.summarise([])
    assert (s.headcount, s.with_data, s.on_track, s.rostered_pct) == (0, 0, 0, None)
