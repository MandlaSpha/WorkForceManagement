import pytest

from wfm.core import telemetry


def test_redact_query_drops_query_and_fragment() -> None:
    url = "https://wfm.example/api/v1/leave?employee=42&name=Pat#top"
    assert telemetry.redact_query(url) == "https://wfm.example/api/v1/leave"


def test_redact_query_leaves_clean_urls_alone() -> None:
    assert telemetry.redact_query("/api/v1/auth/me") == "/api/v1/auth/me"


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([r"C:\git\api\.venv\Scripts\celery.exe", "-A", "config", "worker"], True),
        (["/usr/bin/celery", "-A", "config", "worker"], True),
        (["python", "-m", "celery"], False),  # only the first two arguments are inspected
        (["manage.py", "runserver"], False),
        (["gunicorn", "config.wsgi"], False),
    ],
)
def test_running_under_celery(argv: list[str], expected: bool) -> None:
    assert telemetry.running_under_celery(argv) is expected


def test_no_exporter_without_an_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    assert telemetry._exporter_from_env() is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0.25", 0.25), ("5", 1.0), ("-1", 0.0), ("not-a-number", 1.0)],
)
def test_sample_ratio_is_clamped_and_forgiving(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: float
) -> None:
    monkeypatch.setenv("WFM_OTEL_SAMPLE_RATIO", raw)
    assert telemetry._sample_ratio() == expected


def test_no_trace_id_outside_a_trace() -> None:
    assert telemetry.trace_id_hex() == ""
