from __future__ import annotations

import logging

from celery import shared_task

from . import integrity, services
from .models import Action, ActorType, Outcome

log = logging.getLogger(__name__)


@shared_task(name="wfm.audit.verify_chain")  # type: ignore[untyped-decorator]
def verify_audit_chain() -> dict[str, int]:
    """Nightly integrity check. A broken chain is recorded as an audit event of its own and
    logged at CRITICAL so alerting can pick it up."""
    problems = integrity.verify_chain()
    if problems:
        first = problems[0]
        log.critical(
            "Audit chain broken: %d problem(s); first at seq=%s event=%s: %s",
            len(problems),
            first.seq,
            first.event_id,
            first.problem,
        )
        services.record(
            actor=None,
            action=Action.CHAIN_BROKEN,
            outcome=Outcome.FAILED,
            actor_type=ActorType.SYSTEM,
            reason=f"{len(problems)} problem(s); first at seq {first.seq}: {first.problem}"[:300],
        )
    return {"problems": len(problems)}
