"""Call data that is keyed by an ACD login, for the POPIA subject-access export and erasure.

The per-call detail tables are never served to anyone (`for_user` returns nothing), so the two
admin-only callers (`people.subject_export`, `people.erasure`) come here with the logins of ONE
employee, read from `AgentLogin`. Only rows keyed by those exact logins are touched or returned:
never another person's. Erasing replaces the login with a random token (the same token for all of
one person's logins), so counts per call, per queue and per day do not move but the rows no longer
point at anyone. The caller records the audit event, as the last write of its transaction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .models import AgentOffer, CallDisposition, CallPause, CallRecord, CallTransfer

PSEUDONYM_PREFIX = "erased-"
MAX_EXPORT_ROWS = 5000


def counts(logins: Sequence[str]) -> dict[str, int]:
    """How many rows carry these logins: calls handled, offers and transfers made."""
    if not logins:
        return {"callRecordLogins": 0, "offerLogins": 0, "transferLogins": 0}
    return {
        "callRecordLogins": CallRecord.objects.filter(agent_login__in=logins).count(),
        "offerLogins": AgentOffer.objects.filter(agent_login__in=logins).count(),
        "transferLogins": CallTransfer.objects.filter(by_login__in=logins).count(),
    }


def export_rows(logins: Sequence[str]) -> dict[str, Any]:
    """The person's own rows. Calls they handled are counted (with what hangs off those calls);
    their offers and the transfers they made are listed. Nothing about anyone else."""
    if not logins:
        return {"summary": {}, "offers": [], "transfers": []}
    handled = CallRecord.objects.filter(agent_login__in=logins)
    summary = {
        "callsHandled": handled.count(),
        "dispositions": CallDisposition.objects.filter(call__in=handled).count(),
        "mutesAndHolds": CallPause.objects.filter(call__in=handled).count(),
        "offers": AgentOffer.objects.filter(agent_login__in=logins).count(),
        "transfers": CallTransfer.objects.filter(by_login__in=logins).count(),
    }
    offers = [
        {
            "queue": o.call.queue.name,
            "offeredAt": o.offered_at.isoformat(),
            "ringSeconds": o.ring_s,
            "answered": o.answered,
        }
        for o in AgentOffer.objects.filter(agent_login__in=logins)
        .select_related("call__queue")
        .order_by("offered_at", "id")[:MAX_EXPORT_ROWS]
    ]
    transfers = [
        {
            "queue": t.call.queue.name,
            "secondsToAnswer": t.answer_s,
            "secondsTalked": t.duration_s,
        }
        for t in CallTransfer.objects.filter(by_login__in=logins)
        .select_related("call__queue")
        .order_by("call__start_at", "id")[:MAX_EXPORT_ROWS]
    ]
    return {"summary": summary, "offers": offers, "transfers": transfers}


def pseudonymise(logins: Sequence[str], token: str) -> dict[str, int]:
    """Replace these logins on calls, offers and transfers with `erased-<token>`; returns counts."""
    done = counts(logins)
    if not logins:
        return done
    pseudonym = f"{PSEUDONYM_PREFIX}{token.lower()}"
    CallRecord.objects.filter(agent_login__in=logins).update(agent_login=pseudonym)
    AgentOffer.objects.filter(agent_login__in=logins).update(agent_login=pseudonym)
    CallTransfer.objects.filter(by_login__in=logins).update(by_login=pseudonym)
    return done
