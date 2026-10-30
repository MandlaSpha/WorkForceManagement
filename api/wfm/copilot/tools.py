"""The Copilot's fixed registry of read tools (requirements AI-02, AI-03; tech spec section 8.2).

Rules that make it role-safe by construction:

- A tool is a closed, named function with the roles allowed to call it. `call_tool` checks the
  role BEFORE running anything, so a refused role never reaches a selector.
- Every tool reads through a module selector that starts from the model's `for_user(user)`
  scope (or a named-roles variant for counts). This module never imports a model.
- No tool takes a user id, employee id or any record id. The "my" tools use the signed-in user
  only. The few parameters (a day, a queue name used to filter) are validated here.
- There is no tool for pay or overtime money, for any role.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from django.utils import timezone

from wfm.accounts.models import Role, User
from wfm.contracts import copilot_selectors as contract_reads
from wfm.forecasting import selectors as forecast_selectors
from wfm.people import copilot_selectors as people_reads
from wfm.people import ess_selectors, swap_selectors
from wfm.people import selectors as leave_selectors
from wfm.scheduling import copilot_selectors as roster_reads
from wfm.scheduling import selectors as roster_selectors

MAX_ROWS = 25  # rows a tool hands back; the answer says when there were more
MAX_TEXT = 300


class ToolNotAllowedError(Exception):
    """The tool does not exist or the role may not call it. Both look the same to the caller."""


class ToolParamsError(ValueError):
    """The parameters do not match the tool's declared schema."""


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool: str
    facts: dict[str, Any]  # plain JSON-safe data: this is all an answer may be built from
    row_count: int
    open_path: str | None = None


@dataclass(frozen=True, slots=True)
class Param:
    name: str
    kind: str  # "day" | "week" | "text"
    required: bool = False


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    roles: frozenset[Role]
    params: tuple[Param, ...]
    run: Callable[[User, Mapping[str, Any]], ToolResult]
    example: str  # a question this tool answers: offered to the role as a suggestion
    screen: str  # label of the screen its answer links to


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _iso(day: date) -> str:
    return day.isoformat()


def _text(params: Mapping[str, Any], name: str) -> str:
    return str(params.get(name) or "").strip().lower()[:MAX_TEXT]


# --- planner and admin -----------------------------------------------------------------------


def _day_gap(plan: Any, day: date) -> tuple[int, int]:
    """People-half-hours short, and half-hours under, for one queue on one day."""
    cells = plan.cells.get(day, [])
    gap = sum(max(-c.variance, 0) for c in cells if c.variance is not None)
    return gap, sum(1 for c in cells if c.state == "under")


def coverage_gaps(user: User, params: Mapping[str, Any]) -> ToolResult:
    day: date = params["day"]
    week = params.get("scope") == "week"
    found = roster_selectors.overview(user, _monday(day))
    rows: list[dict[str, Any]] = []
    for plan in found.plans:
        if plan.summary.intervals_known == 0:
            continue
        if week:
            gap, under = plan.summary.gap, plan.summary.under_intervals
        else:
            gap, under = _day_gap(plan, day)
        if gap > 0:
            rows.append({"queue": plan.queue.name, "gap": gap, "under_intervals": under})
    rows.sort(key=lambda r: (-r["gap"], r["queue"]))
    facts: dict[str, Any] = {
        "scope": "week" if week else "day",
        "day": _iso(day),
        "week_start": _iso(found.week_start),
        "queues_with_forecast": sum(1 for p in found.plans if p.summary.intervals_known > 0),
        "queues": rows[:MAX_ROWS],
    }
    if week:
        facts["days"] = [
            {"day": _iso(d.day), "gap": d.gap, "under_intervals": d.under_intervals}
            for d in found.days
        ]
    return ToolResult("coverage_gaps", facts, len(rows[:MAX_ROWS]), "/planner")


