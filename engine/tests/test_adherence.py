from datetime import datetime

import pytest

from wfm_engine.adherence import adherence, parse_state_csv, scheduled_spans, team_adherence_pct


def t(hhmm: str, day: int = 25) -> datetime:
    return datetime(2026, 5, day, int(hhmm[:2]), int(hhmm[3:]))


# 09:00-12:00 and 12:30-17:30 on the phones (a 30 minute lunch between): 180 + 300 = 480 minutes.
PLAN = [(t("09:00"), t("12:00")), (t("12:30"), t("17:30"))]


def test_the_schedule_is_the_shift_less_its_activities() -> None:
    # Failure caught: a lunch inside the shift counted as time the person should be on the phones.
    # Shift 09:00-17:30, lunch = 6 half-hours in, 1 long (12:00-12:30); a break at 10:30 (3, 1).
    spans = scheduled_spans(t("09:00"), t("17:30"), [(6, 1), (3, 1)])
    assert spans == [
        (t("09:00"), t("10:30")),
        (t("11:00"), t("12:00")),
        (t("12:30"), t("17:30")),
    ]
    assert scheduled_spans(t("09:00"), t("10:00")) == [(t("09:00"), t("10:00"))]
    # An activity at the very start, and one running to the very end, leave no empty pieces.
    assert scheduled_spans(t("09:00"), t("10:00"), [(0, 1), (1, 1)]) == []


def test_a_perfect_day_is_one_hundred_percent() -> None:
    states = [
        ("available", t("09:00"), t("12:00")),
        ("lunch", t("12:00"), t("12:30")),
        ("on_call", t("12:30"), t("17:30")),
    ]
    a = adherence(PLAN, states)
    assert (a.scheduled_min, a.in_adherence_min, a.adherence_pct) == (480, 480, 100.0)
    assert a.exceptions == []


def test_working_states_count_and_other_states_do_not() -> None:
    # Failure caught: wrap-up after a call, or a meeting, scored the wrong way round.
    states = [
        ("on_call", t("09:00"), t("10:00")),  # 60 in
        ("wrap_up", t("10:00"), t("10:30")),  # 30 in
        ("meeting", t("10:30"), t("11:00")),  # 30 out
        ("away", t("11:00"), t("11:45")),  # 45 out
        ("available", t("11:45"), t("12:00")),  # 15 in
        ("available", t("12:30"), t("17:30")),  # 300 in
    ]
    a = adherence(PLAN, states)
    assert a.in_adherence_min == 405  # 60 + 30 + 15 + 300
    assert a.out_of_adherence_min == 75
    assert a.adherence_pct == 84.4  # 405 / 480 = 84.375
    assert a.exceptions == ["out_of_adherence"]


def test_working_outside_the_schedule_neither_helps_nor_hurts() -> None:
    # Failure caught: an hour of unscheduled work lifting the percentage over 100.
    states = [("available", t("08:00"), t("18:30"))]
    a = adherence(PLAN, states)
    assert a.adherence_pct == 100.0
    assert a.in_adherence_min == 480  # the 30 minute lunch is not scheduled, so not counted


def test_a_late_start_and_an_early_finish_are_measured_from_the_schedule() -> None:
    states = [("available", t("09:20"), t("16:50"))]
    a = adherence(PLAN, states)
    assert a.late_start_min == 20
    assert a.early_finish_min == 40
    # The 30 minute lunch window is not scheduled, so it is neither in nor out:
    # (09:20-12:00 = 160) + (12:30-16:50 = 260) = 420 of 480 = 87.5, below the 90 threshold.
    assert a.adherence_pct == 87.5
    assert a.exceptions == ["late_start", "early_finish", "out_of_adherence"]


def test_within_the_grace_a_late_start_is_not_an_exception() -> None:
    # Failure caught: a 3 minute walk to the desk raising an exception every morning.
    states = [("available", t("09:03"), t("17:30"))]
    a = adherence(PLAN, states)
    assert a.late_start_min == 3
    assert a.exceptions == []


