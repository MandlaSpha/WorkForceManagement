"""Settings shared by every environment. Environment-specific values come from env vars."""

from __future__ import annotations

import os
from pathlib import Path

from celery.schedules import crontab

from ._env import broker_url_from_env, database_from_env, env, env_bool, env_list

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env_bool("DJANGO_DEBUG")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "wfm.core",
    "wfm.accounts",
    "wfm.identity",
    "wfm.audit",
    "wfm.telephony",
    "wfm.forecasting",
    "wfm.scheduling",
    "wfm.capacity",
    "wfm.contracts",
    "wfm.servicedesk",
    "wfm.people",
    "wfm.notifications",
    "wfm.jobs",
    "wfm.insight",
    "wfm.reports",
    "wfm.overtime",
]

# No django.contrib.admin on purpose: it would be a write path that bypasses the audited
# service layer (requirement AUD-08). Reference-data admin is added later, read-only.

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "wfm.core.middleware.RequestContextMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "OPTIONS": {"connect_timeout": 5},
        **database_from_env(),
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Sessions (gap G7): server-side, sliding 30-minute idle timeout.
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 30 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the SPA reads the token and sends it as X-CSRFToken

# Identity providers (AUTH-01..03): JSON list, or the path of a JSON file in WFM_IDENTITY_CONFIG.
# Secrets are never in it; a provider names the environment variable that holds its secret.
WFM_IDENTITY_PROVIDERS = (
    Path(os.environ["WFM_IDENTITY_CONFIG"]).read_text(encoding="utf-8")
    if os.environ.get("WFM_IDENTITY_CONFIG")
    else os.environ.get("WFM_IDENTITY_PROVIDERS", "")
)

# Login lockout (gap G7)
LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_MINUTES = 15

# Time: store UTC, display Africa/Johannesburg at the edge (NFR-07).
USE_TZ = True
TIME_ZONE = "Africa/Johannesburg"

# Seconds the auto-scheduler may think for one queue-week (SCH-05).
AUTOSCHEDULE_TIME_LIMIT_S = 10

LANGUAGE_CODE = "en-za"
USE_I18N = False

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Tracing is on whenever an OTLP endpoint is configured (Aspire sets one in development).
WFM_TELEMETRY = env_bool("WFM_TELEMETRY", default="OTEL_EXPORTER_OTLP_ENDPOINT" in os.environ)

# Features switched on in this deployment (FEAT-01): "all", "none" or a comma-separated list such
# as "telephony,forecasting". Checked at start-up; a typo or a missing dependency stops the app.
WFM_FEATURES = os.environ.get("WFM_FEATURES", "all")

# Call data import (DAT-01..04). The ACD writes local times without a zone; this says which zone.
# Confirm with the ACD vendor: if it exports UTC, set this to "UTC".
WFM_CDR_SOURCE_TIMEZONE = os.environ.get("WFM_CDR_SOURCE_TIMEZONE", "Africa/Johannesburg")
WFM_CDR_MAX_UPLOAD_MB = int(os.environ.get("WFM_CDR_MAX_UPLOAD_MB", "25"))
# Service-level threshold used when intervals are built. Per-queue and per-contract targets
# (ENG-05) come with the configuration screens; changing this needs the intervals rebuilt.
WFM_SL_THRESHOLD_S = int(os.environ.get("WFM_SL_THRESHOLD_S", "20"))

CELERY_BEAT_SCHEDULE = {
    # Nightly check that the audit trail's hash chain is intact (AUD-10).
    "audit-verify-chain": {
        "task": "wfm.audit.verify_chain",
        "schedule": crontab(hour=3, minute=0),
    },
    # Emailed report schedules that have come due (RPT-10).
    "reports-send-due": {
        "task": "wfm.reports.send_due",
        "schedule": crontab(minute="*/15"),
    },
    # Finished background jobs are kept a week.
    "jobs-delete-old": {
        "task": "wfm.jobs.delete_old",
        "schedule": crontab(hour=3, minute=30),
    },
}

CELERY_BROKER_URL = broker_url_from_env()
# Results are only used for short round trips (the worker ping); real jobs report through the
# database. Valkey also serves as the result store, and results expire after an hour.
CELERY_RESULT_BACKEND = broker_url_from_env()
CELERY_RESULT_EXPIRES = 3600
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_TIME_LIMIT = 15 * 60

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    # Every line carries the trace id so a log entry can be matched to its trace.
    "filters": {"trace": {"()": "wfm.core.telemetry.TraceContextFilter"}},
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s [trace=%(trace_id)s] %(message)s"}
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["trace"],
            "formatter": "plain",
        }
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}

# Outgoing email (scheduled reports). Development writes messages to the console; a real SMTP
# server is set with these variables, and its password is named by variable, never written here.
EMAIL_BACKEND = os.environ.get(
    "WFM_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("WFM_EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("WFM_EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.environ.get("WFM_EMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("WFM_EMAIL_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("WFM_EMAIL_TLS", "") == "1"
DEFAULT_FROM_EMAIL = os.environ.get("WFM_EMAIL_FROM", "wfm@localhost")
