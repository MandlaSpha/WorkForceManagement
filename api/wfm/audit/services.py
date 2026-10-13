"""The only way to write audit events. Call it inside the same transaction as the change
(AUD-08): a change without its audit event must be impossible.

Call it as the LAST write of the transaction. Inserting an event takes a database lock that is
held until commit (it keeps the hash chain linear), so every other transaction that audits
waits behind it. Doing the slow work first and recording last keeps that wait to milliseconds."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.db import transaction

from wfm.core import request_context

from .models import ActorType, AuditChange, AuditEvent, Outcome


@dataclass(frozen=True, slots=True)
class FieldChange:
    entity_type: str
    entity_id: str
    field: str
    old: str | None
    new: str | None


def record(
    *,
    actor: Any | None,
    action: str,
    outcome: str = Outcome.SUCCESS,
    entity_type: str = "",
    entity_id: str = "",
    subject_employee_id: int | None = None,
    reason: str = "",
    changes: Sequence[FieldChange] = (),
    batch_id: UUID | None = None,
    actor_type: str | None = None,
) -> AuditEvent:
    """Insert one audit event (plus field-level changes). There is deliberately no timestamp
    parameter: the database clock decides when it happened."""
    ctx = request_context.current()
    resolved_type = actor_type or (ActorType.USER if actor is not None else ActorType.SYSTEM)
    with transaction.atomic():
        event = AuditEvent.objects.create(
            actor_user_id=getattr(actor, "pk", None),
            actor_role=getattr(actor, "role", ""),
            actor_type=resolved_type,
            subject_employee_id=subject_employee_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome=outcome,
            reason=reason,
            request_id=ctx.request_id,
            trace_id=ctx.trace_id,
            session_hash=ctx.session_hash,
            ip=ctx.ip,
            user_agent=ctx.user_agent,
            batch_id=batch_id,
        )
        if changes:
            AuditChange.objects.bulk_create(
                AuditChange(
                    event=event,
                    entity_type=c.entity_type,
                    entity_id=c.entity_id,
                    field=c.field,
                    old_value=c.old,
                    new_value=c.new,
                )
                for c in changes
            )
    return event
