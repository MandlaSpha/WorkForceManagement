"""Tracing behaviour (OBS-01, OBS-10): the browser's trace continues through the API into the
audit trail, spans carry the role but never an identity, and secrets stay out of every span."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
from django.db import connections
from django.test import Client
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditEvent
from wfm.core import telemetry

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import ReadableSpan

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery"
BROWSER_TRACE = "4bf92f3577b34da6a3ce929d0e0e4736"
TRACEPARENT = f"00-{BROWSER_TRACE}-00f067aa0ba902b7-01"


@pytest.fixture(scope="module")
def exporter() -> Iterator[InMemorySpanExporter]:
    """Switch tracing on for this module only, exporting to memory, then switch it off again."""
    import os

    from opentelemetry.instrumentation.django import DjangoInstrumentor
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

    os.environ["WFM_OTEL_SYNC"] = "1"
    memory = InMemorySpanExporter()
    # Connections opened before instrumentation are not traced, so start from fresh ones.
    connections.close_all()
    telemetry.configure(service_name="wfm-test", exporter=memory)
    yield memory
    DjangoInstrumentor().uninstrument()
    PsycopgInstrumentor().uninstrument()
    telemetry._provider = None
    telemetry._configured_pid = None
    os.environ.pop("WFM_OTEL_SYNC", None)
    connections.close_all()


@pytest.fixture
def spans(exporter: InMemorySpanExporter) -> Iterator[InMemorySpanExporter]:
    exporter.clear()
    yield exporter
    exporter.clear()


def server_spans(exporter: InMemorySpanExporter) -> list[ReadableSpan]:
    return [s for s in exporter.get_finished_spans() if s.kind == trace.SpanKind.SERVER]


def everything_recorded(exporter: InMemorySpanExporter) -> str:
    """All span names, attributes and events as one string, to search for leaked values."""
    out = []
    for span in exporter.get_finished_spans():
        out.append(
            json.dumps(
                {
                    "name": span.name,
                    "attributes": dict(span.attributes or {}),
                    "events": [
                        {"name": e.name, "attributes": dict(e.attributes or {})}
                        for e in span.events
                    ],
                },
                default=str,
            )
        )
    return "\n".join(out)


def signed_in_client(role: Role = Role.PLANNER) -> Client:
    User.objects.create_user(
        username="pat.private", password=PASSWORD, role=role, first_name="Pat", last_name="Secret"
    )
    client = Client()
    client.force_login(User.objects.get(username="pat.private"))
    return client


def test_server_span_continues_the_browsers_trace(spans: InMemorySpanExporter) -> None:
    Client().get("/api/v1/auth/csrf", headers={"traceparent": TRACEPARENT})

    (span,) = server_spans(spans)
    assert format(span.context.trace_id, "032x") == BROWSER_TRACE
    assert span.parent is not None  # child of the browser's span, not a new root


def test_audit_event_records_the_same_trace_id_as_the_browser(spans: InMemorySpanExporter) -> None:
    User.objects.create_user(username="pat.private", password=PASSWORD, role=Role.PLANNER)
    client = Client(enforce_csrf_checks=True)
    token = client.get("/api/v1/auth/csrf").json()["csrfToken"]

    client.post(
        "/api/v1/auth/login",
        data={"username": "pat.private", "password": PASSWORD},
        content_type="application/json",
        headers={"X-CSRFToken": token, "traceparent": TRACEPARENT},
    )

    (event,) = AuditEvent.objects.filter(action=Action.LOGIN_SUCCESS)
    assert event.trace_id == BROWSER_TRACE


def test_spans_carry_the_role_but_never_the_person(spans: InMemorySpanExporter) -> None:
    client = signed_in_client(Role.LEAD)
    spans.clear()

    client.get("/api/v1/auth/me")

    (span,) = server_spans(spans)
    assert span.attributes is not None
    assert span.attributes["wfm.role"] == "lead"
    assert span.attributes["wfm.request_id"]
    recorded = everything_recorded(spans)
    for secret in ("pat.private", "Pat Secret", "Secret", PASSWORD):
        assert secret not in recorded


def test_anonymous_requests_are_labelled_anonymous(spans: InMemorySpanExporter) -> None:
    Client().get("/api/v1/auth/csrf")
    (span,) = server_spans(spans)
    assert span.attributes is not None
    assert span.attributes["wfm.role"] == "anonymous"


def test_database_queries_are_traced_without_their_values(spans: InMemorySpanExporter) -> None:
    client = signed_in_client()
    spans.clear()

    client.get("/api/v1/auth/me")

    db_spans = [
        s
        for s in spans.get_finished_spans()
        if (s.attributes or {}).get("db.system") == "postgresql"
        or (s.attributes or {}).get("db.system.name") == "postgresql"
    ]
    assert db_spans, "expected psycopg spans for the session and user lookups"
    assert all(s.context.trace_id == server_spans(spans)[0].context.trace_id for s in db_spans)
    recorded = everything_recorded(spans)
    assert "pat.private" not in recorded
    assert PASSWORD not in recorded


def test_login_password_never_reaches_a_span(spans: InMemorySpanExporter) -> None:
    User.objects.create_user(username="pat.private", password=PASSWORD, role=Role.AGENT)
    client = Client(enforce_csrf_checks=True)
    token = client.get("/api/v1/auth/csrf").json()["csrfToken"]

    client.post(
        "/api/v1/auth/login",
        data={"username": "pat.private", "password": PASSWORD},
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )

    recorded = everything_recorded(spans)
    assert PASSWORD not in recorded
    assert "pat.private" not in recorded
    assert token not in recorded


def test_the_callers_address_and_browser_never_reach_a_span(spans: InMemorySpanExporter) -> None:
    # A client address and a user agent can single a person out (POPIA), so neither is recorded.
    client = signed_in_client()

    client.get(
        "/api/v1/auth/me",
        REMOTE_ADDR="203.0.113.77",
        HTTP_USER_AGENT="SecretBrowser/9.9 (Private Device)",
    )

    recorded = everything_recorded(spans)
    assert "203.0.113.77" not in recorded
    assert "SecretBrowser" not in recorded
    assert "Private Device" not in recorded


def test_a_copilot_question_never_reaches_a_span(spans: InMemorySpanExporter) -> None:
    # Failure caught: the question text (it can name a person) or the answer in a span, a query
    # parameter or an event. The question lives only in the audit trail, for admin review.
    client = signed_in_client(Role.AGENT)
    spans.clear()

    response = client.post(
        "/api/v1/copilot/ask",
        {"question": "When is Zandile Qwertyuiop's next leave? CANARY-QUESTION-9917"},
        content_type="application/json",
    )

    assert response.status_code == 200
    recorded = everything_recorded(spans)
    for secret in ("Zandile", "Qwertyuiop", "CANARY-QUESTION-9917", "next leave"):
        assert secret not in recorded
    assert "I can't share" not in recorded
    event = AuditEvent.objects.get(action=Action.COPILOT_ASKED)
    assert "CANARY-QUESTION-9917" in event.reason  # kept on the trail for admins (AI-08)


def test_query_strings_are_removed_from_spans(spans: InMemorySpanExporter) -> None:
    Client().get("/api/v1/auth/csrf?search=hunter2&name=Pat")

    recorded = everything_recorded(spans)
    assert "hunter2" not in recorded
    assert "name=Pat" not in recorded


def test_health_probes_are_not_traced(spans: InMemorySpanExporter) -> None:
    Client().get("/healthz")
    Client().get("/readyz")
    assert server_spans(spans) == []


def test_log_lines_carry_the_trace_id(spans: InMemorySpanExporter) -> None:
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    telemetry.TraceContextFilter().filter(record)
    assert record.trace_id == "-"  # type: ignore[attr-defined]

    with trace.get_tracer("test").start_as_current_span("work") as span:
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
        telemetry.TraceContextFilter().filter(record)
        assert record.trace_id == telemetry.trace_id_hex(span)  # type: ignore[attr-defined]


class TestTheMirrorDestination:
    """WFM_OTEL_MIRROR_ENDPOINT (OBS-11): the same spans to a second place, never on its own."""

    def test_nothing_is_mirrored_unless_asked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("WFM_OTEL_MIRROR_ENDPOINT", raising=False)
        assert telemetry._mirror_exporter() is None

    def test_an_http_endpoint_gets_the_traces_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WFM_OTEL_MIRROR_ENDPOINT", "http://localhost:4318/")
        mirror = telemetry._mirror_exporter()
        assert mirror is not None
        # The exporter keeps its target in a private attribute; there is no public getter.
        assert getattr(mirror, "_endpoint", "") == "http://localhost:4318/v1/traces"

    @pytest.mark.parametrize("value", ["localhost:4318", "ftp://collector", "file:///tmp/x", "  "])
    def test_anything_but_an_http_url_is_ignored(
        self, value: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("WFM_OTEL_MIRROR_ENDPOINT", value)
        assert telemetry._mirror_exporter() is None

    def test_a_mirror_alone_does_not_switch_telemetry_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No standard OTLP variable: the primary exporter is None, so telemetry stays off.
        monkeypatch.setenv("WFM_OTEL_MIRROR_ENDPOINT", "http://localhost:4318")
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
        assert telemetry._exporter_from_env() is None
