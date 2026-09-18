# Repository Review

**Repository:** `cashflow_manager`
**Revision:** `294d39e` (`main`)
**Review date:** 2026-09-18
**Scope:** Application code, migrations, frontend, tests, deployment, CI/CD, and documentation. Generated dependencies and build outputs were excluded.

## Executive assessment

This is a well-structured personal project with unusually strong automated coverage for its size. The backend has clear router/service/model boundaries, user scoping is applied consistently, the frontend is type-safe and componentized, and the production container follows several good practices.

The application is **not yet safe to treat as an authoritative financial ledger**. The main blockers are data-loss and financial-correctness defects:

1. Re-submitting onboarding deletes all of the user's financial data.
2. Example production secrets are accepted as secure production values.
3. Several valid account configurations produce incorrect bank balances.
4. Tax configuration accepts internally inconsistent values that can crash salary calculation.
5. ORM metadata and the migrated database schema have diverged.

**Overall quality: 3/5.** The engineering foundation is good, but the correctness boundary around money, dates, and account identity needs to be tightened before broader production use.

## Review method and validation

The repository was divided into nine logical sections and traced from API schemas through routers, services, models, migrations, frontend callers, and tests.

Validation performed:

- Backend: **375 tests passed**, approximately **96% coverage**, in a clean temporary environment.
- Frontend: **159 tests passed**, approximately **74% statement coverage**.
- Frontend production build and TypeScript checks passed.
- All Alembic migrations upgraded a fresh SQLite database successfully.
- `alembic check` failed after that upgrade because model metadata differs from the migrated schema.
- Focused isolated-database probes reproduced the destructive onboarding, insecure-secret, bank-balance, transfer, forecast, and tax failures described below.
- A local backend start using the host Python installation failed because that environment has a broken `cryptography/_cffi_backend` installation. This is a host-environment issue; clean-environment tests passed.

Automated tests prove substantial behavior, but they currently encode or omit some incorrect edge cases. High coverage should not be read as high financial correctness.

## Severity-ranked findings

### High severity

#### H1. Re-submitting onboarding destroys existing financial records

`POST /onboarding` is available after onboarding is complete. It unconditionally deletes forecasts, assets, transactions, transfers, bank history, payment methods, categories, salary configuration, tax configuration, and settings before rebuilding setup data (`backend/app/routers/onboarding.py:39-59`). A direct second submission was reproduced and removed existing transaction data.

**Impact:** Complete loss of a user's application data through an authenticated request, accidental UI regression, replay, or same-site request attack.

**Recommendation:** Reject submission when `onboarding_complete=true`. If reset is required, expose a separate re-authenticated, explicitly confirmed reset operation.

#### H2. Production example secrets bypass the insecure-default check

The startup guard rejects only three development values (`backend/app/config.py:71-90`). The production template supplies different public placeholders (`deploy/.env.example:4-7`), which are not rejected. Starting production configuration with those values was reproduced successfully.

**Impact:** A copy-and-run deployment can issue forgeable JWTs and use a known OIDC-cookie encryption key, contrary to the fail-fast guarantee.

**Recommendation:** Reject template markers and low-entropy values; preferably require explicit Compose interpolation. Test that `deploy/.env.example` cannot start until both values are replaced.

#### H3. Main-bank balance initialization fails for non-month-first history dates

The balance walker selects history at each `YYYY-MM-01` boundary and initializes only when `valid_from == month_first` (`backend/app/services/bank_balance.py:84-95`). Onboarding accepts an unconstrained string and stores it unchanged (`backend/app/schemas/onboarding.py:38-45`, `backend/app/routers/onboarding.py:61-73`). A mid-month value therefore never initializes the opening balance; later months continue from zero.

**Impact:** Persistent incorrect balances for API/imported data or future UI changes.

**Recommendation:** Use typed dates, normalize effective dates to month boundaries, and initialize from the first applicable history row. Test mid-month and bank-switch boundaries.

#### H4. Account identity is not respected consistently in bank balances

Two independent paths misstate balances:

- A transfer from a bank account to itself matches `from_match` first and subtracts the amount (`backend/app/services/bank_balance.py:124-147`); the API does not reject identical endpoints.
- Card activity is applied to the current main bank without checking `linked_bank_id` (`backend/app/services/bank_balance.py:96-122`). A card linked to another bank changes the main-bank balance.

