"""OpenTelemetry for the API and the background worker (requirements OBS-01, OBS-10).

What a trace may carry: timings, HTTP method, route path, status code, SQL text with its
placeholders, the user's *role* and an opaque request id. What it must never carry: names,
usernames, passwords, pay values, query strings or SQL parameter values. The user id lives only
in the audit trail, which is a separate system (system design section 7.1).

Configuration is by the standard OTEL_* environment variables, which Aspire sets in development.
With no exporter endpoint configured, telemetry is simply off. WFM_OTEL_MIRROR_ENDPOINT adds a
second OTLP/HTTP destination for the same spans (the optional Grafana stack, OBS-11).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
)
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

log = logging.getLogger(__name__)

_configured_pid: int | None = None
_provider: TracerProvider | None = None

# Health probes would drown real traffic in noise.
EXCLUDED_URLS = "healthz,readyz"
# Span attributes that can carry a URL, and so a query string.
_URL_ATTRIBUTES = ("url.full", "http.url", "http.target", "url.query")
# Span attributes that identify the caller's machine or browser: a client address and a user agent
# can single a person out, so they are blanked (POPIA, OBS-05 and OBS-10), old and new names alike.
_CLIENT_ATTRIBUTES = (
    "net.peer.ip",
    "net.sock.peer.addr",
    "http.client_ip",
    "client.address",
    "http.user_agent",
    "user_agent.original",
)


def trace_id_hex(span: trace.Span | None = None) -> str:
    """The current (or given) span's trace id as 32 hex characters, or "" outside a trace."""
    context = (span or trace.get_current_span()).get_span_context()
    return format(context.trace_id, "032x") if context.is_valid else ""


