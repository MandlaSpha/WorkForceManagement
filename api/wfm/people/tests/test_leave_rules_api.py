"""Blackout periods and the limit on people away at once (LV-04), on PostgreSQL.

Today is frozen at Wednesday 20 May 2026. Unpaid leave is a restricted kind (the rules apply);
sick leave is not (it cannot wait). A, B and C are agents managed by the lead `u-lead`.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.people.models import LeaveBlackout, LeaveRequest, LeaveStatus, LeaveType
from wfm.scheduling.tests.helpers import login as scheduling_login
from wfm.scheduling.tests.helpers import person

from .team import lead_of

pytestmark = pytest.mark.django_db

LEAVE = "/api/v1/people/leave"
TODAY = date(2026, 5, 20)
TUE_26, WED_27 = date(2026, 5, 26), date(2026, 5, 27)
FRI_29, MON_1, TUE_2, FRI_5, MON_8 = (
    date(2026, 5, 29),
    date(2026, 6, 1),
    date(2026, 6, 2),
    date(2026, 6, 5),
    date(2026, 6, 8),
)


@pytest.fixture(autouse=True)
def today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wfm.people.services.timezone.localdate", lambda: TODAY)


def as_user(username: str, role: Role = Role.AGENT) -> Client:
    user, _ = User.objects.get_or_create(username=username, defaults={"role": role})
    client = Client()
    client.force_login(user)
    return client


def login(role: Role = Role.PLANNER) -> Client:
    return scheduling_login(role)


@pytest.fixture
def team() -> None:
    people = []
    for name, emp in (("u-agent", "E001"), ("u-colleague", "E002"), ("u-third", "E003")):
        as_user(name)
        people.append(person(emp, user=User.objects.get(username=name)))
    lead_of(*people)


def ask(login_name: str, start: date, end: date | None = None, code: str = "unpaid") -> Any:
    return as_user(login_name).post(
        f"{LEAVE}/requests",
        {
            "leaveTypeId": LeaveType.objects.get(code=code).pk,
            "startDate": str(start),
            "endDate": str(end or start),
        },
        content_type="application/json",
    )


def decide(request_id: int, what: str = "approve", who: str = "u-lead") -> Any:
    return as_user(who, Role.LEAD).post(f"{LEAVE}/requests/{request_id}/{what}")


def blackout(name: str, first: date, last: date) -> Any:
    return login(Role.ADMIN).post(
        f"{LEAVE}/blackouts",
        {"name": name, "dateFrom": str(first), "dateTo": str(last)},
        content_type="application/json",
    )


def set_limit(value: int | None, role: Role = Role.ADMIN) -> Any:
    return login(role).put(
        f"{LEAVE}/limit", {"maxConcurrent": value}, content_type="application/json"
    )


class TestBlackoutPeriods:
    def test_leave_inside_a_blackout_is_refused_naming_it(self, team: None) -> None:
        assert blackout("Year-end close", MON_1, FRI_5).status_code == 201
        response = ask("u-agent", TUE_2)
        assert (response.status_code, response.json()["code"]) == (409, "leave.blackout")
        assert "Year-end close" in response.json()["detail"]
        assert LeaveRequest.objects.count() == 0

    def test_a_request_that_only_touches_the_edge_is_still_refused_but_outside_is_fine(
        self, team: None
    ) -> None:
        blackout("Year-end close", MON_1, FRI_5)
        # Friday 29 May to Monday 1 June reaches the first blackout day.
        assert ask("u-agent", FRI_29, MON_1).json()["code"] == "leave.blackout"
        assert ask("u-agent", FRI_29).status_code == 201  # the day before
        assert ask("u-colleague", MON_8).status_code == 201  # the day after the period

    def test_sick_leave_cannot_wait_so_it_ignores_a_blackout(self, team: None) -> None:
        blackout("Year-end close", MON_1, FRI_5)
        assert ask("u-agent", TUE_2, code="sick").status_code == 201

    def test_removing_the_blackout_lets_the_request_through(self, team: None) -> None:
        period = blackout("Year-end close", MON_1, FRI_5).json()["id"]
        assert ask("u-agent", TUE_2).status_code == 409
        assert login(Role.ADMIN).delete(f"{LEAVE}/blackouts/{period}").status_code == 200
        assert ask("u-agent", TUE_2).status_code == 201

    @pytest.mark.parametrize(
        ("name", "first", "last", "code"),
        [
            ("", MON_1, FRI_5, "blackout.name_invalid"),
            ("x" * 61, MON_1, FRI_5, "blackout.name_invalid"),
            ("Backwards", FRI_5, MON_1, "blackout.dates_invalid"),
            ("Too long", date(2026, 6, 1), date(2027, 8, 1), "blackout.too_long"),
        ],
    )
    def test_nonsense_periods_are_refused_with_a_reason(
        self, name: str, first: date, last: date, code: str
    ) -> None:
        response = blackout(name, first, last)
        assert (response.status_code, response.json()["code"]) == (422, code)
        assert LeaveBlackout.objects.count() == 0

    def test_only_the_customers_admin_manages_the_rules_everyone_who_takes_leave_reads_them(
        self, team: None
    ) -> None:
        period = blackout("Year-end close", MON_1, FRI_5).json()["id"]
        for role in (Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS):
            client = login(role)
            body = {"name": "x", "dateFrom": str(MON_1), "dateTo": str(FRI_5)}
            assert (
                client.post(f"{LEAVE}/blackouts", body, content_type="application/json").status_code
                == 403
            )
            assert client.delete(f"{LEAVE}/blackouts/{period}").status_code == 403
            assert set_limit(3, role).status_code == 403
        assert LeaveBlackout.objects.count() == 1
        for role in (Role.AGENT, Role.LEAD, Role.PLANNER, Role.ADMIN):
            assert login(role).get(f"{LEAVE}/blackouts").status_code == 200
            assert login(role).get(f"{LEAVE}/limit").status_code == 200
        for role in (Role.EXECUTIVE, Role.CUSTOMER_OPS):
            assert login(role).get(f"{LEAVE}/blackouts").status_code == 403
            assert login(role).get(f"{LEAVE}/limit").status_code == 403

    def test_adding_and_removing_are_audited(self, team: None) -> None:
        period = blackout("Year-end close", MON_1, FRI_5).json()["id"]
        login(Role.ADMIN).delete(f"{LEAVE}/blackouts/{period}")
        actions = list(
            AuditEvent.objects.filter(action__startswith="leave.blackout")
            .order_by("chain_seq")
            .values_list("action", flat=True)
        )
        assert actions == [Action.LEAVE_BLACKOUT_ADDED, Action.LEAVE_BLACKOUT_REMOVED]

    def test_removing_one_that_does_not_exist_is_not_found(self) -> None:
        assert login(Role.ADMIN).delete(f"{LEAVE}/blackouts/999999").status_code == 404


class TestPeopleAwayAtOnce:
    def test_a_request_that_would_pass_the_limit_is_refused_with_the_day(self, team: None) -> None:
        set_limit(2)
        for name in ("u-agent", "u-colleague"):
            decide(ask(name, TUE_26).json()["id"])
        response = ask("u-third", TUE_26)
        assert (response.status_code, response.json()["code"]) == (409, "leave.too_many_away")
        assert "2 people are already away on 2026-05-26" in response.json()["detail"]
        assert "at most 2" in response.json()["detail"]
        assert ask("u-third", WED_27).status_code == 201  # nobody is away the next day

    def test_asked_but_not_yet_approved_leave_does_not_use_up_the_limit(self, team: None) -> None:
        set_limit(1)
        assert ask("u-agent", TUE_26).status_code == 201  # waiting
        assert ask("u-colleague", TUE_26).status_code == 201  # still fine: nobody is away yet

    def test_approving_checks_again_so_the_limit_holds_for_requests_made_before_it(
        self, team: None
    ) -> None:
        first = ask("u-agent", TUE_26).json()["id"]
        second = ask("u-colleague", TUE_26).json()["id"]
        set_limit(1)  # introduced while both were waiting
        assert decide(first).status_code == 200
        response = decide(second)
        assert (response.status_code, response.json()["code"]) == (409, "leave.too_many_away")
        assert LeaveRequest.objects.get(pk=second).status == LeaveStatus.PENDING
        # The approver can still turn it down.
        assert decide(second, "reject").status_code == 200

    def test_sick_leave_neither_counts_nor_is_blocked(self, team: None) -> None:
        set_limit(1)
        decide(ask("u-agent", TUE_26, code="sick").json()["id"])  # away, but it cannot wait
        unpaid = ask("u-colleague", TUE_26)  # the sick leave did not use the limit
        assert unpaid.status_code == 201
        assert decide(unpaid.json()["id"]).status_code == 200
        assert ask("u-third", TUE_26, code="sick").status_code == 201  # and is never refused

    def test_the_limit_counts_working_days_only(self, team: None) -> None:
        set_limit(1)
        # Friday 29 May to Sunday 31 May is one working day; a weekend request cannot be made at
        # all, and Monday 1 June is a different day.
        decide(ask("u-agent", FRI_29, date(2026, 5, 31)).json()["id"])
        assert ask("u-colleague", MON_1).status_code == 201

    def test_cancelled_leave_frees_the_day(self, team: None) -> None:
        set_limit(1)
        approved = ask("u-agent", TUE_26).json()["id"]
        decide(approved)
        assert ask("u-colleague", TUE_26).status_code == 409
        assert as_user("u-agent").post(f"{LEAVE}/requests/{approved}/cancel").status_code == 200
        assert ask("u-colleague", TUE_26).status_code == 201

    def test_no_limit_means_anyone_can_be_away(self, team: None) -> None:
        set_limit(None)
        for name in ("u-agent", "u-colleague", "u-third"):
            decide(ask(name, TUE_26).json()["id"])

    @pytest.mark.parametrize("value", [0, -1, 1001])
    def test_a_limit_outside_1_to_1000_is_refused(self, value: int) -> None:
        response = set_limit(value)
        assert (response.status_code, response.json()["code"]) == (422, "limit.invalid")

    def test_changing_the_limit_is_audited_with_before_and_after(self) -> None:
        set_limit(5)
        set_limit(3)
        event = AuditEvent.objects.filter(action=Action.LEAVE_LIMIT_CHANGED).latest("chain_seq")
        changes = {
            c.field: (c.old_value, c.new_value) for c in AuditChange.objects.filter(event=event)
        }
        assert changes["max_concurrent"] == ("5", "3")
        assert login(Role.AGENT).get(f"{LEAVE}/limit").json() == {"maxConcurrent": 3}
