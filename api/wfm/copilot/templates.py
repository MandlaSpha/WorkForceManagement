"""Every sentence the rule-based Copilot can say (requirement AI-05, AI-09).

An answer is a template filled ONLY from the tool result of this request. The words of the
templates are the constants the output check allows besides the tool output, so a sentence that
is not here cannot be said. The refusal is one fixed text: identical for every refused case, so
neither its wording nor its shape can hint at whether the data exists.
"""

# ruff: noqa: E501 - the sentences are kept whole on a line so they can be read and searched

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from typing import Any

REFUSAL = "I can't share that for your role."
UNKNOWN = "I can't answer that yet. Here is what I can help with for your role."
WRITE = "I can only read data, so I can't make that change. Use the screen below to do it yourself."

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

T: dict[str, str] = {
    "refusal": REFUSAL,
    "unknown": UNKNOWN,
    "write": WRITE,
    # planner and admin
    "gaps_none": "No queue is short of people on {when}.",
    "gaps_no_forecast": "No queue has a published forecast for that week, so I can't say where the gap is.",
    "gaps_day": "On {when}, {queue} has the biggest gap: {gap} people-half-hours short across {under} half-hours.",
    "gaps_week": "For the week starting {week}, {queue} has the biggest gap: {gap} people-half-hours short across {under} half-hours.",
    "gaps_worst_day": " The worst day is {when}, with {gap} people-half-hours short.",
    "gaps_next": " Next: {queue} ({gap}).",
    "short_none_found": "I could not find a queue with a forecast for {when}.",
    "short_covered": "{queue} on {when} is covered by the roster.",
    "short_gap": "{queue} on {when}: {gap} people-half-hours short across {under} half-hours.",
    "short_worst": " The worst half-hour is {time}, with {rostered} rostered against {required} required.",
    "short_leave": " People on approved leave that day: {leave}.",
    "short_status": " The roster is {status}.",
    "forecast_none": "There is no forecast yet.",
    "forecast_head": "Forecast status:",
    "forecast_row": " {queue} is {status}, covering {date_from} to {date_to};",
    # team lead
    "leave_none": "Nobody in your team has leave waiting for a decision.",
    "leave_head": "Leave waiting for a decision:",
    "leave_row": " {name}, {leave_type}, {start} to {end} ({days} days);",
    "shift_none": "Nobody in your team is rostered on {when}.",
    "shift_head": "Rostered on {when}:",
    "shift_row": " {name} ({shift}, {start} to {end}, {queue});",
    "swaps_team_none": "No shift swaps are open in your team.",
    "swaps_team_head": "Open shift swaps in your team:",
    "swaps_team_row": " {name} on {when} ({shift}, {status});",
    # agent
    "mine_none": "You have no published shifts in the week starting {week}.",
    "mine_head": "Your shifts for the week starting {week}:",
    "mine_row": " {when} {shift}, {start} to {end};",
    "mine_leave": " Your leave: {leave_type}, {start} to {end}.",
    "mine_unpublished": " {n} more shifts are not published yet.",
    "balance_none": "I have no leave balance on record for you.",
    "balance_head": "Your leave balance for {year}:",
    "balance_row": " {leave_type}, {available} days available ({taken} taken, {pending} pending);",
    "swaps_mine_none": "You have no open shift swaps.",
    "swaps_mine_head": "Your open shift swaps:",
    "swaps_mine_row": " {when} ({shift}, {status});",
    # executive, planner, admin
    "cover_head": "People rostered in the week starting {week} (headcount {headcount}):",
    "cover_row": " {when} {n};",
    "absence": "From {first} to {last}, {rate}% of staff time was approved leave. Person-days away: {away}. Headcount: {headcount}.",
    # customer operations
    "contracts_none": "There are no contracts to report on.",
    "contracts": "Contracts you can read: {contracts}, of which active: {active}. Open Contracts for their service levels.",
}

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_PLACEHOLDER = re.compile(r"\{[a-z_]+\}")


def vocabulary() -> frozenset[str]:
    """The words the templates themselves use (lower case), plus the names of days."""
    words: set[str] = set()
    for text in T.values():
        words.update(w.lower() for w in _WORD.findall(_PLACEHOLDER.sub(" ", text)))
    words.update(w.lower() for w in WEEKDAYS)
    return frozenset(words)


def when(iso: str) -> str:
    """'Tuesday 2026-11-03' from an ISO date taken out of a tool result."""
    return f"{WEEKDAYS[date.fromisoformat(iso).weekday()]} {iso}"


def _num(value: Any) -> str:
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def _list(head: str, rows: list[str]) -> str:
    out = head + "".join(rows)
    return out[:-1] + "." if out.endswith(";") else out


def gaps(f: dict[str, Any]) -> str:
    queues = f["queues"]
    if f["queues_with_forecast"] == 0:
        return T["gaps_no_forecast"]
    if not queues:
        return T["gaps_none"].format(when=when(f["day"]))
    top = queues[0]
    if f["scope"] == "week":
        text = T["gaps_week"].format(
            week=f["week_start"], queue=top["queue"], gap=top["gap"], under=top["under_intervals"]
        )
        worst = max(f["days"], key=lambda d: d["gap"])
        if worst["gap"] > 0:
            text += T["gaps_worst_day"].format(when=when(worst["day"]), gap=worst["gap"])
    else:
        text = T["gaps_day"].format(
            when=when(f["day"]), queue=top["queue"], gap=top["gap"], under=top["under_intervals"]
        )
    for other in queues[1:3]:
        text += T["gaps_next"].format(queue=other["queue"], gap=other["gap"])
    return text


