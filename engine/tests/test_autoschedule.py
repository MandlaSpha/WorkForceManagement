import random
from datetime import date, time, timedelta

import pytest

from wfm_engine.autoschedule import Held, Person, Problem, Template, solve
from wfm_engine.availability import window_of
from wfm_engine.compliance import DEFAULT_RULES, Rules
from wfm_engine.roster import (
    breaks_rest_rule,
    consecutive_run,
    shift_slots,
    shift_span,
)

MON = date(2026, 5, 25)
DAYS = [MON + timedelta(days=n) for n in range(7)]
E1 = Template(1, time(7, 0), time(15, 30), 480)
D1 = Template(2, time(9, 0), time(17, 30), 480)
L1 = Template(3, time(13, 0), time(22, 0), 480)
N1 = Template(4, time(22, 0), time(6, 0), 480)
TEMPLATES = (E1, D1, L1, N1)
FULL_WEEK = 40 * 60


def need(day: date, template: Template, people: int = 1) -> dict:
    """The requirement that exactly one shift of this kind would satisfy."""
    return {slot: people for slot in shift_slots(day, template.start, template.end)}


def merged(*parts: dict) -> dict:
    out: dict = {}
    for part in parts:
        for key, n in part.items():
            out[key] = out.get(key, 0) + n
    return out


def problem(people, required, rules=DEFAULT_RULES, templates=TEMPLATES) -> Problem:
    return Problem(
        week_start=MON,
        templates=templates,
        people=tuple(people),
        required=required,
        rules=rules,
        max_time_s=20,
    )


def early_morning(day: date) -> dict:
    """07:00 to 13:00: only E1 covers it among E1 and L1."""
    return {(day, slot): 1 for slot in range(14, 26)}


def worker(pid: int = 1, **kw) -> Person:
    return Person(id=pid, max_week_minutes=kw.pop("minutes", FULL_WEEK), **kw)


def spans_of(solution, template_of=None):
    template_of = template_of or {t.id: t for t in TEMPLATES}
    return [
        (pid, day, shift_span(day, template_of[tid].start, template_of[tid].end))
        for pid, day, tid in solution.placements
    ]


def test_fills_exactly_the_shift_that_meets_the_requirement():
    # Failure caught: nothing placed, or the wrong shape of shift chosen for the demand.
    result = solve(problem([worker()], need(MON, D1)))
    assert result.placements == ((1, MON, D1.id),)
    assert (result.short_before, result.short_after, result.over_after) == (17, 0, 0)
    assert result.status == "optimal"


def test_does_not_overstaff_when_one_person_is_enough():
    # Failure caught: filling everybody in because they are available.
    result = solve(problem([worker(1), worker(2)], need(MON, D1)))
    assert len(result.placements) == 1


def test_two_people_needed_are_both_placed():
    result = solve(problem([worker(1), worker(2)], need(MON, D1, 2)))
    assert {p[0] for p in result.placements} == {1, 2}
    assert result.short_after == 0


def test_a_person_on_leave_or_blocked_is_never_placed_that_day():
    # Failure caught: leave, "not employed" or "rostered elsewhere" ignored by the optimiser.
    away = worker(1, blocked_days=frozenset({MON}))
    result = solve(problem([away], need(MON, D1)))
    assert result.placements == ()
    assert result.short_after == result.short_before == 17


def test_a_cannot_work_window_is_respected_and_the_other_person_takes_it():
    sunday_morning = window_of(0, time(8, 0), time(10, 0))  # Monday
    busy = worker(1, cannot_work=(sunday_morning,))
    free = worker(2)
    result = solve(problem([busy, free], need(MON, D1)))
    assert result.placements == ((2, MON, D1.id),)


