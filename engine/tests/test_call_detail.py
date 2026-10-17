"""Call-detail sums (DAT-01): ring-no-answer, IVR drop-off, transfers, holds, mutes, incidents."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from wfm_engine.call_detail import (
    KIND_HOLD,
    KIND_MUTE,
    KIND_TRANSFER,
    EventFact,
    IncidentFact,
    IvrCall,
    IvrStep,
    Offer,
    event_summary,
    incident_links,
    ivr_by_queue,
    ring_by_agent,
)

D1, D2 = date(2031, 3, 3), date(2031, 3, 4)


def test_ring_no_answer_counts_rate_and_average_ring_per_login() -> None:
    rows = ring_by_agent(
        [
            Offer("b", True, 4),
            Offer("a", False, 20),
            Offer("a", True, 10),
            Offer("a", False, None),
            Offer("a", False, 30),
        ]
    )
    a, b = rows
    assert (a.login, a.offers, a.answered, a.ring_no_answer) == ("a", 4, 1, 3)
    assert a.ring_no_answer_pct == Decimal("75.0")
    assert a.avg_ring_s == Decimal("20.0")  # the unknown ring time is left out, not counted as 0
    assert (b.login, b.ring_no_answer, b.ring_no_answer_pct) == ("b", 0, Decimal("0.0"))


def test_ring_rows_are_in_login_order_whatever_the_input_order() -> None:
    # Failure caught: a league table (worst first) creeping in through the sort.
    offers = [Offer("zed", False, 1), Offer("amy", False, 1), Offer("zed", False, 1)]
    assert [r.login for r in ring_by_agent(offers)] == ["amy", "zed"]
    assert [r.login for r in ring_by_agent(reversed(offers))] == ["amy", "zed"]


def test_an_average_with_no_known_ring_time_is_none_not_zero() -> None:
    (row,) = ring_by_agent([Offer("a", False, None)])
    assert row.avg_ring_s is None


def test_no_offers_no_rows() -> None:
    assert ring_by_agent([]) == []


def step(n: int, digit: str, activity: str) -> IvrStep:
    return IvrStep(n, digit, activity)


def test_ivr_counts_calls_per_step_and_where_they_dropped_off() -> None:
    s1, s2 = step(1, "1", "Support"), step(2, "2", "Billing")
    calls = [
        IvrCall("Q", (s1, s2), reached_queue=True, abandoned=False),
        IvrCall("Q", (s1, s2), reached_queue=True, abandoned=True),
        IvrCall("Q", (s1,), reached_queue=False, abandoned=False),
        IvrCall("Q", (s1, s2), reached_queue=False, abandoned=False),
        IvrCall("Q", (), reached_queue=True, abandoned=False),  # no IVR step: not an IVR call
    ]
    (q,) = ivr_by_queue(calls)
    assert (q.calls, q.reached_queue, q.ended_in_ivr, q.abandoned_after_ivr) == (4, 2, 2, 1)
    assert [(s.step, s.calls, s.ended_here) for s in q.steps] == [(1, 4, 1), (2, 3, 1)]


def test_ivr_is_kept_per_queue_and_a_repeated_step_counts_the_call_once() -> None:
    s1 = step(1, "1", "Support")
    out = ivr_by_queue(
        [
            IvrCall("B", (s1, s1), reached_queue=True, abandoned=False),
            IvrCall("A", (s1,), reached_queue=True, abandoned=False),
        ]
    )
    assert [q.queue for q in out] == ["A", "B"]
    assert out[1].steps[0].calls == 1


def test_events_are_counted_and_averaged_per_queue_and_per_day() -> None:
    facts = [
        EventFact("Q", D1, KIND_TRANSFER, 60, 4),
        EventFact("Q", D1, KIND_TRANSFER, 90, 6),
        EventFact("Q", D2, KIND_HOLD, 30),
        EventFact("Q", D2, KIND_HOLD, None),
        EventFact("Q", D2, KIND_MUTE, 10),
    ]
    by_day = event_summary(facts, by_day=True)
    assert [(r.day, r.transfers, r.holds, r.mutes) for r in by_day] == [
        (D1, 2, 0, 0),
        (D2, 0, 2, 1),
    ]
    assert by_day[0].avg_transfer_s == Decimal("75.0")
    assert by_day[0].avg_transfer_answer_s == Decimal("5.0")
    assert by_day[0].avg_hold_s is None  # no hold that day: not 0 seconds
    assert by_day[1].avg_hold_s == Decimal(
        "30.0"
    )  # the hold with no duration is counted, not averaged
    total = event_summary(facts, by_day=False)
    assert len(total) == 1
    assert total[0].day is None
    assert (total[0].transfers, total[0].holds, total[0].mutes) == (2, 2, 1)


def test_a_listed_queue_with_no_events_shows_zero_counts_on_the_total() -> None:
    rows = event_summary([], by_day=False, queues=["Quiet"])
    assert [(r.queue, r.transfers, r.holds, r.mutes, r.avg_hold_s) for r in rows] == [
        ("Quiet", 0, 0, 0, None)
    ]
    assert event_summary([], by_day=True, queues=["Quiet"]) == []


def test_incident_links_count_calls_once_and_list_numbers_once() -> None:
    out = incident_links(
        [
            IncidentFact("B", 1, "inc000000000002"),
            IncidentFact("A", 1, "INC000000000001"),
            IncidentFact("A", 1, "INC000000000009"),  # a second disposition of the same call
            IncidentFact("A", 2, "INC000000000001"),  # same incident on another call
            IncidentFact("A", 3, "  "),  # blank: no link
        ]
    )
    a, b = out
    assert (a.queue, a.calls_with_incident, a.incidents) == (
        "A",
        2,
        ["INC000000000001", "INC000000000009"],
    )
    assert (b.queue, b.calls_with_incident, b.incidents) == ("B", 1, ["INC000000000002"])


def test_no_incidents_no_rows() -> None:
    assert incident_links([IncidentFact("A", 1, "")]) == []
