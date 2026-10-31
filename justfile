# Gijima WFM task runner. `just --list` shows everything. Same commands locally and in CI.
#
# One command per line on purpose: just stops at the first line that fails. Chaining commands
# with `;` in PowerShell would carry on after a failure and could still exit 0.
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# mypy loads the Django settings module, so the api folder must be importable.
export PYTHONPATH := "."

# On Windows PowerShell, npm's pnpm.ps1 shim is blocked by the default execution policy, so call
# the .cmd shim there instead of loosening the machine's security setting.
pnpm := if os() == "windows" { "pnpm.cmd" } else { "pnpm" }

default:
    @just --list

# Auto-fix formatting and lint everywhere.
fmt: fmt-engine fmt-api fmt-web

[working-directory: 'engine']
fmt-engine:
    uv run ruff format .
    uv run ruff check . --fix

[working-directory: 'api']
fmt-api:
    uv run ruff format .
    uv run ruff check . --fix

[working-directory: 'web']
fmt-web:
    {{pnpm}} format

# Format check, lint, strict types and unit tests for engine, api and web. Run before every push.
verify: verify-engine verify-api verify-web

[working-directory: 'engine']
verify-engine:
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy
    uv run pytest -q

[working-directory: 'api']
verify-api:
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy wfm config

[working-directory: 'web']
verify-web:
    {{pnpm}} lint
    {{pnpm}} typecheck
    {{pnpm}} test

# API tests on a real PostgreSQL in Testcontainers (needs Docker Desktop running). Parallel: one
# database per worker on a single container.
[working-directory: 'api']
test-int:
    uv run pytest -q -n auto

# Regenerate the web app's typed API client from the Django API's OpenAPI schema.
api-types:
    just _export-schema
    just _generate-types

[working-directory: 'api']
_export-schema:
    uv run python manage.py export_openapi ../web/src/shared/api/openapi.json

[working-directory: 'web']
_generate-types:
    {{pnpm}} api:types

# Browser tests against a running stack. Start `just dev` first, then:
#   $env:WFM_BASE_URL="http://localhost:<web port from the Aspire dashboard>"
#   $env:WFM_DEMO_PASSWORD="<demo-password from `dotnet user-secrets list --project infra/aspire/WfmAppHost`>"
[working-directory: 'e2e']
e2e:
    {{pnpm}} exec playwright test

# Start everything locally with .NET Aspire (Postgres, Valkey, migrations, demo logins, API,
# worker and the Vue app). Dashboard: http://localhost:15888 (no login in dev), pgAdmin: http://localhost:5050.
dev:
    dotnet run --project infra/aspire/WfmAppHost --launch-profile http

# `dev` plus the optional Grafana operations dashboards (OBS-11): an OpenTelemetry Collector, Jaeger,
# Prometheus and Grafana (http://localhost:3000, anonymous, this machine only). First start pulls the images.
[windows]
dev-grafana:
    $env:WFM_GRAFANA = "1"; dotnet run --project infra/aspire/WfmAppHost --launch-profile http

[unix]
dev-grafana:
    WFM_GRAFANA=1 dotnet run --project infra/aspire/WfmAppHost --launch-profile http

# Everything CI runs (grows as security and CI-only checks are added).
# The two halves are independent (lint/types/unit tests; API tests on their own Postgres), so they
# run side by side. About 2 minutes instead of 5.
[parallel]
verify-full: verify test-int
