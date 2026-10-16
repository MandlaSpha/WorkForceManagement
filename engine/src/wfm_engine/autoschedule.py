"""Automatic roster for one queue and one week (requirements SCH-05, PLN-04).

Pure: no Django, no clock, no I/O. The caller says who may work when, what is already held, and how
many people each half-hour needs; this finds the shifts to add. It is a model for the CP-SAT solver
(Google OR-Tools): one yes/no choice per person, day and shift, under the same rules the roster
checks by hand, so nothing it proposes can be one the roster would refuse.

Hard rules: at most one shift a day, rest between shifts, days in a row, hours in the week (the
lower of the contract and the cap), nothing on a blocked day or in a "cannot work" window.
Wishes only tip a tie. The aim, in order: do not leave a half-hour short (weighted heavily), do not
overstaff, spread hours evenly, and use as few shifts as will do.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from ortools.sat.python import cp_model

from . import availability
from .compliance import Rules
from .roster import SlotKey, breaks_rest_rule, coverage, shift_slots, shift_span

UNDER_WEIGHT = 30  # a half-hour short, per person missing
OVER_WEIGHT = 10  # a half-hour with one person too many
SHIFT_COST = 3  # every shift added costs something, so none is added for nothing
WISH_BONUS = 2  # a shift inside a "would rather work" window, taken off its cost
SPREAD_WEIGHT = 2  # per half-hour on the most heavily loaded person
LOOK_AROUND_DAYS = 3  # rest of up to 24 h can only be broken by a shift this many days away


@dataclass(frozen=True)
class Template:
    id: int
    start: time
    end: time
    paid_minutes: int


@dataclass(frozen=True)
class Held:
    """A shift the person already has. It counts against their rules; if `counts_here`, it is on
    the queue being planned and so also counts towards its coverage."""

    day: date
    template_id: int
    counts_here: bool


@dataclass(frozen=True)
class Person:
    id: int
    max_week_minutes: int  # the lower of the contract hours and any cap, in minutes
    blocked_days: frozenset[date] = frozenset()  # leave, not employed, rostered elsewhere
    cannot_work: tuple[availability.Window, ...] = ()
    would_rather: tuple[availability.Window, ...] = ()
    held: tuple[Held, ...] = ()


@dataclass(frozen=True)
class Problem:
    week_start: date  # a Monday
    templates: tuple[Template, ...]
    people: tuple[Person, ...]
    required: Mapping[SlotKey, int]  # only half-hours whose requirement is known
    rules: Rules
    max_time_s: float = 10.0


@dataclass(frozen=True)
class Solution:
    status: str  # optimal, feasible, or none (no answer found)
    placements: tuple[tuple[int, date, int], ...] = ()  # (person id, day, template id)
    short_before: int = 0  # people-half-hours short with nothing added
    short_after: int = 0
    over_after: int = 0
    kept: int = 0  # shifts already held on this queue, left as they are


def _days(week_start: date) -> list[date]:
    return [week_start + timedelta(days=n) for n in range(7)]


def _short_and_over(
    required: Mapping[SlotKey, int], covered: Mapping[SlotKey, int]
) -> tuple[int, int]:
    short = sum(max(need - covered.get(slot, 0), 0) for slot, need in required.items())
    over = sum(max(covered.get(slot, 0) - need, 0) for slot, need in required.items())
    return short, over


def solve(problem: Problem) -> Solution:
    templates = {t.id: t for t in problem.templates}
    days = _days(problem.week_start)
    week = set(days)
    rules = problem.rules

    def span(day: date, template_id: int) -> tuple[datetime, datetime]:
        t = templates[template_id]
        return shift_span(day, t.start, t.end)

    # What the queue already has covered (kept shifts, including a Sunday-night shift spilling in).
    kept_here = [
        (h.day, templates[h.template_id].start, templates[h.template_id].end)
        for p in problem.people
        for h in p.held
        if h.counts_here
    ]
    held_coverage: Counter[SlotKey] = coverage(kept_here)
    short_before, _ = _short_and_over(problem.required, held_coverage)

    model = cp_model.CpModel()
    choice: dict[tuple[int, date, int], cp_model.IntVar] = {}
    by_person_day: dict[tuple[int, date], list[cp_model.IntVar]] = {}

    for person in problem.people:
        busy_days = {h.day for h in person.held}
        held_spans = [span(h.day, h.template_id) for h in person.held]
        for day in days:
            if day in person.blocked_days or day in busy_days:
                continue
            for t in problem.templates:
                if availability.touches(person.cannot_work, day, t.start, t.end):
                    continue
                candidate = shift_span(day, t.start, t.end)
                if breaks_rest_rule(held_spans, candidate, min_hours=rules.min_rest_hours):
                    continue
                var = model.new_bool_var(f"x_{person.id}_{day}_{t.id}")
                choice[(person.id, day, t.id)] = var
                by_person_day.setdefault((person.id, day), []).append(var)

    for vars_that_day in by_person_day.values():
        model.add_at_most_one(vars_that_day)

    # Rest between two shifts both being chosen.
    for person in problem.people:
        keys = [k for k in choice if k[0] == person.id]
        for i, (_, d1, t1) in enumerate(keys):
            for _, d2, t2 in keys[i + 1 :]:
                gap = abs((d2 - d1).days)
                if gap > LOOK_AROUND_DAYS or d1 == d2:
                    continue
                first, second = (d1, t1), (d2, t2)
                if d2 < d1:
                    first, second = second, first
                if breaks_rest_rule([span(*first)], span(*second), min_hours=rules.min_rest_hours):
                    model.add_bool_or(
                        [
                            choice[(person.id, d1, t1)].negated(),
                            choice[(person.id, d2, t2)].negated(),
                        ]
                    )

    # Days in a row and hours in the week.
    for person in problem.people:
        held_days = {h.day for h in person.held}
        window = rules.max_consecutive_days + 1
        first_day = days[0] - timedelta(days=window - 1)
        for offset in range(0, 7 + window - 1):
            start = first_day + timedelta(days=offset)
            run = [start + timedelta(days=n) for n in range(window)]
            constants = sum(1 for d in run if d in held_days)
            variables = [v for d in run for v in by_person_day.get((person.id, d), [])]
            if variables:
                model.add(sum(variables) <= max(rules.max_consecutive_days - constants, 0))
        held_minutes = sum(
            templates[h.template_id].paid_minutes for h in person.held if h.day in week
        )
        room = max(person.max_week_minutes - held_minutes, 0)
        mine = [
            (var, templates[k[2]].paid_minutes) for k, var in choice.items() if k[0] == person.id
        ]
        if mine:
            model.add(sum(var * minutes for var, minutes in mine) <= room)

    # Coverage against the requirement.
    cover_terms: dict[SlotKey, list[cp_model.IntVar]] = {}
    for (_, day, template_id), var in choice.items():
        t = templates[template_id]
        for slot in shift_slots(day, t.start, t.end):
            if slot in problem.required:
                cover_terms.setdefault(slot, []).append(var)
    objective: list[cp_model.LinearExpr] = []
    for slot, need in problem.required.items():
        here = held_coverage.get(slot, 0)
        terms = cover_terms.get(slot, [])
        if not terms and here >= need:
            continue
        short = model.new_int_var(0, need, f"short_{slot}")
        over = model.new_int_var(0, len(terms) + here, f"over_{slot}")
        model.add(here + sum(terms) + short - over == need)
        objective.append(UNDER_WEIGHT * short)
        objective.append(OVER_WEIGHT * over)

    people = {p.id: p for p in problem.people}
    for (person_id, day, template_id), var in choice.items():
        t = templates[template_id]
        person = people[person_id]
        wished = availability.touches(person.would_rather, day, t.start, t.end)
        objective.append((SHIFT_COST - (WISH_BONUS if wished else 0)) * var)

    # Spread the hours: keep the most heavily loaded person as light as the requirement allows.
    loads = []
    for person in problem.people:
        mine = [
            (var, templates[k[2]].paid_minutes // 30)
            for k, var in choice.items()
            if k[0] == person.id
        ]
        if mine:
            loads.append(sum(var * halves for var, halves in mine))
    if loads:
        heaviest = model.new_int_var(0, 7 * 48, "heaviest")
        for load in loads:
            model.add(heaviest >= load)
        objective.append(SPREAD_WEIGHT * heaviest)

    model.minimize(sum(objective))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = problem.max_time_s
    solver.parameters.num_workers = (
        1  # one worker and a fixed seed: the same input, the same roster
    )
    solver.parameters.random_seed = 1
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Solution(status="none", short_before=short_before, short_after=short_before)

    placements = tuple(
        sorted(
            (person_id, day, template_id)
            for (person_id, day, template_id), var in choice.items()
            if solver.value(var)
        )
    )
    added = coverage(
        (day, templates[template_id].start, templates[template_id].end)
        for _, day, template_id in placements
    )
    total = held_coverage + added
    short_after, over_after = _short_and_over(problem.required, total)
    return Solution(
        status="optimal" if status == cp_model.OPTIMAL else "feasible",
        placements=placements,
        short_before=short_before,
        short_after=short_after,
        over_after=over_after,
        kept=len(kept_here),
    )
