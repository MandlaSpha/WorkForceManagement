import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def test_liveness() -> None:
    response = Client().get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_checks_the_database() -> None:
    response = Client().get("/readyz")
    assert response.status_code == 200
    assert response.json()["database"] == "up"


def test_every_response_carries_a_request_id() -> None:
    response = Client().get("/healthz")
    assert response["X-Request-ID"]


def test_request_id_from_caller_is_kept_for_correlation() -> None:
    response = Client().get("/healthz", headers={"X-Request-ID": "abc123"})
    assert response["X-Request-ID"] == "abc123"
