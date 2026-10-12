import os

from celery import Celery
from celery.signals import worker_process_init

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("wfm")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@worker_process_init.connect  # type: ignore[untyped-decorator]
def _configure_tracing(**_: object) -> None:
    """Runs in every pool process (the solo pool sends it too), so exporter threads are created
    after any fork. Trace context from the web request travels in the task headers."""
    from django.conf import settings

    from wfm.core import telemetry

    if settings.WFM_TELEMETRY:
        telemetry.configure(
            service_name=os.environ.get("OTEL_SERVICE_NAME", "wfm-worker"),
            django=False,
            celery=True,
        )