def why_short(user: User, params: Mapping[str, Any]) -> ToolResult:
    day: date = params["day"]
    hint = _text(params, "queue")
    found = roster_selectors.overview(user, _monday(day))
    known = [p for p in found.plans if p.summary.intervals_known > 0]
    named = [p for p in known if p.queue.name.lower() in hint]
    if named:
        chosen = max(named, key=lambda p: len(p.queue.name))
    elif known:  # no queue named: the one that is shortest that day
        chosen = max(known, key=lambda p: (_day_gap(p, day)[0], p.queue.name))
    else:
        chosen = None
    if chosen is None:
        return ToolResult("why_short", {"day": _iso(day), "found": False}, 0, "/planner")
    gap, under = _day_gap(chosen, day)
    cells = [c for c in chosen.cells.get(day, []) if c.variance is not None]
    worst = min(cells, key=lambda c: (c.variance or 0, c.slot), default=None)
    leave = people_reads.leave_count_on(user, chosen.queue.pk, day)
    facts: dict[str, Any] = {
        "found": True,
        "day": _iso(day),
        "queue": chosen.queue.name,
        "gap": gap,
        "under_intervals": under,
        "approved_leave_people": leave,
        "roster_status": chosen.roster_status,
    }
    if worst is not None and worst.variance is not None and worst.variance < 0:
        facts["worst_time"] = f"{worst.slot // 2:02d}:{(worst.slot % 2) * 30:02d}"
        facts["worst_rostered"] = worst.scheduled
        facts["worst_required"] = worst.required
    return ToolResult("why_short", facts, 1, "/planner")


def forecast_status(user: User, params: Mapping[str, Any]) -> ToolResult:
    hint = _text(params, "queue")
    latest: dict[str, Any] = {}
    for version in forecast_selectors.list_versions(user):  # newest first
        latest.setdefault(version.queue.name, version)
    rows = [
        {
            "queue": name,
            "status": v.status,
            "label": v.label,
            "date_from": _iso(v.date_from),
            "date_to": _iso(v.date_to),
        }
        for name, v in sorted(latest.items())
        if not hint or name.lower() in hint
    ]
    if hint and not rows:  # the question did not name a known queue: say how every queue stands
        rows = [
            {
                "queue": name,
                "status": v.status,
                "label": v.label,
                "date_from": _iso(v.date_from),
                "date_to": _iso(v.date_to),
            }
            for name, v in sorted(latest.items())
        ]
    return ToolResult(
        "forecast_status", {"queues": rows[:MAX_ROWS]}, len(rows[:MAX_ROWS]), "/forecast"
    )


# --- team lead -------------------------------------------------------------------------------


def team_pending_leave(user: User, params: Mapping[str, Any]) -> ToolResult:
    found = leave_selectors.requests(user, status="pending")[:MAX_ROWS]
    rows = [
        {
            "name": r.employee.name,
            "leave_type": r.leave_type.name,
            "start": _iso(r.start_date),
            "end": _iso(r.end_date),
            "days": r.days,
        }
        for r in found
    ]
    return ToolResult("team_pending_leave", {"items": rows}, len(rows), "/leave")


def team_on_shift(user: User, params: Mapping[str, Any]) -> ToolResult:
    day: date = params["day"]
    rows = [
        {"name": p.name, "shift": p.shift, "start": p.start, "end": p.end, "queue": p.queue}
        for p in roster_reads.team_on_shift(user, day)[:MAX_ROWS]
    ]
    return ToolResult("team_on_shift", {"day": _iso(day), "items": rows}, len(rows), "/roster")


def team_open_swaps(user: User, params: Mapping[str, Any]) -> ToolResult:
    rows = []
    for status in ("open", "awaiting_approval"):
        for s in swap_selectors.swaps(user, status=status):
            rows.append(
                {
                    "name": s.from_employee.name,
                    "day": _iso(s.from_day),
                    "shift": s.from_template.code,
                    "status": status,
                }
            )
    rows = rows[:MAX_ROWS]
    return ToolResult("team_open_swaps", {"items": rows}, len(rows), "/shift-swaps")


# --- agent: the signed-in person only --------------------------------------------------------