**Impact:** Incorrect cash balances for configurations supported by onboarding and payment-method settings.

**Recommendation:** Reject same-account transfers. Use stable account IDs end to end and apply card activity only to the linked bank. Define behavior for unlinked cards and main-bank changes.

#### H5. Tax and salary inputs can crash or materially misstate output

Tax fields are almost entirely unconstrained floats (`backend/app/schemas/tax_config.py:5-42`); salary rates and extras are similarly permissive (`backend/app/schemas/salary.py:9-20`). The calculator divides by configured deduction ranges (`backend/app/services/salary.py:90-100`). A zero band-2 range was reproduced as `ZeroDivisionError`/HTTP 500. Negative rates, descending thresholds, and rates above 100% are also accepted.

`manual_net_override` is stored and displayed but does not govern the returned computed value (`backend/app/routers/salary.py:99-113`, `frontend/src/pages/SalaryPage.tsx:245-248`).

**Impact:** API failures and plausible but incorrect salary outputs.

**Recommendation:** Add field bounds and cross-field invariants, protect service arithmetic, clarify override semantics, and add adversarial tax-table tests.

#### H6. Fresh migrated databases do not match ORM metadata

`upgrade head` succeeds, but `alembic check` reports nullable mismatches on `forecast_adjustments.adjustment_type` and several timestamp columns, plus missing indexes on `users.email` and `users.oidc_sub`. Migration 004 adds `adjustment_type` nullable (`backend/alembic/versions/004_add_indexes_transfer_updated_at.py:21-31`) while the ORM infers non-null (`backend/app/models/forecast.py:46-60`). The initial migration also omits explicit indexes represented by `index=True` in the user model (`backend/alembic/versions/001_initial_schema.py:19-28`, `backend/app/models/user.py:13-20`).

**Impact:** Future autogeneration includes unrelated changes; guarantees and indexes differ by schema history.

**Recommendation:** Add a reconciliation migration and run `alembic check` in CI after a fresh upgrade.

### Medium severity

#### M1. Forecast auto-import ignores recurrence validity and can use the wrong year

Creation selects every recurring transaction regardless of whether recurrence ended before the base year (`backend/app/routers/forecasts.py:53-58`). It then uses the latest occurrence not after December 31, potentially from a prior year (`backend/app/routers/forecasts.py:64-86`), despite the UI promising recurring transactions “from the base year” (`frontend/src/components/forecasting/CreateForecastForm.tsx:29-36`).

**Impact:** Expired commitments appear indefinitely and projected amounts may not represent the base year.

**Recommendation:** Import only series intersecting the base year and choose an occurrence effective in that year. Test all year boundaries.

#### M2. Forecasting is not a future bank-balance projection

The service aggregates line amounts by month (`backend/app/services/forecasting.py:20-75`). It has no opening balance, income/expense sign, transfers, assets, or running balance. Documentation nevertheless calls it a future-bank-balance projection (`README.md:22`, `docs/architecture.md:90-96`).

**Impact:** Users can interpret commitments as projected cash position.

**Recommendation:** Rename it to recurring-commitment projection or add signed cash flows, opening balance, and a running-balance series.

#### M3. Transaction direction semantics conflict across layers

The backend treats `credit` as an addition for direct bank/debit-card records but as a payoff for next-month card types (`backend/app/services/bank_balance.py:99-122`). The form labels both `debit` and `credit` as “Outcome” (`frontend/src/components/transactions/TransactionForm.tsx:50-61`), while summary outgoings include both (`backend/app/services/summary.py:100-107`).

**Impact:** The same displayed concept can increase or reduce cash unexpectedly.

**Recommendation:** Use explicit concepts such as income, purchase, refund, and card payment, or define and enforce one strict direction invariant by payment-method type.

#### M4. Transfers accept nonexistent, stale, and identical accounts

Creation validates type strings but not the existence of non-bank names; bank IDs are resolved opportunistically and may remain null (`backend/app/routers/transfers.py:25-42`). Persistence stores mutable names plus optional IDs (`backend/app/models/transfer.py:20-31`), and assets group by those names (`backend/app/services/assets.py:42-72`).

**Impact:** Typos create phantom accounts, renames split history, and invalid transfers affect analytics.

