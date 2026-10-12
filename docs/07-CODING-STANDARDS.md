# Gijima WFM — Coding Standards and Ways of Working

Status: Draft v0.1, 12 October 2026. Everything here is enforced by tooling where possible; a rule that only lives in this document will drift. All tools listed are open source (no paid licences).

## 1. General

| Topic | Standard |
|---|---|
| Language of code and docs | English (South African spelling in UI text: "colour", "organise") |
| Line endings / encoding | LF, UTF-8, enforced by `.gitattributes` and `.editorconfig` |
| Formatting | Never argued about in review: the formatter decides |
| Comments | Explain *why*, not *what*. No commented-out code. TODOs need a ticket id: `# TODO(WFM-123): …` |
| Naming | Domain words from the requirements, used consistently: `requirement`, `coverage`, `variance`, `interval`, `shrinkage`, `roster_week`, `shift_assignment`. No synonyms (`schedule` vs `roster` mean different things here) |
| Units in names | `_s` seconds, `_min` minutes, `_pct` as 0–100, `_ratio` as 0–1, `_zar` rands: `aht_s`, `sl_target_pct`, `occupancy_ratio`, `hourly_rate_zar` |
| Time | Store and compute in UTC (`timestamptz`); convert to Africa/Johannesburg only at the edge (API output / UI). Never naive datetimes. Never `datetime.now()` in the engine |
| Money | `Decimal` in Python, `numeric(12,2)` in Postgres, never float. Rounding: banker's rounding only where payroll rules say so; otherwise half-up to cents |
| Personal data | Never in logs, traces, analytics, exception messages or test fixtures. Use ids, not names, in log lines |

## 2. Python (api + engine)

| Tool | Licence | Rule |
|---|---|---|
| Python 3.12 | PSF | Pinned in `pyproject.toml` and Docker image |
| `ruff` | MIT | Lint + format (replaces black, isort, flake8). Line length 100. Rule sets: E, F, W, I, B, UP, SIM, S (bandit), DJ (Django), PT (pytest), N, RUF |
| `mypy --strict` + `django-stubs` | MIT | Type hints required on all public functions; `engine/` must be fully strict, `api/` strict except migrations |
| `import-linter` | BSD-2 | Module boundary contracts (code architecture §3.4) |
| `pytest`, `pytest-django`, `pytest-cov`, `testcontainers` | MIT / BSD / MIT / Apache-2.0 | See tech spec §7 |
| `uv` | MIT / Apache-2.0 | Dependency management and lock file (`uv.lock`) |

Conventions:
- Services and selectors are **functions with keyword-only arguments** (`def assign_shift(*, actor, …)`). No "manager" or "helper" god classes.
- Business errors are typed exceptions from `wfm.core.errors` (`RuleViolation`, `NotFound`, `PermissionDenied`, `Conflict`); the API layer maps them to HTTP. No bare `except:`; never swallow exceptions.
- No business logic in `models.py` beyond field definitions, `__str__`, simple properties and the scoped manager.
- No logic in Django signals (except auth events for audit). Side effects are explicit in services.
- Queries: avoid N+1 (`select_related`/`prefetch_related`); integration tests assert query counts on hot endpoints (`django_assert_max_num_queries`).
- Migrations: one concern per migration, reviewed like code, backwards-compatible within a release (add column → backfill → enforce later). Never edit a merged migration.
- Celery tasks: idempotent, take ids not objects, call a service, `acks_late=True`, explicit retries with backoff.

## 3. TypeScript (web + e2e)

| Tool | Licence | Rule |
|---|---|---|
| TypeScript `strict: true`, `noUncheckedIndexedAccess` | Apache-2.0 | No `any` (lint error); `unknown` + narrowing instead |
| ESLint + Prettier (or Biome as a single tool) | MIT | `eslint-plugin-vue` (recommended + strongly-recommended), `eslint-plugin-vuejs-accessibility`, `steiger` or `eslint-plugin-boundaries` for FSD layers |
| Vitest, Vue Testing Library, MSW, Playwright | MIT / MIT / MIT / Apache-2.0 | See tech spec §7 |
| pnpm | MIT | Package manager, lock file committed |

Conventions:
- Components: PascalCase single-file components (`RosterGrid.vue`), composables `useXxx.ts`; everything else kebab-case folders, camelCase functions.
- API types come only from the generated client; never redeclare a backend type by hand.
- No `v-html` on data from the API.
- Every data-loading screen handles four states: loading (skeleton), empty (honest message), error, data.
- Colour is never the only signal (numbers on heatmap cells, text on pills); WCAG 2.1 AA.
- Playwright selectors use roles and labels (`getByRole`, `getByLabel`), `data-testid` only when there is no accessible handle.

## 4. API conventions

| Topic | Standard |
|---|---|
| Base path | `/api/v1/…`; breaking changes → `/v2`, old version kept for one release |
| Resources | Plural nouns, kebab-case: `/shift-templates`, `/leave-requests/{id}` |
| Actions | State transitions as sub-resources: `POST /leave-requests/{id}/approve`, `POST /roster-weeks/{id}/publish` |
| JSON fields | camelCase on the wire (Ninja alias generator), snake_case in Python |
| Dates/times | ISO 8601 with offset: `2026-08-17T06:30:00+02:00`; dates as `YYYY-MM-DD` |
| Errors | RFC 9457 Problem Details: `{type, title, status, detail, code, violations[]}`; `code` is stable and documented (e.g. `rule.rest_11h`) |
| Status codes | 200/201 success, 202 job accepted, 400 malformed, 401 not logged in, 403 not allowed, 404 not found or not in your scope, 409 conflict (stale version), 422 business rule violation |
| Concurrency | Optimistic locking with a `version` field on editable aggregates (roster week, leave request); stale update → 409 |
| Pagination | Cursor-based for lists: `?cursor=…&limit=50` |
| KPIs | Always `{value, basis: measured|modelled, coverage}` (DAT-10) |
| Not-found vs forbidden | Records outside the user's scope return **404**, not 403, so existence is not revealed |

