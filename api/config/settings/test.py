"""Test settings. The database is a real PostgreSQL 16 in a Testcontainers container
(tech spec section 7). It starts when this module is first imported, i.e. before Django reads
DATABASES, and stops when the test process exits. Set WFM_TEST_DATABASE_URL to reuse an
existing server instead (for example a CI service container).
"""

import atexit
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-key")


def _ensure_database() -> None:
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
AUTH_PASSWORD_VALIDATORS = []
CELERY_TASK_ALWAYS_EAGER = True
