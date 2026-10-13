"""Call data from the ACD: queues, import batches, call records and 30-minute interval actuals.

Privacy by design (POPIA): a call record keeps what workforce planning needs (queue, times,
durations, outcome, the agent's login) and nothing else. The caller's phone number, the number
they dialled and the agent's display name are never stored, and no endpoint serves call-level
rows: people only ever see aggregates.
"""

from __future__ import annotations

import uuid
from typing import Any, Self

from django.db import models

from wfm.accounts.models import User
from wfm.core.scoping import ScopedQuerySet

from .policy import AGGREGATE_ROLES, IMPORT_ROLES


class QueueQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        return self if user.role in AGGREGATE_ROLES else self.none()


class Queue(models.Model):
    """A call queue. Created the first time an import sees its name, then confirmed by an admin
    (tech spec section 5)."""

    name = models.CharField(max_length=100, unique=True)
    confirmed = models.BooleanField(default=False)
    # Staffing assumptions (ENG-01, ENG-02, ENG-05). They start as ASSUMED defaults and are shown
    # as such until an admin confirms them (DAT-10: a defaulted value is never passed off as fact).
    sl_target_pct = models.DecimalField(max_digits=5, decimal_places=2, default=80)
    sl_threshold_s = models.PositiveSmallIntegerField(default=20)
    occupancy_ceiling_pct = models.DecimalField(max_digits=5, decimal_places=2, default=85)
    shrinkage_pct = models.DecimalField(max_digits=5, decimal_places=2, default=30)
    settings_confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(
        db_default=models.Func(function="now", output_field=models.DateTimeField())
    )

    objects = QueueQuerySet.as_manager()

    def __str__(self) -> str:
        return self.name


class ImportBatchQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        return self if user.role in IMPORT_ROLES else self.none()


class ImportBatch(models.Model):
    """One accepted import. Refused imports are not stored; they are audited instead."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file_name = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64, unique=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(
        db_default=models.Func(function="now", output_field=models.DateTimeField())
    )
    source_timezone = models.CharField(max_length=64)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    rows_read = models.PositiveIntegerField()
    rows_inserted = models.PositiveIntegerField()
    rows_duplicate = models.PositiveIntegerField()
    rows_rejected = models.PositiveIntegerField()
    rejected_summary = models.JSONField(default=dict)  # reason code -> count, never cell values
    rejected_samples = models.JSONField(default=list)  # up to 50 of {row, code}
    warnings_summary = models.JSONField(default=dict)  # code -> calls kept with one cell cleared
    sheets_ignored = models.JSONField(default=list)  # sheets this version does not read yet
    reconciliation = models.JSONField(default=dict)

    objects = ImportBatchQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")),
                name="telephony_batch_period_ordered",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.file_name


class CallRecordQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        # Call-level rows are never served to anyone: the API only returns aggregates.
        return self.none()


class CallRecord(models.Model):
    call_id = models.BigIntegerField(unique=True)
    batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT, related_name="calls")
    queue = models.ForeignKey(Queue, on_delete=models.PROTECT, related_name="calls")
    call_type = models.CharField(max_length=30)
    status = models.CharField(max_length=30)
    agent_login = models.CharField(max_length=100, blank=True, default="")
    start_at = models.DateTimeField()
    queue_at = models.DateTimeField(null=True)
    agent_at = models.DateTimeField(null=True)
    hangup_at = models.DateTimeField(null=True)
    call_duration_s = models.PositiveIntegerField(null=True)
    wait_s = models.PositiveIntegerField(null=True)
    talk_s = models.PositiveIntegerField(null=True)
    wrap_s = models.PositiveIntegerField(null=True)
    hold_s = models.PositiveIntegerField(null=True)
    hangup_by = models.CharField(max_length=20, blank=True)

    objects = CallRecordQuerySet.as_manager()

    class Meta:
        indexes = [models.Index(fields=["queue", "start_at"], name="telephony_call_queue_start")]

    def __str__(self) -> str:
        return f"call {self.call_id}"


class IntervalActualQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        if user.role not in AGGREGATE_ROLES:
            return self.none()
        return self.filter(queue__in=Queue.objects.for_user(user))


class IntervalActual(models.Model):
    """Inbound call totals for one queue and one 30-minute interval (DAT-04). Rebuilt from the
    call records by the importer, so it can never drift from them."""

    queue = models.ForeignKey(Queue, on_delete=models.PROTECT, related_name="intervals")
    interval_start = models.DateTimeField()
    offered = models.PositiveIntegerField()
    answered = models.PositiveIntegerField()
    abandoned = models.PositiveIntegerField()
    answered_in_sl = models.PositiveIntegerField()
    sum_wait_s = models.PositiveBigIntegerField()
    sum_handle_s = models.PositiveBigIntegerField()

    objects = IntervalActualQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["queue", "interval_start"], name="telephony_interval_unique"
            ),
        ]
        indexes = [models.Index(fields=["interval_start"], name="telephony_interval_start")]

    def __str__(self) -> str:
        return f"{self.queue_id} {self.interval_start:%Y-%m-%d %H:%M}"