## 5. Database conventions

- Table names: Django default `<app>_<model>`; columns snake_case; units in names (`aht_s`).
- Primary keys `bigint` identity internally; a separate `uuid` (v7) for anything exposed in URLs or exports.
- Every business table: `created_at`, `updated_at` (DB defaults), plus `version` where edited concurrently.
- Foreign keys indexed; composite indexes for hot paths: `(queue_id, interval_start)`, `(employee_id, date)`.
- Check constraints for invariants the DB can enforce (`end > start`, `0 <= pct <= 100`, one published forecast per queue as a partial unique index).
- Soft-deactivate reference data (`is_active`), never hard-delete it.

## 6. Git workflow

| Topic | Standard |
|---|---|
| Branching | Trunk-based: `main` always releasable; short-lived branches `feat/WFM-123-assign-shift`, `fix/…`, `chore/…`, merged within days |
| Commits | Conventional Commits: `feat(scheduling): validate 11h rest on assign`; enforced by `commitlint` (MIT) |
| Pull requests | Small (aim < 400 changed lines), one concern, linked ticket, description says what/why/how tested, screenshots for UI changes |
| Reviews | At least one approval; author does not merge their own unreviewed PR; CI must be green |
| Merging | Squash merge to keep `main` linear |
| Protected `main` | No direct pushes, no force pushes, required status checks |
| Releases | Semantic versioning tags `vMAJOR.MINOR.PATCH`; changelog generated from commit messages |
| Secrets | Never committed; `gitleaks` (MIT) in pre-commit and CI |

## 7. Automated gates

### 7.1 Local verify commands

One task runner, `just` (CC0, single binary, works on Windows, macOS, Linux), so every developer and CI run the **same** commands:

| Command | Runs | When | Target time |
|---|---|---|---|
| `just fmt` | Auto-fix formatting (ruff format, Prettier) | Any time | seconds |
| `just verify` | Format check, lint, type check, boundary lint, **unit tests** (engine, api, web) | Before every push (pre-push hook runs it) | < 2 min |
| `just test-int` | Integration tests on Testcontainers Postgres (needs a container runtime: Docker Desktop) | Before opening a PR that touches the API or DB | < 5 min |
| `just e2e` | Playwright against the Compose stack | Before opening a PR that changes a user flow | < 10 min |
| `just verify-full` | `verify` + `test-int` + `e2e` + licence and security checks: exactly what CI runs | Before asking for review; CI runs it on every PR | < 15 min |

Hook layering, from fastest to slowest:
1. **pre-commit** (on `git commit`, staged files only, < 10 s): the checks below. Kept fast so nobody is tempted to bypass it.
2. **commit-msg**: commitlint (Conventional Commits).
3. **pre-push**: `just verify`.
4. **CI**: `just verify-full` on every PR; merge blocked until green.

`--no-verify` is not used to get past a failing hook; fix the cause. CI repeats every check anyway, so skipping locally only delays the failure.

### 7.2 Hooks and CI

`pre-commit` (MIT) runs locally on every commit: ruff (lint+format), mypy on changed files, ESLint/Prettier, gitleaks, commitlint, trailing whitespace/EOF/LF checks, and a guard that blocks `.xlsx`/`.xls` files outside `fixtures/`.

CI on every PR:
1. Lint, format check, type check (Python + TS)
2. `import-linter` and FSD boundary lint
3. Unit tests (engine, api, web) with coverage gates (engine ≥ 90%, api ≥ 80%, web ≥ 70%)
4. Integration tests on Testcontainers Postgres (incl. role matrix, audit coverage)
5. Build images and generated API client (fails if the client is out of date)
6. Playwright e2e on the Compose stack (incl. telemetry-privacy journey)
7. Security: `pip-audit` (Apache-2.0), `pnpm audit`, `bandit` via ruff `S` rules, `gitleaks`; OWASP ZAP (Apache-2.0) baseline scan nightly against UAT
8. **Licence check**: `pip-licenses` (MIT) and `license-checker` (BSD-3) fail the build on any dependency outside the allow-list (MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0, PostgreSQL, LGPL for runtime-linked libs). AGPL/SSPL/commercial require an ADR

## 8. Definition of Done (per story)

- [ ] Acceptance criteria met and demoed
- [ ] Unit tests for new logic; integration test for each new or changed endpoint, including **every role** (allowed and refused)
- [ ] Every new write path produces an audit event (AUD-08) — covered by the audit contract test
- [ ] Playwright journey added or updated if the user flow changed
- [ ] Loading, empty and error states handled; accessible (keyboard, labels, contrast)
- [ ] No personal data in logs, traces, analytics or fixtures
- [ ] OpenAPI schema and generated client updated; migrations reviewed
- [ ] Docs/ADR updated if behaviour or a decision changed
- [ ] CI green, reviewed, merged

## 9. Code review checklist (reviewer)

1. Is the logic in the right place? (maths → engine; writes → service; reads → selector; HTTP → api)
2. Can a role see or change something it should not? Is there a test proving it cannot?
3. Is the change audited, with the right actor and reason?
4. Units and time zones correct? Money as Decimal?
5. N+1 queries, missing indexes, unbounded lists?
6. Errors: typed, mapped to the right status, no leaked internals or personal data?
7. Would a new team member understand the names without asking?
