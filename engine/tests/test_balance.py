from wfm_engine import balance as b


def load(i: int, req: int, sched: int) -> b.QueueLoad:
    return b.QueueLoad(i, f"Q{i}", req, sched)


def test_classification_and_ratio():
    assert b.classify(load(1, 120, 100)) == b.STRETCHED
    assert b.classify(load(1, 70, 100)) == b.SLACK
    assert b.classify(load(1, 100, 100)) == b.BALANCED
    assert b.classify(load(1, 0, 100)) == b.UNKNOWN
    assert b.load_ratio(load(1, 10, 0)) == 10.0  # needed and nobody scheduled


def test_moves_a_skilled_person_from_slack_to_stretched():
    loads = [load(1, 140, 100), load(2, 40, 100)]
    movers = [b.Mover(7, 2, frozenset({1, 2}), 16), b.Mover(8, 2, frozenset({2}), 16)]
    assert b.suggest_moves(loads, movers) == [b.Suggestion(7, 2, 1, 16)]


def test_never_leaves_the_source_short_and_stops_when_target_is_met():
    loads = [load(1, 120, 100), load(2, 70, 100)]  # target short 20, source spare 30
    movers = [b.Mover(1, 2, frozenset({1}), 20), b.Mover(2, 2, frozenset({1}), 20)]
    assert b.suggest_moves(loads, movers) == [b.Suggestion(1, 2, 1, 20)]


def test_balanced_queues_give_no_suggestions_and_nobody_twice():
    assert b.suggest_moves([load(1, 100, 100)], [b.Mover(1, 1, frozenset({1}), 8)]) == []
    loads = [load(1, 200, 100), load(2, 200, 100), load(3, 10, 200)]
    movers = [b.Mover(5, 3, frozenset({1, 2}), 40)]
    assert len(b.suggest_moves(loads, movers)) == 1


def test_exactly_110_percent_is_balanced_not_stretched():
    # Failure caught: OVER_RATIO compared with >= so a queue at exactly 110% reads as stretched
    assert b.classify(load(1, 110, 100)) == b.BALANCED


def test_a_move_that_leaves_the_source_exactly_covered_is_allowed():
    # Failure caught: the source-short guard flipped to >= 0, refusing a move that leaves the
    # source exactly at its requirement (source spare 30, mover puts 30 half-hours on the phones)
    loads = [load(1, 120, 100), load(2, 70, 100)]
    movers = [b.Mover(3, 2, frozenset({1}), 30)]
    assert b.suggest_moves(loads, movers) == [b.Suggestion(3, 2, 1, 30)]
