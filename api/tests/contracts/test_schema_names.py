"""Two apps must not define an API schema with the same class name.

The OpenAPI description names every schema by its class, so two classes called `ImportOut` become
one entry and the generated web types silently describe the wrong one (it happened when the
service desk added an `ImportOut` beside the call-report one).
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections import defaultdict

from ninja import Schema

import wfm


def test_every_schema_class_name_is_used_by_one_app_only() -> None:
    owners: dict[str, set[str]] = defaultdict(set)
    for module_info in pkgutil.walk_packages(wfm.__path__, "wfm."):
        if not module_info.name.rsplit(".", 1)[-1].endswith("schemas"):  # schemas, swap_schemas
            continue
        module = importlib.import_module(module_info.name)
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, Schema) and cls.__module__ == module.__name__:
                owners[name].add(module.__name__)
    clashes = {name: sorted(mods) for name, mods in owners.items() if len(mods) > 1}
    assert clashes == {}, f"rename one of each: {clashes}"