def test_a_wish_breaks_a_tie_but_never_a_rule():
    wants = worker(1, would_rather=(window_of(0, time(9, 0), time(17, 30)),))
    result = solve(problem([worker(2), wants], need(MON, D1)))
    assert result.placements == ((1, MON, D1.id),)
    # The same wish on a blocked day changes nothing.
    blocked = worker(
        1, would_rather=(window_of(0, time(9, 0), time(17, 30)),), blocked_days=frozenset({MON})
    )
    assert solve(problem([blocked, worker(2)], need(MON, D1))).placements == ((2, MON, D1.id),)


def test_the_rest_rule_stops_an_early_shift_after_a_late_one():
    # Failure caught: the solver sending somebody from 22:00 to 07:00 with nine hours' rest.
    tue = MON + timedelta(days=1)
    held = worker(1, held=(Held(MON, L1.id, counts_here=False),))
    early = solve(problem([held], early_morning(tue), templates=(L1, E1)))
    assert early.placements == ()  # 22:00 to 07:00 is nine hours
    later = solve(problem([held], need(tue, D1), templates=(L1, D1)))
    assert later.placements == ((1, tue, D1.id),)  # 11 hours is allowed


def test_the_rest_rule_between_two_new_shifts():
    tue = MON + timedelta(days=1)
    required = merged(need(MON, L1), early_morning(tue))
    one = solve(problem([worker(1)], required, templates=(L1, E1)))
    assert len(one.placements) == 1  # one of the two, never both for the same person
    two = solve(problem([worker(1), worker(2)], required, templates=(L1, E1)))
    assert {p[0] for p in two.placements} == {1, 2}


def test_a_longer_rest_rule_changes_the_answer():
    tue = MON + timedelta(days=1)
    morning = {(tue, slot): 1 for slot in range(18, 26)}  # 09:00 to 13:00, only D1 covers it
    required = merged(need(MON, L1), morning)  # L1 ends 22:00, D1 starts 09:00: 11 hours
    templates = (L1, D1)
    assert len(solve(problem([worker(1)], required, templates=templates)).placements) == 2
    stricter = Rules(min_rest_hours=12, max_consecutive_days=6)
    assert len(solve(problem([worker(1)], required, stricter, templates)).placements) == 1


def test_night_shift_over_the_edge_of_the_week_is_respected():
    # A Sunday-night shift held from the previous week leaves no room for a Monday morning shift.
    previous_sunday = MON - timedelta(days=1)
    held = worker(1, held=(Held(previous_sunday, N1.id, counts_here=False),))
    result = solve(problem([held], need(MON, D1)))
    assert result.placements == ()


def test_the_hours_in_the_week_are_a_limit():
    # Failure caught: a person given more than their contract hours.
    required = merged(*(need(d, D1) for d in DAYS[:5]))
    result = solve(problem([worker(1, minutes=16 * 60)], required))
    assert len(result.placements) == 2  # two eight-hour shifts is the whole week
    assert result.short_after > 0


def test_hours_already_held_this_week_count_against_the_limit():
    held = worker(1, minutes=16 * 60, held=(Held(MON, D1.id, counts_here=False),))
    required = merged(*(need(d, D1) for d in DAYS[1:4]))
    result = solve(problem([held], required))
    assert len(result.placements) == 1  # 8 of 16 hours left


def test_days_in_a_row_are_a_limit_counting_what_is_already_held():
    rules = Rules(min_rest_hours=11, max_consecutive_days=3)
    required = merged(*(need(d, D1) for d in DAYS))
    result = solve(problem([worker(1)], required, rules))
    worked = {day for _, day, _ in result.placements}
    for day in worked:
        assert consecutive_run(worked - {day}, day) <= 3
    # Two days already worked just before the week leave room for only one more.
    before = tuple(Held(MON - timedelta(days=n), D1.id, counts_here=False) for n in (1, 2))
    held = worker(1, held=before)
    worked2 = {day for _, day, _ in solve(problem([held], required, rules)).placements}
    everything = worked2 | {h.day for h in before}
    for day in worked2:
        assert consecutive_run(everything - {day}, day) <= 3
    assert not {MON, MON + timedelta(days=1)} <= worked2  # Sat, Sun, Mon, Tue would be four


