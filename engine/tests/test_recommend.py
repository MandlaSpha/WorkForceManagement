import random
from datetime import date, time, timedelta

import pytest

from wfm_engine.autoschedule import Held, Person, Problem, Template
from wfm_engine.availability import window_of
from wfm_engine.compliance import DEFAULT_RULES, Rules
from wfm_engine.recommend import ADD, CHANGE, recommend
from wfm_engine.roster import breaks_rest_rule, coverage, shift_slots, shift_span

MON = date(2026, 5, 25)
TUE = MON + timedelta(days=1)
DAYS = [MON + timedelta(days=n) for n in range(7)]
E1 = Template(1, time(7, 0), time(15, 30), 480)
D1 = Template(2, time(9, 0), time(17, 30), 480)
L1 = Template(3, time(13, 0), time(22, 0), 480)
TEMPLATES = (E1, D1, L1)
BY_ID = {t.id: t for t in TEMPLATES}


def need(day: date, template: Template, people: int = 1) -> dict:
    return {slot: people for slot in shift_slots(day, template.start, template.end)}


def problem(people, required, rules=DEFAULT_RULES, templates=TEMPLATES) -> Problem:
    return Problem(MON, templates, tuple(people), required, rules)


def worker(pid=1, **kw) -> Person:
    return Person(id=pid, max_week_minutes=kw.pop("minutes", 40 * 60), **kw)


def held_here(day, template) -> Held:
    return Held(day, template.id, counts_here=True)


def test_a_free_person_is_recommended_for_an_uncovered_shift():
    # Failure caught: a gap with a free, rule-respecting person and no suggestion.
    found = recommend(problem([worker()], need(MON, D1)))
    top = found[0]
    assert (top.kind, top.person_id, top.day, top.template_id) == (ADD, 1, MON, D1.id)
    assert (top.closes, top.adds_over, top.replaces) == (17, 0, None)
    assert top.score == 30 * 17 - 3


def test_changing_a_shift_is_offered_when_it_closes_more_than_it_loses():
    # One person on 07:00 to 15:30, the demand runs to 17:30: moving them to D1 closes the end.
    held = worker(1, held=(held_here(MON, E1),))
    found = recommend(problem([held], need(MON, D1)))
    change = next(r for r in found if r.kind == CHANGE)
    assert (change.person_id, change.template_id, change.replaces) == (1, D1.id, E1.id)
    assert change.closes == 4  # 15:30 to 17:30


def test_a_change_that_opens_a_new_gap_is_not_a_gain():
    # Failure caught: moving somebody off a half-hour that needs them to fill one that needs fewer.
    held = worker(1, held=(held_here(MON, D1),))
    required = need(MON, D1)  # exactly met by D1 already
    assert recommend(problem([held], required)) == []


def test_nothing_is_recommended_when_there_is_no_gap():
    held = worker(1, held=(held_here(MON, D1),))
    assert recommend(problem([held, worker(2)], need(MON, D1))) == []


def test_somebody_who_cannot_work_is_never_recommended():
    # Failure caught: suggesting somebody on leave, in a cannot-work window, or on another queue.
    away = worker(1, blocked_days=frozenset({MON}))
    cannot = worker(2, cannot_work=(window_of(0, time(8, 0), time(12, 0)),))
    elsewhere = worker(3, held=(Held(MON, D1.id, counts_here=False),))
    found = recommend(problem([away, cannot, elsewhere], need(MON, D1)))
    assert [r for r in found if r.day == MON and r.template_id == D1.id] == []


def test_the_rest_rule_is_respected_for_both_add_and_change():
    late = worker(1, held=(held_here(MON, L1),))  # ends 22:00
    early_need = {(TUE, slot): 1 for slot in range(14, 18)}  # 07:00 to 09:00: only E1 covers it
    found = recommend(problem([late], early_need))
    assert [r for r in found if r.template_id == E1.id and r.day == TUE] == []


def test_the_hours_in_the_week_are_respected():
    full = worker(
        1, minutes=8 * 60, held=(held_here(DAYS[3], D1),)
    )  # the whole week's hours are already used
    assert recommend(problem([full], need(MON, D1))) == []


