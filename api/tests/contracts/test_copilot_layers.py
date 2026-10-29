"""Layer contract for the Copilot (requirements AI-03, tech spec section 8.2): `wfm.copilot` reads
only through other modules' selectors and policies. It never imports another app's models or
services, never touches `.objects`, and never opens a raw database cursor, so the role scoping
inside the selectors cannot be bypassed from here.

Failure caught: a tool "just" importing a model to save writing a selector, which would be a
second route to the data that skips `Model.objects.for_user(user)`.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

COPILOT = Path(__file__).resolve().parents[2] / "wfm" / "copilot"
SOURCES = sorted(p for p in COPILOT.rglob("*.py") if "tests" not in p.parts)

# The only non-selector modules of other apps the Copilot may import: the Role/User types it is
# handed, the audit vocabulary and the audit writer (every question is audited).
ALLOWED_EXACT = {
    "wfm.accounts.models",
    "wfm.audit.models",
    "wfm.audit.services",
}
ALLOWED_SUFFIXES = ("selectors", "policy")  # selectors, copilot_selectors, *_selectors, policy
ALLOWED_PACKAGES = ("wfm.copilot", "wfm.core")


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
            found.extend(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
    return found


def _is_allowed(module: str) -> bool:
    if not module.startswith("wfm."):
        return True
    if module in ALLOWED_EXACT or module.startswith(ALLOWED_PACKAGES):
        return True
    return module.rsplit(".", 1)[-1].endswith(ALLOWED_SUFFIXES)


def test_there_are_sources_to_check() -> None:
    assert {p.name for p in SOURCES} >= {"tools.py", "adapter.py", "guard.py", "services.py"}


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_copilot_imports_only_selectors_and_policies_of_other_modules(path: Path) -> None:
    bad = []
    for module in _imports(path):
        if not module.startswith("wfm."):
            continue
        # `from wfm.people import selectors` appears as the package AND as `wfm.people.selectors`.
        package_only = module.count(".") == 1
        if package_only:
            continue
        if not _is_allowed(module):
            bad.append(module)
    # An alias such as `wfm.audit.AuditEvent` names a symbol, not a module: ignore names that
    # are not modules by checking only the ones that can be files.
    bad = [m for m in bad if not re.search(r"\.[A-Z][A-Za-z]+$", m)]
    assert not bad, f"{path.name} imports {bad}: go through a selector or policy"


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_copilot_never_touches_a_manager_or_a_raw_cursor(path: Path) -> None:
    source = path.read_text(encoding="utf8")
    assert ".objects" not in source, f"{path.name} reads a manager directly"
    assert "_base_manager" not in source
    assert "_default_manager" not in source
    assert not re.search(r"\b(cursor|connection|\.raw\()", source), f"{path.name} uses raw SQL"
