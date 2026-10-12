"""Erlang C staffing maths (requirement ENG-01, ENG-02).

All functions are pure. Time units are seconds; traffic is in Erlangs.
Computed iteratively (Erlang B recurrence) so large agent counts do not overflow.
"""

from __future__ import annotations

import math


def traffic_erlangs(*, volume: float, interval_s: float, aht_s: float) -> float:
    """Offered load A = arrivals per second x average handle time."""
    if volume < 0 or interval_s <= 0 or aht_s < 0:
        raise ValueError("volume and aht_s must be >= 0 and interval_s > 0")
    return volume / interval_s * aht_s


def erlang_c_wait_probability(agents: int, traffic: float) -> float:
    """Probability an arriving call has to wait, with `agents` servers and `traffic` Erlangs.

    Returns 1.0 when agents <= traffic (unstable queue).
    """
    if agents < 1:
        raise ValueError("agents must be >= 1")
    if traffic <= 0:
        return 0.0
    if agents <= traffic:
        return 1.0
    b = 1.0  # Erlang B, built up one server at a time
    for k in range(1, agents + 1):
        b = traffic * b / (k + traffic * b)
    rho = traffic / agents
    return b / (1 - rho * (1 - b))


def service_level(*, agents: int, traffic: float, aht_s: float, threshold_s: float) -> float:
    """Fraction of calls answered within `threshold_s` seconds (0..1)."""
    if traffic <= 0:
        return 1.0
    if agents <= traffic:
        return 0.0
    pw = erlang_c_wait_probability(agents, traffic)
    return 1 - pw * math.exp(-(agents - traffic) * threshold_s / aht_s)


def required_agents(
    *,
    volume: float,
    interval_s: float,
    aht_s: float,
    sl_target: float,
    threshold_s: float,
    occupancy_ceiling: float = 1.0,
    shrinkage: float = 0.0,
    max_agents: int = 2000,
) -> int:
    """Smallest agent count meeting the service-level target and occupancy ceiling,
    then grossed up for shrinkage (share of paid time agents are not available).

    `sl_target`, `occupancy_ceiling` and `shrinkage` are ratios in 0..1 (units rule).
    """
    if not 0 < sl_target <= 1:
        raise ValueError("sl_target must be in (0, 1]")
    if not 0 < occupancy_ceiling <= 1:
        raise ValueError("occupancy_ceiling must be in (0, 1]")
    if not 0 <= shrinkage < 1:
        raise ValueError("shrinkage must be in [0, 1)")
    traffic = traffic_erlangs(volume=volume, interval_s=interval_s, aht_s=aht_s)
    if traffic == 0:
        return 0
    n = max(1, math.floor(traffic) + 1)
    while n <= max_agents:
        meets_sl = (
            service_level(agents=n, traffic=traffic, aht_s=aht_s, threshold_s=threshold_s)
            >= sl_target
        )
        if meets_sl and traffic / n <= occupancy_ceiling:
            return math.ceil(n / (1 - shrinkage))
        n += 1
    raise ValueError("no feasible staffing within max_agents")