**Recommendation:** Introduce stable identities for all account types. Meanwhile, validate owned names and reject identical endpoints.

#### M5. Dashboard assets for a selected month are calculated through year-end

Assets are requested by year only (`backend/app/routers/assets.py:17-20`). The service includes transfers through December 31 and full-year pension accrual (`backend/app/services/assets.py:23-49,74-97`), while the dashboard places that value beside a selected month (`frontend/src/pages/DashboardPage.tsx:17-28`).

**Impact:** January can include later or future-dated activity.

**Recommendation:** Add an `as_of` date/month and use the selected dashboard month as cutoff.

#### M6. Broad schema-validation gaps push invalid states into services

String dates/months, unrestricted years, negative/non-finite amounts, permissive rates, and weak forecast/analytics bounds appear across onboarding, forecast, salary, tax, summary, and asset APIs.

**Impact:** Invalid state reaches string comparisons, parsers, loops, arithmetic, and persistence, producing 500s or plausible but wrong totals.

**Recommendation:** Use `date`, constrained integers/decimals, enums, and model validators. Keep service assertions for financial invariants and prefer `Decimal` for money.

#### M7. Cookie-authenticated mutations lack explicit CSRF defense

The auth cookie is `HttpOnly`, `SameSite=Lax`, and conditionally `Secure` (`backend/app/routers/auth.py:28-37`), but unsafe methods have no CSRF token or Origin/Referer validation. CORS alone is not a CSRF control.

**Impact:** `SameSite=Lax` reduces ordinary cross-site POST attacks, but same-site sibling-origin compromise and policy edge cases remain, including for destructive routes.

**Recommendation:** Validate Origin on unsafe methods and/or add a CSRF token; retain cookie flags as defense in depth.

#### M8. Authentication lacks abuse controls and immediate revocation

Login/registration have no throttling (`backend/app/routers/auth.py:124-166`). JWTs contain only subject and expiry (`backend/app/services/auth.py:17-35`), so password changes do not revoke existing 30-day tokens (`backend/app/routers/users.py:24-38`).

**Impact:** Application-layer password guessing is unrestricted, and stolen sessions survive password rotation.

**Recommendation:** Add rate limits and a token-version or `password_changed_at` check; consider shorter access-token lifetimes.

#### M9. Direct Alembic commands ignore `DB_PATH`

Runtime database configuration uses `DB_PATH` (`backend/app/database.py:9-13`), but Alembic uses a hard-coded `/app/data/cashflow.db` (`backend/alembic.ini:1-5`, `backend/alembic/env.py:17-30`). This conflicts with the documented local workflow (`docs/development.md:18-35,69-83`) and was reproduced.

**Impact:** Developers can migrate a different database or fail on a missing `/app/data`.

**Recommendation:** Override Alembic's URL from the same settings/environment source and test custom paths.

#### M10. Migration execution has two owners

Both `start.sh:5-6` and FastAPI lifespan (`backend/app/main.py:16-22`) run `alembic upgrade head`.

**Impact:** Redundant work and confusing lock/race ownership.

**Recommendation:** Select one migration owner and document its concurrency assumptions.

#### M11. Deployment lacks a tested recovery path

Production Compose pulls mutable `latest` and exposes plain HTTP (`deploy/docker-compose.yml:2-22`). Backups are documented but not automated or restore-tested. Default secure cookies also conflict with non-local plain HTTP unless security is reduced (`docs/configuration.md:65-66`).

**Impact:** Failed upgrades are harder to reverse; database recovery is manual; some documented network modes break authentication defaults.

**Recommendation:** Pin releases/digests, automate SQLite snapshots and restore drills, document rollback, and terminate TLS by default.

#### M12. Frontend forecasting exposes only part of the backend model

The client supports line and adjustment CRUD (`frontend/src/api/forecasts.ts:31-50`), but the detail page only displays projection and adds adjustments (`frontend/src/pages/ForecastDetailPage.tsx:8-57`). It cannot add/edit/delete lines or manage existing adjustments.

**Impact:** Incorrect auto-imported lines cannot be repaired through the UI.

**Recommendation:** Complete the workflow or reduce unsupported API/UI affordances.

### Low severity

#### L1. Frontend cache invalidation is sometimes too narrow

