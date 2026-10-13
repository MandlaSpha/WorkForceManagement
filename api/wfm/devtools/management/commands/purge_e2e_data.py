"""Delete the synthetic data the browser tests create (development only).

Every end-to-end run imports a small made-up report into the dev database, in a queue called
"E2E Queue" (or one whose name starts with that), and runs forecasts on it. This removes those
queues' forecasts, calls, intervals and import batches so they do not pile up next to real data.
A batch is deleted only when ALL of its calls were in test queues.

It lives in its own app, installed only in development and test settings, because it must know
every feature that holds data about a queue and so sits at the top of the dependency graph: the
feature apps must never import it, and production does not contain it at all.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.forecasting.models import ForecastVersion
from wfm.telephony.models import CallRecord, ImportBatch, IntervalActual, Queue

DEFAULT_PREFIX = "E2E Queue"


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
        if not queues:
            self.stdout.write("Nothing to purge.")
            return

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
            Queue.objects.filter(pk__in=[q.pk for q in queues]).delete()
            audit.record(  # last write of the transaction
                actor=None,
                action=Action.DEV_DATA_PURGED,
                entity_type="queue",
                entity_id=prefix,
                reason=f"{calls} calls, {len(batch_ids)} imports, {forecasts} forecasts",
            )
        self.stdout.write(
            f"Purged {calls} calls, {len(batch_ids)} imports and {forecasts} forecasts "
            f"from {len(queues)} test queue(s)."
        )
