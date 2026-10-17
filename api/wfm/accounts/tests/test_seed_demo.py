from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from wfm.accounts.management.commands.seed_demo import DEMO_ACCOUNTS, DEMO_TEAM_ACCOUNTS
from wfm.accounts.models import Role, User
from wfm.audit.models import AuditEvent
from wfm.scheduling.models import Employee

pytestmark = pytest.mark.django_db

STRONG = "demo-password-123"


@override_settings(DEBUG=True)
def test_seeds_one_account_per_role_and_audits_it() -> None:
    call_command("seed_demo", password=STRONG)

    roles = set(User.objects.values_list("role", flat=True))
    assert roles == {role.value for role in Role}
    assert User.objects.get(username="planner").check_password(STRONG)
    assert AuditEvent.objects.filter(action="system.seed_demo", actor_type="system").count() == 1


@override_settings(DEBUG=True)
def test_seeding_twice_does_not_duplicate_or_reset_passwords() -> None:
    call_command("seed_demo", password=STRONG)
    call_command("seed_demo", password="another-password-456")

    assert User.objects.count() == len(DEMO_ACCOUNTS) + len(DEMO_TEAM_ACCOUNTS)
    assert User.objects.get(username="planner").check_password(STRONG)


@override_settings(DEBUG=False)
def test_refuses_outside_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WFM_ALLOW_DEMO_SEED", raising=False)
    with pytest.raises(CommandError, match="disabled"):
        call_command("seed_demo", password=STRONG)
    assert User.objects.count() == 0


@override_settings(DEBUG=True)
def test_refuses_a_weak_password() -> None:
    with pytest.raises(CommandError, match="12 characters"):
        call_command("seed_demo", password="short")


@override_settings(DEBUG=True)
def test_reset_passwords_updates_existing_demo_users_and_clears_lockout() -> None:
    call_command("seed_demo", password=STRONG)
    planner = User.objects.get(username="planner")
    planner.failed_login_count = 3
    planner.locked_until = timezone.now() + timedelta(minutes=10)
    planner.save()

    call_command("seed_demo", password="rotated-password-789", reset_passwords=True)

    planner.refresh_from_db()
    assert planner.check_password("rotated-password-789")
    assert planner.failed_login_count == 0
    assert planner.locked_until is None
    assert User.objects.count() == len(DEMO_ACCOUNTS) + len(DEMO_TEAM_ACCOUNTS)


@override_settings(DEBUG=True)
def test_the_demo_floor_logins_get_one_synthetic_employee_record_each() -> None:
    call_command("seed_demo", password=STRONG)
    call_command("seed_demo", password=STRONG)

    employees = Employee.objects.filter(user__isnull=False)
    names = sorted((e.emp_no, e.user.username) for e in employees)
    assert ("DEMO-AGENT", "agent") in names
    assert ("DEMO-LEAD", "lead") in names
    # Only the people who work the floor (two leads and ten agents): planners, admins and the rest
    # are not on the roster list just by being demo users.
    assert Employee.objects.count() == 12


@override_settings(DEBUG=True)
def test_two_teams_of_five_agents_each_under_their_own_lead() -> None:
    # Failure caught: a demo where one lead holds everybody, so a swap needing a different lead's
    # approval, or a lead seeing only their own team, cannot be tried.
    call_command("seed_demo", password=STRONG)
    teams = {
        lead: sorted(
            Employee.objects.filter(manager__emp_no=lead, user__role=Role.AGENT).values_list(
                "emp_no", flat=True
            )
        )
        for lead in ("DEMO-LEAD", "DEMO-LEAD2")
    }
    assert [len(members) for members in teams.values()] == [5, 5]
    assert set(teams["DEMO-LEAD"]).isdisjoint(teams["DEMO-LEAD2"])


@override_settings(DEBUG=True)
def test_the_demo_lead_manages_the_demo_agent_so_the_lead_can_decide_their_leave() -> None:
    call_command("seed_demo", password=STRONG)
    agent = Employee.objects.get(emp_no="DEMO-AGENT")
    assert agent.manager is not None
    assert agent.manager.emp_no == "DEMO-LEAD"
