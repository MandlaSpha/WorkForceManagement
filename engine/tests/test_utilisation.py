from decimal import Decimal

import pytest

from wfm_engine import utilisation as u


def test_utilisation_and_gap_against_a_weighted_target():
    result = u.utilisation(
        [u.Block(480, 360, Decimal(80)), u.Block(480, 480, Decimal(60)), u.Block(240, 0, None)]
    )
    assert (result.worked_min, result.billable_min) == (1200, 840)
    assert result.utilisation_pct == 70.0
    assert result.target_pct == 70.0  # 80 and 60 held equally; the non-contract block has none
    assert result.gap_pct == 0.0


def test_negative_gap_when_short_of_target():
    result = u.utilisation([u.Block(600, 300, Decimal(75))])
    assert result.utilisation_pct == 50.0
    assert result.gap_pct == -25.0


def test_nothing_worked_claims_nothing():
    result = u.utilisation([])
    assert (result.utilisation_pct, result.target_pct, result.gap_pct) == (None, None, None)


def test_no_contract_means_no_target_and_no_gap():
    result = u.utilisation([u.Block(480, 0)])
    assert result.utilisation_pct == 0.0
    assert result.target_pct is None
    assert result.gap_pct is None


def test_billable_cannot_exceed_worked():
    with pytest.raises(ValueError, match=r"negative|exceed"):
        u.utilisation([u.Block(60, 90)])


def test_billable_minutes():
    assert u.billable_minutes(480, on_contract=True, non_billable_min=90) == 390
    assert u.billable_minutes(480, on_contract=False, non_billable_min=0) == 0
    assert u.billable_minutes(60, on_contract=True, non_billable_min=90) == 0
    with pytest.raises(ValueError, match=r"negative|exceed"):
        u.billable_minutes(-1, on_contract=True, non_billable_min=0)


def test_cost_of_rounds_half_up_to_the_cent():
    assert u.cost_of(Decimal("100.00"), 90) == Decimal("150.00")
    assert u.cost_of(Decimal("0.01"), 30) == Decimal("0.01")  # 0.005 rounds up
    with pytest.raises(ValueError, match=r"negative|exceed"):
        u.cost_of(Decimal(-1), 10)


def test_allocate_adds_up_to_the_total_exactly():
    parts = u.allocate(Decimal("100.00"), {"a": 1, "b": 1, "c": 1})
    assert sum(parts.values()) == Decimal("100.00")
    assert sorted(parts.values()) == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]


def test_allocate_follows_the_shares_and_handles_none():
    assert u.allocate(Decimal("200.00"), {"a": 3, "b": 1}) == {
        "a": Decimal("150.00"),
        "b": Decimal("50.00"),
    }
    assert u.allocate(Decimal("50.00"), {}) == {}
    assert u.allocate(Decimal("50.00"), {"a": 0}) == {"a": Decimal("0.00")}


def test_blended_rate():
    assert u.blended_hourly_rate([Decimal(100), Decimal(200)]) == Decimal(150)
    assert u.blended_hourly_rate([]) is None


def test_ticket_cost_counts_unestimated_but_does_not_price_them():
    result = u.ticket_cost([60, 30, None], Decimal("120.00"))
    assert (result.closed, result.estimated, result.effort_min) == (3, 2, 90)
    assert result.cost == Decimal("180.00")
    assert result.per_ticket == Decimal("90.00")


def test_ticket_cost_unknown_without_a_rate_or_an_estimate():
    assert u.ticket_cost([60], None).cost is None
    assert u.ticket_cost([None, None], Decimal(100)).per_ticket is None
    assert u.ticket_cost([], Decimal(100)).closed == 0


def test_share_pct():
    assert u.share_pct(Decimal(25), Decimal(200)) == 12.5
    assert u.share_pct(Decimal(25), None) is None
    assert u.share_pct(Decimal(25), Decimal(0)) is None
