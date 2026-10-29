"""The pluggable answerer (tech spec section 8.2) and its rule-based default.

An `Answerer` turns a question into an `AnswerPlan` using ONLY the tools it is handed for the
asking role. It never sees a database, a user, or another role's tools. The default,
`RuleBasedAnswerer`, is deterministic: it matches the question against fixed patterns, picks one
tool, and writes the reply from a template filled with that tool's result. It does not interpret
the question as instructions, so text planted in the question or in the data has nothing to act on.

A model-backed answerer can be swapped in later behind the same interface; its tool output must go
through `fence.fence()` and its reply through `guard.check()` (the service applies the guard to
every adapter).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from wfm.accounts.models import Role
from wfm.core.errors import ApiError

from . import templates
from .tools import Tool, ToolNotAllowedError, ToolParamsError, ToolResult

SAST = ZoneInfo("Africa/Johannesburg")
CallTool = Callable[[str, Mapping[str, Any]], ToolResult]


def sast_today() -> date:
    return datetime.now(SAST).date()


@dataclass(frozen=True, slots=True)
class AnswerPlan:
    answer: str
    refused: bool
    intent: str
    tool_results: tuple[ToolResult, ...] = ()
    actions: tuple[tuple[str, str], ...] = field(default=())  # (label, path) for a write request
    suggest: bool = False  # show the role's question list (unknown questions)


class Answerer(Protocol):
    def answer(
        self,
        question: str,
        role_tools: Sequence[Tool],
        call_tool: CallTool,
        *,
        role: str,
    ) -> AnswerPlan: ...


REFUSED = "refused"


def refuse(intent: str) -> AnswerPlan:
    """The one refusal: same text and shape for every refused case, whatever the reason."""
    return AnswerPlan(templates.REFUSAL, True, intent)


# --- reading the question ----------------------------------------------------------------------

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_POSSESSIVE = re.compile(r"\b([A-Za-z]+)[']s\b")
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAYS = [d.lower() for d in templates.WEEKDAYS]
_NOT_NAMES = frozenset(
    {
        *_DAYS,
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december",
        "i", "copilot", "sast", "ok", "what", "who", "when", "where", "why", "how", "which",
        "show", "tell", "is", "are", "do", "does", "can", "list", "give", "please", "my",
    }
)  # fmt: skip
_NOT_POSSESSIVE = frozenset(
    {"what", "who", "that", "it", "there", "here", "let", "how", "where", "when", "which",
     "he", "she", "today", "tomorrow", "yesterday", "why"}
)  # fmt: skip


def names_in(question: str) -> list[str]:
    """Words that look like a person's, team's or customer's name: capitalised words (not the
    first word, unless a capitalised word follows it), and any 'X's'. Deliberately cautious."""
    found: list[str] = []
    words = _WORD.findall(question)

    def titled(w: str) -> bool:
        return w[0].isupper() and any(c.islower() for c in w) and w.lower() not in _NOT_NAMES

    for i, w in enumerate(words):
        if not titled(w):
            continue
        if i == 0 and not (len(words) > 1 and titled(words[1])):
            continue
        found.append(w.removesuffix("'s"))
    for m in _POSSESSIVE.finditer(question):
        if m.group(1).lower() not in _NOT_POSSESSIVE:
            found.append(m.group(1))
    return found


def resolve_day(low: str, today: date) -> tuple[date, bool]:
    """The day (or a day in the week) the question means, in Johannesburg time, and whether it
    asked about a whole week. Nothing named means today."""
    iso = _ISO.search(low)
    if iso:
        try:
            return date(int(iso[1]), int(iso[2]), int(iso[3])), False
        except ValueError:
            pass
    monday = today - timedelta(days=today.weekday())
    if "next week" in low:
        return monday + timedelta(days=7), True
    if "last week" in low:
        return monday - timedelta(days=7), True
    if "this week" in low:
        return today, True
    for index, name in enumerate(_DAYS):
        found = re.search(rf"\b(next\s+)?{name}\b", low)
        if found:
            ahead = (index - today.weekday()) % 7
            if found.group(1) and ahead == 0:
                ahead = 7
            return today + timedelta(days=ahead), False
    if "tomorrow" in low:
        return today + timedelta(days=1), False
    if "yesterday" in low:
        return today - timedelta(days=1), False
    return today, bool(re.search(r"\bweek\b", low))


