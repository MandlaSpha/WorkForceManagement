from datetime import date
from decimal import Decimal

import pytest

from wfm_engine.compliance import Rules
from wfm_engine.overtime import (
    HOLIDAY,
    SUNDAY_KIND,
    WEEKDAY,
    day_kind,
    hourly_rate,
    multiplier,
    price,
)

RULES = Rules()
MON, SUN = date(2026, 5, 25), date(2026, 5, 31)
HOLIDAY_DAY = date(2026, 6, 16)  # Youth Day, a Tuesday


def cost(minutes=60, salary="21650", hours="40", kind=WEEKDAY, sundays=False, rules=RULES):
    return price(
        minutes=minutes,
        monthly_salary=Decimal(salary),
        weekly_hours=Decimal(hours),
        kind=kind,
        ordinarily_works_sundays=sundays,
        rules=rules,
    )


def test_the_hourly_rate_is_the_monthly_salary_over_the_hours_in_a_month():
    # 40 h x 4.333 = 173.32 hours; R17 332 / 173.32 = R100 an hour. Failure caught: a 52/12 or
    # 4.345 weeks-per-month slip changing every price by a few cents.
    assert hourly_rate(Decimal("17332"), Decimal("40")) == Decimal("100")


def test_an_hour_of_weekday_overtime_is_one_and_a_half_times_the_rate():
    assert cost(salary="17332") == Decimal("150.00")


def test_sunday_pays_double_unless_the_person_ordinarily_works_sundays():
    assert cost(salary="17332", kind=SUNDAY_KIND) == Decimal("200.00")
    # Failure caught: paying double to somebody who works Sundays as a matter of course.
    assert cost(salary="17332", kind=SUNDAY_KIND, sundays=True) == Decimal("150.00")


def test_a_public_holiday_pays_double_even_for_someone_who_works_sundays():
    assert cost(salary="17332", kind=HOLIDAY, sundays=True) == Decimal("200.00")


def test_the_rates_come_from_the_rules_in_force():
    # Failure caught: multipliers hard-coded instead of read from the editable rules.
    rich = Rules(
        overtime_multiplier=Decimal("1.75"),
        sunday_multiplier=Decimal("2.5"),
        holiday_multiplier=Decimal("3"),
    )
    assert cost(salary="17332", rules=rich) == Decimal("175.00")
    assert cost(salary="17332", kind=SUNDAY_KIND, rules=rich) == Decimal("250.00")
    assert cost(salary="17332", kind=HOLIDAY, rules=rich) == Decimal("300.00")


def test_minutes_are_prorated_and_rounded_half_up_to_the_cent():
    assert cost(minutes=30, salary="17332") == Decimal("75.00")
    # R100.005 an hour x 1.5 x 1 minute / 60 = R2.500125 -> R2.50; 3 minutes R7.50
    assert cost(minutes=1, salary="17332") == Decimal("2.50")
    # a half cent rounds up
    assert cost(minutes=1, salary="17333.10") == Decimal("2.50")
    assert cost(minutes=7, salary="17332") == Decimal("17.50")


def test_part_time_hours_change_the_rate():
    # The same salary spread over fewer hours is a higher hourly rate.
    assert cost(salary="8666", hours="20") == Decimal("150.00")


def test_a_holiday_beats_a_sunday():
    assert day_kind(date(2026, 8, 9), {date(2026, 8, 9)}) == HOLIDAY  # a Sunday that is a holiday
    assert day_kind(SUN, set()) == SUNDAY_KIND
    assert day_kind(MON, set()) == WEEKDAY
    assert day_kind(HOLIDAY_DAY, {HOLIDAY_DAY}) == HOLIDAY


def test_multiplier_picks_the_right_rule():
    assert multiplier(WEEKDAY, ordinarily_works_sundays=True, rules=RULES) == Decimal("1.5")


@pytest.mark.parametrize(("salary", "hours"), [("-1", "40"), ("1000", "0"), ("1000", "-5")])
def test_nonsense_inputs_are_refused_not_priced(salary, hours):
    with pytest.raises(ValueError, match="salary cannot be negative"):
        hourly_rate(Decimal(salary), Decimal(hours))


def test_zero_minutes_are_refused():
    with pytest.raises(ValueError, match="above zero minutes"):
        cost(minutes=0)
