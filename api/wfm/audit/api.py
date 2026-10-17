"""The audit log viewer (AUD-11, AUD-12): read-only, admin only, and itself audited (AUD-07)."""

from __future__ import annotations

from datetime import UTC, datetime

from django.db import transaction
from django.http import HttpRequest, HttpResponse
from ninja import Query, Router, Schema
from wfm_engine import payroll as fmt

from wfm.accounts.models import Role
from wfm.core.errors import ApiError
from wfm.core.features import CORE
from wfm.core.permissions import RoleSessionAuth, current_user

from . import integrity, selectors, services
from .models import Action, AuditEvent

router = Router(tags=["audit"])
ADMIN = RoleSessionAuth(Role.ADMIN, feature=CORE)

CSV_HEADER = [
    "Sequence",
    "When (UTC)",
    "Who",
    "Role",
    "Action",
    "Entity",
    "Entity id",
    "Outcome",
    "Reason",
    "Request id",
    "Changes",
]


class FilterIn(Schema):
    actor: str = ""
    action: str = ""
    entityType: str = ""  # noqa: N815
    outcome: str = ""
    since: datetime | None = None
    until: datetime | None = None


class PageIn(Schema):
    page: int = 1
    pageSize: int = 50  # noqa: N815


class AuditChangeOut(Schema):
    entityType: str  # noqa: N815
    entityId: str  # noqa: N815
    field: str
    old: str | None
    new: str | None


class AuditEventOut(Schema):
    id: int
    seq: int
    occurredAt: datetime  # noqa: N815
    actor: str  # a username, "System" or "Deleted user"
    actorRole: str  # noqa: N815
    actorType: str  # noqa: N815
    action: str
    actionLabel: str  # noqa: N815
    entityType: str  # noqa: N815
    entityId: str  # noqa: N815
    outcome: str
    reason: str
    requestId: str  # noqa: N815
    ip: str | None
    changes: list[AuditChangeOut]


class AuditEventPageOut(Schema):
    items: list[AuditEventOut]
    total: int
    page: int
    pageSize: int  # noqa: N815


class AuditOptionOut(Schema):
    value: str
    label: str


class AuditOptionsOut(Schema):
    actions: list[AuditOptionOut]
    entityTypes: list[AuditOptionOut]  # noqa: N815
    outcomes: list[AuditOptionOut]


class AuditChainProblemOut(Schema):
    seq: int | None
    eventId: int | None  # noqa: N815
    problem: str


class AuditChainOut(Schema):
    intact: bool
    events: int
    problemCount: int  # noqa: N815
    problems: list[AuditChainProblemOut]  # the first few only
    checkedAt: datetime  # noqa: N815


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def _filters(f: FilterIn) -> selectors.Filters:
    since, until = _aware(f.since), _aware(f.until)
    if since and until and until <= since:
        raise ApiError(422, "audit.bad_range", "The end of the time range is before its start.")
    return selectors.Filters(
        actor=f.actor.strip()[:150],
        action=f.action.strip()[:60],
        entity_type=f.entityType.strip()[:60],
        outcome=f.outcome.strip()[:8],
        since=since,
        until=until,
    )


def _event_out(e: AuditEvent, names: dict[int, str]) -> AuditEventOut:
    who = "System" if e.actor_user_id is None else names.get(e.actor_user_id, "Deleted user")
    return AuditEventOut(
        id=e.pk,
        seq=e.chain_seq,
        occurredAt=e.occurred_at,
        actor=who,
        actorRole=e.actor_role,
        actorType=e.actor_type,
        action=e.action,
        actionLabel=str(dict(Action.choices).get(e.action, e.action)),
        entityType=e.entity_type,
        entityId=e.entity_id,
        outcome=e.outcome,
        reason=e.reason,
        requestId=e.request_id,
        ip=e.ip,
        changes=[
            AuditChangeOut(
                entityType=c.entity_type,
                entityId=c.entity_id,
                field=c.field,
                old=c.old_value,
                new=c.new_value,
            )
            for c in sorted(e.changes.all(), key=lambda c: c.pk)
        ],
    )


def _csv_row(e: AuditEventOut) -> list[str]:
    changes = "; ".join(
        f"{c.entityType}#{c.entityId}.{c.field}: {c.old} -> {c.new}" for c in e.changes
    )
    return [
        str(e.seq),
        e.occurredAt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        e.actor,
        e.actorRole,
        e.action,
        e.entityType,
        e.entityId,
        e.outcome,
        e.reason,
        e.requestId,
        changes,
    ]


@router.get(
    "/events",
    auth=ADMIN,
    response=AuditEventPageOut,
    summary="Search the audit trail, newest first (admin)",
)
def list_events(
    request: HttpRequest, filters: Query[FilterIn], paging: Query[PageIn]
) -> AuditEventPageOut:
    user = current_user(request)
    f = _filters(filters)
    page = max(paging.page, 1)
    size = min(max(paging.pageSize, 1), selectors.MAX_PAGE_SIZE)
    with transaction.atomic():
        qs = selectors.search(user, f)
        total = qs.count()
        rows = list(qs.prefetch_related("changes")[(page - 1) * size : page * size])
        names = selectors.usernames({r.actor_user_id for r in rows if r.actor_user_id})
        items = [_event_out(r, names) for r in rows]
        services.record(  # last write of the transaction
            actor=user,
            action=Action.AUDIT_VIEWED,
            entity_type="audit_log",
            reason=f"{f.shape()}; page {page}"[:300],  # the shape of the search, never the results
        )
    return AuditEventPageOut(items=items, total=total, page=page, pageSize=size)


@router.get(
    "/events.csv",
    auth=ADMIN,
    response={200: None},
    summary="Download the filtered audit trail as CSV (admin; the download is itself audited)",
)
def export_events(request: HttpRequest, filters: Query[FilterIn]) -> HttpResponse:
    user = current_user(request)
    f = _filters(filters)
    with transaction.atomic():
        rows = list(selectors.search(user, f).prefetch_related("changes")[: selectors.EXPORT_CAP])
        names = selectors.usernames({r.actor_user_id for r in rows if r.actor_user_id})
        text = fmt.to_csv(CSV_HEADER, [_csv_row(_event_out(r, names)) for r in rows])
        services.record(  # last write of the transaction
            actor=user,
            action=Action.AUDIT_EXPORTED,
            entity_type="audit_log",
            reason=f"{f.shape()}; {len(rows)} rows"[:300],
        )
    response = HttpResponse(text, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="audit-log.csv"'
    response["Cache-Control"] = "no-store"
    return response


@router.get(
    "/options", auth=ADMIN, response=AuditOptionsOut, summary="Values the filters offer (admin)"
)
def options(request: HttpRequest) -> dict[str, list[dict[str, str]]]:
    return selectors.filter_options(current_user(request))


@router.get(
    "/chain",
    auth=ADMIN,
    response=AuditChainOut,
    summary="Walk the hash chain and report whether it is intact (admin, read-only)",
)
def chain_status(request: HttpRequest) -> AuditChainOut:
    problems = integrity.verify_chain()
    return AuditChainOut(
        intact=not problems,
        events=AuditEvent.objects.for_user(current_user(request)).count(),
        problemCount=len(problems),
        problems=[
            AuditChainProblemOut(seq=p.seq, eventId=p.event_id, problem=p.problem)
            for p in problems[:10]
        ],
        checkedAt=datetime.now(UTC),
    )
