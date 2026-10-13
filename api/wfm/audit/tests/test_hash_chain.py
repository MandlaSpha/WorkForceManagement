"""The audit hash chain (AUD-10): it forms correctly, and every kind of tampering is detected, even
by someone with superuser rights who has switched the append-only triggers off."""

from __future__ import annotations

import hashlib
import io
import logging
import re
import threading
import time
from datetime import date
from itertools import pairwise
from pathlib import Path
from typing import Any

import psycopg
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone

from wfm.audit import integrity, services
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.audit.tasks import verify_audit_chain

GENESIS = "0" * 64
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def make_event(reason: str = "", *, changes: int = 0) -> AuditEvent:
    return services.record(
        actor=None,
        action="test.event",
        reason=reason,
        changes=[
            services.FieldChange("leave", "42", f"f{i}", "old", f"new{i}") for i in range(changes)
        ],
    )


def chain() -> list[AuditEvent]:
    return list(AuditEvent.objects.order_by("chain_seq"))


def event_then_failure() -> None:
    """An audited change whose transaction fails after the event was written."""
    from django.db import transaction

    with transaction.atomic():
        make_event("rolled back")
        raise RuntimeError


def bypass(sql: str, params: list[Any] | None = None) -> None:
    """Do what an attacker with superuser rights would: switch the guard triggers off, then edit.
    Everything is rolled back with the test's transaction, triggers included."""
    with connection.cursor() as cursor:
        # Rows inserted in this same transaction still have foreign-key checks pending, and
        # PostgreSQL refuses ALTER TABLE until those have run.
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("ALTER TABLE audit_auditevent DISABLE TRIGGER audit_event_append_only")
        cursor.execute("ALTER TABLE audit_auditchange DISABLE TRIGGER audit_change_append_only")
        cursor.execute(sql, params or [])


@pytest.mark.django_db
class TestChainForms:
    def test_events_form_a_chain_from_a_genesis_value(self) -> None:
        for i in range(3):
            make_event(f"event {i}")

        events = chain()

        assert [e.chain_seq for e in events] == [1, 2, 3]
        assert events[0].prev_hash == GENESIS
        for previous, current in pairwise(events):
            assert current.prev_hash == previous.hash
        assert all(HEX64.match(e.hash) for e in events)
        assert len({e.hash for e in events}) == 3

    def test_python_cannot_choose_the_hash_or_the_position(self) -> None:
        make_event("first")
        forged = AuditEvent.objects.create(
            actor_type="system",
            action="test.forged",
            outcome="success",
            chain_seq=999,
            prev_hash="f" * 64,
            hash="a" * 64,
            hash_version=7,
        )

        forged.refresh_from_db()

        assert forged.chain_seq == 2
        assert forged.prev_hash == chain()[0].hash
        assert forged.hash != "a" * 64
        assert forged.hash_version == 1

    def test_change_rows_are_hashed_against_their_event(self) -> None:
        event = make_event(changes=2)
        hashes = list(AuditChange.objects.filter(event=event).values_list("hash", flat=True))
        assert len(set(hashes)) == 2
        assert all(HEX64.match(h) for h in hashes)

    def test_an_intact_chain_verifies_clean(self) -> None:
        make_event("a", changes=2)
        make_event("b")
        make_event("c", changes=1)
        assert integrity.verify_chain() == []

    def test_an_empty_chain_verifies_clean(self) -> None:
        assert integrity.verify_chain() == []

    def test_a_rolled_back_event_leaves_no_gap(self) -> None:
        make_event("kept")
        with pytest.raises(RuntimeError):
            event_then_failure()
        make_event("after")

        assert [e.chain_seq for e in chain()] == [1, 2]
        assert integrity.verify_chain() == []


