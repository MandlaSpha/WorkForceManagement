from django.apps import AppConfig


class JobsConfig(AppConfig):
    name = "wfm.jobs"
    label = "jobs"

    def ready(self) -> None:
        from . import runners  # noqa: F401 - registers what each kind of job does