_INJECTION = re.compile(
    r"ignore (all |any |the |your )?(previous|prior|above|earlier)|disregard|system prompt|"
    r"you are now|pretend (to be|you)|act as|reveal your|developer mode|jailbreak|"
    r"forget (all |your )?(previous|prior|instructions|rules)|new instructions",
)
_PAY = re.compile(
    r"\b(pay|paid|payslip|payroll|salary|salaries|wage|wages|hourly rate|rate of pay|earn|earns|"
    r"earning|earnings|remuneration|bonus|bonuses|rands?|overtime cost|cost of overtime|"
    r"how much overtime|compensation|stipend)\b"
)
_PERSON_DETAIL = re.compile(
    r"\b(who|which (people|agents|staff|employees|person))\b.*\b(absent|sick|off sick|called in|"
    r"away|was off|were off|no.show|late|not in)\b|"
    r"\ball (the )?(employees|staff|agents|people)\b|\beveryone\b|\bevery (employee|agent)\b|"
    r"\b(list|names? of) (all |the )?(employees|staff|agents|people)\b"
)
_OTHERS = re.compile(
    r"\b(colleagues?|co-?workers?|someone|somebody|anyone|anybody|his|her|hers|their|theirs|"
    r"him|them|other (agents|people|staff|employees)|teammates?|manager)\b"
)
_WRITE = re.compile(
    r"^(?:(?:please|kindly|can you|could you|would you|will you|i want to|i would like to|"
    r"i'd like to|i need to|help me|go ahead and)\s+)*"
    r"(approve|reject|decline|cancel|delete|remove|assign|move|change|update|edit|publish|"
    r"unpublish|book|apply|create|add|set|grant|clear|reassign|swap|post|submit|reopen|fix)\b"
)

# intent name, pattern, candidate tools (the first one the role may call is used)
_INTENTS: tuple[tuple[str, re.Pattern[str], tuple[str, ...]], ...] = tuple(
    (name, re.compile(pattern), tools)
    for name, pattern, tools in (
        ("why_short", r"\bwhy\b.*\b(short|understaffed|gap|under)", ("why_short",)),
        (
            "gaps",
            r"\b(gaps?|short|shortfall|shortage|understaffed|biggest gap|worst)\b",
            ("coverage_gaps",),
        ),
        (
            "team_on_shift",
            r"\b(who|team)\b.*\b(on shift|working|rostered|on duty|in today|in tomorrow)\b|"
            r"\bon shift\b",
            ("team_on_shift",),
        ),
        (
            "headcount",
            r"\bhow many (people|staff|agents)\b|\bheadcount\b|\brostered\b",
            ("coverage_summary",),
        ),
        (
            "coverage",
            r"\b(coverage|covered|staffing|staffed)\b",
            ("coverage_gaps", "coverage_summary"),
        ),
        ("forecast", r"\bforecast", ("forecast_status",)),
        (
            "leave_balance",
            r"\b(balance|days left|days remaining|entitle\w*)\b|\bhow many (leave )?days\b",
            ("my_leave_balance",),
        ),
        (
            "pending_leave",
            r"\b(pending|outstanding|awaiting|waiting)\b.*\bleave\b|"
            r"\bleave\b.*\b(pending|requests?|approval|approve|waiting)\b|\bwho\b.*\bleave\b",
            ("team_pending_leave",),
        ),
        ("swaps", r"\bswaps?\b", ("my_open_swaps", "team_open_swaps")),
        ("absence", r"\b(absence|absenteeism|absent|shrinkage)\b", ("absence_rate",)),
        (
            "contracts",
            r"\b(contracts?|sla|service level|capacity|at risk)\b",
            ("my_contracts_capacity",),
        ),
        ("schedule", r"\b(schedule|shifts?|roster|rota|working)\b", ("my_schedule",)),
    )
)