def test_the_compliance_rules_in_force_are_respected():
    held = worker(1, held=(held_here(MON, L1),))
    required = {(TUE, slot): 1 for slot in range(18, 20)}  # 09:00 to 10:00: only D1 covers it
    assert any(r.template_id == D1.id for r in recommend(problem([held], required)))
    stricter = Rules(min_rest_hours=12, max_consecutive_days=6)
    assert not any(r.template_id == D1.id for r in recommend(problem([held], required, stricter)))


def test_a_move_that_overstaffs_far_more_than_it_closes_is_not_worth_recommending():
    # One short half-hour against a 17-half-hour shift: it would overstaff 16 for nothing.
    required = {(MON, 20): 1}
    required.update({(MON, slot): 0 for slot in range(18, 35) if slot != 20})
    assert recommend(problem([worker()], required, templates=(D1,))) == []


def test_the_biggest_gain_comes_first_and_the_list_is_limited():
    half_a_day = {(TUE, slot): 1 for slot in range(18, 26)}  # 09:00 to 13:00
    required = {**need(MON, D1), **half_a_day}
    people = [worker(n) for n in range(1, 4)]
    found = recommend(problem(people, required, templates=(D1,)), limit=3)
    assert [(r.day, r.closes) for r in found] == [(MON, 17), (TUE, 8)]
    assert [r.score for r in found] == sorted((r.score for r in found), reverse=True)
    assert len(recommend(problem(people, required, templates=(D1,)), limit=1)) == 1


def test_of_the_people_who_could_the_lightest_week_is_offered():
    busy = worker(1, held=(held_here(TUE, D1),))
    free = worker(2)
    found = recommend(problem([busy, free], need(MON, D1)))
    assert found[0].person_id == 2


def test_the_same_input_gives_the_same_list():
    people = [worker(n) for n in range(1, 4)]
    assert recommend(problem(people, need(MON, D1))) == recommend(problem(people, need(MON, D1)))


@pytest.mark.parametrize("seed", range(10))
def test_every_recommendation_is_legal_and_closes_what_it_says(seed):
    """Failure caught: a score that disagrees with the real effect, or a move the roster refuses."""
    rng = random.Random(seed)
    people = []
    for pid in range(1, rng.randint(3, 6) + 1):
        held = ()
        if rng.random() < 0.6:
            held = (Held(rng.choice(DAYS), rng.choice(TEMPLATES).id, rng.random() < 0.7),)
        people.append(
            worker(
                pid,
                minutes=rng.choice([16, 24, 40]) * 60,
                blocked_days=frozenset(rng.sample(DAYS, rng.randint(0, 1))),
                held=held,
            )
        )
    required: dict = {}
    for _ in range(6):
        for slot, n in need(rng.choice(DAYS), rng.choice(TEMPLATES), rng.randint(1, 2)).items():
            required[slot] = required.get(slot, 0) + n
    prob = problem(people, required)

    def short(held_people) -> int:
        cov = coverage(
            (h.day, BY_ID[h.template_id].start, BY_ID[h.template_id].end)
            for p in held_people
            for h in p.held
            if h.counts_here
        )
        return sum(max(n - cov.get(slot, 0), 0) for slot, n in required.items())

    base = short(people)
    for rec in recommend(prob, limit=50):
        person = next(p for p in people if p.id == rec.person_id)
        others = [h for h in person.held if h.day != rec.day]
        assert not any(h.day == rec.day and not h.counts_here for h in person.held)
        assert rec.day not in person.blocked_days
        candidate = shift_span(rec.day, BY_ID[rec.template_id].start, BY_ID[rec.template_id].end)
        spans = [
            shift_span(h.day, BY_ID[h.template_id].start, BY_ID[h.template_id].end) for h in others
        ]
        assert not breaks_rest_rule(spans, candidate, min_hours=11)
        week_minutes = sum(BY_ID[h.template_id].paid_minutes for h in others)
        assert week_minutes + BY_ID[rec.template_id].paid_minutes <= person.max_week_minutes
        changed = [
            Person(
                id=p.id,
                max_week_minutes=p.max_week_minutes,
                blocked_days=p.blocked_days,
                held=(*others, Held(rec.day, rec.template_id, True))
                if p.id == rec.person_id
                else p.held,
            )
            for p in people
        ]
        assert base - short(changed) == rec.closes
        assert rec.score > 0
