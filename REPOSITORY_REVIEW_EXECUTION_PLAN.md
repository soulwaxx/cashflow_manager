# Repository Review Remediation Execution Plan

## Delivery contract

All remediation from `REPOSITORY_REVIEW.md` will be delivered in one pull request. Coding tasks run serially against the same PR branch so only one agent writes the checkout at a time. Every table row is owned by one fresh coder subagent, and no coder identity is reused for a different scope.

If work discovered during a task does not directly support that row's acceptance criteria, the coder must stop and report it. The orchestrator must add a new row and spin up a fresh coder rather than expanding the current assignment. Coders may not push, open, merge, or publish the PR; the parent retains those actions and final acceptance.

Each coder handoff must include:

- the exact current branch and diff;
- the assigned row only, including relevant findings and files;
- repository invariants from `AGENTS.md`;
- focused tests to add before or with the fix;
- commands run, failures, changed files, and residual risks;
- a stop request for any unapproved product, schema, or deployment decision.

Commit boundaries are review gates, not individual coder rows. Create one baseline commit for accepted C01-C06/C20 work and the clean R1 corrections, then commit the C07-C11, C12-C14, C15-C19, and final-acceptance blocks only after R2, R3, R4, and R5 respectively are clean. After the final commit, create local feature branch `fix/review-remediation` at the completed commit series; until then work remains on local `main` as explicitly directed by the owner.

## Owner decisions required before affected rows

| Decision | Recommended default | Blocks |
|---|---|---|
| Repeated onboarding | Return `409 Conflict`; do not add reset behavior in this PR | C01 |
| Card-to-bank routing | Require a valid owned `linked_bank_id` for bank-funded card activity; reject unsupported unlinked configurations | C03 |
| Card relinking history | Use effective-dated link history with an explicit first-of-month billing period; route transactions by `billing_month` | C20 |
| Transaction directions | Define one payment-method/direction cash-impact matrix and use the same terms in API, summary, and UI | C05 |
| Manual salary override | Make the override the returned/displayed effective monthly net while retaining the computed value separately | C06 |
| Missing salary tax table | Return `422`; do not persist a zero or pending computed net | C06 |
| Forecast meaning | Treat forecasts as recurring-commitment projections, not future bank balances | C12, C13 |
| Migration owner | Keep FastAPI lifespan as the owner and remove the duplicate `start.sh` migration | C08 |

## Current execution state

Snapshot for continuation on 2026-09-20:

- Branch `main`, fixed base `ccc67f4`. The baseline commit at this snapshot contains all accepted C01-C06/C20 remediation, R1 corrections, and the pre-existing `AGENTS.md`/documentation changes.
- Active mission: `0857cf47-0db5-47a9-9bfa-c4910cace129`.
- C01-C06 and C20 are implemented and accepted. Their focused clean-environment backend suites, focused frontend suites/builds, migration checks, and `git diff --check` passed as recorded by the owning coders.
- Fresh R1 review `5ff85cc8-b59d-44a9-a37c-5eaa83f361dd` found no additional issues after corrections R1-012 through R1-015 and returned `R1 verdict: CLEAN`.
- C07-C19 have not started. Initial C07 run `aee30234-2375-4b30-808a-823be86f99b1` was intentionally paused before edits when the owner added commit boundaries; it produced no project changes or patch.
- Next action: complete the baseline commit, then resume C07 with a fresh same-role fallback if the paused run is not resumable.

| Row | Latest coder evidence | State |
|---|---|---|
| C01 | `e15d4f59-2426-4b55-a0c5-e9dc6dcfc914` | R1-013 corrected; onboarding suite passed in a clean environment |
| C02 | `7dc9db8a-d4a2-429d-91b1-2666ef4c1456` | Accepted |
| C03 | `85f206ac-bcf4-4a68-9e36-46d54d954e67` | SetupPage and inactive-bank corrections complete; focused backend suites passed |
| C04 | `36e2021a-3aaa-4a96-aca6-137c9a6d3d56` | Accepted |
| C05 | `7a8c2065-2bfa-4351-9d73-1384622c8073` | R1-015 corrected; 12 focused frontend tests and production build passed |
| C06 | `728dc1dc-5748-4b91-a3de-f638b564d0e0` | R1-012 corrected; 3 isolation and 39 affected salary tests passed |
| C20 | `0464555a-a4be-4e5c-b25f-7a694c706ecd` | R1-014 corrected; 57 payment-method/bank-routing tests passed |

