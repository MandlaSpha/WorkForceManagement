"""Bringing work items in and setting a pool's productive time. Writes happen here, in one
transaction, with the audit event as the LAST write (hard rule: the audit insert holds the
audit-chain lock until commit)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action, Outcome
from wfm.core.errors import ApiError, not_found

from . import importer
from .models import ServicePool, WorkItem

LOOKUP_CHUNK = 5000
FIELDS = (
    "pool_id",
    "priority",
    "opened_at",
    "due_at",
    "effort_minutes",
    "closed_at",
    "first_contact_resolved",
    "csat",
    "nps",
)


@dataclass(frozen=True, slots=True)
class ImportResult:
    created: int
    updated: int
    unchanged: int
    rejected: dict[str, int]
    ignored_columns: list[str]


def import_items(*, user: User, content: bytes) -> ImportResult:
    """Add the work items of a CSV and update the ones already known (matched on their reference),
    so the same export can be brought in again as tickets are worked and closed. Nothing is ever
    deleted. Only the known columns are read; anything else in the file is ignored."""
    zone = ZoneInfo(settings.TIME_ZONE)
    try:
        parsed = importer.parse(content, zone)
    except importer.UnreadableFileError as error:
        audit.record(
            actor=user,
            action=Action.WORKITEMS_IMPORT_REFUSED,
            outcome=Outcome.FAILED,
            entity_type="work_items",
            reason="unreadable",
        )
        raise ApiError(422, "workitems.unreadable", "Unusable file", str(error)) from error

    with transaction.atomic():
        pools = _ensure_pools({row.pool for row in parsed.rows})
        known = _known({row.ref for row in parsed.rows})
        create: list[WorkItem] = []
        update: list[WorkItem] = []
        unchanged = 0
        for row in parsed.rows:
            values = {
                "pool_id": pools[row.pool].pk,
                "priority": row.priority,
                "opened_at": row.opened_at,
                "due_at": row.due_at,
                "effort_minutes": row.effort_minutes,
                "closed_at": row.closed_at,
                "first_contact_resolved": row.first_contact_resolved,
                "csat": row.csat,
                "nps": row.nps,
            }
            item = known.get(row.ref)
            if item is None:
                create.append(WorkItem(ref=row.ref, **values))
            elif any(getattr(item, name) != value for name, value in values.items()):
                for name, value in values.items():
                    setattr(item, name, value)
                update.append(item)
            else:
                unchanged += 1
        WorkItem.objects.bulk_create(create)
        WorkItem.objects.bulk_update(update, list(FIELDS))
        rejected = sum(parsed.rejected.values())
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.WORKITEMS_IMPORTED,
            entity_type="work_items",
            entity_id="import",
            changes=[
                audit.FieldChange("work_items", "import", name, None, str(value))
                for name, value in (
                    ("created", len(create)),
                    ("updated", len(update)),
                    ("unchanged", unchanged),
                    ("rejected", rejected),
                )
            ],
        )
    return ImportResult(
        len(create), len(update), unchanged, parsed.rejected, parsed.ignored_columns
    )


def _ensure_pools(names: set[str]) -> dict[str, ServicePool]:
    """Pools are created on first sight, with the default productive time, for an admin or planner
    to confirm."""
    ServicePool.objects.bulk_create(
        [ServicePool(name=n) for n in sorted(names)], ignore_conflicts=True
    )
    return {p.name: p for p in ServicePool.objects.filter(name__in=names)}


def _known(refs: set[str]) -> dict[str, WorkItem]:
    found: dict[str, WorkItem] = {}
    ordered: Sequence[str] = sorted(refs)
    for at in range(0, len(ordered), LOOKUP_CHUNK):
        chunk = ordered[at : at + LOOKUP_CHUNK]
        for item in WorkItem.objects.filter(ref__in=chunk):
            found[item.ref] = item
    return found


def set_productive_minutes(*, user: User, pool_id: int, minutes: int) -> ServicePool:
    """How many minutes of a working day an engineer in this pool really spends on tickets. Marks
    the pool's assumption confirmed."""
    if not 30 <= minutes <= 600:
        raise ApiError(
            422,
            "pool.minutes_invalid",
            "Invalid request",
            "Productive time is between 30 and 600 minutes a day.",
        )
    with transaction.atomic():
        pool: ServicePool | None = (
            ServicePool.objects.select_for_update(no_key=True)
            .for_user(user)
            .filter(pk=pool_id)
            .first()
        )
        if pool is None:
            raise not_found("No such pool.")
        changes = []
        if pool.productive_minutes_per_day != minutes:
            changes.append(
                audit.FieldChange(
                    "service_pool",
                    str(pool.pk),
                    "productive_minutes_per_day",
                    str(pool.productive_minutes_per_day),
                    str(minutes),
                )
            )
        if not pool.settings_confirmed:
            changes.append(
                audit.FieldChange(
                    "service_pool", str(pool.pk), "settings_confirmed", "False", "True"
                )
            )
        pool.productive_minutes_per_day = minutes
        pool.settings_confirmed = True
        pool.save(update_fields=["productive_minutes_per_day", "settings_confirmed"])
        if changes:
            audit.record(  # last write of the transaction
                actor=user,
                action=Action.SERVICE_POOL_CHANGED,
                entity_type="service_pool",
                entity_id=str(pool.pk),
                changes=changes,
            )
    return pool
