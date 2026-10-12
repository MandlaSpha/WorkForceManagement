import math

import pytest

from wfm_engine import erlang


def test_traffic_is_arrival_rate_times_aht() -> None:
    # 30 calls in a 30-min interval at 180 s AHT = 3 Erlangs
    assert erlang.traffic_erlangs(volume=30, interval_s=1800, aht_s=180) == pytest.approx(3.0)


def test_wait_probability_matches_published_value() -> None:
    # Textbook Erlang C: 10 Erlangs, 12 agents -> P(wait) ~= 0.4494
    assert erlang.erlang_c_wait_probability(12, 10.0) == pytest.approx(0.4494, abs=1e-3)


def test_unstable_queue_always_waits() -> None:
    assert erlang.erlang_c_wait_probability(5, 5.0) == 1.0
    assert erlang.erlang_c_wait_probability(4, 5.0) == 1.0


def test_no_traffic_never_waits() -> None:
    assert erlang.erlang_c_wait_probability(3, 0.0) == 0.0
    assert erlang.service_level(agents=3, traffic=0.0, aht_s=200, threshold_s=20) == 1.0


def test_service_level_matches_published_value() -> None:
    # 10 Erlangs, 12 agents, AHT 180 s, 20 s threshold.
    # Expected 0.6402 from the textbook factorial formula, computed independently of
    # the iterative implementation: Pw = 0.4494, SL = 1 - Pw * exp(-(12-10) * 20 / 180).
    sl = erlang.service_level(agents=12, traffic=10.0, aht_s=180, threshold_s=20)
    assert sl == pytest.approx(0.6402, abs=1e-3)


def test_service_level_rises_with_more_agents() -> None:
    levels = [
        erlang.service_level(agents=n, traffic=10.0, aht_s=180, threshold_s=20)
        for n in range(11, 20)
    ]
    assert levels == sorted(levels)
    assert levels[-1] > 0.95


def test_required_agents_meets_target_and_one_fewer_does_not() -> None:
    kwargs = dict(volume=100, interval_s=1800, aht_s=210, sl_target=0.8, threshold_s=20)
    n = erlang.required_agents(**kwargs)
    traffic = erlang.traffic_erlangs(volume=100, interval_s=1800, aht_s=210)
    assert erlang.service_level(agents=n, traffic=traffic, aht_s=210, threshold_s=20) >= 0.8
    assert erlang.service_level(agents=n - 1, traffic=traffic, aht_s=210, threshold_s=20) < 0.8


def test_shrinkage_grosses_up_requirement() -> None:
    base = erlang.required_agents(
        volume=100, interval_s=1800, aht_s=210, sl_target=0.8, threshold_s=20
    )
    with_shrink = erlang.required_agents(
        volume=100, interval_s=1800, aht_s=210, sl_target=0.8, threshold_s=20, shrinkage=0.3
    )
    assert with_shrink == math.ceil(base / 0.7)


def test_occupancy_ceiling_can_raise_requirement() -> None:
    loose = erlang.required_agents(
        volume=100, interval_s=1800, aht_s=210, sl_target=0.5, threshold_s=60
    )
    capped = erlang.required_agents(
        volume=100, interval_s=1800, aht_s=210, sl_target=0.5, threshold_s=60, occupancy_ceiling=0.6
    )
    assert capped >= loose
    traffic = erlang.traffic_erlangs(volume=100, interval_s=1800, aht_s=210)
    assert traffic / capped <= 0.6


def test_zero_volume_needs_zero_agents() -> None:
    assert (
        erlang.required_agents(volume=0, interval_s=1800, aht_s=210, sl_target=0.8, threshold_s=20)
        == 0
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"sl_target": 0.0}, "sl_target"),
        ({"sl_target": 1.5}, "sl_target"),
        ({"occupancy_ceiling": 0.0}, "occupancy_ceiling"),
        ({"shrinkage": 1.0}, "shrinkage"),
        ({"shrinkage": -0.1}, "shrinkage"),
    ],
)
def test_invalid_ratios_rejected(kwargs: dict[str, float], message: str) -> None:
    params: dict[str, float] = {
        "volume": 10,
        "interval_s": 1800,
        "aht_s": 200,
        "sl_target": 0.8,
        "threshold_s": 20,
    }
    params.update(kwargs)
    with pytest.raises(ValueError, match=message):
        erlang.required_agents(**params)


def test_large_queue_does_not_overflow() -> None:
    n = erlang.required_agents(
        volume=5000, interval_s=1800, aht_s=240, sl_target=0.8, threshold_s=20
    )
    assert 600 < n < 800