Latest R1 findings and disposition:

1. **R1-012 / C06:** compact salary dates prevented cross-user isolation tests from reaching ownership assertions. Corrected with canonical fixture dates; salary list/update/delete isolation now executes.
2. **R1-013 / C01:** compact onboarding dates bypassed canonical validation and could break balance reads. Corrected with exact `YYYY-MM-DD` validation; 23 onboarding tests passed.
3. **R1-014 / C20:** compact card-link periods were accepted but ordered incorrectly against dashed billing months. Corrected with canonical round-trip validation and regression coverage; 57 focused backend tests passed.
4. **R1-015 / C05:** the UI fabricated cash impact for unsupported legacy method/direction pairs. Corrected with an explicit unsigned unsupported presentation; focused tests and the frontend build passed.
5. Fresh full-diff R1 rerun found no standards or specification findings and returned `R1 verdict: CLEAN`.

Continuation order:

1. Create the baseline commit for C01-C06/C20 and clean R1 corrections.
2. Execute C07-C11 serially, run R2, correct any findings, update this plan, and commit the block only after R2 is clean.
3. Execute C12-C14 serially, run R3, correct any findings, update this plan, and commit the block only after R3 is clean.
4. Execute C15-C19 serially, run R4, correct any findings, update this plan, and commit the block only after R4 is clean.
5. Run every final acceptance gate and R5, update this plan, and create the final block commit only after R5 is clean. Backend evidence must use a clean `uv`/virtualenv or container environment because the host installation has a broken `cryptography/_cffi_backend`.
6. Create local feature branch `fix/review-remediation` at the completed commit series.

Recovery evidence: workflow `dd24755d-428c-4328-b4d7-e7e606b7e0cd` failed only when R1 pass 1 hit the provider usage limit; its receipt is retained under the async run directory. Earlier failed runs remain `de4ddbff-5b93-430a-a6b2-1771aa26a05a`, `705cd549-797c-40e9-8788-c3a1759d7c77`, and `64c805b7-099c-42bd-9dd0-fa9742cacc99`.

## Coder execution table

Rows are executed in numeric order unless a dependency explicitly permits reordering. Even independent rows remain serial because they share one PR worktree. C20 was added from R1 and executes immediately after the C01/C05/C06 corrections, before C07, because C07 must reconcile all settled model changes.

