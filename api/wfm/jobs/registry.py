"""What each kind of job does. A runner gets the owner and the job parameters and returns the
result (counts and ids only). It must do its work through the same services a click would use, so
the owner's scope, the roster rules and the audit trail all apply."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from wfm.accounts.models import User

Runner = Callable[[User, dict[str, Any]], dict[str, Any]]

RUNNERS: dict[str, Runner] = {}


def register(kind: str) -> Callable[[Runner], Runner]:
    def decorate(runner: Runner) -> Runner:
        if kind in RUNNERS:
            raise RuntimeError(f"job kind {kind!r} is registered twice")
        RUNNERS[kind] = runner
        return runner

    return decorate
