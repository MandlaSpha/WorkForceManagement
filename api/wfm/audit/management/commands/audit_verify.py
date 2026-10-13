"""Check the audit hash chain. Exit status 1 if it is broken, so a scheduler or CI job can alert."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from wfm.audit import integrity


class Command(BaseCommand):
    help = "Verify the audit trail's hash chain."

    def handle(self, *args: Any, **options: Any) -> None:
        problems = integrity.verify_chain()
        if not problems:
            self.stdout.write(self.style.SUCCESS("Audit chain intact."))
            return
        for p in problems:
            self.stderr.write(f"seq={p.seq} event={p.event_id}: {p.problem}")
        raise CommandError(f"Audit chain broken: {len(problems)} problem(s).")
