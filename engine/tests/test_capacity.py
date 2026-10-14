import pytest

from wfm_engine.capacity import Split, combine, peak, split_demand


class TestSplitDemand:
    """The tender's pools: 100 permanent and 250 seasonal, 350 in all."""

    def test_a_quiet_day_is_covered_by_permanent_staff_alone(self) -> None:
        assert split_demand(60, 100, 250) == Split(60, 0, 0)

    def test_permanent_staff_fill_first_then_seasonal_agents(self) -> None:
        # 180 at the same time: all 100 permanent, 80 seasonal.
        assert split_demand(180, 100, 250) == Split(100, 80, 0)

    def test_exactly_the_whole_workforce_is_not_overflow(self) -> None:
        assert split_demand(350, 100, 250) == Split(100, 250, 0)

    def test_one_more_than_everybody_is_overflow(self) -> None:
        assert split_demand(351, 100, 250) == Split(100, 250, 1)
        assert split_demand(420, 100, 250) == Split(100, 250, 70)

    def test_nobody_needed_needs_nobody(self) -> None:
        assert split_demand(0, 100, 250) == Split(0, 0, 0)

    def test_no_seasonal_pool_sends_the_excess_straight_to_overflow(self) -> None:
        assert split_demand(130, 100, 0) == Split(100, 0, 30)

    def test_the_parts_always_add_up_to_the_peak(self) -> None:
        for demand in range(0, 500, 7):
            s = split_demand(demand, 100, 250)
            assert s.permanent + s.seasonal + s.overflow == demand

    @pytest.mark.parametrize("args", [(-1, 100, 250), (10, -1, 250), (10, 100, -1)])
    def test_negative_numbers_are_refused(self, args: tuple[int, int, int]) -> None:
        with pytest.raises(ValueError, match="negative"):
            split_demand(*args)


class TestCombineQueues:
    def test_adds_the_queues_slot_by_slot(self) -> None:
        assert combine([[1, 2, 3], [10, 0, 5]]) == [11, 2, 8]

    def test_a_slot_unknown_in_any_queue_is_unknown_not_zero(self) -> None:
        assert combine([[1, None, 3], [10, 4, 5]]) == [11, None, 8]

    def test_a_queue_with_zero_required_adds_nothing_but_is_known(self) -> None:
        assert combine([[0, 0], [2, 3]]) == [2, 3]

    def test_no_queues_means_no_slots(self) -> None:
        assert combine([]) == []

    def test_queues_of_different_lengths_are_refused(self) -> None:
        with pytest.raises(ValueError, match="same slots"):
            combine([[1, 2], [1]])


class TestPeak:
    def test_the_busiest_moment_of_a_complete_day(self) -> None:
        assert peak([3, 9, 4]) == (9, True)

    def test_unknown_moments_make_the_peak_a_lower_bound(self) -> None:
        assert peak([3, None, 4]) == (4, False)

    def test_nothing_known_is_no_peak_not_zero(self) -> None:
        assert peak([None, None]) == (None, False)
        assert peak([]) == (None, False)

    def test_a_day_of_zeros_is_a_known_peak_of_zero(self) -> None:
        assert peak([0, 0]) == (0, True)
