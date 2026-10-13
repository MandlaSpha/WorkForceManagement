"""Acceptance test against the REAL May, June and July reports (requirement DAT-02, deck slide 2).

The reports hold real caller numbers and staff names, so they are never in the repository and this
test is skipped unless you point it at them. It reads them from disk, imports them into the
throwaway test database and asserts only aggregate figures; nothing is printed.

    set WFM_REAL_CDR_DIR=C:\\git\\WorkForceManagement\\Files
    uv run pytest wfm/telephony/tests/test_real_reports.py

It looks for one file with "May", one with "June" and one with "July" in its name.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User

from .workbooks import upload

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        not os.environ.get("WFM_REAL_CDR_DIR"), reason="set WFM_REAL_CDR_DIR to run on real data"
    ),
]

# What the deck (slide 2) says, as (offered, answered, abandoned, abandon %, SL %, ASA s, AHT s).
DECK = {
    "May": (5649, 5181, 468, 8.28, 81.1, 18.5, 215),  # AHT 3:35
    "July": (4837, 4632, 205, 4.24, 89.8, 11.7, 202),  # AHT 3:22
}


def report(month: str) -> Path:
    folder = Path(os.environ["WFM_REAL_CDR_DIR"])
    found = sorted(p for p in folder.glob("*.xlsx") if month in p.name and "Call Detail" in p.name)
    assert len(found) == 1, f"expected exactly one {month} Call Detail Report in the folder"
    return found[0]


def planner() -> Client:
    user = User.objects.create_user(username="real-planner", password="x", role=Role.PLANNER)
    client = Client()
    client.force_login(user)
    return client


def import_month(client: Client, month: str) -> Any:
    path = report(month)
    return client.post(
        "/api/v1/telephony/imports", {"file": upload(path.read_bytes(), "real-report.xlsx")}
    )


def figures(client: Client, first: str, last: str) -> dict[str, Any]:
    response = client.get("/api/v1/telephony/kpis", {"date_from": first, "date_to": last})
    assert response.status_code == 200
    return response.json()["total"]  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("month", "first", "last"),
    [("May", "2026-05-01", "2026-05-31"), ("July", "2026-07-01", "2026-07-31")],
)
def test_the_imported_month_matches_the_deck(month: str, first: str, last: str) -> None:
    client = planner()
    imported = import_month(client, month)
    assert imported.status_code == 201
    assert imported.json()["reconciles"] is True
    assert imported.json()["rowsRejected"] == 0

    total = figures(client, first, last)
    offered, answered, abandoned, abandon_pct, sl_pct, asa_s, aht_s = DECK[month]
    assert (total["offered"], total["answered"], total["abandoned"]) == (
        offered,
        answered,
        abandoned,
    )
    assert round(total["abandonPct"]["value"], 2) == abandon_pct
    assert round(total["serviceLevelPct"]["value"], 1) == sl_pct
    assert round(total["asaS"]["value"], 1) == asa_s
    assert round(total["ahtS"]["value"]) == aht_s


def test_the_june_file_is_refused_because_it_is_may_again() -> None:
    client = planner()
    assert import_month(client, "May").status_code == 201
    june = import_month(client, "June")
    assert june.status_code == 409
    assert june.json()["code"] in {"import.duplicate_period", "import.duplicate_file"}
