import pytest

from wfm_engine.hiring import plan, validate

RAMP = [0.0, 0.5, 1.0]  # a hire is useless the first month, half the second, full the third
FLAT = [100.0] * 12


def test_no_attrition_and_enough_people_needs_no_hires() -> None:
    rows = plan(FLAT, incumbents=100, attrition=0.0, ramp=RAMP)
    assert [r.hires for r in rows] == [0] * 12
    assert all(r.gap == pytest.approx(0) for r in rows)


def test_a_rising_need_is_met_by_hires_made_two_months_early() -> None:
    # Failure caught: hiring in the month the people are needed, so they arrive still learning.
    need = [100.0] * 6 + [110.0] * 6
    rows = plan(need, incumbents=100, attrition=0.0, ramp=RAMP)
    assert [r.hires for r in rows] == [0, 0, 0, 0, 10, 0, 0, 0, 0, 0, 0, 0]
    assert rows[6].gap == pytest.approx(0)  # 110 fully productive in month 6
    assert rows[4].headcount == pytest.approx(110)  # paid from the month hired
    assert rows[4].effective == pytest.approx(100)  # but not yet working at full strength


def test_attrition_is_replaced() -> None:
    rows = plan(FLAT, incumbents=100, attrition=0.02, ramp=RAMP)
    assert sum(r.hires for r in rows) > 0
    # Every month from the lead time on is covered.
    assert all(r.gap >= -1e-6 for r in rows if r.index >= 2)


def test_a_shortfall_inside_the_lead_time_is_flagged_unavoidable() -> None:
    # Failure caught: a planner told to hire for a gap that no hire could close in time.
    need = [120.0] * 12
    rows = plan(need, incumbents=100, attrition=0.0, ramp=RAMP)
    assert rows[0].gap == pytest.approx(-20)
    assert rows[0].unavoidable
    assert rows[1].gap < 0
    assert rows[1].unavoidable
    assert rows[2].gap == pytest.approx(0)
    assert not rows[2].unavoidable
    assert rows[0].hires > 0  # the hiring that fixes month 2 starts at once


def test_hires_are_whole_people_rounded_up() -> None:
    need = [100.0] * 6 + [100.4] * 6
    rows = plan(need, incumbents=100, attrition=0.0, ramp=RAMP)
    assert sum(r.hires for r in rows) == 1


def test_nothing_is_hired_for_months_after_the_plan_ends() -> None:
    need = [100.0] * 11 + [200.0]
    rows = plan(need, incumbents=100, attrition=0.0, ramp=RAMP)
    # The jump is in the last month; the hire for it starts in month 9, inside the plan.
    assert rows[9].hires == 100
    assert rows[10].hires == 0
    assert rows[11].hires == 0


def test_a_falling_need_hires_nobody_and_shows_the_surplus() -> None:
    need = [100.0] * 4 + [60.0] * 8
    rows = plan(need, incumbents=100, attrition=0.0, ramp=RAMP)
    assert sum(r.hires for r in rows) == 0
    assert rows[8].gap == pytest.approx(40)


def test_a_quick_ramp_hires_late() -> None:
    need = [100.0] * 6 + [110.0] * 6
    rows = plan(need, incumbents=100, attrition=0.0, ramp=[1.0])
    assert rows[6].hires == 10
    assert rows[6].gap == pytest.approx(0)


@pytest.mark.parametrize(
    ("required", "inc", "attr", "ramp", "why"),
    [
        ([1.0] * 11, 1, 0.0, [1.0], "12 to 18"),
        ([1.0] * 19, 1, 0.0, [1.0], "12 to 18"),
        ([-1.0] + [1.0] * 11, 1, 0.0, [1.0], "negative"),
        ([1.0] * 12, -1, 0.0, [1.0], "incumbents"),
        ([1.0] * 12, 1, 1.0, [1.0], "attrition"),
        ([1.0] * 12, 1, 0.0, [0.5, 0.9], "ends at 1"),
        ([1.0] * 12, 1, 0.0, [0.8, 0.5, 1.0], "less productive"),
        ([1.0] * 12, 1, 0.0, [0.0] * 12 + [1.0], "longer than the plan"),
    ],
)
def test_nonsense_is_refused(
    required: list[float], inc: float, attr: float, ramp: list[float], why: str
) -> None:
    with pytest.raises(ValueError, match=why):
        validate(required, inc, attr, ramp)
