"""Local development (run by Aspire or `manage.py runserver`)."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "dev-only-insecure-key-not-for-any-shared-environment")
os.environ.setdefault("DJANGO_DEBUG", "1")

from .base import *  # noqa: F403

CSRF_TRUSTED_ORIGINS = [*CSRF_TRUSTED_ORIGINS, "http://localhost:5173"]  # noqa: F405

# Development-only tools (never installed in production).
INSTALLED_APPS = [*INSTALLED_APPS, "wfm.devtools"]  # noqa: F405
