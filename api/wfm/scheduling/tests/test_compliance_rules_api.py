"""Compliance rules (CFG-06): who may change them, that the roster really reads them, and that a
rule change cannot rewrite the past or slip in unrecorded."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from django.utils import timezone

from wfm.accounts.models import Role
from wfm.audit.models import Action, AuditEvent
from wfm.scheduling.models import ComplianceRuleVersion

from .helpers import (
    FRI,
    MON,
    SAT,
    SUN,
    THU,
    TUE,
    WED,
    assign,
    login,
    person,
    queue,
    standard_shifts,
)

pytestmark = pytest.mark.django_db

RULES = "/api/v1/scheduling/compliance-rules"
LONG_AGO = date(2026, 1, 1)  # before the roster days the helpers use (May 2026)


def put(client: Any, day: date | None = None, **body: Any) -> Any:
    payload = {
        "effectiveFrom": str(day or timezone.localdate() + timedelta(days=1)),
        "minRestHours": 11,
        "maxConsecutiveDays": 6,
        "maxWeeklyHours": None,
        **body,
    }
    return client.put(RULES, payload, content_type="application/json")


def version(**fields: Any) -> ComplianceRuleVersion:
    return ComplianceRuleVersion.objects.create(
        **{
            "effective_from": LONG_AGO,
            "min_rest_hours": 11,
            "max_consecutive_days": 6,
            "max_weekly_hours": None,
            **fields,
        }
    )


@pytest.fixture
def shifts() -> dict[str, Any]:
    return standard_shifts()


class TestWhoMayDoWhat:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.LEAD])
    def test_those_who_build_rosters_can_read_the_rules(self, role: Role) -> None:
        assert login(role).get(RULES).status_code == 200

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_can_read_them(self, role: Role) -> None:
        assert login(role).get(RULES).status_code == 403

    @pytest.mark.parametrize(
        "role", [Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS]
    )
    def test_only_the_admin_changes_them_even_with_a_valid_request(self, role: Role) -> None:
        # Failure caught: a planner loosening the rest rule to fit a roster.
        assert put(login(role)).status_code == 403
        assert ComplianceRuleVersion.objects.count() == 0
        assert not AuditEvent.objects.filter(action=Action.COMPLIANCE_RULES_CHANGED).exists()

    def test_an_admin_sets_rules_and_everybody_who_reads_sees_them(self) -> None:
        tomorrow = timezone.localdate() + timedelta(days=1)
        response = put(login(Role.ADMIN), tomorrow, minRestHours=12, maxWeeklyHours=45)
        assert response.status_code == 200, response.content
        assert response.json()["warnings"] == []
        state = login(Role.LEAD).get(RULES, {"on": str(tomorrow)}).json()
        assert state["inForce"] == {
            "effectiveFrom": str(tomorrow),
            "minRestHours": 12,
            "maxConsecutiveDays": 6,
            "maxWeeklyHours": 45,
            "overtimeMultiplier": 1.5,
            "sundayMultiplier": 2.0,
            "holidayMultiplier": 2.0,
        }


class TestOvertimePay:
    def test_the_multipliers_are_saved_and_read_back(self) -> None:
        # Failure caught: pay rates accepted by the screen and silently dropped.
        day = timezone.localdate() + timedelta(days=2)
        response = put(
            login(Role.ADMIN),
            day,
            overtimeMultiplier=1.75,
            sundayMultiplier=2.5,
            holidayMultiplier=3,
        )
        assert response.status_code == 200, response.content
        assert response.json()["warnings"] == []
        row = ComplianceRuleVersion.objects.get()
        assert (str(row.overtime_multiplier), str(row.sunday_multiplier)) == ("1.75", "2.50")
        state = login(Role.PLANNER).get(RULES, {"on": str(day)}).json()["inForce"]
        assert (state["overtimeMultiplier"], state["holidayMultiplier"]) == (1.75, 3.0)

    def test_pay_below_the_statutory_rate_is_saved_with_a_warning(self) -> None:
        response = put(login(Role.ADMIN), overtimeMultiplier=1.25, holidayMultiplier=1.5)
        assert response.status_code == 200
        warnings = response.json()["warnings"]
        assert len(warnings) == 2
        assert any("Overtime pay of 1.25x" in w for w in warnings)

    @pytest.mark.parametrize(
        "field", ["overtimeMultiplier", "sundayMultiplier", "holidayMultiplier"]
    )
    @pytest.mark.parametrize("bad", [0.5, 5])
    def test_a_multiplier_outside_one_to_four_is_refused(self, field: str, bad: float) -> None:
        extra: dict[str, Any] = {field: bad}
        response = put(login(Role.ADMIN), **extra)
        assert response.status_code == 422
        assert response.json()["code"] == "rules.invalid"
        assert ComplianceRuleVersion.objects.count() == 0

    def test_the_audit_shows_the_rates(self) -> None:
        put(login(Role.ADMIN), overtimeMultiplier=1.75)
        change = AuditEvent.objects.get(action=Action.COMPLIANCE_RULES_CHANGED).changes.get()
        assert "overtime 1.75x" in (change.new_value or "")


class TestWhatTheRulesAre:
    def test_with_nothing_set_the_rules_are_the_ones_the_roster_always_used(self) -> None:
        state = login(Role.PLANNER).get(RULES).json()
        assert state["inForce"] == {
            "effectiveFrom": None,
            "minRestHours": 11,
            "maxConsecutiveDays": 6,
            "maxWeeklyHours": None,
            "overtimeMultiplier": 1.5,
            "sundayMultiplier": 2.0,
            "holidayMultiplier": 2.0,
        }
        assert (state["versions"], state["warnings"]) == ([], [])

    def test_a_future_version_is_listed_but_not_yet_in_force(self) -> None:
        # Failure caught: a rule scheduled for next month changing today's roster checks.
        later = timezone.localdate() + timedelta(days=30)
        put(login(Role.ADMIN), later, minRestHours=14)
        state = login(Role.PLANNER).get(RULES).json()
        assert state["inForce"]["minRestHours"] == 11
        assert [v["effectiveFrom"] for v in state["versions"]] == [str(later)]

    def test_asking_for_a_day_gives_the_rules_of_that_day(self) -> None:
        version(effective_from=date(2026, 1, 1), min_rest_hours=12)
        version(effective_from=date(2026, 6, 1), min_rest_hours=10)
        planner = login(Role.PLANNER)
        assert planner.get(RULES, {"on": "2026-05-31"}).json()["inForce"]["minRestHours"] == 12
        assert planner.get(RULES, {"on": "2026-06-01"}).json()["inForce"]["minRestHours"] == 10


class TestChangingThem:
    def test_loosening_below_the_floor_is_saved_with_a_warning(self) -> None:
        # Failure caught: refusing a legitimate customer policy, or saying nothing about the law.
        response = put(login(Role.ADMIN), minRestHours=9, maxConsecutiveDays=8)
        assert response.status_code == 200
        warnings = response.json()["warnings"]
        assert len(warnings) == 2
        assert ComplianceRuleVersion.objects.get().min_rest_hours == 9

    @pytest.mark.parametrize(
        "body",
        [
            {"minRestHours": 0},
            {"minRestHours": 30},
            {"maxConsecutiveDays": 0},
            {"maxConsecutiveDays": 20},
            {"maxWeeklyHours": 0},
            {"maxWeeklyHours": 200},
        ],
    )
    def test_nonsense_is_refused_and_stores_nothing(self, body: dict[str, Any]) -> None:
        response = put(login(Role.ADMIN), **body)
        assert response.status_code == 422
        assert response.json()["code"] == "rules.invalid"
        assert ComplianceRuleVersion.objects.count() == 0

    def test_a_rule_cannot_start_in_the_past(self) -> None:
        # Failure caught: rewriting what applied to rosters already worked.
        yesterday = timezone.localdate() - timedelta(days=1)
        response = put(login(Role.ADMIN), yesterday)
        assert response.status_code == 422
        assert response.json()["code"] == "rules.in_the_past"
        assert ComplianceRuleVersion.objects.count() == 0

    def test_today_is_allowed(self) -> None:
        assert put(login(Role.ADMIN), timezone.localdate()).status_code == 200

    def test_setting_a_day_twice_replaces_it_and_the_audit_shows_both_values(self) -> None:
        day = timezone.localdate() + timedelta(days=5)
        admin = login(Role.ADMIN)
        put(admin, day, minRestHours=12)
        put(admin, day, minRestHours=13)
        assert ComplianceRuleVersion.objects.get().min_rest_hours == 13
        second = AuditEvent.objects.filter(action=Action.COMPLIANCE_RULES_CHANGED).latest("id")
        change = second.changes.get()
        assert "rest 12 h" in (change.old_value or "")
        assert "rest 13 h" in (change.new_value or "")

    def test_every_change_is_audited_with_who(self) -> None:
        put(login(Role.ADMIN))
        event = AuditEvent.objects.get(action=Action.COMPLIANCE_RULES_CHANGED)
        assert event.actor_role == Role.ADMIN
        assert event.entity_type == "compliance_rules"


class TestTheRosterReadsThem:
    def test_a_longer_rest_makes_a_roster_the_old_rule_allowed_refused(
        self, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: the rule screen saving values the roster never reads.
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["L1"])  # ends 22:00
        assert assign(login(), queue(), e1, TUE, shifts["D1"]).status_code == 200  # 11 h: fine
        version(min_rest_hours=12)
        response = assign(login(), queue(), e1, WED, shifts["D1"])  # still fine: free day before
        assert response.status_code == 200
        assign(login(), queue(), e1, THU, shifts["L1"])  # ends 22:00
        refused = assign(login(), queue(), e1, FRI, shifts["D1"])  # 11 h: now below 12
        assert refused.status_code == 422
        assert refused.json()["code"] == "roster.rest_period"
        assert "12 hours" in refused.json()["detail"]

    def test_a_shorter_rest_lets_an_early_shift_follow_a_late_one(
        self, shifts: dict[str, Any]
    ) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["L1"])  # ends 22:00
        assert assign(login(), queue(), e1, TUE, shifts["E1"]).status_code == 422  # 9 h
        version(min_rest_hours=8)
        assert assign(login(), queue(), e1, TUE, shifts["E1"]).status_code == 200

    def test_fewer_days_in_a_row(self, shifts: dict[str, Any]) -> None:
        version(max_consecutive_days=3)
        e1 = person(hours=60)
        for day in (MON, TUE, WED):
            assert assign(login(), queue(), e1, day, shifts["D1"]).status_code == 200
        refused = assign(login(), queue(), e1, THU, shifts["D1"])
        assert refused.json()["code"] == "roster.too_many_days"
        assert "3 days" in refused.json()["detail"]

    def test_a_weekly_cap_below_the_contract_hours_is_the_limit(
        self, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: the cap ignored for a person whose contract allows more.
        version(max_weekly_hours=32)
        e1 = person(hours=40)
        for day in (MON, TUE, WED, THU):
            assert assign(login(), queue(), e1, day, shifts["D1"]).status_code == 200  # 4 x 8 = 32
        refused = assign(login(), queue(), e1, FRI, shifts["D1"])
        assert refused.json()["code"] == "roster.over_weekly_cap"

    def test_a_cap_above_the_contract_hours_changes_nothing(self, shifts: dict[str, Any]) -> None:
        # Failure caught: a cap raising a person's own contract limit.
        version(max_weekly_hours=60)
        e1 = person(hours=40)
        for day in (MON, TUE, WED, THU, FRI):
            assign(login(), queue(), e1, day, shifts["D1"])
        refused = assign(login(), queue(), e1, SAT, shifts["D1"])
        assert refused.json()["code"] == "roster.over_hours"

    def test_a_version_that_starts_after_the_day_does_not_apply_to_it(
        self, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: a new rule applied backwards to days already planned.
        version(effective_from=date(2026, 6, 1), max_consecutive_days=1, min_rest_hours=20)
        e1 = person(hours=60)
        assert assign(login(), queue(), e1, MON, shifts["D1"]).status_code == 200
        assert assign(login(), queue(), e1, TUE, shifts["D1"]).status_code == 200
        assert assign(login(), queue(), e1, SUN, shifts["D1"]).status_code == 200

    def test_refusals_under_the_new_rules_are_audited_like_any_other(
        self, shifts: dict[str, Any]
    ) -> None:
        version(max_weekly_hours=8)
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["D1"])
        assign(login(), queue(), e1, TUE, shifts["D1"])
        event = AuditEvent.objects.get(action=Action.ROSTER_REFUSED)
        assert event.reason == "roster.over_weekly_cap"
