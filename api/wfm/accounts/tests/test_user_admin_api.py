"""Administering users: what an admin may do, what stops them locking everyone out, and that a
password never reaches the audit trail."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from wfm.accounts.models import Role, RoleSource, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.scheduling.models import Employee

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def real_password_rules(settings: Any) -> None:
    """The test settings switch the password rules off for speed; these tests are about them."""
    from config.settings import base

    settings.AUTH_PASSWORD_VALIDATORS = base.AUTH_PASSWORD_VALIDATORS


U = "/api/v1/users"
LOGIN = "/api/v1/auth/login"
GOOD = "correct-horse-battery"
NEW = "another-long-passphrase"


def client_for(username: str, role: Role) -> Client:
    user, _ = User.objects.get_or_create(username=username, defaults={"role": role})
    client = Client()
    client.force_login(user)
    return client


def admin(username: str = "root") -> Client:
    return client_for(username, Role.ADMIN)


def make(username: str, role: Role = Role.AGENT, **extra: Any) -> User:
    return User.objects.create_user(username=username, password=GOOD, role=role, **extra)


def create(
    client: Client, username: str = "newbie", role: str = "agent", password: str = GOOD
) -> Any:
    return client.post(
        U,
        {
            "username": username,
            "firstName": "New",
            "lastName": "Person",
            "role": role,
            "password": password,
        },
        content_type="application/json",
    )


def sign_in(username: str, password: str) -> Any:
    client = Client()
    return client.post(
        LOGIN, {"username": username, "password": password}, content_type="application/json"
    ), client


class TestWhoMayAdminister:
    @pytest.mark.parametrize("role", [r for r in Role if r != Role.ADMIN])
    def test_only_the_admin_reaches_any_of_it(self, role: Role) -> None:
        target = make("target")
        client = client_for("someone", role)
        assert client.get(U).status_code == 403
        assert create(client).status_code == 403
        for method, path, body in (
            ("put", f"{U}/{target.pk}/role", {"role": "admin"}),
            ("put", f"{U}/{target.pk}/active", {"active": False}),
            ("post", f"{U}/{target.pk}/unlock", {}),
            ("post", f"{U}/{target.pk}/password", {"password": NEW}),
        ):
            response = getattr(client, method)(path, body, content_type="application/json")
            assert response.status_code == 403, path
        target.refresh_from_db()
        assert (target.role, target.is_active) == (Role.AGENT, True)

    def test_the_list_says_who_is_what_and_never_shows_a_password(self) -> None:
        make("amy", Role.LEAD)
        rows = {u["username"]: u for u in admin().get(U).json()}
        assert rows["amy"]["role"] == "lead"
        assert rows["amy"]["hasPassword"] is True
        assert "password" not in " ".join(rows["amy"].keys()).replace("hasPassword", "").replace(
            "mustChangePassword", ""
        )


class TestCreating:
    def test_a_local_user_is_created_with_a_temporary_password_they_must_change(self) -> None:
        response = create(admin())
        assert response.status_code == 201, response.content
        assert response.json()["mustChangePassword"] is True
        signed, client = sign_in("newbie", GOOD)
        assert signed.status_code == 200
        assert client.get("/api/v1/auth/me").json()["mustChangePassword"] is True

    @pytest.mark.parametrize(
        ("kwargs", "code"),
        [
            ({"username": "ab"}, "user.username_invalid"),
            ({"username": "has space"}, "user.username_invalid"),
            ({"role": "emperor"}, "user.role_invalid"),
            ({"password": "short"}, "password.too_weak"),
            ({"password": "123456789012"}, "password.too_weak"),
            ({"password": "password1234"}, "password.too_weak"),
        ],
    )
    def test_nonsense_is_refused_with_a_reason(self, kwargs: dict[str, str], code: str) -> None:
        response = create(admin(), **kwargs)
        assert (response.status_code, response.json()["code"]) == (422, code)
        assert User.objects.filter(username="newbie").count() == 0

    def test_a_username_can_only_be_used_once(self) -> None:
        make("taken")
        response = create(admin(), username="taken")
        assert (response.status_code, response.json()["code"]) == (409, "user.username_taken")

    def test_the_password_is_never_in_the_audit_trail(self) -> None:
        create(admin(), password="a-secret-phrase-1234")
        event = AuditEvent.objects.get(action=Action.USER_CREATED)
        everything = " ".join(
            [event.reason or "", event.entity_id]
            + [
                f"{c.field}{c.old_value}{c.new_value}"
                for c in AuditChange.objects.filter(event=event)
            ]
        )
        # Failure caught: a secret written to a log that is kept for years.
        assert "a-secret-phrase-1234" not in everything


class TestRole:
    def test_an_admin_changes_someones_role_and_it_is_audited_with_before_and_after(self) -> None:
        target = make("target")
        assert (
            admin()
            .put(f"{U}/{target.pk}/role", {"role": "lead"}, content_type="application/json")
            .json()["role"]
            == "lead"
        )
        event = AuditEvent.objects.get(action=Action.USER_ROLE_SET)
        change = AuditChange.objects.get(event=event)
        assert (change.old_value, change.new_value) == ("agent", "lead")

    def test_a_role_from_the_identity_provider_cannot_be_edited_here(self) -> None:
        target = make("sso", role_source=RoleSource.DIRECTORY)
        response = admin().put(
            f"{U}/{target.pk}/role", {"role": "admin"}, content_type="application/json"
        )
        assert (response.status_code, response.json()["code"]) == (409, "user.role_from_directory")
        target.refresh_from_db()
        assert target.role == Role.AGENT

    def test_you_cannot_change_your_own_role(self) -> None:
        me = User.objects.create(username="root", role=Role.ADMIN)
        client = Client()
        client.force_login(me)
        response = client.put(
            f"{U}/{me.pk}/role", {"role": "agent"}, content_type="application/json"
        )
        assert (response.status_code, response.json()["code"]) == (409, "user.own_role")

    def test_an_unknown_role_or_user_is_refused(self) -> None:
        target = make("target")
        bad = admin().put(f"{U}/{target.pk}/role", {"role": "x"}, content_type="application/json")
        assert bad.status_code == 422
        missing = admin().put(f"{U}/999999/role", {"role": "lead"}, content_type="application/json")
        assert missing.status_code == 404


class TestSwitchingOff:
    def test_a_switched_off_account_cannot_sign_in_and_can_be_switched_on_again(self) -> None:
        make("target")
        root = admin()
        target_id = User.objects.get(username="target").pk
        assert (
            root.put(
                f"{U}/{target_id}/active", {"active": False}, content_type="application/json"
            ).json()["active"]
            is False
        )
        assert sign_in("target", GOOD)[0].status_code == 401
        root.put(f"{U}/{target_id}/active", {"active": True}, content_type="application/json")
        assert sign_in("target", GOOD)[0].status_code == 200

    def test_you_cannot_switch_off_your_own_account(self) -> None:
        me = User.objects.create(username="root", role=Role.ADMIN)
        client = Client()
        client.force_login(me)
        own = client.put(f"{U}/{me.pk}/active", {"active": False}, content_type="application/json")
        assert (own.status_code, own.json()["code"]) == (409, "user.own_account")
        me.refresh_from_db()
        assert me.is_active


class TestUnlockAndReset:
    def test_unlocking_lets_a_locked_account_in(self) -> None:
        target = make("target")
        target.locked_until = timezone.now() + timedelta(minutes=30)
        target.failed_login_count = 5
        target.save()
        assert sign_in("target", GOOD)[0].status_code == 401
        assert admin().post(f"{U}/{target.pk}/unlock").json()["locked"] is False
        assert sign_in("target", GOOD)[0].status_code == 200

    def test_a_reset_sets_a_temporary_password_and_clears_a_lock(self) -> None:
        target = make("target")
        target.locked_until = timezone.now() + timedelta(minutes=30)
        target.save()
        response = admin().post(
            f"{U}/{target.pk}/password", {"password": NEW}, content_type="application/json"
        )
        assert response.json()["mustChangePassword"] is True
        assert sign_in("target", GOOD)[0].status_code == 401  # the old one no longer works
        assert sign_in("target", NEW)[0].status_code == 200

    def test_a_weak_reset_is_refused_and_a_provider_account_has_nothing_to_reset(self) -> None:
        target = make("target")
        weak = admin().post(
            f"{U}/{target.pk}/password", {"password": "short"}, content_type="application/json"
        )
        assert (weak.status_code, weak.json()["code"]) == (422, "password.too_weak")
        sso = User.objects.create(username="sso", role=Role.AGENT)
        sso.set_unusable_password()
        sso.save()
        refused = admin().post(
            f"{U}/{sso.pk}/password", {"password": NEW}, content_type="application/json"
        )
        assert (refused.status_code, refused.json()["code"]) == (409, "user.no_local_password")


class TestChangingYourOwnPassword:
    CHANGE = "/api/v1/auth/change-password"

    def body(self, current: str = GOOD, new: str = NEW) -> dict[str, str]:
        return {"current": current, "new": new}

    def test_it_changes_it_clears_the_flag_and_keeps_this_session_but_ends_others(self) -> None:
        make("target", must_change_password=True)
        _, mine = sign_in("target", GOOD)
        _, other = sign_in("target", GOOD)
        response = mine.post(self.CHANGE, self.body(), content_type="application/json")
        assert response.status_code == 200
        assert mine.get("/api/v1/auth/me").json()["mustChangePassword"] is False
        # Failure caught: a stolen session surviving a password change.
        assert other.get("/api/v1/auth/me").status_code == 401
        assert sign_in("target", NEW)[0].status_code == 200
        assert sign_in("target", GOOD)[0].status_code == 401

    @pytest.mark.parametrize(
        ("current", "new", "code"),
        [
            ("not-it", NEW, "password.wrong"),
            (GOOD, GOOD, "password.unchanged"),
            (GOOD, "short", "password.too_weak"),
        ],
    )
    def test_a_wrong_unchanged_or_weak_change_is_refused(
        self, current: str, new: str, code: str
    ) -> None:
        make("target")
        _, mine = sign_in("target", GOOD)
        response = mine.post(self.CHANGE, self.body(current, new), content_type="application/json")
        assert (response.status_code, response.json()["code"]) == (422, code)
        assert sign_in("target", GOOD)[0].status_code == 200

    def test_anyone_signed_in_can_but_nobody_else(self) -> None:
        assert (
            Client().post(self.CHANGE, self.body(), content_type="application/json").status_code
            == 401
        )

    def test_the_change_is_audited_without_either_password(self) -> None:
        make("target")
        _, mine = sign_in("target", GOOD)
        mine.post(self.CHANGE, self.body(), content_type="application/json")
        event = AuditEvent.objects.get(action=Action.USER_PASSWORD_CHANGED)
        text = " ".join(
            [event.reason or ""]
            + [f"{c.old_value}{c.new_value}" for c in AuditChange.objects.filter(event=event)]
        )
        assert GOOD not in text
        assert NEW not in text


class TestLinkingALoginToAnEmployee:
    def employee(self, emp_no: str = "E001") -> Employee:
        return Employee.objects.create(emp_no=emp_no, name=f"Person {emp_no}")

    def link(self, client: Client, employee: Employee, user_id: int | None) -> Any:
        return client.put(
            f"/api/v1/scheduling/employees/{employee.pk}/login",
            {"userId": user_id},
            content_type="application/json",
        )

    def test_the_admin_links_and_unlinks_and_the_users_list_shows_it(self) -> None:
        person = make("amy")
        emp = self.employee()
        assert self.link(admin(), emp, person.pk).json()["hasLogin"] is True
        listed = {u["username"]: u for u in admin().get(U).json()}
        assert listed["amy"]["employee"] == "E001"
        assert self.link(admin(), emp, None).json()["hasLogin"] is False
        assert {u["username"]: u for u in admin().get(U).json()}["amy"]["employee"] is None

    def test_one_login_belongs_to_one_employee(self) -> None:
        person = make("amy")
        self.link(admin(), self.employee("E001"), person.pk)
        response = self.link(admin(), self.employee("E002"), person.pk)
        assert (response.status_code, response.json()["code"]) == (409, "employee.login_taken")

    def test_only_the_admin_may_and_unknown_things_are_not_found(self) -> None:
        person = make("amy")
        emp = self.employee()
        for role in (Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS):
            assert self.link(client_for(f"u-{role.value}", role), emp, person.pk).status_code == 403
        assert self.link(admin(), emp, 999999).status_code == 404
        missing = Employee(pk=999999)
        assert self.link(admin(), missing, person.pk).status_code == 404

    def test_the_audit_trail_records_ids_not_usernames(self) -> None:
        person = make("amy.private@example.test")
        emp = self.employee()
        self.link(admin(), emp, person.pk)
        event = AuditEvent.objects.get(action=Action.EMPLOYEE_LOGIN_LINKED)
        change = AuditChange.objects.get(event=event)
        assert change.new_value == str(person.pk)
        assert "amy.private" not in f"{change.old_value}{change.new_value}{event.reason}"
