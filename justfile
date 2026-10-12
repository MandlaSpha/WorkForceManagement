# Gijima WFM task runner. `just --list` shows everything. Same commands locally and in CI.
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# On Windows PowerShell, npm's pnpm.ps1 shim is blocked by the default execution policy, so call
# the .cmd shim there instead of loosening the machine's security setting.
pnpm := if os() == "windows" { "pnpm.cmd" } else { "pnpm" }

default:
    @just --list

# Auto-fix formatting and lint.
fmt:
    cd engine; uv run ruff format .; uv run ruff check . --fix
    cd api; uv run ruff format .; uv run ruff check . --fix
    cd web; {{pnpm}} format

# Lint, format check, strict types and unit tests for engine and web. Run before every push.
verify:
    cd engine; uv run ruff format --check .; uv run ruff check .; uv run mypy; uv run pytest -q
    cd api; uv run ruff format --check .; uv run ruff check .; $env:PYTHONPATH="."; uv run mypy wfm config
    cd web; {{pnpm}} lint; {{pnpm}} typecheck; {{pnpm}} test

# API tests on a real PostgreSQL in Testcontainers (needs Docker Desktop running).
test-int:
    cd api; uv run pytest -q

# Regenerate the web app's typed API client from the Django API's OpenAPI schema.
api-types:
    cd api; $env:DJANGO_SETTINGS_MODULE="config.settings.dev"; uv run python manage.py export_openapi ../web/src/shared/api/openapi.json
    cd web; {{pnpm}} api:types

# Browser tests against a running stack. Start `just dev` first, then:
#   $env:WFM_BASE_URL="http://localhost:<web port from the Aspire dashboard>"
#   $env:WFM_DEMO_PASSWORD="<demo-password from `dotnet user-secrets list --project infra/aspire/WfmAppHost`>"
e2e:
    cd e2e; {{pnpm}} exec playwright test

# Start everything locally with .NET Aspire (Postgres, Valkey, migrations, demo logins, API,
# worker and the Vue app). Dashboard: http://localhost:15888 (login link printed on start).
dev:
    dotnet run --project infra/aspire/WfmAppHost --launch-profile http

# Everything CI runs (grows as security and CI-only checks are added).
verify-full: verify test-int