def test_never_working_is_a_no_show() -> None:
    a = adherence(PLAN, [("logged_out", t("09:00"), t("17:30"))])
    assert a.adherence_pct == 0.0
    assert a.late_start_min == 480
    assert a.exceptions == ["no_show", "out_of_adherence"]


def test_nothing_scheduled_has_no_percentage_and_no_exceptions() -> None:
    # Failure caught: a day off showing 0% or a division by zero.
    a = adherence([], [("available", t("09:00"), t("10:00"))])
    assert (a.scheduled_min, a.adherence_pct, a.exceptions) == (0, None, [])


def test_overlapping_scheduled_and_state_spans_are_not_counted_twice() -> None:
    # Failure caught: a duplicated feed row, or overlapping schedule pieces, counting minutes twice.
    plan = [(t("09:00"), t("10:00")), (t("09:30"), t("10:30"))]
    states = [("available", t("09:00"), t("10:30")), ("on_call", t("09:15"), t("10:00"))]
    a = adherence(plan, states)
    assert (a.scheduled_min, a.in_adherence_min) == (90, 90)


def test_a_night_shift_across_midnight() -> None:
    plan = [(t("22:00"), t("06:00", 26))]
    a = adherence(plan, [("available", t("22:00"), t("06:00", 26))])
    assert (a.scheduled_min, a.adherence_pct) == (480, 100.0)


def test_team_adherence_is_weighted_by_scheduled_minutes() -> None:
    full = adherence([(t("09:00"), t("17:00"))], [("available", t("09:00"), t("17:00"))])
    half = adherence([(t("09:00"), t("11:00"))], [("available", t("09:00"), t("10:00"))])
    # (480 + 60) / (480 + 120) = 90, not the plain mean of 100 and 50.
    assert team_adherence_pct([full, half]) == 90.0
    assert team_adherence_pct([]) is None


GOOD = "login,state,from,to\nagent1,available,2026-05-25T09:00:00,2026-05-25T10:00:00\n"


def test_a_good_file_parses() -> None:
    p = parse_state_csv(GOOD)
    assert (p.rows_read, p.rows_rejected, len(p.rows)) == (1, 0, 1)
    assert p.rows[0].login == "agent1"
    assert p.rows[0].start == datetime(2026, 5, 25, 9)


def test_the_columns_may_be_in_any_order_and_case() -> None:
    p = parse_state_csv("TO,From,State,Login\n2026-05-25T10:00,2026-05-25T09:00,break,a1\n")
    assert [(r.login, r.state) for r in p.rows] == [("a1", "break")]


def test_a_wrong_header_refuses_the_file() -> None:
    # Failure caught: a different vendor layout read column by column into the wrong fields.
    p = parse_state_csv("agent,status,start,stop\na,available,x,y\n")
    assert p.header_error is not None
    assert p.rows == []


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ("a1,dancing,2026-05-25T09:00,2026-05-25T10:00", "state"),
        ("a1,available,not-a-time,2026-05-25T10:00", "ISO"),
        ("a1,available,2026-05-25T09:00+02:00,2026-05-25T10:00+02:00", "ISO"),
        ("a1,available,2026-05-25T10:00,2026-05-25T09:00", "after"),
        ("a1,available,2026-05-25T09:00,2026-05-27T09:00", "24 hours"),
        (",available,2026-05-25T09:00,2026-05-25T10:00", "login"),
        ("a1,available,2026-05-25T09:00", "columns"),
    ],
)
def test_bad_rows_are_rejected_with_a_reason_that_does_not_quote_them(
    line: str, reason: str
) -> None:
    # Failure caught: a bad row stored, or its content echoed back in the error.
    p = parse_state_csv(f"login,state,from,to\n{line}\n{GOOD.splitlines()[1]}\n")
    assert (p.rows_rejected, len(p.rows)) == (1, 1)
    number, text = p.errors[0]
    assert number == 2
    assert reason in text
    assert "a1" not in text