def test_what_the_queue_already_has_counts_as_covered():
    # Failure caught: adding people to a half-hour that is already met by kept shifts.
    held = worker(1, held=(Held(MON, D1.id, counts_here=True),))
    result = solve(problem([held, worker(2)], need(MON, D1)))
    assert result.placements == ()
    assert (result.short_before, result.short_after, result.kept) == (0, 0, 1)


def test_a_shift_held_on_another_queue_blocks_the_day_but_is_not_coverage_here():
    elsewhere = worker(1, held=(Held(MON, D1.id, counts_here=False),))
    result = solve(problem([elsewhere, worker(2)], need(MON, D1)))
    assert result.placements == ((2, MON, D1.id),)


def test_unknown_requirement_is_not_filled():
    assert solve(problem([worker()], {})).placements == ()


def test_the_hours_are_shared_out_rather_than_piled_on_one_person():
    # Failure caught: one person given every shift while a colleague sits idle.
    required = merged(need(DAYS[0], D1), need(DAYS[2], D1))
    result = solve(problem([worker(1), worker(2)], required))
    assert sorted(p[0] for p in result.placements) == [1, 2]


def test_the_same_problem_gives_the_same_roster():
    required = merged(*(need(d, D1, 2) for d in DAYS[:3]))
    people = [worker(n) for n in (1, 2, 3)]
    assert (
        solve(problem(people, required)).placements == solve(problem(people, required)).placements
    )


def test_nothing_to_do_returns_an_empty_optimal_answer():
    result = solve(problem([worker()], need(MON, D1, 0)))
    assert result.placements == ()
    assert result.short_after == 0


@pytest.mark.parametrize("seed", range(12))
def test_whatever_it_proposes_obeys_every_rule(seed):
    """A property check on random problems, with the rules re-checked by the same functions the
    roster uses by hand. Failure caught: any way the model is looser than the checks."""
    rng = random.Random(seed)
    rules = Rules(
        min_rest_hours=rng.choice([8, 11, 12]), max_consecutive_days=rng.choice([3, 5, 6])
    )
    people = []
    for pid in range(1, rng.randint(3, 6) + 1):
        blocked = frozenset(rng.sample(DAYS, rng.randint(0, 2)))
        held = ()
        if rng.random() < 0.5:
            day = rng.choice([d for d in DAYS if d not in blocked])
            held = (Held(day, rng.choice(TEMPLATES).id, rng.random() < 0.5),)
        people.append(
            worker(pid, minutes=rng.choice([16, 24, 40]) * 60, blocked_days=blocked, held=held)
        )
    required = merged(
        *(need(rng.choice(DAYS), rng.choice(TEMPLATES), rng.randint(1, 3)) for _ in range(8))
    )
    result = solve(problem(people, required, rules))
    by_id = {p.id: p for p in people}
    template_of = {t.id: t for t in TEMPLATES}
    for pid in {p[0] for p in result.placements}:
        mine = [(d, tid) for p, d, tid in result.placements if p == pid]
        person = by_id[pid]
        held_all = [(h.day, h.template_id) for h in person.held]
        days_used = [d for d, _ in mine] + [d for d, _ in held_all]
        assert len(days_used) == len(set(days_used)), "two shifts on one day"
        assert not {d for d, _ in mine} & person.blocked_days
        minutes = sum(template_of[t].paid_minutes for d, t in mine + held_all if d in DAYS)
        assert minutes <= max(
            person.max_week_minutes,
            sum(template_of[h.template_id].paid_minutes for h in person.held if h.day in DAYS),
        )
        spans = [
            shift_span(d, template_of[t].start, template_of[t].end) for d, t in mine + held_all
        ]
        for i, span in enumerate(spans):
            assert not breaks_rest_rule(
                spans[:i] + spans[i + 1 :], span, min_hours=rules.min_rest_hours
            )
        for d, _ in mine:
            assert (
                consecutive_run({x for x in days_used if x != d}, d) <= rules.max_consecutive_days
            )
    assert result.short_after <= result.short_before