@pytest.mark.django_db
class TestTamperingIsDetected:
    def test_editing_an_events_content(self) -> None:
        make_event("original")
        target = make_event("original too")
        make_event("later")

        bypass("UPDATE audit_auditevent SET reason = 'rewritten' WHERE id = %s", [target.pk])

        problems = integrity.verify_chain()
        assert [(p.seq, "altered" in p.problem) for p in problems] == [(2, True)]

    def test_deleting_an_event_from_the_middle(self) -> None:
        make_event("one")
        victim = make_event("two")
        make_event("three")

        bypass("DELETE FROM audit_auditevent WHERE id = %s", [victim.pk])

        problems = integrity.verify_chain()
        assert any("sequence break" in p.problem for p in problems)
        assert any("prev_hash" in p.problem for p in problems)

    def test_deleting_the_most_recent_event_is_caught_by_the_exported_checkpoint(
        self, tmp_path: Path
    ) -> None:
        # The chain alone cannot see a missing *tail*; the daily export can: it records the last
        # hash, which no longer exists in the database afterwards.
        make_event("one")
        tail = make_event("two")
        digest = integrity.export_day(timezone.now().date(), tmp_path / "day.jsonl")
        exported = (tmp_path / "day.jsonl").read_text(encoding="utf-8")
        assert tail.pk is not None
        assert hashlib.sha256(exported.encode()).hexdigest() == digest

        bypass("DELETE FROM audit_auditevent WHERE id = %s", [tail.pk])

        survivors = {e.hash for e in chain()}
        exported_hashes = {
            line.split('"hash": "')[1].split('"')[0] for line in exported.splitlines()
        }
        assert exported_hashes - survivors, "export still holds a hash the database lost"

    def test_inserting_a_forged_event(self) -> None:
        make_event("one")
        make_event("two")
        # skip the chain trigger so a forger can pick the position and hash
        bypass("ALTER TABLE audit_auditevent DISABLE TRIGGER audit_event_chain_insert")
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO audit_auditevent
                   (chain_seq, prev_hash, hash, hash_version, actor_type, action, entity_type,
                    entity_id, outcome, reason, request_id, trace_id, session_hash, user_agent,
                    actor_role)
                   VALUES (9, %s, %s, 1, 'user', 'forged', '', '', 'success', '', '', '', '', '',
                           '')""",
                ["b" * 64, "c" * 64],
            )

        problems = integrity.verify_chain()

        assert any("sequence break" in p.problem for p in problems)
        assert any("altered" in p.problem for p in problems)

    def test_swapping_the_order_of_two_events(self) -> None:
        make_event("one")
        make_event("two")
        make_event("three")

        # chain_seq is unique, so a forger has to move the rows out of the way first
        bypass("UPDATE audit_auditevent SET chain_seq = chain_seq + 100 WHERE chain_seq IN (2, 3)")
        with connection.cursor() as cursor:
            cursor.execute(
                """UPDATE audit_auditevent SET chain_seq = CASE chain_seq WHEN 102 THEN 3 ELSE 2 END
                   WHERE chain_seq IN (102, 103)"""
            )

        assert integrity.verify_chain() != []

    def test_editing_a_change_row(self) -> None:
        event = make_event(changes=2)

        bypass(
            "UPDATE audit_auditchange SET new_value = 'tampered' WHERE event_id = %s", [event.pk]
        )

        problems = integrity.verify_chain()
        assert problems
        assert all("change row" in p.problem for p in problems)

    def test_recomputing_one_events_hash_still_breaks_the_next_link(self) -> None:
        make_event("one")
        target = make_event("two")
        make_event("three")
        bypass(
            """UPDATE audit_auditevent SET reason = 'rewritten' WHERE id = %s""",
            [target.pk],
        )
        # the forger also fixes that row's own hash...
        with connection.cursor() as cursor:
            cursor.execute(
                """UPDATE audit_auditevent e SET hash = audit_event_digest(e) WHERE e.id = %s""",
                [target.pk],
            )

        problems = integrity.verify_chain()

        # ...so the row itself is consistent, but the *next* event no longer links to it.
        assert [(p.seq, p.problem) for p in problems] == [
            (3, "prev_hash does not match the previous event")
        ]


@pytest.mark.django_db
class TestOperations:
    def test_verify_command_reports_success(self) -> None:
        make_event("fine")
        out = io.StringIO()
        call_command("audit_verify", stdout=out)
        assert "intact" in out.getvalue()

    def test_verify_command_fails_with_the_problem_when_broken(self) -> None:
        target = make_event("original")
        bypass("UPDATE audit_auditevent SET reason = 'x' WHERE id = %s", [target.pk])
        err = io.StringIO()

        with pytest.raises(CommandError, match="broken"):
            call_command("audit_verify", stderr=err)

        assert "altered" in err.getvalue()

    def test_nightly_task_is_quiet_when_intact(self, caplog: pytest.LogCaptureFixture) -> None:
        make_event("fine")
        with caplog.at_level(logging.CRITICAL):
            assert verify_audit_chain() == {"problems": 0}
        assert not caplog.records
        assert not AuditEvent.objects.filter(action=Action.CHAIN_BROKEN).exists()

    def test_nightly_task_raises_the_alarm_and_records_it(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        target = make_event("original")
        bypass("UPDATE audit_auditevent SET reason = 'x' WHERE id = %s", [target.pk])

        with caplog.at_level(logging.CRITICAL):
            result = verify_audit_chain()

        assert result == {"problems": 1}
        assert any("Audit chain broken" in r.message for r in caplog.records)
        (alarm,) = AuditEvent.objects.filter(action=Action.CHAIN_BROKEN)
        assert alarm.outcome == "failed"
        assert alarm.actor_type == "system"

    def test_export_writes_one_line_per_event_for_the_day(self, tmp_path: Path) -> None:
        make_event("a")
        make_event("b")
        output = tmp_path / "audit" / "today.jsonl"

        digest = integrity.export_day(timezone.now().date(), output)

        lines = output.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert hashlib.sha256(output.read_bytes()).hexdigest() == digest
        assert '"seq": 1' in lines[0]

    def test_export_of_an_empty_day_is_an_empty_file(self, tmp_path: Path) -> None:
        output = tmp_path / "empty.jsonl"
        digest = integrity.export_day(date(2000, 1, 1), output)
        assert output.read_text(encoding="utf-8") == ""
        assert digest == hashlib.sha256(b"").hexdigest()

    def test_export_command_prints_the_digest(self, tmp_path: Path) -> None:
        make_event("a")
        out = io.StringIO()
        call_command(
            "audit_export",
            str(tmp_path / "x.jsonl"),
            date=timezone.now().date().isoformat(),
            stdout=out,
        )
        assert re.search(r"sha256=[0-9a-f]{64}", out.getvalue())


def test_concurrent_transactions_extend_one_linear_chain(
    django_db_setup: None, django_db_blocker: object
) -> None:
    """Two transactions must never chain to the same predecessor. The second waits for the first
    to commit (the advisory lock is held until then), and the result is still one linear chain.

    Uses its own connections and cleans up as a superuser, because rows committed from another
    connection are not rolled back by the test's transaction."""
    from django.conf import settings

    insert = """INSERT INTO audit_auditevent (actor_type, action, entity_type, entity_id, outcome,
                reason, request_id, trace_id, session_hash, user_agent, actor_role, chain_seq,
                prev_hash, hash)
                VALUES ('system', 'concurrency.test', '', '', 'success', %s, '', '', '', '', '',
                0, '', '')"""
    with django_db_blocker.unblock():  # type: ignore[attr-defined]
        db = settings.DATABASES["default"]
    dsn = (
        f"dbname={db['NAME']} user={db['USER']} password={db['PASSWORD']} "
        f"host={db['HOST']} port={db['PORT']}"
    )
    first_inserted = threading.Event()
    waits: dict[str, float] = {}

    def first() -> None:
        with psycopg.connect(dsn) as conn:
            conn.execute(insert, ["first"])
            first_inserted.set()
            time.sleep(0.7)  # hold the transaction open, lock held
            conn.commit()

    def second() -> None:
        first_inserted.wait(timeout=5)
        with psycopg.connect(dsn) as conn:
            started = time.monotonic()
            conn.execute(insert, ["second"])  # must wait for the first transaction
            waits["second"] = time.monotonic() - started
            conn.commit()

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    cleanup = psycopg.connect(dsn, autocommit=True)
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        rows = cleanup.execute(
            "SELECT chain_seq, reason, prev_hash, hash FROM audit_auditevent ORDER BY chain_seq"
        ).fetchall()
        problems = cleanup.execute("SELECT * FROM audit_verify_chain()").fetchall()
    finally:
        cleanup.execute("ALTER TABLE audit_auditevent DISABLE TRIGGER USER")
        cleanup.execute("DELETE FROM audit_auditevent WHERE action = 'concurrency.test'")
        cleanup.execute("ALTER TABLE audit_auditevent ENABLE TRIGGER USER")
        cleanup.close()

    assert [(r[0], r[1]) for r in rows] == [(1, "first"), (2, "second")]
    assert rows[1][2] == rows[0][3], "second event must chain to the first, not fork"
    assert problems == []
    assert waits["second"] >= 0.4, f"second insert did not wait for the first ({waits})"
