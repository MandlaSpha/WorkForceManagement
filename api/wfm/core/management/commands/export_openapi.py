"""Write the API's OpenAPI schema to a file. The web app generates its typed client from it,
so a backend change that breaks the UI fails the front-end type check (standards section 3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from wfm.api import api


class Command(BaseCommand):
    help = "Export the OpenAPI schema as JSON."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("output", type=Path)

    def handle(self, *args: Any, **options: Any) -> None:
        output: Path = options["output"]
        schema = api.get_openapi_schema()
        output.parent.mkdir(parents=True, exist_ok=True)
        # Stable output (sorted keys, trailing newline) so the CI "client is up to date" check
        # does not flap.
        output.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.stdout.write(f"Wrote {output}")