| Task | Single coder | Scope and findings | Main files | Depends on | Required validation |
|---|---|---|---|---|---|
| C01 | `coder` (`C01-onboarding`) | Make onboarding one-shot, preserve existing data, and constrain onboarding dates, names, balances, linked-bank names, salary values, and nested duplicates. Covers H1 and onboarding portions of M6. | `backend/app/routers/onboarding.py`, `backend/app/schemas/onboarding.py`, onboarding tests and frontend error handling | Owner onboarding decision | Re-submission is rejected without changing any row; first submission still works; malformed nested payload tests |
| C02 | `coder` (`C02-secret-guard`) | Reject deployment placeholders, malformed encryption keys, and insufficient production secrets. Covers H2. | `backend/app/config.py`, `deploy/.env.example`, config/bootstrap tests, configuration docs | None | Every template placeholder fails outside development mode; generated valid secrets start successfully |
| C03 | `coder` (`C03-bank-routing`) | Normalize effective bank dates, initialize from the first applicable history row, respect card linkage, and define unlinked-card handling. Covers H3 and the card-routing part of H4 plus related validation in M6. | `backend/app/services/bank_balance.py`, payment-method/onboarding write paths, bank-balance tests | Owner card-routing decision | Parameterized month-start/mid-month/bank-switch/linkage tests; Decimal balances remain stable |
| C04 | `coder` (`C04-transfer-validation`) | Reject identical endpoints, unknown/stale owned accounts, empty names, and invalid transfer values without yet redesigning account storage. Covers immediate H4/M4 defects and transfer portions of M6. | `backend/app/routers/transfers.py`, `backend/app/schemas/transfer.py`, transfer/balance tests | C03 | Same-account and phantom-account requests return 422; valid recurrence/cascade behavior is unchanged |
| C05 | `coder` (`C05-transaction-semantics`) | Implement and document one direction/cash-impact matrix across transaction API validation, bank balance, summaries, and transaction form terminology. Covers M3. | transaction router/schema, `services/bank_balance.py`, `services/summary.py`, `TransactionForm.tsx`, backend/frontend tests | C03 and owner direction decision | Exhaustive payment-method × direction tests; refunds/payoffs have consistent summary and balance signs |
| C06 | `coder` (`C06-salary-tax`) | Add bounded Decimal tax/salary fields, ordered-threshold and positive-range validators, arithmetic guards, and agreed manual-override behavior. Covers H5 and salary/tax portions of M6. | salary/tax schemas, routers, models/services as needed, Salary page/types/tests | Owner override decision | Invalid tables return 422, never 500; adversarial cases and verified golden calculations pass |
| C20 | `coder` (`C20-card-link-history`) | Add effective-dated card-to-bank link history after R1 showed that mutable links rewrite historical balances. Relinking requires an explicit first-of-month billing period; transactions route to the link effective for their billing month, while migrated existing links preserve prior routing. | payment-method/link-history models and migration, payment-method API/schema, bank-balance service, frontend payment-method settings/types, backend/frontend tests | C03, R1 finding R1-002, owner effective-link and explicit-bill-month decisions | Existing transactions retain their historical bank after relink; the new bank applies from the selected billing month; invalid/overlapping/cross-user links are rejected; fresh and upgrade migrations pass |
| C07 | `coder` (`C07-schema-drift`) | Add a reconciliation migration for nullability and user indexes; add a fresh-upgrade drift gate. Covers H6 and the Alembic-check part of L2. | models, new Alembic revision, migration tests, `.github/workflows/ci.yml` | C01-C06 and C20 model changes settled | Fresh `upgrade head && alembic check`; upgrade from previous head; migration test suite |
| C08 | `coder` (`C08-migration-runtime`) | Make direct Alembic resolve `DB_PATH` through application settings and establish one migration owner. Covers M9 and M10. | `backend/alembic/env.py`, `alembic.ini`, `app/main.py`, `start.sh`, startup/development docs and tests | Owner migration decision, C07 | Custom-path CLI migration test; direct Uvicorn and production image startup; no duplicate upgrade invocation |
| C09 | `coder` (`C09-account-identities`) | Introduce stable identities for saving/investment/pension accounts, migrate name-keyed settings and transfer endpoints, and retain a bounded compatibility path. Completes M4. | models, schemas, onboarding, transfers, assets, migration, frontend types/forms, tests | C04, C07, C08 | Fresh/upgrade migration, rename-history preservation, cross-user ownership, transfer/assets regression tests |
| C10 | `coder` (`C10-reporting-validation`) | Add typed and bounded year/month/date-range inputs for summary, analytics, and asset endpoints; reject reversed and non-finite ranges. Covers reporting portions of M6. | summary/analytics/assets routers and tests; shared schemas only where reused | C09 | Month 1–12 and bounded years; valid ISO ranges; reversed/invalid/non-finite requests return 422 |
| C11 | `coder` (`C11-assets-asof`) | Add `as_of` month semantics to assets, cut off transfers and pension accrual accordingly, and align dashboard requests/cache keys. Covers M5. | assets router/service/API/types, `DashboardPage.tsx`, backend/frontend tests | C09, C10 | January excludes later records; year-end remains equivalent; salary-period boundary tests |
| C12 | `coder` (`C12-forecast-domain`) | Define forecasts as recurring commitments, import only series intersecting the base year, preserve cadence, validate forecast inputs, and correct backend/docs terminology. Covers M1, M2, and forecast portions of M6. | forecast schema/router/service/models if needed, README/docs, migrations if needed, backend tests | Owner forecast decision, C07-C08 | Expired/future/boundary recurrence tests; cadence projection tests; no bank-balance claims remain |
| C13 | `coder` (`C13-forecast-ui`) | Complete line and adjustment add/edit/delete flows and align user-facing terminology and errors with the forecast contract. Covers M12 and frontend part of M2. | forecast API/types/pages/components/MSW/frontend tests | C12 | CRUD integration tests and production build; incorrect auto-imported lines are repairable in UI |
| C14 | `coder` (`C14-query-cache`) | Centralize query keys/invalidation dependencies and invalidate all derived views affected by tax, salary, payment-method, transaction, transfer, asset, and forecast mutations. Covers L1. | frontend query usage and tests | C05, C06, C09, C11-C13 | Mutation tests assert each affected cache family is invalidated; no unrelated broad cache clears |
| C15 | `coder` (`C15-csrf`) | Add explicit unsafe-method Origin validation or the approved equivalent while preserving cookie defenses and documented proxy behavior. Covers M7. | app middleware/dependencies, auth/configuration docs and security tests | None | Allowed same-origin requests pass; absent/foreign browser origins follow documented policy; CORS tests remain valid |
| C16 | `coder` (`C16-session-security`) | Add login/register abuse controls and immediate session revocation after password changes using a token version or password-change timestamp. Covers M8. | auth/user model, migration, services/routers/config, frontend handling, tests | C07-C08 | Rate-limit boundary tests; old token rejected after password change; new login and OIDC behavior preserved |
| C17 | `coder` (`C17-recovery-deploy`) | Pin deployable releases, automate consistent SQLite backups/retention, provide a restore drill, and keep TLS-first deployment guidance. Covers M11. | deploy files, scripts, Docker/docs, deployment tests | C08 | Compose config, image health smoke, backup integrity, restore into released image, rollback instructions |
| C18 | `coder` (`C18-dependency-lock`) | Produce a reproducible production Python dependency lock compatible with Python 3.14/Alpine and separate runtime from test dependencies. Covers L3. | requirements/lock inputs, Dockerfile, CI/Renovate/docs | C17 | Clean locked install with hashes, image build, backend suite; update workflow documented |
| C19 | `coder` (`C19-e2e-ci`) | Add the missing critical Playwright journey to CI and connect existing schema/container/recovery gates without duplicating C07/C17 ownership. Completes L2. | `e2e/`, CI workflow, MSW/app startup support only if required | C01-C18, C20 | Login → onboarding → transaction → transfer → dashboard verification → logout; exact CI commands pass |

