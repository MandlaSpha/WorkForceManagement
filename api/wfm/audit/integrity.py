"""Verifying the audit hash chain (requirement AUD-10) and exporting it for external storage."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from django.db import connection


@dataclass(frozen=True, slots=True)
class ChainProblem:
    seq: int | None
    event_id: int | None
    problem: str


def verify_chain() -> list[ChainProblem]:
    """Walk the whole chain. An empty list means every event and change row is intact and no event
    has been removed, inserted or reordered. The walk runs inside the database so it reads the
    rows exactly as stored."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT seq, event_id, problem FROM audit_verify_chain()")
        return [ChainProblem(*row) for row in cursor.fetchall()]


def export_day(day: date, output: Path) -> str:
    """Write one UTC day's chain heads as JSON lines and return the file's SHA-256.

    Copy the file (and the printed digest) to immutable storage each day. An attacker who rewrites
    the database *and* recomputes every hash still cannot change what was already exported."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT chain_seq, id, to_char(occurred_at AT TIME ZONE 'UTC',
                   'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'), action, prev_hash, hash
              FROM audit_auditevent
             WHERE (occurred_at AT TIME ZONE 'UTC')::date = %s
             ORDER BY chain_seq
            """,
            [day],
        )
        rows = cursor.fetchall()
    lines = [
        json.dumps(
            dict(zip(("seq", "id", "at", "action", "prev_hash", "hash"), row, strict=True)),
            sort_keys=True,
        )
        for row in rows
    ]
    payload = ("\n".join(lines) + "\n") if lines else ""
    output.parent.mkdir(parents=True, exist_ok=True)
    # Bytes, not write_text(): text mode rewrites line feeds as CR+LF on Windows, and the digest
    # printed here would then not match the file that gets copied to immutable storage.
    data = payload.encode("utf-8")
    output.write_bytes(data)
    return hashlib.sha256(data).hexdigest()
