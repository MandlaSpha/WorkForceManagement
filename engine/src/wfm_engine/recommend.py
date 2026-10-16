"""Ranked, concrete fixes for a roster week's gaps (requirement REC-01).

Pure: no Django, no clock, no I/O. Takes the same `Problem` the auto-scheduler does, with the
roster as it stands (every shift already there is `held`), and proposes single moves that each make
the week better: add a free person to a shift, or change a person's shift on the queue to a
different one (which covers moving or extending a shift). Every move is checked against the same
rules the roster enforces, so applying one can never be refused for a rule; and each is scored by
the aim the auto-scheduler uses, so what is ranked first is what that would also have wanted.

Not covered yet: moving a person between queues (it needs both queues' plans together).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from . import availability
from .autoschedule import OVER_WEIGHT, SHIFT_COST, UNDER_WEIGHT, Person, Problem, Template
from .roster import SlotKey, breaks_rest_rule, consecutive_run, coverage, shift_slots, shift_span

ADD = "add"
CHANGE = "change"


@dataclass(frozen=True)
class Recommendation:
    kind: str  # "add" a person to a shift, or "change" the shift they already have
    person_id: int
    day: date
    template_id: int
    replaces: int | None  # the shift being changed (kind "change"), else None
    closes: int  # people-half-hours no longer short
    adds_over: int  # half-hours that would have one person too many that did not before
    score: int  # what the auto-scheduler's aim makes of it; always above zero


def _slots(template: Template, day: date) -> list[SlotKey]:
    return shift_slots(day, template.start, template.end)


def _gap_and_over(
    required: Mapping[SlotKey, int], covered: Mapping[SlotKey, int], slots: set[SlotKey]
) -> tuple[int, int]:
    short = over = 0
    for slot in slots:
        need = required.get(slot)
        if need is None:
            continue
        have = covered.get(slot, 0)
        short += max(need - have, 0)
        over += max(have - need, 0)
    return short, over


def _allowed(
    problem: Problem, person: Person, day: date, template: Template, others: list[tuple[date, int]]
) -> bool:
    """Would the roster accept this person on this shift this day, given their other shifts?"""
    if day in person.blocked_days:
        return False
    if availability.touches(person.cannot_work, day, template.start, template.end):
        return False
    by_id = {t.id: t for t in problem.templates}
    candidate = shift_span(day, template.start, template.end)
    spans = [shift_span(d, by_id[t].start, by_id[t].end) for d, t in others]
    rules = problem.rules
    if breaks_rest_rule(spans, candidate, min_hours=rules.min_rest_hours):
        return False
    if consecutive_run({d for d, _ in others}, day) > rules.max_consecutive_days:
        return False
    week = {problem.week_start + timedelta(days=n) for n in range(7)}
    used = sum(by_id[t].paid_minutes for d, t in others if d in week)
    return used + template.paid_minutes <= person.max_week_minutes


def recommend(problem: Problem, limit: int = 10) -> list[Recommendation]:
    templates = {t.id: t for t in problem.templates}
    week = [problem.week_start + timedelta(days=n) for n in range(7)]
    here: Counter[SlotKey] = coverage(
        (h.day, templates[h.template_id].start, templates[h.template_id].end)
        for p in problem.people
        for h in p.held
        if h.counts_here
    )

    best: dict[tuple[str, date, int, int | None], tuple[int, Recommendation]] = {}
    for person in problem.people:
        minutes = sum(templates[h.template_id].paid_minutes for h in person.held if h.day in week)
        for day in week:
            today = [h for h in person.held if h.day == day]
            if any(not h.counts_here for h in today):
                continue  # on another queue that day
            current = today[0].template_id if today else None
            others = [(h.day, h.template_id) for h in person.held if h.day != day]
            for template in problem.templates:
                if template.id == current:
                    continue
                if not _allowed(problem, person, day, template, others):
                    continue
                gained = set(_slots(template, day))
                lost = set(_slots(templates[current], day)) if current is not None else set()
                touched = gained | lost
                before = _gap_and_over(problem.required, here, touched)
                after_cov = here.copy()
                after_cov.subtract(lost)
                after_cov.update(gained)
                after = _gap_and_over(problem.required, after_cov, touched)
                closes = before[0] - after[0]
                adds_over = after[1] - before[1]
                score = UNDER_WEIGHT * closes - OVER_WEIGHT * adds_over
                if current is None:
                    score -= SHIFT_COST
                if closes <= 0 or score <= 0:
                    continue
                key = (CHANGE if current is not None else ADD, day, template.id, current)
                found = Recommendation(
                    kind=key[0],
                    person_id=person.id,
                    day=day,
                    template_id=template.id,
                    replaces=current,
                    closes=closes,
                    adds_over=adds_over,
                    score=score,
                )
                # Many people can make the same move: offer the one with the lightest week.
                rank = minutes
                if key not in best or (rank, person.id) < (best[key][0], best[key][1].person_id):
                    best[key] = (rank, found)

    ranked = sorted(
        (rec for _, rec in best.values()),
        key=lambda r: (-r.score, r.day, r.template_id, r.person_id),
    )
    return ranked[:limit]