def my_schedule(user: User, params: Mapping[str, Any]) -> ToolResult:
    week_start = _monday(params["day"])
    employee = leave_selectors.own_employee(user)
    if employee is None:
        return ToolResult(
            "my_schedule", {"week_start": _iso(week_start), "shifts": []}, 0, "/my-schedule"
        )
    mine = ess_selectors.my_schedule(employee, week_start, week_start + timedelta(days=6))
    shifts = [
        {
            "day": _iso(a.day),
            "shift": a.template.code,
            "start": f"{a.template.start_time:%H:%M}",
            "end": f"{a.template.end_time:%H:%M}",
        }
        for a in mine.shifts
    ]
    leave = [
        {"leave_type": r.leave_type.name, "start": _iso(r.start_date), "end": _iso(r.end_date)}
        for r in mine.leave
    ]
    facts = {
        "week_start": _iso(week_start),
        "shifts": shifts,
        "leave": leave,
        "unpublished_shifts": mine.unpublished,
    }
    return ToolResult("my_schedule", facts, len(shifts) + len(leave), "/my-schedule")


def my_leave_balance(user: User, params: Mapping[str, Any]) -> ToolResult:
    year: int = params["day"].year
    rows = [
        {
            "leave_type": b.leave_type,
            "entitlement": b.entitlement,
            "taken": b.taken,
            "pending": b.pending,
            "available": b.available,
        }
        for b in people_reads.own_balances(user, year)
        if b.entitlement is not None
    ]
    return ToolResult("my_leave_balance", {"year": year, "items": rows}, len(rows), "/leave")


def my_open_swaps(user: User, params: Mapping[str, Any]) -> ToolResult:
    """The person's own swaps. Names of the other side are left out on purpose (SWP-01)."""
    rows = []
    for status in ("open", "awaiting_approval"):
        for s in swap_selectors.swaps(user, status=status):
            rows.append({"day": _iso(s.from_day), "shift": s.from_template.code, "status": status})
    rows = rows[:MAX_ROWS]
    return ToolResult("my_open_swaps", {"items": rows}, len(rows), "/shift-swaps")


# --- executive (and planner, admin): numbers only --------------------------------------------


def coverage_summary(user: User, params: Mapping[str, Any]) -> ToolResult:
    counts = roster_reads.coverage_counts(user, _monday(params["day"]))
    facts = {
        "week_start": _iso(counts.week_start),
        "headcount": counts.headcount,
        "days": [{"day": _iso(d.day), "on_shift": d.on_shift} for d in counts.days],
    }
    return ToolResult("coverage_summary", facts, len(counts.days), "/planner")


def absence_rate(user: User, params: Mapping[str, Any]) -> ToolResult:
    last: date = params["day"] - timedelta(days=1)
    found = people_reads.absence_rate(user, last - timedelta(days=6), last)
    facts = {
        "first": _iso(found.first),
        "last": _iso(found.last),
        "headcount": found.headcount,
        "away_person_days": found.away_person_days,
        "rate_pct": found.rate_pct,
    }
    return ToolResult("absence_rate", facts, 1, "/shrinkage")


# --- customer operations ---------------------------------------------------------------------


def my_contracts_capacity(user: User, params: Mapping[str, Any]) -> ToolResult:
    """Counts of the contracts this role can read: for customer operations, only those of the
    customers an admin assigned to them (none until then). No contract or customer is named."""
    found = contract_reads.contract_counts(user)
    facts = {"contracts": found.contracts, "active": found.active}
    return ToolResult("my_contracts_capacity", facts, found.contracts, "/contracts")


# --- the registry ----------------------------------------------------------------------------

_DAY = Param("day", "day")
_SCOPE = Param("scope", "text")
_QUEUE = Param("queue", "text")

