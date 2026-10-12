from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from wfm.accounts.models import Role, User
from wfm.audit.models import AuditEvent

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

    assert User.objects.count() == len(Role)
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
    assert User.objects.count() == len(Role)
