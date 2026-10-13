"""Delete the synthetic call data the browser tests import (development only).

Every end-to-end run imports a small made-up report into the dev database, in a queue called
"E2E Queue". This removes that queue's calls, intervals and import batches so they do not pile up
next to real data. It refuses to run outside development and never touches another queue: a
batch is deleted only when ALL of its calls were in the test queue.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.telephony.models import CallRecord, ImportBatch, IntervalActual, Queue

DEFAULT_QUEUE = "E2E Queue"


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--queue", default=DEFAULT_QUEUE, help="Name of the test queue.")

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("Refusing to run: this deletes data and is for development only.")
        queue = Queue.objects.filter(name=options["queue"]).first()
        if queue is None:
            self.stdout.write("Nothing to purge.")
            return

        with transaction.atomic():
            # Batches that hold calls from any other queue are kept, whatever else they hold.
            mixed = CallRecord.objects.exclude(queue=queue).values("batch_id")
            batches = ImportBatch.objects.filter(calls__queue=queue).exclude(pk__in=mixed)
            batch_ids = list(batches.values_list("pk", flat=True).distinct())
            calls = CallRecord.objects.filter(queue=queue).count()
            IntervalActual.objects.filter(queue=queue).delete()
            CallRecord.objects.filter(queue=queue).delete()
            ImportBatch.objects.filter(pk__in=batch_ids).delete()
            queue.delete()
            audit.record(  # last write of the transaction
                actor=None,
                action=Action.DEV_DATA_PURGED,
                entity_type="queue",
                entity_id=options["queue"],
                reason=f"{calls} calls, {len(batch_ids)} imports",
            )
        self.stdout.write(
            f"Purged {calls} calls and {len(batch_ids)} imports from {options['queue']}."
        )
