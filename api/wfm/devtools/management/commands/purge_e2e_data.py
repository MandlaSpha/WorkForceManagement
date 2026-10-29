"""Delete the synthetic data the browser tests create (development only).

Every end-to-end run imports a small made-up report into the dev database, in a queue called
"E2E Queue" (or one whose name starts with that), and runs forecasts on it. This removes those
queues' forecasts, calls, intervals and import batches so they do not pile up next to real data.
A batch is deleted only when ALL of its calls were in test queues.

It also removes the other made-up rows the specs leave: shift templates, employees (with the leave,
overtime and swap rows made for them), customers and forecast events, found by the tight patterns
below and never when something real still points at them.

It lives in its own app, installed only in development and test settings, because it must know
every feature that holds data about a queue and so sits at the top of the dependency graph: the
feature apps must never import it, and production does not contain it at all.
"""

from __future__ import annotations

import re
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.db.models import PROTECT, ForeignObjectRel, Model, ProtectedError

from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.contracts.models import Customer
from wfm.forecasting.models import ForecastEvent, ForecastVersion
from wfm.scheduling.models import Employee, ShiftTemplate
from wfm.telephony.models import CallRecord, ImportBatch, IntervalActual, Queue

DEFAULT_PREFIX = "E2E Queue"

# Made-up rows the browser specs leave besides queues. Each pattern is deliberately tight, so a
# real row can only match by looking exactly like test data, and a row is only deleted when
# nothing real still points at it (see _purge_one). New specs should name their data with the
# "E2E" marker; the older shapes stay listed so rows from earlier runs are still cleaned.
#   shift code:  E2E123456, E2EA1234 (current) | T123456, SA4318, SB4318, A123456, C123456 (old)
SHIFT_CODE = re.compile(r"E2E[A-Z]?\d+|T\d{4,}|S[AB]\d{3,}|[AC]\d{5,}")
#   employee number: E2E-123456A (current) | T123456A, SA..., U..., I..., O..., R..., A..., C...
EMP_NO = re.compile(r"E2E-[A-Z0-9-]+|(?:T|SA|U|I|O|R|A|C)\d{4,}[A-Z0-9]?")
#   employee name: "E2E Pat 123456" (current) | "Pat Example 123456", "Unmanaged 123456", ...
#   BOTH the number and the name must match, and the person must have no login attached.
EMP_NAME = re.compile(r"E2E .+|[A-Za-z]+ [A-Za-z]+ \d{3,}|Unmanaged \d{3,}")
CUSTOMER_PREFIX = "E2E Customer "
EVENT_NAME = re.compile(r"Payment run \d{4,}|E2E .+")


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--prefix",
            default=DEFAULT_PREFIX,
            help="Queues whose name starts with this are test queues.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("Refusing to run: this deletes data and is for development only.")
        prefix = str(options["prefix"]).strip()
        if len(prefix) < 3:
            raise CommandError("The prefix is too short to be safe.")
        queues = list(Queue.objects.filter(name__startswith=prefix))

        with transaction.atomic():
            calls = forecasts = 0
            batch_ids: set[Any] = set()
            for queue in queues:
                # Batches that hold calls from any other queue are kept, whatever else they hold.
                mixed = CallRecord.objects.exclude(queue__in=queues).values("batch_id")
                batches = ImportBatch.objects.filter(calls__queue=queue).exclude(pk__in=mixed)
                batch_ids.update(batches.values_list("pk", flat=True).distinct())
                calls += CallRecord.objects.filter(queue=queue).count()
                forecasts += ForecastVersion.objects.filter(queue=queue).count()
                ForecastVersion.objects.filter(queue=queue).delete()  # its intervals go with it
                IntervalActual.objects.filter(queue=queue).delete()
                CallRecord.objects.filter(queue=queue).delete()
            ImportBatch.objects.filter(pk__in=batch_ids).delete()
            # Skills, rosters, swaps and the like point at the queue with PROTECT, so the queue
            # cannot go while they exist. They belong to the test queue, so they go first.
            for relation in Queue._meta.get_fields(include_hidden=True):
                if not isinstance(relation, ForeignObjectRel) or relation.on_delete is not PROTECT:
                    continue
                if relation.related_model is None:  # a reverse relation always names its model
                    continue
                relation.related_model._base_manager.filter(
                    **{f"{relation.field.name}__in": queues}
                ).delete()
            Queue.objects.filter(pk__in=[q.pk for q in queues]).delete()

            # After the queues, so their rosters are gone and a test shift is no longer "in use".
            extras = {
                "employees": self._purge(
                    Employee.objects.filter(user__isnull=True),
                    lambda e: bool(EMP_NO.fullmatch(e.emp_no) and EMP_NAME.fullmatch(e.name)),
                    with_dependents=True,
                ),
                "shifts": self._purge(
                    ShiftTemplate.objects.all(), lambda t: bool(SHIFT_CODE.fullmatch(t.code))
                ),
                "customers": self._purge(
                    Customer.objects.filter(name__startswith=CUSTOMER_PREFIX),
                    lambda c: True,
                    with_dependents=True,
                ),
                "events": self._purge(
                    ForecastEvent.objects.all(), lambda e: bool(EVENT_NAME.fullmatch(e.name))
                ),
            }
            if not queues and not any(v[0] for v in extras.values()):
                self.stdout.write("Nothing to purge.")
                return
            reason = f"{calls} calls, {len(batch_ids)} imports, {forecasts} forecasts"
            for label, (removed, _, _) in extras.items():
                if removed:
                    reason += f", {removed} {label}"
            audit.record(  # last write of the transaction
                actor=None,
                action=Action.DEV_DATA_PURGED,
                entity_type="queue",
                entity_id=prefix,
                reason=reason,
            )
        self.stdout.write(
            f"Purged {calls} calls, {len(batch_ids)} imports and {forecasts} forecasts "
            f"from {len(queues)} test queue(s)."
        )
        for label, (removed, kept, rows) in extras.items():
            self.stdout.write(
                f"Purged {removed} {label} ({rows} rows in all); kept {kept} still in use."
            )

    @staticmethod
    def _purge(
        candidates: Any, is_test: Any, with_dependents: bool = False
    ) -> tuple[int, int, int]:
        """Delete the candidates that look like test data. Returns (removed, kept, rows).

        An object that something else still points at (PROTECT) is kept, unless it is a person or
        customer that is itself test data: then the rows that depend on it go first, because they
        were made for it. Each object is tried in its own savepoint so one kept object never
        blocks the rest.
        """
        removed = kept = rows = 0
        for obj in [o for o in candidates if is_test(o)]:
            try:
                with transaction.atomic():
                    count = 0
                    if with_dependents:
                        count += _delete_protected_dependents(obj)
                    count += obj.delete()[0]
            except ProtectedError:
                kept += 1
                continue
            removed += 1
            rows += count
        return removed, kept, rows


def _delete_protected_dependents(obj: Model) -> int:
    """Delete rows that point at obj with PROTECT (a contract of a customer, a swap of a person)."""
    total = 0
    for relation in type(obj)._meta.get_fields(include_hidden=True):
        if not isinstance(relation, ForeignObjectRel) or relation.on_delete is not PROTECT:
            continue
        if relation.related_model is None:
            continue
        total += relation.related_model._base_manager.filter(**{relation.field.name: obj}).delete()[
            0
        ]
    return total