## Review and correction gates

Each gate is run by a fresh read-only `code-reviewer` subagent and does not replace coder ownership.

| Gate | Reviewer scope | Trigger | Blocking result |
|---|---|---|---|
| R1 | Financial correctness and cross-user isolation | After C01/C03/C05/C06 corrections and C20 | Any mismatch in onboarding safety, cash-impact matrix, card routing/history, transfer ownership, or salary/tax invariants |
| R2 | Migration and data compatibility | After C11 | Drift, unsafe migration, lost legacy account history, path mismatch, or incorrect as-of semantics |
| R3 | Forecast/frontend contract | After C14 | API/type/UI mismatch, unrecoverable forecast data, stale derived cache, or misleading terminology |
| R4 | Security and operations | After C19 | CSRF/session bypass, mutable deployment artifact, unverified restore, unlocked runtime, or missing CI evidence |
| R5 | Final repository review | After all accepted fixes | Any P0/P1 finding in the aggregate diff or any failed required gate |

A valid review finding is returned to the coder that owns the affected row only when it remains within that row's original scope. A finding that crosses into a different domain gets a new coder row and fresh agent. After every correction, rerun the focused tests and the affected review gate.

## Final single-PR acceptance

Before publication, the parent must verify:

1. every H/M/L item is mapped to at least one completed coder row;
2. no row contains unapproved scope expansion;
3. backend coverage gate, frontend build and coverage gate, Playwright journey, Compose validation, image smoke test, fresh migration, `alembic check`, and restore drill pass on the final head;
4. the full diff contains only remediation, tests, migrations, deployment changes, and required documentation;
5. migration upgrade and backup/restore compatibility are documented;
6. the PR title satisfies Conventional Commits;
7. remaining risks and intentionally deferred work are explicit in the PR description;
8. after the final accepted commit, local feature branch `fix/review-remediation` is created at the completed commit series.
