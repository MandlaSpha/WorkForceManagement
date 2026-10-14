"""The events calendar (requirements FC-04). Writes happen here, in one transaction, with the audit
event as the LAST write (hard rule: the audit insert holds the audit-chain lock until commit)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError, not_found
from wfm.telephony.models import Queue

from .models import ForecastEvent

MAX_DAYS = 366
MIN_UPLIFT = Decimal(-100)  # no calls at all: the queue is closed
MAX_UPLIFT = Decimal(500)


def _invalid(code: str, detail: str) -> ApiError:
    return ApiError(422, code, "Invalid request", detail)


def _check(name: str, date_from: date, date_to: date, uplift_pct: Decimal) -> str:
    name = name.strip()
    if not 1 <= len(name) <= 100:
        raise _invalid("event.name_invalid", "An event needs a name of 1 to 100 characters.")
    if date_to < date_from:
        raise _invalid("event.range_invalid", "The event ends before it starts.")
    if (date_to - date_from).days + 1 > MAX_DAYS:
        raise _invalid("event.range_too_long", f"An event lasts at most {MAX_DAYS} days.")
    if not MIN_UPLIFT <= uplift_pct <= MAX_UPLIFT:
        raise _invalid("event.uplift_invalid", "The change is between -100% and +500%.")
    return name


def _queue(user: User, queue_id: int | None) -> Queue | None:
    if queue_id is None:
        return None
    queue: Queue | None = Queue.objects.for_user(user).filter(pk=queue_id).first()
    if queue is None:
        raise not_found("No such queue.")
    return queue


def _describe(event: ForecastEvent) -> dict[str, str]:
    return {
        "name": event.name,
        "queue": event.queue.name if event.queue else "all queues",
        "range": f"{event.date_from}..{event.date_to}",
        "uplift_pct": f"{event.uplift_pct:+}",
    }


def create_event(
    *,
    user: User,
    name: str,
    queue_id: int | None,
    date_from: date,
    date_to: date,
    uplift_pct: Decimal,
) -> ForecastEvent:
    name = _check(name, date_from, date_to, uplift_pct)
    queue = _queue(user, queue_id)
    with transaction.atomic():
        event = ForecastEvent.objects.create(
            name=name,
            queue=queue,
            date_from=date_from,
            date_to=date_to,
            uplift_pct=uplift_pct,
            created_by=user,
        )
        event.refresh_from_db()
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.FORECAST_EVENT_CREATED,
            entity_type="forecast_event",
            entity_id=str(event.pk),
            changes=[
                audit.FieldChange("forecast_event", str(event.pk), field, None, value)
                for field, value in _describe(event).items()
            ],
        )
    return event


def update_event(
    *,
    user: User,
    event_id: int,
    name: str,
    queue_id: int | None,
    date_from: date,
    date_to: date,
    uplift_pct: Decimal,
) -> ForecastEvent:
    name = _check(name, date_from, date_to, uplift_pct)
    queue = _queue(user, queue_id)
    with transaction.atomic():
        found: ForecastEvent | None = (
            ForecastEvent.objects.select_for_update(of=("self",))
            .for_user(user)
            .select_related("queue")
            .filter(pk=event_id)
            .first()
        )
        if found is None:
            raise not_found("No such event.")
        event = found
        before = _describe(event)
        event.name, event.queue = name, queue
        event.date_from, event.date_to, event.uplift_pct = date_from, date_to, uplift_pct
        event.save()
        event.refresh_from_db()
        after = _describe(event)
        changes = [
            audit.FieldChange("forecast_event", str(event.pk), field, before[field], after[field])
            for field in after
            if before[field] != after[field]
        ]
        if changes:
            audit.record(  # last write of the transaction
                actor=user,
                action=Action.FORECAST_EVENT_CHANGED,
                entity_type="forecast_event",
                entity_id=str(event.pk),
                changes=changes,
            )
    return event


def delete_event(*, user: User, event_id: int) -> None:
    """Forecasts already run keep the events they used (recorded on the version)."""
    with transaction.atomic():
        found: ForecastEvent | None = (
            ForecastEvent.objects.select_for_update(of=("self",))
            .for_user(user)
            .select_related("queue")
            .filter(pk=event_id)
            .first()
        )
        if found is None:
            raise not_found("No such event.")
        event = found
        described = _describe(event)
        pk = event.pk
        event.delete()
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.FORECAST_EVENT_DELETED,
            entity_type="forecast_event",
            entity_id=str(pk),
            changes=[
                audit.FieldChange("forecast_event", str(pk), field, value, None)
                for field, value in described.items()
            ],
        )
