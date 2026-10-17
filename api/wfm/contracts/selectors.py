"""Reading customers and contracts, and how each contract is doing (CAP-04).

A contract's risk joins two different kinds of figure and says which is which (DAT-10): the service
level actually MEASURED over the last 28 days of imported calls, and the coverage MODELLED for a
week (the roster against the published forecast). Nothing is invented: a contract with no calls in
the window has no measured service level, and a queue with no forecast has no known gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from wfm_engine.kpi import Totals, kpis

from wfm.accounts.models import User
from wfm.scheduling.selectors import week_plan
from wfm.telephony.models import Queue
from wfm.telephony.selectors import kpi_summary

from .models import Contract, ContractQueue, Customer

WINDOW_DAYS = 28


def customers(user: User) -> list[Customer]:
    return list(Customer.objects.for_user(user))


@dataclass(slots=True)
class ContractRow:
    contract: Contract
    queues: list[Queue]
    offered: int = 0  # calls in the window, from imported call data
    measured_sl_pct: float | None = None  # None: no calls in the window
    intervals_known: int = 0  # half-hours of the week with a known requirement
    under_intervals: int = 0
    gap: int = 0  # people short, summed over the half-hours of the week
    risks: list[str] = field(default_factory=list)

    @property
    def at_risk(self) -> bool:
        return bool(self.risks)


def contract_rows(user: User, week_start: date) -> list[ContractRow]:
    today = timezone.localdate()
    window_from, window_to = today - timedelta(days=WINDOW_DAYS), today - timedelta(days=1)

    members: dict[int, list[Queue]] = {}
    for link in ContractQueue.objects.for_user(user).select_related("queue"):
        members.setdefault(link.contract_id, []).append(link.queue)

    measured = {q.queue_id: q.totals for q in kpi_summary(user, window_from, window_to).queues}
    # Only the queues a contract holds: planning every queue of the site just to read these few
    # made this screen slower with every queue anybody ever made.
    held = {q.pk: q for queues in members.values() for q in queues}
    coverage = {queue_id: week_plan(user, queue_id, week_start).summary for queue_id in held}

    rows: list[ContractRow] = []
    for contract in Contract.objects.for_user(user).select_related("customer"):
        queues = sorted(members.get(contract.pk, []), key=lambda q: q.name)
        row = ContractRow(contract=contract, queues=queues)
        totals = Totals()
        for queue in queues:
            totals = totals + measured.get(queue.pk, Totals())
            summary = coverage.get(queue.pk)
            if summary is not None:
                row.intervals_known += summary.intervals_known
                row.under_intervals += summary.under_intervals
                row.gap += summary.gap
        row.offered = totals.offered
        row.measured_sl_pct = kpis(totals).service_level_pct if totals.offered > 0 else None
        _judge(row)
        rows.append(row)
    return rows


def _judge(row: ContractRow) -> None:
    target = float(Decimal(str(row.contract.sl_target_pct)))
    if row.measured_sl_pct is not None and row.measured_sl_pct < target:
        row.risks.append(
            f"service level {row.measured_sl_pct:.1f}% over the last {WINDOW_DAYS} days is below "
            f"the {target:g}% promised"
        )
    if row.gap > 0:
        row.risks.append(
            f"{row.under_intervals} half-hours of the week are short of the people needed"
        )
