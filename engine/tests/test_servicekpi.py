from datetime import UTC, datetime

from wfm_engine import servicekpi as k

START = datetime(2026, 10, 1, tzinfo=UTC)
END = datetime(2026, 11, 1, tzinfo=UTC)
NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)


def t(opened_day, closed_day=None, fcr=None, csat=None, nps=None, hour=0):
    return k.Ticket(
        datetime(2026, 10, opened_day, hour, tzinfo=UTC),
        datetime(2026, 10, closed_day, tzinfo=UTC) if closed_day else None,
        fcr,
        csat,
        nps,
    )


def run(tickets):
    return k.kpis(tickets, period_start=START, period_end=END, as_of=NOW)


def test_mttr_is_the_mean_hours_of_tickets_closed_in_the_period():
    r = run([t(1, 2), t(1, 3), t(5)])  # 24h and 48h closed; one still open
    assert r.closed == 2
    assert r.mttr_h == 36.0


def test_a_ticket_closed_outside_the_period_is_not_counted():
    old = k.Ticket(datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 2, tzinfo=UTC), True, 5, 10)
    r = run([old])
    assert (r.closed, r.mttr_h, r.fcr_pct, r.csat_average, r.nps) == (0, None, None, None, None)


def test_fcr_uses_only_tickets_that_carry_a_flag():
    r = run([t(1, 2, fcr=True), t(1, 2, fcr=False), t(1, 2, fcr=True), t(1, 2)])
    assert (r.fcr_known, r.fcr_pct) == (3, 66.7)


def test_csat_average_and_satisfied_share():
    r = run([t(1, 2, csat=5), t(1, 2, csat=4), t(1, 2, csat=2), t(1, 2)])
    assert r.csat_count == 3
    assert r.csat_average == 3.67
    assert r.csat_satisfied_pct == 66.7


def test_nps_promoters_less_detractors():
    answers = [10, 9, 9, 8, 7, 6, 0, 3]  # 3 promoters, 3 detractors, 2 passives
    assert run([t(1, 2, nps=a) for a in answers]).nps == 0.0
    assert run([t(1, 2, nps=a) for a in (10, 10, 8, 2)]).nps == 25.0


def test_backlog_age_at_as_of():
    # as_of is 17 Oct 12:00. Open then: the 7th 12:00 (10 d), the 13th 12:00 (4 d), and the 1st
    # 00:00 closed only on the 20th (16.5 d). The one opened on the 20th is not yet opened.
    r = run([t(7, hour=12), t(13, hour=12), t(1, 20), t(20)])
    assert r.backlog_count == 3
    assert r.backlog_oldest_age_days == 16.5
    assert r.backlog_median_age_days == 10.0


def test_nothing_in_the_period_claims_nothing():
    r = run([])
    assert (r.closed, r.mttr_h, r.backlog_count, r.backlog_avg_age_days) == (0, None, 0, None)


def test_a_ticket_closed_at_the_instant_the_period_ends_belongs_to_next_month():
    # Failure caught: the period end made inclusive, so a ticket closed at 00:00 on 1 November
    # is counted in October
    r = k.kpis(
        [k.Ticket(datetime(2026, 10, 1, tzinfo=UTC), END, None, None, None)],
        period_start=START,
        period_end=END,
        as_of=NOW,
    )
    assert r.closed == 0
