"""Ranked fixes for a roster week's gaps, and applying one (REC-01).

Reading changes nothing. Applying never trusts what the client saw: the list is worked out again
and the request must match a suggestion that is still on it, otherwise it is refused as stale. The
shift then goes in through the same `assign` the planner's own clicks use, so it is checked by every
roster rule and audited like any other assignment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from wfm_engine import recommend as engine

from wfm.accounts.models import User
from wfm.core.errors import ApiError

from .autoschedule_selectors import Context, build_context
from .roster_services import assign

SHOWN = 10
CHECKED = 500  # how far down the ranking a request may reach: effectively everything


@dataclass(frozen=True, slots=True)
class Recommendations:
    context: Context
    items: list[engine.Recommendation]


def recommendations(
    user: User, queue_id: int, week_start: date, limit: int = SHOWN
) -> Recommendations:
    context = build_context(user, queue_id, week_start)
    return Recommendations(context, engine.recommend(context.problem, limit=limit))


def apply(
    *,
    user: User,
    queue_id: int,
    week_start: date,
    employee_id: int,
    day: date,
    template_id: int,
) -> engine.Recommendation:
    found = recommendations(user, queue_id, week_start, limit=CHECKED)
    match = next(
        (
            r
            for r in found.items
            if (r.person_id, r.day, r.template_id) == (employee_id, day, template_id)
        ),
        None,
    )
    if match is None:
        raise ApiError(
            409,
            "recommendation.stale",
            "Suggestion refused",
            "That suggestion no longer applies: the roster has changed. Look at the list again.",
        )
    assign(user=user, queue_id=queue_id, employee_id=employee_id, day=day, template_id=template_id)
    return match
