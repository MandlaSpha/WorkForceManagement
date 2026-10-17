from datetime import date

from wfm_engine.forecast_range import Slot, summarise

MON, TUE, WED = date(2031, 3, 3), date(2031, 3, 4), date(2031, 3, 5)


def test_a_day_with_no_slots_has_no_forecast_and_is_not_a_day_of_zero_calls() -> None:
    # Failure caught: a missing day shown as 0 calls / 0 people, which a planner would read as
    # "closed" and staff to nothing.
    r = summarise([Slot(MON, 20, 10, 180, 4)], [MON, TUE])
    assert r.days[1].has_forecast is False
    assert r.days[1].peak_required is None
    assert r.days[1].hours_required is None
    assert r.days[1].required_by_slot == ()


def test_totals_peak_and_hours_are_added_up_by_hand() -> None:
    # 10:00 -> 10 calls, 4 people; 10:30 -> 30 calls, 6 people. Hours = (4 + 6) * 0.5 = 5.
    # AHT is call-weighted: (10*100 + 30*200) / 40 = 175, not the plain mean 150.
    r = summarise([Slot(MON, 20, 10, 100, 4), Slot(MON, 21, 30, 200, 6)], [MON])
    d = r.days[0]
    assert (d.calls, d.aht_s, d.peak_required, d.hours_required) == (40, 175, 6, 5)
    assert d.busiest_slot == 21
    assert d.required_by_slot[20] == 4
    assert len(d.required_by_slot) == 48


def test_a_busy_half_hour_with_no_requirement_withholds_the_peak_and_hours() -> None:
    # Failure caught: claiming "peak 4" when the 10:30 half-hour (which has calls) could not be
    # staffed and may need more.
    r = summarise([Slot(MON, 20, 10, 100, 4), Slot(MON, 21, 30, 200, None)], [MON])
    d = r.days[0]
    assert (d.complete, d.peak_required, d.hours_required) == (False, None, None)
    assert d.calls == 40  # calls are still known


def test_a_quiet_half_hour_with_no_stored_requirement_does_not_make_the_day_incomplete() -> None:
    r = summarise([Slot(MON, 20, 10, 100, 4), Slot(MON, 3, 0, None, None)], [MON])
    assert r.days[0].complete is True
    assert r.days[0].peak_required == 4


def test_busiest_and_quietest_ignore_days_without_a_forecast() -> None:
    # Failure caught: an unforecast day winning "quietest" with its 0 calls.
    r = summarise(
        [Slot(MON, 20, 50, 100, 5), Slot(WED, 20, 5, 100, 2)],
        [MON, TUE, WED],
    )
    assert (r.busiest_day, r.quietest_day) == (MON, WED)


def test_no_busiest_or_quietest_when_the_days_are_alike_or_there_is_only_one() -> None:
    same = summarise([Slot(MON, 20, 5, 100, 2), Slot(TUE, 20, 5, 100, 2)], [MON, TUE])
    assert (same.busiest_day, same.quietest_day) == (None, None)
    one = summarise([Slot(MON, 20, 5, 100, 2)], [MON, TUE])
    assert (one.busiest_day, one.quietest_day) == (None, None)


def test_ties_pick_the_earlier_day_so_the_same_data_gives_the_same_marks() -> None:
    r = summarise(
        [Slot(WED, 20, 9, 1, 1), Slot(TUE, 20, 9, 1, 1), Slot(MON, 20, 1, 1, 1)],
        [MON, TUE, WED],
    )
    assert (r.busiest_day, r.quietest_day) == (TUE, MON)


def test_aht_is_none_when_no_call_has_a_handling_time() -> None:
    assert summarise([Slot(MON, 20, 0, None, 0)], [MON]).days[0].aht_s is None
