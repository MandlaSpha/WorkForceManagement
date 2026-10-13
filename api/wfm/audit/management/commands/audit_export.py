"""Export one UTC day's audit chain heads for copying to immutable storage (AUD-10)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from wfm.audit import integrity


class Command(BaseCommand):
    help = "Write a day's audit chain heads to a file and print its SHA-256."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("output", type=Path, help="File to write (JSON lines).")
        parser.add_argument(
            "--date",
            type=date.fromisoformat,
            default=None,
            help="UTC day to export, YYYY-MM-DD. Defaults to yesterday.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        day = options["date"] or (timezone.now() - timedelta(days=1)).date()
        digest = integrity.export_day(day, options["output"])
        self.stdout.write(f"{options['output']}  sha256={digest}  day={day}")
