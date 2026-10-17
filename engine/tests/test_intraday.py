import pytest

from wfm_engine.intraday import alerts, reforecast


def day(value: float) -> list[float]:
    return [value] * 48


def test_a_busier_morning_scales_the_afternoon_up() -> None:
    # 4 finished half-hours, forecast 10 each, 20 came: (80 + 30) / (40 + 30) = 1.571...
    actual: list[int | None] = [20, 20, 20, 20, *([None] * 44)]
    r = reforecast(day(10), actual, elapsed=4)
    assert r.ratio == pytest.approx(110 / 70)
    assert r.volumes[:4] == [20.0] * 4  # what happened is kept as it happened
    assert r.volumes[10] == pytest.approx(10 * 110 / 70)
    assert r.basis_calls == 80


def test_a_quiet_morning_scales_it_down_but_never_below_half() -> None:
    zero: list[int | None] = [0, 0, 0, 0, *([None] * 44)]
    # Forecast 5 a half-hour, nothing came: (0 + 30) / (20 + 30) = 0.6, steadied by the prior.
    assert reforecast(day(5), zero, elapsed=4).ratio == pytest.approx(0.6)
    # Forecast 10: (0 + 30) / (40 + 30) = 0.43, which is clamped to a half.
    assert reforecast(day(10), zero, elapsed=4).ratio == 0.5


def test_a_huge_morning_cannot_more_than_double_the_afternoon() -> None:
    big: list[int | None] = [500, 500, *([None] * 46)]
    assert reforecast(day(10), big, elapsed=2).ratio == 2.0


def test_few_calls_barely_move_the_estimate() -> None:
    # Failure caught: three early calls against a forecast of one swinging the whole day.
    few: list[int | None] = [3, *([None] * 47)]
    r = reforecast(day(1), few, elapsed=1)
    assert r.ratio == pytest.approx(33 / 31)


def test_no_data_means_no_ratio_and_the_forecast_stands() -> None:
    # Failure caught: a half-hour nobody has imported read as zero calls and the day cut in half.
    none: list[int | None] = [None] * 48
    r = reforecast(day(10), none, elapsed=10)
    assert (r.ratio, r.volumes) == (None, day(10))


def test_a_finished_half_hour_without_data_keeps_its_forecast_unscaled() -> None:
    actual: list[int | None] = [20, None, *([None] * 46)]
    r = reforecast(day(10), actual, elapsed=2)
    assert r.volumes[1] == 10.0
    assert r.volumes[5] != 10.0


def test_mismatched_lengths_are_refused() -> None:
    with pytest.raises(ValueError, match="same"):
        reforecast([1.0], [1, 2], 1)
    with pytest.raises(ValueError, match="same"):
        alerts([1], [1, 2], 0)


def test_alerts_only_look_ahead_and_only_where_the_requirement_is_known() -> None:
    scheduled = [0, 0, 1, 3, 2]
    required: list[int | None] = [5, 5, 2, 3, None]
    found = alerts(scheduled, required, elapsed=2)
    # Slots 0 and 1 are over; slot 3 is met; slot 4 has no known requirement.
    assert [(a.slot, a.short) for a in found] == [(2, 1)]


def test_severity_is_critical_when_two_short_or_a_quarter_short() -> None:
    found = alerts([1, 4, 3, 10], [2, 6, 4, 11], elapsed=0)
    got = {a.slot: a.severity for a in found}
    # 1 of 2 short is half of the need: critical; 2 short: critical; 1 of 4 is a quarter: critical;
    # 1 of 11 is not.
    assert got == {0: "critical", 1: "critical", 2: "critical", 3: "warning"}
