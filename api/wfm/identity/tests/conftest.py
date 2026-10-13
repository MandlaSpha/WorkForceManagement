from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest
from django.test import RequestFactory

from wfm.identity import registry


@pytest.fixture
def configure_identity(settings: Any) -> Iterator[Callable[[list[dict[str, Any]]], None]]:
    """Set the identity providers for one test and forget them afterwards."""

    def apply(providers: list[dict[str, Any]]) -> None:
        settings.WFM_IDENTITY_PROVIDERS = json.dumps(providers)
        registry.reset()

    yield apply
    registry.reset()


@pytest.fixture
def web_request() -> HttpRequest:
    """A request with a working session, as sign-in needs."""
    request = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(request)  # type: ignore[arg-type]
    request.session.save()
    return request
