# Gijima WFM — notes for Claude Code

Workforce Management web app for Gijima Customer Services (contact centre / service desk), built by VMK. Specs live in `docs/` and are the source of truth; read the relevant one before changing behaviour:

- `docs/01-REQUIREMENTS.md`: what to build (IDs like SCH-04, AUD-08), open questions, gaps list
- `docs/02-TECH-SPEC.md`: stack, engine maths, CDR import format, test strategy, phases
- `docs/03-UI-SPEC.md`: screens (from the reference video)
- `docs/04-UML.md`, `docs/05-SYSTEM-DESIGN.md`: models and runtime design
- `docs/06-CODE-ARCHITECTURE.md`: repo layout and boundary rules
- `docs/07-CODING-STANDARDS.md`: style, conventions, verify commands, Definition of Done

## Stack
Django 5.2 + Django Ninja, PostgreSQL 16, Celery + Valkey, pure-Python `wfm_engine` (NumPy, OR-Tools). Front end: Vue 3 (decided), TypeScript, Vite, Pinia, TanStack Query, Tailwind, ECharts. Hosting is undecided: build portable containers (tech spec §9). Dev runs on .NET Aspire + Docker Desktop. Open-source only: no dependency with a paid or non-allow-listed licence without an ADR.

## Commands
Docker Desktop is installed per-user; if `docker` is not found in a shell, add its `resources/bin` folder (under `%LOCALAPPDATA%/Programs/DockerDesktop`) to PATH. `uv` and `just` live in the Python Scripts folder.
- `just dev`: start everything under .NET Aspire (dashboard http://localhost:15888; pgAdmin data browser http://localhost:5050, already connected to the dev database; the dashboard needs no login in dev because it only listens on localhost).
- The API and worker run with `--noreload` under Aspire: after a backend change, restart that resource in the Aspire dashboard (or `just dev` again). The Vue dev server hot-reloads.
- `just verify`: format check, lint, strict types, engine + web unit tests, layer rules. Run before saying a change is done.
- `just test-int`: API tests on a real Postgres in Testcontainers (needs Docker running). Runs in parallel (pytest-xdist, one database per worker, about 75 s).
- `just e2e`: Playwright against a running `just dev` stack (needs WFM_BASE_URL and WFM_DEMO_PASSWORD, see the justfile). 4 workers by default (`E2E_WORKERS=1` to run one at a time); each spec uses its own queue and dates. About 1.5 minutes.
- **Test workflow (speed matters, agreed 15 Oct 2026):** while developing inside a phase, run ONLY the tests for what you touched (`pytest path -n 4`, `vitest run path`, `playwright test file.spec.ts`, plus `just verify` lint/types when cheap). Run the whole battery (`just verify-full` and the e2e suite, at the same time, once) only when a PHASE is done, before its final commit; do not run e2e twice. A test Playwright reports as "flaky" is a finding to look at, not noise; a timeout that passes alone but fails when three suites share the machine is load, not a bug.
- **Row locks:** lock rows with `select_for_update(no_key=True)`, never the plain form: a plain lock deadlocks with another transaction's foreign-key check at commit (a test scans for it).
- `POST /api/v1/system/ping-worker` (admin): proves the worker is alive and that trace context survives the queue.
- `just api-types`: regenerate the web app's typed API client after changing the API.
- `just verify-full`: everything CI runs (grows as web/e2e are added).
- `uv run python manage.py seed_demo --password <12+ chars>`: synthetic demo logins (dev only).

## Hard rules
- **Never commit or copy real data.** `Files/` holds real caller numbers, staff names and confidential documents; it is git-ignored. Tests use anonymised fixtures only. No personal data in logs, traces, analytics, errors or fixtures (POPIA).
- `Files/Call Detail Report - June.xlsx` is a duplicate of May; don't treat it as June.
- Writes go through module `services.py` and must call `audit.record()` in the same transaction, as the LAST write (the audit insert holds a lock until commit that keeps the hash chain linear; recording first would make every other audited transaction wait for your slow work). Never edit or delete audit rows; the chain detects it. `manage.py audit_verify` checks the chain; `audit_export` writes a day's heads for immutable storage. Reads go through `selectors.py` starting from `Model.objects.for_user(user)`. Never use raw `Model.objects` in views.
- `wfm_engine` must not import Django, read the clock or do I/O.
- Every new or changed endpoint needs an integration test for every role, both allowed and refused. Out-of-scope records return 404.
- Store UTC, display Africa/Johannesburg. Money is `Decimal`. Units go in names (`aht_s`, `sl_target_pct`).
- Web: Feature-Sliced Design layers (app > pages > widgets > features > entities > shared); import other slices only via their `index.ts`. Never `v-html`. UI role checks are cosmetic; the API enforces access.
- Identity: sign-in methods are adapters that return an `Identity`; linking, provisioning, group-to-role mapping and auditing live ONLY in `wfm/identity/services.py`. Never put a secret in provider config (name an environment variable). Failures shown to users must be generic; the reason goes to the audit trail. See docs/adr/0001 and tech spec section 10.
- Telemetry: spans and logs carry the role and request id only. Never put a name, username, id of a person, pay value, query string or request body in a span, log line or analytics event. Scrubbing lives in `wfm/core/telemetry.py` and `web/src/shared/telemetry`; both have tests that search spans for leaked values.
- The Copilot / AI assistant is **parked**: don't build it.
- Don't skip hooks (`--no-verify`); fix the failure.
