from datetime import date, time

from wfm_engine.flex import Candidate, Donor, suggest
from wfm_engine.roster import shift_slots

MON = date(2026, 5, 25)
START, END = time(9, 0), time(11, 0)  # four half-hours
SLOTS = shift_slots(MON, START, END)


def cell(n: int | None) -> dict:
    return {s: n for s in SLOTS}


def cand(person=1, donor=10) -> Candidate:
    return Candidate(person, donor, MON, 7, START, END)


def test_borrows_a_person_the_donor_can_spare():
    got = suggest(cell(2), cell(1), {10: Donor(cell(1), cell(2))}, [cand()])
    assert len(got) == 1
    assert (got[0].person_id, got[0].closes, got[0].adds_over) == (1, 4, 0)


def test_never_leaves_the_donor_short():
    assert suggest(cell(2), cell(1), {10: Donor(cell(2), cell(2))}, [cand()]) == []


def test_unknown_donor_requirement_is_not_spare():
    assert suggest(cell(2), cell(1), {10: Donor(cell(None), cell(5))}, [cand()]) == []


def test_donor_short_in_one_half_hour_blocks_the_whole_move():
    covered = cell(2)
    covered[SLOTS[-1]] = 1
    assert suggest(cell(2), cell(1), {10: Donor(cell(1), covered)}, [cand()]) == []


def test_no_gap_on_the_borrowing_queue_means_no_move():
    assert suggest(cell(1), cell(1), {10: Donor(cell(1), cell(3))}, [cand()]) == []


def test_unknown_donor_queue_is_ignored():
    assert suggest(cell(2), cell(1), {}, [cand()]) == []


def test_best_net_gain_ranks_first_and_limit_applies():
    required = cell(2)
    covered = {s: (1 if i < 2 else 2) for i, s in enumerate(SLOTS)}  # short for 2 half-hours
    donors = {10: Donor(cell(1), cell(2))}
    full = Candidate(1, 10, MON, 7, START, END)
    short = Candidate(2, 10, MON, 8, START, time(10, 0))  # only the two short half-hours
    got = suggest(required, covered, donors, [full, short], limit=5)
    # The full shift closes 2 but would overstaff 2, so it is not worth it; the short one is.
    assert [f.person_id for f in got] == [2]
    assert (got[0].closes, got[0].adds_over) == (2, 0)


def test_limit_applies():
    donors = {10: Donor(cell(1), cell(3))}
    many = [cand(person=n) for n in range(1, 5)]
    assert len(suggest(cell(2), cell(1), donors, many, limit=2)) == 2
