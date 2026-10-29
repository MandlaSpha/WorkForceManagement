"""Reads of the audit trail (AUD-11, AUD-12). Admin only, decided in `AuditQuerySet.for_user`.

Nothing here writes: the trail is append-only and a viewer must never be a way to change it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db.models import QuerySet

from wfm.accounts.models import User

from .models import Action, AuditEvent, Outcome

MAX_PAGE_SIZE = 200
EXPORT_CAP = 10_000


def count_recent(*, actor_user_id: int, action: str, since: datetime) -> int:
    """How many successful events of one kind the person caused since a moment (used for rate
    limits). It counts the person's OWN events only and returns a number, so it needs no role
    scope."""
    return AuditEvent.objects.filter(
        actor_user_id=actor_user_id, action=action, occurred_at__gte=since, outcome=Outcome.SUCCESS
    ).count()


@dataclass(frozen=True, slots=True)
class Filters:
    actor: str = ""  # part of a username; "system" matches events with no user
    action: str = ""
    entity_type: str = ""
    outcome: str = ""
    since: datetime | None = None  # inclusive
    until: datetime | None = None  # exclusive

    def shape(self) -> str:
        """Which filters were used, never their values (they may hold a person's login)."""
        used = [
            name
            for name, value in (
                ("actor", self.actor),
                ("action", self.action),
                ("entity", self.entity_type),
                ("outcome", self.outcome),
                ("since", self.since),
                ("until", self.until),
            )
            if value
        ]
        return ("filters: " + ",".join(used)) if used else "no filters"


def search(user: Any, f: Filters) -> QuerySet[AuditEvent]:
    qs = AuditEvent.objects.for_user(user)
    if f.actor:
        if f.actor.lower() == "system":
            qs = qs.filter(actor_user_id__isnull=True)
        else:
            ids = User.objects.filter(username__icontains=f.actor).values_list("pk", flat=True)
            qs = qs.filter(actor_user_id__in=list(ids[:500]))
    if f.action:
        qs = qs.filter(action=f.action)
    if f.entity_type:
        qs = qs.filter(entity_type=f.entity_type)
    if f.outcome:
        qs = qs.filter(outcome=f.outcome)
    if f.since:
        qs = qs.filter(occurred_at__gte=f.since)
    if f.until:
        qs = qs.filter(occurred_at__lt=f.until)
    return qs.order_by("-chain_seq")


def usernames(ids: set[int]) -> dict[int, str]:
    return dict(User.objects.filter(pk__in=ids).values_list("pk", "username"))


def filter_options(user: Any) -> dict[str, list[dict[str, str]]]:
    """What the filter drop-downs offer: every known action plus any older one in the trail."""
    labels = dict(Action.choices)
    seen = AuditEvent.objects.for_user(user).values_list("action", flat=True).distinct()
    actions = sorted({*labels, *seen})
    types = (
        AuditEvent.objects.for_user(user)
        .exclude(entity_type="")
        .values_list("entity_type", flat=True)
        .distinct()
    )
    return {
        "actions": [{"value": a, "label": str(labels.get(a, a))} for a in actions],
        "entityTypes": [{"value": t, "label": t} for t in sorted(types)],
        "outcomes": [{"value": v, "label": str(label)} for v, label in Outcome.choices],
    }
