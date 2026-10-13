from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "wfm.core"
    label = "core"

    def ready(self) -> None:
        import os

        from django.conf import settings

        from . import features, telemetry

        # A mistyped feature list must stop the application, not quietly enable or disable
        # something a customer has (or has not) paid for.
        features.enabled_features()

        # A Celery worker sets tracing up per pool process (config/celery.py), after any fork.
        if settings.WFM_TELEMETRY and not telemetry.running_under_celery():
            # celery=True here too: the *publishing* side writes the trace context into the task
            # headers, and the worker only continues a trace it was handed.
            telemetry.configure(
                service_name=os.environ.get("OTEL_SERVICE_NAME", "wfm-api"), celery=True
            )
