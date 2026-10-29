"""POST /api/v1/copilot/ask: one question, one answer, nothing remembered (AI-01, AI-04)."""

from __future__ import annotations

from django.http import HttpRequest
from ninja import Field, Router, Schema

from wfm.core.features import Feature
from wfm.core.permissions import ANY_ROLE, RoleSessionAuth, current_user

from . import services
from .services import MAX_QUESTION

router = Router(tags=["copilot"])
# Every signed-in role may ask. What it is told is decided tool by tool, not here.
ASK = RoleSessionAuth(*ANY_ROLE, feature=Feature.COPILOT)


class CopilotAskIn(Schema):
    question: str = Field(min_length=1, max_length=MAX_QUESTION)


class CopilotSourceOut(Schema):
    tool: str
    rows: int


class CopilotActionOut(Schema):
    label: str
    path: str


class CopilotAnswerOut(Schema):
    answer: str
    refused: bool
    sources: list[CopilotSourceOut]
    actions: list[CopilotActionOut]
    suggestions: list[str]


@router.post(
    "/ask",
    auth=ASK,
    response=CopilotAnswerOut,
    summary="Ask the Copilot a question; it answers only from what the asking role can see",
)
def ask(request: HttpRequest, body: CopilotAskIn) -> CopilotAnswerOut:
    reply = services.ask(user=current_user(request), question=body.question)
    return CopilotAnswerOut(
        answer=reply.answer,
        refused=reply.refused,
        sources=[CopilotSourceOut(tool=t, rows=n) for t, n in reply.sources],
        actions=[CopilotActionOut(label=label, path=path) for label, path in reply.actions],
        suggestions=list(reply.suggestions),
    )
