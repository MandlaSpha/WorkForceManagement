"""Integration tests for sign-in, lockout, CSRF and audit (real PostgreSQL via Testcontainers)."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from django.test import Client
from django.utils import timezone

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditEvent, Outcome

if TYPE_CHECKING:  # stub-only name, not importable at runtime
    from django.test.client import _MonkeyPatchedWSGIResponse as TestResponse

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery"
LOGIN = "/api/v1/auth/login"


def make_user(username: str = "pat", role: Role = Role.PLANNER) -> User:
    return User.objects.create_user(username=username, password=PASSWORD, role=role)


def csrf_client() -> tuple[Client, str]:
    """A client that enforces CSRF like a browser does, plus a valid token."""
    client = Client(enforce_csrf_checks=True)
    token = client.get("/api/v1/auth/csrf").json()["csrfToken"]
    return client, token


def fresh_token(client: Client) -> str:
    """Sign-in rotates the CSRF token; a browser reads the new one from its cookie."""
    return client.cookies["csrftoken"].value


def post_login(client: Client, token: str, username: str, password: str) -> TestResponse:
    return client.post(
        LOGIN,
        data={"username": username, "password": password},
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )


def events(action: str) -> list[AuditEvent]:
    return list(AuditEvent.objects.filter(action=action).order_by("id"))


def test_login_succeeds_and_is_audited_with_who_and_role() -> None:
    user = make_user()
    client, token = csrf_client()

    response = post_login(client, token, "pat", PASSWORD)

    assert response.status_code == 200
    assert response.json() == {"username": "pat", "displayName": "pat", "role": "planner"}
    (event,) = events(Action.LOGIN_SUCCESS)
    assert event.actor_user_id == user.pk
    assert event.actor_role == "planner"
    assert event.outcome == Outcome.SUCCESS
    assert event.request_id  # links the audit entry to the technical trace
    assert event.session_hash
    assert event.ip == "127.0.0.1"


def test_audit_timestamp_comes_from_the_database_clock() -> None:
    make_user()
    client, token = csrf_client()
    before = timezone.now()
    post_login(client, token, "pat", PASSWORD)
    after = timezone.now()

    (event,) = events(Action.LOGIN_SUCCESS)
    assert before - timedelta(seconds=2) <= event.occurred_at <= after + timedelta(seconds=2)


def test_login_without_csrf_token_is_refused() -> None:
    make_user()
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        LOGIN,
        data={"username": "pat", "password": PASSWORD},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["code"] == "auth.csrf"
    assert not events(Action.LOGIN_SUCCESS)


def test_wrong_password_is_generic_and_audited_as_failed() -> None:
    make_user()
    client, token = csrf_client()

    response = post_login(client, token, "pat", "wrong")

    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_credentials"
    (event,) = events(Action.LOGIN_FAILED)
    assert event.outcome == Outcome.FAILED
    assert event.reason == "bad_password"


def test_unknown_user_looks_identical_and_never_stores_the_typed_username() -> None:
    client, token = csrf_client()

    response = post_login(client, token, "does-not-exist-hunter2", "x")

    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_credentials"
    (event,) = events(Action.LOGIN_FAILED)
    assert event.reason == "unknown_account"
    assert event.actor_user_id is None
    assert "hunter2" not in repr(event.__dict__)


def test_failure_counter_survives_the_rejected_attempt() -> None:
    user = make_user()
    client, token = csrf_client()

    post_login(client, token, "pat", "wrong")
    post_login(client, token, "pat", "wrong")

    user.refresh_from_db()
    assert user.failed_login_count == 2


def test_account_locks_after_five_failures_and_refuses_the_correct_password() -> None:
    user = make_user()
    client, token = csrf_client()

    for _ in range(5):
        assert post_login(client, token, "pat", "wrong").status_code == 401
    user.refresh_from_db()
    assert user.locked_until is not None

    # correct password, but locked: same generic 401, audited as denied
    assert post_login(client, token, "pat", PASSWORD).status_code == 401
    (locked_event,) = events(Action.LOGIN_LOCKED)
    assert locked_event.outcome == Outcome.DENIED
    assert not events(Action.LOGIN_SUCCESS)


def test_lockout_expires() -> None:
    user = make_user()
    user.locked_until = timezone.now() - timedelta(minutes=1)
    user.failed_login_count = 0
    user.save()
    client, token = csrf_client()

    assert post_login(client, token, "pat", PASSWORD).status_code == 200


def test_successful_login_resets_failure_counter() -> None:
    user = make_user()
    client, token = csrf_client()
    post_login(client, token, "pat", "wrong")

    assert post_login(client, token, "pat", PASSWORD).status_code == 200

    user.refresh_from_db()
    assert user.failed_login_count == 0


def test_me_requires_login() -> None:
    response = Client().get("/api/v1/auth/me")

    assert response.status_code == 401


def test_me_returns_the_signed_in_user() -> None:
    make_user(role=Role.LEAD)
    client, token = csrf_client()
    post_login(client, token, "pat", PASSWORD)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["role"] == "lead"


def test_logout_is_audited_and_ends_the_session() -> None:
    user = make_user()
    client, token = csrf_client()
    post_login(client, token, "pat", PASSWORD)

    response = client.post("/api/v1/auth/logout", headers={"X-CSRFToken": fresh_token(client)})

    assert response.status_code == 200
    (event,) = events(Action.LOGOUT)
    assert event.actor_user_id == user.pk
    assert client.get("/api/v1/auth/me").status_code == 401


def test_every_role_can_sign_in_and_sees_its_own_role() -> None:
    for role in Role:
        username = f"user-{role.value}"
        make_user(username=username, role=role)
        client, token = csrf_client()
        assert post_login(client, token, username, PASSWORD).status_code == 200
        assert client.get("/api/v1/auth/me").json()["role"] == role.value
