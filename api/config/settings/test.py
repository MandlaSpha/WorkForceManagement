"""Test settings. The database is a real PostgreSQL 16 in a Testcontainers container
(tech spec section 7). It starts when this module is first imported, i.e. before Django reads
DATABASES, and stops when the test process exits. With pytest-xdist the controller starts it once
and every worker uses it, each on its own database. Set WFM_TEST_DATABASE_URL to reuse an
existing server instead (for example a CI service container).
"""

import atexit
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-key")


def _ensure_database() -> None:
    if os.environ.get("PYTEST_XDIST_WORKER") and os.environ.get("DATABASE_URL"):
        # A parallel worker: the controller already started the container and its address was
        # inherited. pytest-django gives each worker its own database on that one server.
        return
    external = os.environ.get("WFM_TEST_DATABASE_URL")
    if external:
        os.environ["DATABASE_URL"] = external
        return
    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer("postgres:16-alpine", driver=None)
    container.start()
    atexit.register(container.stop)
    os.environ["DATABASE_URL"] = container.get_connection_url()


_ensure_database()

from .base import *  # noqa: E402, F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed only; never in prod
INSTALLED_APPS = [*INSTALLED_APPS, "wfm.devtools"]  # noqa: F405
AUTH_PASSWORD_VALIDATORS = []
CELERY_TASK_ALWAYS_EAGER = True
CELERY_RESULT_BACKEND = "cache+memory://"
WFM_TELEMETRY = False  # tests that need tracing switch it on explicitly
