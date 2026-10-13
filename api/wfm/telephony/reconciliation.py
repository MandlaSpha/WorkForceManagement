"""DAT-02: prove the stored data adds up to the source, by independent routes.

    source    = the engine, straight from the rows read from the file
    stored    = SQL over the call records written for the batch
    intervals = the rebuilt 30-minute intervals against SQL over the same span's call records

Three routes that share no code for the arithmetic: if the importer, the interval rebuild or the
engine has a bug, at least one pair disagrees and `matches` is false.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime
from typing import Any

from django.conf import settings
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce
from wfm_engine.cdr import INBOUND, STATUS_ABANDONED, STATUS_ANSWERED, CallRow
from wfm_engine.kpi import Totals, kpis, totals_for_call

from .models import CallRecord, ImportBatch, IntervalActual, Queue


def reconcile(
    batch: ImportBatch, fresh: Sequence[CallRow], first: datetime, end: datetime
) -> dict[str, Any]:
    source, not_inbound = _source_totals(fresh)
    stored = _stored_totals(batch)

    queue_ids = list(Queue.objects.filter(name__in=source.keys()).values_list("pk", flat=True))
    span_calls = _totals_of(
        CallRecord.objects.filter(
            call_type=INBOUND, queue_id__in=queue_ids, start_at__gte=first, start_at__lt=end
        ).aggregate(**_call_aggregates())
    )
    span_intervals = _totals_of(
        IntervalActual.objects.filter(
            queue_id__in=queue_ids, interval_start__gte=first, interval_start__lt=end
        ).aggregate(**_interval_aggregates())
    )

    per_queue = {
        name: {
            "source": asdict(totals),
            "stored": asdict(stored.get(name, Totals())),
            "matches": totals == stored.get(name, Totals()),
        }
        for name, totals in sorted(source.items())
    }
    overall_source = sum(source.values(), Totals())
    overall_stored = sum(stored.values(), Totals())
    matches = (
        all(q["matches"] for q in per_queue.values())
        and overall_source == overall_stored
        and span_calls == span_intervals
    )
    return {
        "basis": "measured",
        "matches": matches,
        "excluded": {"not_inbound": not_inbound},
        "total": {"source": asdict(overall_source), "stored": asdict(overall_stored)},
        "intervals": {"calls": asdict(span_calls), "intervals": asdict(span_intervals)},
        "queues": per_queue,
        "kpis": asdict(kpis(overall_source)),
        "slThresholdS": settings.WFM_SL_THRESHOLD_S,
    }


def _source_totals(fresh: Sequence[CallRow]) -> tuple[dict[str, Totals], int]:
    totals: dict[str, Totals] = defaultdict(Totals)
    not_inbound = 0
    for call in fresh:
        if call.call_type != INBOUND:
            not_inbound += 1
            continue
        totals[call.queue] = totals[call.queue] + totals_for_call(
            call_type=call.call_type,
            status=call.status,
            wait_s=call.wait_s,
            handle_s=(call.talk_s or 0) + (call.wrap_s or 0),
            sl_threshold_s=settings.WFM_SL_THRESHOLD_S,
        )
    return totals, not_inbound


def _stored_totals(batch: ImportBatch) -> dict[str, Totals]:
    rows = (
        CallRecord.objects.filter(batch=batch, call_type=INBOUND)
        .values("queue__name")
        .annotate(**_call_aggregates())
    )
    return {row["queue__name"]: _totals_of(row) for row in rows}


def _call_aggregates() -> dict[str, Any]:
    """The SQL twin of `wfm_engine.kpi.totals_for_call`."""
    answered = Q(status=STATUS_ANSWERED)
    in_sl = Q(wait_s__lte=settings.WFM_SL_THRESHOLD_S) | Q(wait_s__isnull=True)
    return {
        "offered": Count("id"),
        "answered": Count("id", filter=answered),
        "abandoned": Count("id", filter=Q(status=STATUS_ABANDONED)),
        "answered_in_sl": Count("id", filter=answered & in_sl),
        "sum_wait_s": Coalesce(Sum("wait_s", filter=answered), 0),
        "sum_handle_s": Coalesce(
            Sum(Coalesce(F("talk_s"), 0) + Coalesce(F("wrap_s"), 0), filter=answered), 0
        ),
    }


def _interval_aggregates() -> dict[str, Any]:
    return {name: Coalesce(Sum(name), 0) for name in Totals.__dataclass_fields__}


def _totals_of(values: dict[str, Any]) -> Totals:
    return Totals(**{name: int(values[name]) for name in Totals.__dataclass_fields__})