def redact_query(url: str) -> str:
    """Drop the query string and fragment, which can hold identifiers or search terms."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _redact_url_attributes(span: trace.Span) -> None:
    attributes = getattr(span, "attributes", None) or {}
    for name in _URL_ATTRIBUTES:
        value = attributes.get(name)
        if not isinstance(value, str):
            continue
        # url.query is only a query string, so it is blanked rather than rewritten.
        span.set_attribute(name, "" if name == "url.query" else redact_query(value))


def _blank_client_attributes(span: trace.Span) -> None:
    attributes = getattr(span, "attributes", None) or {}
    for name in _CLIENT_ATTRIBUTES:
        if name in attributes:
            span.set_attribute(name, "")


def _django_response_hook(span: trace.Span, request: Any, response: Any) -> None:
    """Runs after all middleware: add the role and request id, scrub URLs. Never the user."""
    if not span.is_recording():
        return
    user = getattr(request, "_cached_user", None)  # loaded by the view; do not trigger a query here
    role = getattr(user, "role", "") if getattr(user, "is_authenticated", False) else ""
    span.set_attribute("wfm.role", role or "anonymous")
    request_id = response.headers.get("X-Request-ID") if hasattr(response, "headers") else None
    if request_id:
        span.set_attribute("wfm.request_id", request_id)
    _redact_url_attributes(span)
    _blank_client_attributes(span)


def _sample_ratio() -> float:
    raw = os.environ.get("WFM_OTEL_SAMPLE_RATIO", "1.0")
    try:
        return min(1.0, max(0.0, float(raw)))
    except ValueError:
        log.warning("Ignoring invalid WFM_OTEL_SAMPLE_RATIO=%r", raw)
        return 1.0


def _exporter_from_env() -> SpanExporter | None:
    """OTLP exporter from the standard variables (endpoint, protocol, headers), or None."""
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") and not os.environ.get(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
    ):
        return None
    protocol = os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    if protocol.startswith("http"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter as HttpExporter,
        )

        return HttpExporter()
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter as GrpcExporter,
    )

    return GrpcExporter()


def _mirror_exporter() -> SpanExporter | None:
    """A second OTLP/HTTP destination for the very same spans, from WFM_OTEL_MIRROR_ENDPOINT
    (requirement OBS-11): the Grafana stack's collector, beside whatever the standard OTEL_*
    variables point at (the Aspire dashboard in development). It is a second processor on the same
    provider, so it sees exactly what the first one sees, spans already scrubbed at the source; it
    never switches telemetry on by itself. None when unset or not an http(s) URL."""
    endpoint = os.environ.get("WFM_OTEL_MIRROR_ENDPOINT", "").strip()
    if not endpoint:
        return None
    if urlsplit(endpoint).scheme not in ("http", "https"):
        log.warning("Ignoring WFM_OTEL_MIRROR_ENDPOINT: it must be an http(s) URL")
        return None
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter as HttpExporter,
    )

    return HttpExporter(endpoint=endpoint.rstrip("/") + "/v1/traces")


def _ensure_provider(service_name: str, exporter: SpanExporter | None) -> TracerProvider | None:
    """Create and register the tracer provider once per process. A forked child (Celery
    prefork) gets its own, because exporter threads do not survive a fork."""
    global _configured_pid, _provider
    if _provider is not None and _configured_pid == os.getpid():
        return _provider

    exporter = exporter or _exporter_from_env()
    if exporter is None:
        log.info("Telemetry disabled: no OTLP endpoint configured")
        return None

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": service_name,
                "service.version": os.environ.get("WFM_VERSION", "0.1.0"),
                "deployment.environment.name": os.environ.get("WFM_ENV", "dev"),
            }
        ),
        # Respect the browser's sampling decision; sample new (root) traces at the set ratio.
        sampler=ParentBased(TraceIdRatioBased(_sample_ratio())),
    )
    # In-process exporters (tests) must not be batched, or spans would arrive late.
    processor = (
        SimpleSpanProcessor(exporter)
        if os.environ.get("WFM_OTEL_SYNC") == "1"
        else BatchSpanProcessor(exporter)
    )
    provider.add_span_processor(processor)
    mirror = _mirror_exporter()
    if mirror is not None:
        provider.add_span_processor(BatchSpanProcessor(mirror))
    try:
        trace.set_tracer_provider(provider)
    except Exception:
        log.debug("Tracer provider was already set; reusing it")
    _provider, _configured_pid = provider, os.getpid()
    log.info("Telemetry enabled for %s", service_name)
    return provider


def configure(
    *,
    service_name: str,
    exporter: SpanExporter | None = None,
    django: bool = True,
    celery: bool = False,
) -> TracerProvider | None:
    """Set up tracing for this process and switch on the requested instrumentations.

    Safe to call repeatedly: the provider is created once per process and each instrumentor
    ignores a second request. Returns None when no exporter is configured (telemetry off).
    """
    provider = _ensure_provider(service_name, exporter)
    if provider is None:
        return None

    # SQL parameter values are never recorded, only the statement with its placeholders.
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

    PsycopgInstrumentor().instrument(tracer_provider=provider, capture_parameters=False)
    if django:
        from opentelemetry.instrumentation.django import DjangoInstrumentor

        # Passed explicitly: the OTEL_PYTHON_DJANGO_EXCLUDED_URLS variable is only read when the
        # instrumentation module is first imported, which is too early to rely on.
        DjangoInstrumentor().instrument(
            tracer_provider=provider,
            response_hook=_django_response_hook,
            excluded_urls=EXCLUDED_URLS,
        )
    if celery:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().instrument(tracer_provider=provider)  # type: ignore[no-untyped-call]
    return provider


def running_under_celery(argv: list[str] | None = None) -> bool:
    """True inside a Celery worker. There, tracing is set up per pool process (after any fork)
    by the worker_process_init signal, not when Django loads."""
    args = argv if argv is not None else sys.argv
    return any(os.path.basename(a).lower().removesuffix(".exe") == "celery" for a in args[:2])


class TraceContextFilter(logging.Filter):
    """Adds the current trace id to every log record so a log line can be matched to its trace."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_hex() or "-"
        return True