Tax mutations invalidate only `['tax-config']` (`frontend/src/pages/settings/TaxConfigSettings.tsx:18-38`) even though salary calculations depend on it. Similar dependencies exist among payment methods, balances, summaries, assets, and forecasts.

**Recommendation:** Centralize query keys and their domain invalidation dependencies.

#### L2. CI omits end-to-end tests and migration drift checks

CI runs unit suites and builds (`.github/workflows/ci.yml:33-83,98-110`) but not Playwright, `alembic check`, deployment startup, or restore smoke tests.

**Recommendation:** Add a focused browser smoke suite, fresh-schema migration/check, and container health test.

#### L3. Runtime dependency reproducibility is partial

Several backend dependencies use lower bounds (`backend/requirements.txt:3-6`) and production installs that file directly (`Dockerfile:16-18`).

**Recommendation:** Use a locked runtime requirements file with hashes or fully pinned transitive dependencies.

## Section-by-section assessment

### 1. Platform, configuration, persistence, migrations — 3/5

**Strengths:** Centralized settings; SQLite foreign keys on every connection; database directory creation; linear migrations; useful composite indexes.

**Concerns:** H2, H6, M9, M10; inconsistent `Decimal` use; unstated single-writer SQLite assumption; no CI schema-parity gate.

**Priority:** Reconcile schema, unify URL resolution, and make migration ownership explicit.

### 2. Authentication, authorization, user lifecycle — 3.5/5

**Strengths:** Bcrypt; fixed JWT algorithm; secure cookie baseline; OIDC state/nonce and encrypted ID-token storage; auth-mode switches; strong cross-user isolation tests; password verification on account deletion.

**Concerns:** H2 and M7/M8. Basic registration is open whenever enabled, which may be acceptable for a personal instance but should be explicit. Revocation currently requires global secret rotation.

**Priority:** Secret validation, mutation-origin protection, throttling, then token revocation.

### 3. Onboarding, settings, categories, payment methods — 2.5/5

**Strengths:** Broad guided setup; useful defaults; ownership checks in CRUD; invalid main-bank types rejected; referenced-category deletion blocked.

**Concerns:** H1; duplicate/empty names, negative balances, invalid links/dates/rates; account state split between rows and name-encoded setting keys; destructive setup logic concentrated in one route.

**Priority:** Make onboarding one-shot, validate nested inputs, and migrate toward stable account records.

### 4. Transactions, recurrence, transfers, bank balance — 2/5

**Strengths:** Consistent user scoping; transaction reference checks; strong recurrence/cascade tests; isolated billing logic; bulk-loaded bank calculation using `Decimal`; migration path toward transfer FKs.

**Concerns:** H3/H4 and M3/M4 affect the core ledger. Name fallback should remain compatibility-only. Source/destination corrections require transfer recreation.

**Priority:** Specify a cash-impact matrix by transaction type, method, linkage, and transfer endpoint; turn it into parameterized tests before repair.

### 5. Summaries, analytics, assets — 3/5

**Strengths:** Grouped/bulk queries; clear user boundaries; prior-year asset carry-forward; isolated stamp-duty logic.

**Concerns:** Inherited ledger errors; M5 period mismatch; frontend merges transfers into transaction-category rows (`frontend/src/pages/AnalyticsPage.tsx:35-80`); weak range validation; annual-only overrides.

**Priority:** Establish consistent “as of” semantics and make transfer analytics an explicit domain series.

### 6. Salary and tax — 2.5/5

**Strengths:** Effective-dated tax periods; global/user configuration; separated calculator; useful breakdown; solid normal-path tests.

**Concerns:** H5; no legal source/year cited for defaults; float arithmetic; unclear manual override; insufficient adversarial tests.

**Priority:** Strict invariants, `Decimal`, source/version documentation, and independently verified golden cases.

### 7. Forecasting — 2/5

**Strengths:** Clean forecast/line/adjustment separation; some bounds; ownership checks on principal resources; simple projection response.

**Concerns:** M1/M2/M12; cadence is lost so every line projects monthly; referenced category/payment method ownership is not fully validated; percentage adjustment overloads `new_amount`.

**Priority:** Define signed cash flow, cadence, opening balance, and adjustment semantics before extending implementation.

### 8. Frontend API, state, UI — 3/5

