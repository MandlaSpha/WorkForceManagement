# Gijima WFM task runner. `just --list` shows everything. Same commands locally and in CI.
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

default:
    @just --list

# Auto-fix formatting and lint.
fmt:
    cd engine; uv run ruff format .; uv run ruff check . --fix
    cd api; uv run ruff format .; uv run ruff check . --fix

# Lint, format check, strict types, unit tests (engine). Run before every push.
verify:
    cd engine; uv run ruff format --check .; uv run ruff check .; uv run mypy; uv run pytest -q
    cd api; uv run ruff format --check .; uv run ruff check .; $env:PYTHONPATH="."; uv run mypy wfm config

# API tests on a real PostgreSQL in Testcontainers (needs Docker Desktop running).
test-int:
    cd api; uv run pytest -q

# Start everything locally with .NET Aspire (Postgres, Valkey, migrations, API, worker).
# Dashboard: http://localhost:15888 (the login link is printed on start).
dev:
    dotnet run --project infra/aspire/WfmAppHost --launch-profile http

# Everything CI runs (grows as web, e2e and security checks are added).
verify-full: verify test-int
