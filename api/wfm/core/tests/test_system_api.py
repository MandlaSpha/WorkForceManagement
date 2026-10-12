import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.core import api as system_api

pytestmark = pytest.mark.django_db


def admin_client() -> Client:
    user = User.objects.create_user(username="ash", password="x", role=Role.ADMIN)
    client = Client()
    client.force_login(user)
    return client


def test_ping_worker_round_trips_through_the_task() -> None:
    response = admin_client().post("/api/v1/system/ping-worker")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    # tracing is off in tests, so both ids are empty; with tracing on they must match
    assert body["apiTraceId"] == body["workerTraceId"] == ""


def test_ping_worker_reports_503_when_the_worker_does_not_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Dead:
        @staticmethod
        def delay() -> None:
            raise TimeoutError

    monkeypatch.setattr(system_api, "ping", Dead)

    response = admin_client().post("/api/v1/system/ping-worker")

    assert response.status_code == 503
    assert response.json()["code"] == "worker.unavailable"
