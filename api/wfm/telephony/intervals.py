"""Building the 30-minute interval actuals (DAT-04) from call records.

This is deliberately SQL, not Python: it runs over every call in the affected span in one
statement. `reconciliation.py` re-derives the same numbers by other routes to prove it is right.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from django.conf import settings
from django.db import connection
from wfm_engine.cdr import INBOUND, STATUS_ABANDONED, STATUS_ANSWERED
from wfm_engine.kpi import INTERVAL_MINUTES

_REBUILD = """
INSERT INTO telephony_intervalactual
    (queue_id, interval_start, offered, answered, abandoned, answered_in_sl,
     sum_wait_s, sum_handle_s)
SELECT queue_id,
       date_bin(%(step)s::interval, start_at, TIMESTAMPTZ '2000-01-01 00:00:00+00') AS slot,
       count(*),
       count(*) FILTER (WHERE status = %(answered)s),
       count(*) FILTER (WHERE status = %(abandoned)s),
       count(*) FILTER (WHERE status = %(answered)s AND coalesce(wait_s, 0) <= %(threshold)s),
       coalesce(sum(coalesce(wait_s, 0)) FILTER (WHERE status = %(answered)s), 0),
       coalesce(sum(coalesce(talk_s, 0) + coalesce(wrap_s, 0))
                FILTER (WHERE status = %(answered)s), 0)
FROM telephony_callrecord
WHERE call_type = %(inbound)s
  AND queue_id = ANY(%(queues)s)
  AND start_at >= %(first)s AND start_at < %(end)s
GROUP BY queue_id, slot
ON CONFLICT (queue_id, interval_start) DO UPDATE SET
    offered = EXCLUDED.offered,
    answered = EXCLUDED.answered,
    abandoned = EXCLUDED.abandoned,
    answered_in_sl = EXCLUDED.answered_in_sl,
    sum_wait_s = EXCLUDED.sum_wait_s,
    sum_handle_s = EXCLUDED.sum_handle_s
"""


def rebuild(queue_ids: Sequence[int], first: datetime, end: datetime) -> None:
    """Recompute whole intervals from the call records between `first` (an interval start) and
    `end`, so an interval touched by two imports is always the sum of all its calls."""
    with connection.cursor() as cursor:
        cursor.execute(
            _REBUILD,
            {
                "step": f"{INTERVAL_MINUTES} minutes",
                "answered": STATUS_ANSWERED,
                "abandoned": STATUS_ABANDONED,
                "threshold": settings.WFM_SL_THRESHOLD_S,
                "inbound": INBOUND,
                "queues": list(queue_ids),
                "first": first,
                "end": end,
            },
        )
