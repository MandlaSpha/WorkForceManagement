"""Putting a question to the Copilot (requirements AI-01 to AI-09).

One question in, one answer out. Nothing is remembered between questions: no conversation memory,
no cache (AI-04). The asking user's identity is the only identity there is (AI-02). The question
is audited as the LAST write of the request (AI-08).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.utils import timezone

from wfm.accounts.models import User
from wfm.audit import selectors as audit_selectors
from wfm.audit import services as audit
from wfm.audit.models import Action, Outcome
from wfm.audit.services import FieldChange
from wfm.core.errors import ApiError

from . import guard, templates, tools
from .adapter import Answerer, AnswerPlan, RuleBasedAnswerer, refuse

MAX_QUESTION = 300
RATE_LIMIT = 20  # questions per user ...
RATE_WINDOW_S = 60  # ... per this many seconds
MAX_TOOL_CALLS = 3  # a single question never fans out into many lookups

DEFAULT_ANSWERER: Answerer = RuleBasedAnswerer()


@dataclass(frozen=True, slots=True)
class Reply:
    answer: str
    refused: bool
    sources: tuple[tuple[str, int], ...]  # (tool, row count): never the rows themselves
    actions: tuple[tuple[str, str], ...]  # (label, path)
    suggestions: tuple[str, ...]


def clean_question(raw: str) -> str:
    text = raw.replace(chr(0x2019), "'")  # a phone's curly apostrophe is an apostrophe
    text = "".join(ch if ch.isprintable() else " " for ch in text)
    return " ".join(text.split())[:MAX_QUESTION]


def _rate_limited(user: User) -> bool:
    since = timezone.now() - timedelta(seconds=RATE_WINDOW_S)
    recent = audit_selectors.count_recent(
        actor_user_id=user.pk, action=Action.COPILOT_ASKED, since=since
    )
    return recent >= RATE_LIMIT


def ask(*, user: User, question: str, answerer: Answerer | None = None) -> Reply:
    text = clean_question(question)
    if not text:
        raise ApiError(422, "copilot.empty", "Invalid request", "Ask a question.")
    if _rate_limited(user):
        audit.record(
            actor=user,
            action=Action.COPILOT_ASKED,
            outcome=Outcome.DENIED,
            entity_type="copilot",
            entity_id="rate_limited",
        )
        raise ApiError(
            429,
            "copilot.rate_limited",
            "Too many questions",
            "You have asked a lot of questions in a short time. "
            "Please wait a minute and try again.",
        )

    role_tools = tools.tools_for(user.role)
    called: list[tools.ToolResult] = []

    def call_tool(name: str, params: Mapping[str, Any]) -> tools.ToolResult:
        if len(called) >= MAX_TOOL_CALLS:
            raise tools.ToolNotAllowedError(name)
        result = tools.call_tool(user, name, params)
        called.append(result)
        return result

    try:
        plan: AnswerPlan = (answerer or DEFAULT_ANSWERER).answer(
            text, role_tools, call_tool, role=user.role
        )
    except (tools.ToolNotAllowedError, tools.ToolParamsError, ApiError):
        # An adapter that reached for a tool its role does not have, or forged an argument.
        plan = refuse("adapter:tool_refused")

    guard_blocked = False
    if plan.refused:
        plan = refuse(plan.intent)
    else:
        # The answer may only contain what this request's tool calls returned (AI-09). The
        # check looks at what was actually called, not at what the adapter says it used.
        verdict = guard.check(plan.answer, [r.facts for r in called])
        if not verdict.ok:
            guard_blocked = True
            plan = refuse(f"{plan.intent}:guard_blocked")

    refused = plan.refused
    screens = {t.name: t.screen for t in role_tools}
    sources: tuple[tuple[str, int], ...] = ()
    actions: tuple[tuple[str, str], ...] = ()
    if not refused:
        sources = tuple((r.tool, r.row_count) for r in called)
        actions = plan.actions or tuple(
            dict.fromkeys(
                (f"Open {screens.get(r.tool, 'screen')}", r.open_path)
                for r in called
                if r.open_path
            )
        )
    suggestions = tuple(t.example for t in role_tools)

    # The audit event is the last write (AUD-08): it holds a lock until commit.
    audit.record(
        actor=user,
        action=Action.COPILOT_ASKED,
        outcome=Outcome.SUCCESS,
        entity_type="copilot",
        entity_id=plan.intent[:200],
        reason=text,
        changes=[
            FieldChange(
                "copilot",
                plan.intent[:180],
                "tools",
                None,
                ",".join(r.tool for r in called) or "none",
            ),
            FieldChange(
                "copilot", plan.intent[:180], "rows", None, str(sum(r.row_count for r in called))
            ),
            FieldChange(
                "copilot", plan.intent[:180], "refused", None, "true" if refused else "false"
            ),
            FieldChange(
                "copilot", plan.intent[:180], "guard", None, "blocked" if guard_blocked else "ok"
            ),
        ],
    )
    return Reply(
        plan.answer if not refused else templates.REFUSAL, refused, sources, actions, suggestions
    )
