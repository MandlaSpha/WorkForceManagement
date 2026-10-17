"""Two API schemas with the same name collapse into one in the OpenAPI document, so the generated
web types for one of them are silently wrong. Every schema class must have a name no other has."""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # the wfm package


def test_every_api_schema_has_a_name_of_its_own() -> None:
    # Failure caught: a second `DayOut` or `SlotOut` replacing the first in the generated types.
    seen: dict[str, list[str]] = defaultdict(list)
    for path in ROOT.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef) and any(
                getattr(base, "id", getattr(base, "attr", "")) == "Schema" for base in node.bases
            ):
                seen[node.name].append(str(path.relative_to(ROOT)))
    clashes = {name: files for name, files in seen.items() if len(files) > 1}
    assert clashes == {}, clashes