_TOOLS = (
    Tool(
        "coverage_gaps",
        "Which queues are short of the people needed, for a day or a week.",
        frozenset({Role.PLANNER, Role.ADMIN}),
        (_SCOPE, _DAY),
        coverage_gaps,
        "Which queue has the biggest gap on Tuesday?",
        "Planner",
    ),
    Tool(
        "why_short",
        "Required against rostered people and approved leave for one queue on one day.",
        frozenset({Role.PLANNER, Role.ADMIN}),
        (_QUEUE, _DAY),
        why_short,
        "Why is Tuesday short?",
        "Planner",
    ),
    Tool(
        "forecast_status",
        "Which forecast each queue is on and whether it is published.",
        frozenset({Role.PLANNER, Role.ADMIN}),
        (_QUEUE,),
        forecast_status,
        "What is the forecast status?",
        "Forecast",
    ),
    Tool(
        "team_pending_leave",
        "Leave requests from your own team that wait for a decision.",
        frozenset({Role.LEAD}),
        (),
        team_pending_leave,
        "Who in my team has pending leave?",
        "Leave",
    ),
    Tool(
        "team_on_shift",
        "Who of your own team is rostered on a day.",
        frozenset({Role.LEAD}),
        (_DAY,),
        team_on_shift,
        "Who in my team is on shift tomorrow?",
        "Roster",
    ),
    Tool(
        "team_open_swaps",
        "Shift swaps of your own team that are still open or waiting for approval.",
        frozenset({Role.LEAD}),
        (),
        team_open_swaps,
        "Which shift swaps are open in my team?",
        "Shift swaps",
    ),
    Tool(
        "my_schedule",
        "Your own published shifts and leave for a week.",
        frozenset({Role.AGENT}),
        (_DAY,),
        my_schedule,
        "What is my schedule next week?",
        "My schedule",
    ),
    Tool(
        "my_leave_balance",
        "Your own leave balance for the year.",
        frozenset({Role.AGENT}),
        (_DAY,),
        my_leave_balance,
        "What is my leave balance?",
        "Leave",
    ),
    Tool(
        "my_open_swaps",
        "Your own shift swaps that are still open.",
        frozenset({Role.AGENT}),
        (),
        my_open_swaps,
        "Do I have any open shift swaps?",
        "Shift swaps",
    ),
    Tool(
        "coverage_summary",
        "How many people are rostered each day of a week (numbers only, no names).",
        frozenset({Role.EXECUTIVE, Role.PLANNER, Role.ADMIN}),
        (_DAY,),
        coverage_summary,
        "How many people are rostered this week?",
        "Planner",
    ),
    Tool(
        "absence_rate",
        "The share of staff away on approved leave over the last 7 days (a rate only).",
        frozenset({Role.EXECUTIVE, Role.PLANNER, Role.ADMIN}),
        (_DAY,),
        absence_rate,
        "What is the absence rate?",
        "Shrinkage",
    ),
    Tool(
        "my_contracts_capacity",
        "How many contracts you can read and how many are active (numbers only).",
        frozenset({Role.CUSTOMER_OPS}),
        (_DAY,),
        my_contracts_capacity,
        "How many contracts do I have?",
        "Contracts",
    ),
)

REGISTRY: dict[str, Tool] = {t.name: t for t in _TOOLS}
assert len(REGISTRY) == len(_TOOLS)  # noqa: S101 - a duplicate name is a programming error
_FORBIDDEN_PARAM_NAMES = {"user", "user_id", "employee", "employee_id", "id", "role"}
assert not any(  # noqa: S101
    p.name in _FORBIDDEN_PARAM_NAMES for t in _TOOLS for p in t.params
), "no tool may take a person or record id"


def tools_for(role: str) -> list[Tool]:
    """The tools this role may call, in registry order."""
    return [t for t in _TOOLS if role in t.roles]


def _validate(tool: Tool, params: Mapping[str, Any]) -> dict[str, Any]:
    declared = {p.name: p for p in tool.params}
    unknown = set(params) - set(declared)
    if unknown:
        raise ToolParamsError(f"{tool.name} takes no parameter {sorted(unknown)[0]}")
    clean: dict[str, Any] = {}
    for p in tool.params:
        value = params.get(p.name)
        if p.kind == "day":
            if value is not None and not isinstance(value, date):
                raise ToolParamsError(f"{p.name} must be a date")
            clean[p.name] = value if value is not None else timezone.localdate()
        else:
            if value is not None and not isinstance(value, str):
                raise ToolParamsError(f"{p.name} must be text")
            clean[p.name] = (value or "")[:MAX_TEXT]
    return clean


def call_tool(user: User, name: str, params: Mapping[str, Any] | None = None) -> ToolResult:
    """Run one tool as `user`. The role is checked first; an unknown tool and a tool the role may
    not call raise the same error."""
    tool = REGISTRY.get(name)
    if tool is None or user.role not in tool.roles:
        raise ToolNotAllowedError(name)
    return tool.run(user, _validate(tool, params or {}))
