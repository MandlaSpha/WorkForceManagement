from datetime import date

import pytest

from wfm_engine import quality as q

TODAY = date(2026, 10, 17)


def fields(**over: str) -> dict[str, str]:
    base = {"login": "a1", "date": "2026-10-01", "score": "86.5"}
    return {**base, **over}


def test_a_minimal_row_is_read_with_defaults():
    row = q.read_row(fields(), TODAY)
    assert isinstance(row, q.Evaluation)
    assert (row.kind, row.ref, row.csat, row.coaching_due) == ("call", "", None, None)
    assert row.score_pct == 86.5


def test_day_first_dates_and_percent_sign_are_forgiven():
    row = q.read_row(fields(date="01/10/2026", score="90%", coaching_due="15/10/2026"), TODAY)
    assert isinstance(row, q.Evaluation)
    assert row.evaluated_on == date(2026, 10, 1)
    assert row.coaching_due == date(2026, 10, 15)


@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({"login": ""}, "bad_login"),
        ({"date": "yesterday"}, "bad_date"),
        ({"date": "2026-10-18"}, "date_in_future"),
        ({"date": "2020-01-01"}, "date_too_old"),
        ({"score": "abc"}, "bad_score"),
        ({"score": "101"}, "bad_score"),
        ({"score": "-1"}, "bad_score"),
        ({"score": "nan"}, "bad_score"),
        ({"kind": "email"}, "bad_kind"),
        ({"ref": "x" * 41}, "bad_ref"),
        ({"csat": "6"}, "bad_csat"),
        ({"csat": "0"}, "bad_csat"),
        ({"csat": "4.5"}, "bad_csat"),
        ({"coaching_due": "soon"}, "bad_coaching_due"),
        ({"coaching_due": "2031-01-01"}, "bad_coaching_due"),
    ],
)
def test_a_bad_row_is_refused_with_a_code_not_its_content(over, reason):
    assert q.read_row(fields(**over), TODAY) == reason


def ev(day: int, score: float, csat: int | None = None, due: date | None = None) -> q.Evaluation:
    return q.Evaluation("a1", date(2026, 10, day), "call", str(day), score, csat, due)


def test_summary_of_one_persons_results():
    s = q.summarise(
        [ev(3, 80, 4), ev(9, 90, 5, date(2026, 10, 20)), ev(1, 70, None, date(2026, 10, 10))],
        TODAY,
    )
    assert s.evaluations == 3
    assert s.average_score_pct == 80.0
    assert (s.latest_score_pct, s.latest_on) == (90.0, date(2026, 10, 9))
    assert (s.csat_count, s.csat_average) == (2, 4.5)
    # The newest evaluation that names a date decides, not the earliest.
    assert s.coaching_due == date(2026, 10, 20)
    assert s.coaching_is_due is False


def test_coaching_is_due_on_the_day_and_after():
    assert q.summarise([ev(1, 70, None, TODAY)], TODAY).coaching_is_due is True


def test_nothing_scored_claims_nothing():
    s = q.summarise([], TODAY)
    assert (s.evaluations, s.average_score_pct, s.csat_average, s.coaching_due) == (
        0,
        None,
        None,
        None,
    )
