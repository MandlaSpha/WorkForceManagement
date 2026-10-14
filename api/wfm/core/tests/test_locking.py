"""Row locks must not block another transaction's foreign-key check.

A plain `SELECT ... FOR UPDATE` on a row conflicts with the `FOR KEY SHARE` lock that PostgreSQL
takes on a referenced row when someone inserts a row pointing at it (a deferred foreign key is
checked at COMMIT). Our services lock a row, then write an audit event as their last step, and the
audit insert waits for the audit-chain lock; a transaction that holds that chain lock and is
committing a row that points at the locked row then waits for the first one: a deadlock. It showed
up when two browsers signed in as the same user while that user's import was committing.

The services lock with `FOR NO KEY UPDATE` (`no_key=True`), which never conflicts with a key-share.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from django.db import OperationalError, connection, connections, transaction

from wfm.accounts.models import Role, User
from wfm.forecasting.models import ForecastEvent

pytestmark = pytest.mark.django_db

WFM = Path(__file__).resolve().parents[2]


def in_own_connection(work: Callable[[], Any]) -> Any:
    """Run `work` in another thread, so it has its own database connection and its own
    transaction: committed rows are really committed, and it really waits on locks."""
    result: list[Any] = []

    def target() -> None:
        try:
            result.append(work())
        finally:
            connections.close_all()

    thread = threading.Thread(target=target)
    thread.start()
    thread.join(timeout=15)
    return result[0] if result else "hung"


@pytest.fixture
def committed_user() -> Iterator[int]:
    """A user that is really in the database (not only inside this test's own transaction), and
    removed again afterwards."""
    user_id: int = in_own_connection(
        lambda: User.objects.create(username="locked", role=Role.PLANNER).pk
    )
    yield user_id
    in_own_connection(lambda: ForecastEvent.objects.filter(created_by_id=user_id).delete())
    in_own_connection(lambda: User.objects.filter(pk=user_id).delete())


def _add_event_pointing_at(user_id: int) -> str:
    """Add a row that references the user and commit, which takes the key-share lock on the user's
    row. Gives up after a second instead of waiting."""
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '1s'")
            ForecastEvent.objects.create(
                name="e",
                date_from=date(2026, 1, 1),
                date_to=date(2026, 1, 1),
                uplift_pct=1,
                created_by_id=user_id,
            )
        return "committed"
    except OperationalError:
        return "blocked"


def _commit_while_user_is_locked(user_id: int, *, no_key: bool) -> str:
    with transaction.atomic():
        User.objects.select_for_update(no_key=no_key).filter(pk=user_id).get()
        return str(in_own_connection(lambda: _add_event_pointing_at(user_id)))


def test_a_lock_that_changes_no_key_does_not_hold_up_a_row_that_points_at_it(
    committed_user: int,
) -> None:
    assert _commit_while_user_is_locked(committed_user, no_key=True) == "committed"


def test_the_plain_lock_does_hold_it_up_which_is_the_deadlock_this_guards_against(
    committed_user: int,
) -> None:
    # The control: it is why the services must not use the plain lock. If this ever stops
    # blocking, the test above no longer proves anything.
    assert _commit_while_user_is_locked(committed_user, no_key=False) == "blocked"


def test_every_service_locks_with_no_key() -> None:
    """The next service written cannot quietly bring the deadlock back."""
    offenders: list[str] = []
    for path in WFM.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"select_for_update\(((?:[^()]|\([^()]*\))*)\)", text):
            if "no_key=True" not in match.group(1):
                offenders.append(f"{path.relative_to(WFM)}: {match.group(0)}")
    assert offenders == []