_STRICT_ROLES = frozenset({Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS})


def _params(tool: str, low: str, today: date) -> dict[str, Any]:
    day, week = resolve_day(low, today)
    if tool == "coverage_gaps":
        return {"scope": "week" if week else "day", "day": day}
    if tool == "why_short":
        return {"queue": low, "day": day}
    if tool == "forecast_status":
        return {"queue": low}
    if tool in {"team_pending_leave", "team_open_swaps", "my_open_swaps"}:
        return {}
    return {"day": day}


def _write_actions(low: str, role: str) -> tuple[tuple[str, str], ...]:
    if "leave" in low:
        return (("Open Leave", "/leave"),) if role in _LEAVE_ROLES else (("Open Dashboard", "/"),)
    if "swap" in low:
        return (("Open Shift swaps", "/shift-swaps"),)
    if role == Role.AGENT:
        return (("Open My schedule", "/my-schedule"),)
    if role in {Role.PLANNER, Role.ADMIN, Role.LEAD}:
        if "overtime" in low:
            return (("Open Overtime", "/overtime"),)
        if "forecast" in low:
            return (("Open Forecast", "/forecast"),)
        return (("Open Roster", "/roster"),)
    return (("Open Dashboard", "/"),)


_LEAVE_ROLES = frozenset({Role.AGENT, Role.LEAD, Role.PLANNER, Role.ADMIN})


class RuleBasedAnswerer:
    """Deterministic intent matching. No model, no network, no new dependency."""

    def answer(
        self,
        question: str,
        role_tools: Sequence[Tool],
        call_tool: CallTool,
        *,
        role: str,
    ) -> AnswerPlan:
        text = " ".join(question.split())
        low = text.lower()
        allowed = {t.name for t in role_tools}
        names = names_in(text)

        # 1. things no role is ever answered, decided before any lookup
        if _INJECTION.search(low):
            return refuse("injection")
        if _PAY.search(low):
            return refuse("pay")
        if _PERSON_DETAIL.search(low):
            return refuse("person_detail")
        if role in _STRICT_ROLES and (names or _OTHERS.search(low)):
            return refuse("other_person")

        # 2. a request to change something: only a link to the screen that does it
        if _WRITE.search(low):
            return AnswerPlan(
                templates.T["write"], False, "write_request", actions=_write_actions(low, role)
            )

        # 3. a question one of the role's tools answers
        for intent, pattern, candidates in _INTENTS:
            if not pattern.search(low):
                continue
            chosen = next((c for c in candidates if c in allowed), None)
            if chosen is None:
                return refuse(f"{intent}:not_allowed")
            return self._run(chosen, intent, low, names, call_tool, role)

        return AnswerPlan(templates.T["unknown"], False, "unknown", suggest=True)

    def _run(
        self, tool: str, intent: str, low: str, names: list[str], call_tool: CallTool, role: str
    ) -> AnswerPlan:
        try:
            result = call_tool(tool, _params(tool, low, sast_today()))
        except (ToolNotAllowedError, ToolParamsError, ApiError):
            return refuse(f"{intent}:tool_failed")
        if names and role not in {Role.PLANNER, Role.ADMIN}:
            # A lead may name someone only if the tool, which returns their own team and nobody
            # else, already returned that name. Anything else is another team or nobody: the
            # same generic refusal either way.
            seen = {w.lower() for w in _WORD.findall(str(result.facts))}
            if any(n.lower() not in seen for n in names):
                return refuse("other_person")
        return AnswerPlan(templates.FORMATTERS[tool](result.facts), False, tool, (result,))