def why_short(f: dict[str, Any]) -> str:
    if not f["found"]:
        return T["short_none_found"].format(when=when(f["day"]))
    if f["gap"] == 0:
        return T["short_covered"].format(queue=f["queue"], when=when(f["day"]))
    text = T["short_gap"].format(
        queue=f["queue"], when=when(f["day"]), gap=f["gap"], under=f["under_intervals"]
    )
    if "worst_time" in f:
        text += T["short_worst"].format(
            time=f["worst_time"], rostered=f["worst_rostered"], required=f["worst_required"]
        )
    text += T["short_leave"].format(leave=f["approved_leave_people"])
    text += T["short_status"].format(status=f["roster_status"])
    return text


def forecast_status(f: dict[str, Any]) -> str:
    if not f["queues"]:
        return T["forecast_none"]
    rows = [
        T["forecast_row"].format(
            queue=q["queue"],
            status=q["status"],
            date_from=q["date_from"],
            date_to=q["date_to"],
        )
        for q in f["queues"]
    ]
    return _list(T["forecast_head"], rows)


def team_pending_leave(f: dict[str, Any]) -> str:
    if not f["items"]:
        return T["leave_none"]
    return _list(T["leave_head"], [T["leave_row"].format(**i) for i in f["items"]])


def team_on_shift(f: dict[str, Any]) -> str:
    if not f["items"]:
        return T["shift_none"].format(when=when(f["day"]))
    rows = [T["shift_row"].format(**i) for i in f["items"]]
    return _list(T["shift_head"].format(when=when(f["day"])), rows)


def team_open_swaps(f: dict[str, Any]) -> str:
    if not f["items"]:
        return T["swaps_team_none"]
    rows = [
        T["swaps_team_row"].format(
            name=i["name"], when=when(i["day"]), shift=i["shift"], status=i["status"]
        )
        for i in f["items"]
    ]
    return _list(T["swaps_team_head"], rows)


def my_schedule(f: dict[str, Any]) -> str:
    parts: list[str] = []
    if f["shifts"]:
        rows = [
            T["mine_row"].format(
                when=when(s["day"]), shift=s["shift"], start=s["start"], end=s["end"]
            )
            for s in f["shifts"]
        ]
        parts.append(_list(T["mine_head"].format(week=f["week_start"]), rows))
    else:
        parts.append(T["mine_none"].format(week=f["week_start"]))
    parts.extend(T["mine_leave"].format(**x).strip() for x in f["leave"])
    if f["unpublished_shifts"]:
        parts.append(T["mine_unpublished"].format(n=f["unpublished_shifts"]).strip())
    return " ".join(parts)


def my_leave_balance(f: dict[str, Any]) -> str:
    if not f["items"]:
        return T["balance_none"]
    rows = [
        T["balance_row"].format(
            leave_type=i["leave_type"],
            available=_num(i["available"]),
            taken=_num(i["taken"]),
            pending=_num(i["pending"]),
        )
        for i in f["items"]
        if i["available"] is not None
    ]
    if not rows:
        return T["balance_none"]
    return _list(T["balance_head"].format(year=f["year"]), rows)


def my_open_swaps(f: dict[str, Any]) -> str:
    if not f["items"]:
        return T["swaps_mine_none"]
    rows = [
        T["swaps_mine_row"].format(when=when(i["day"]), shift=i["shift"], status=i["status"])
        for i in f["items"]
    ]
    return _list(T["swaps_mine_head"], rows)


def coverage_summary(f: dict[str, Any]) -> str:
    rows = [T["cover_row"].format(when=when(d["day"]), n=d["on_shift"]) for d in f["days"]]
    return _list(T["cover_head"].format(week=f["week_start"], headcount=f["headcount"]), rows)


def absence_rate(f: dict[str, Any]) -> str:
    return T["absence"].format(
        first=f["first"],
        last=f["last"],
        rate=_num(f["rate_pct"]),
        away=f["away_person_days"],
        headcount=f["headcount"],
    )


def my_contracts_capacity(f: dict[str, Any]) -> str:
    if f["contracts"] == 0:
        return T["contracts_none"]
    return T["contracts"].format(contracts=f["contracts"], active=f["active"])


FORMATTERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "coverage_gaps": gaps,
    "why_short": why_short,
    "forecast_status": forecast_status,
    "team_pending_leave": team_pending_leave,
    "team_on_shift": team_on_shift,
    "team_open_swaps": team_open_swaps,
    "my_schedule": my_schedule,
    "my_leave_balance": my_leave_balance,
    "my_open_swaps": my_open_swaps,
    "coverage_summary": coverage_summary,
    "absence_rate": absence_rate,
    "my_contracts_capacity": my_contracts_capacity,
}