**Strengths:** Strict TypeScript; central Axios client; consistent React Query usage; clear auth/onboarding routing; accessible modal focus/Escape/ARIA behavior; sensible feature folders; passing production build.

**Concerns:** Lower integration coverage; M3/M5/M12/L1; inconsistent mutation error presentation; client input bounds stronger than server rules; eager large-list rendering.

**Priority:** Add integration tests for core financial journeys and standardize terminology, errors, and invalidation.

### 9. Deployment, CI/CD, tests, documentation — 3/5

**Strengths:** Multi-stage non-root deployment; health check; commit-pinned actions and narrow permissions; backend/frontend/build/Compose CI; Renovate and release automation; broad docs; strong backend isolation/migration/recurrence tests.

**Concerns:** M9-M11/L2/L3; broad world-writable runtime directories (`Dockerfile:31-45`); small E2E suite absent from CI; development examples reference nonexistent `tests/test_auth.py` (`docs/development.md:87-96`); documentation overstates forecast and secret-guard behavior.

**Priority:** Schema/container smoke gates, immutable releases, backup/restore automation, and executable documentation.

## Cross-cutting strengths

1. Per-user filtering is pervasive and cross-user tests cover many resources.
2. 375 backend and 159 frontend tests form a strong regression base.
3. Backend domain files and frontend feature folders are easy to navigate.
4. FK cascades/`SET NULL`/`RESTRICT` choices are mostly deliberate; SQLite enforcement is enabled.
5. Recurrence cascade behavior receives dedicated testing.
6. Strict TypeScript, centralized transport, server-state tooling, and accessible modals are sound foundations.
7. Actions are pinned, permissions are narrow, and release automation exists.
8. Multi-stage build, health check, persistence, and non-root runtime are good deployment basics.

## Recommended remediation sequence

### Phase 0 — protect data and restore financial correctness

1. Block repeated onboarding and design an explicit reset flow.
2. Fix production secret-template rejection.
3. Define and repair bank/account invariants: month initialization, linked-bank routing, same-account transfers, transaction semantics.
4. Enforce salary/tax invariants and eliminate calculation crashes.
5. Add a regression test for every reproduced defect before changing implementation.

### Phase 1 — restore schema and API integrity

1. Reconcile drift and enforce `upgrade head && alembic check` in CI.
2. Make Alembic honor `DB_PATH`; select one migration owner.
3. Replace string dates and unconstrained numerics with typed constrained fields.
4. Validate referenced-resource ownership on every write.
5. Establish stable identities for all accounts and phase out name-keyed balances.

### Phase 2 — align product behavior and UI

1. Decide whether forecasts are commitments or cash balance and align name, API, projection, and docs.
2. Complete forecast line/adjustment management.
3. Add month-aware asset snapshots.
4. Standardize frontend errors and cache invalidation.
5. Test onboarding → transaction/transfer → dashboard → forecast as integrated journeys.

### Phase 3 — operational hardening

1. Add throttling, CSRF/origin protection, and session revocation.
2. Use immutable images and TLS-first deployment.
3. Automate backups, retention, and restore verification.
4. Add Playwright and container smoke tests to CI.
5. Lock production dependencies reproducibly.

## Production-readiness acceptance gates

- Repeated onboarding cannot remove data without a separate confirmed reset.
- Every production template placeholder causes startup failure.
- A parameterized account-impact matrix passes for all method/direction/linkage/transfer combinations.
- Tax/salary APIs reject zero ranges, bad threshold order, negative values, and out-of-range rates without 500s.
- Fresh `alembic upgrade head` followed by `alembic check` passes.
- Application and Alembic use the same custom database path.
- Assets and balances are correct for a requested month, including mid-month setup and future records.
- Forecast naming and results match one documented domain definition.
- Browser tests cover login, onboarding, one transaction, one transfer, dashboard verification, and logout.
- Backup restoration is tested against a released image.

## Residual review limits

- No live OIDC provider was available; interoperability was assessed from code/tests.
- No long-running production dataset was supplied; performance was assessed from query structure, not load benchmarks.
- Tax-law correctness was reviewed for software invariants, not certified as current Italian legal advice.
- Responsive behavior was inspected from code/tests, not a physical-device matrix.
- The host Python cryptography failure prevented treating the host environment as production-like; isolated validation was used instead.
