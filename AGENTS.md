# AGENTS.md

## Project overview

CashFlow Manager is a self-hosted, multi-user personal-finance web app. The backend is FastAPI + SQLAlchemy + SQLite; the frontend is React 19 + strict TypeScript. Production packages the pre-built SPA, Nginx, Uvicorn, Alembic, and SQLite access in one container. Financial behavior is coupled across transactions, billing months, recurrence, transfers, bank balances, assets, salary/tax, and forecasts, so changes to one domain must be checked in its downstream summaries and UI.

## System design and data flow

1. `frontend/src/main.tsx` mounts `App`; `router.tsx` provides auth/onboarding guards and lazy routes.
2. Pages/components use TanStack Query and one module per domain under `frontend/src/api/`. `api/client.ts` sends cookie-authenticated requests to `/api/v1`.
3. Vite proxies `/api` to `localhost:8000` in development. Production Nginx serves the SPA and proxies `/api/` to Uvicorn.
4. `backend/app/main.py` constructs FastAPI, registers routers, checks production secrets, runs Alembic during lifespan, and seeds default tax configuration.
5. Routers are the HTTP/auth seam; Pydantic schemas validate input; services contain reusable financial logic; SQLAlchemy models persist to SQLite through request-scoped sessions.
6. Authentication is an `HttpOnly` JWT cookie. Almost every domain row is user-owned; authorization is enforced by filtering with the authenticated `user_id`, not by roles.
7. Transactions store both occurrence `date` and derived first-of-month `billing_month`. Recurrences are materialized rows linked to a root by `parent_transaction_id`/`parent_transfer_id`; they are not schedules evaluated at read time.

Production startup currently invokes migrations in both `start.sh` and FastAPI lifespan. Preserve this behavior unless migration ownership is deliberately changed and container startup is retested.

## Directory ownership

- `backend/app/routers/`: transport, dependency injection, ownership checks, status codes. Keep multi-step financial rules in services when they are reused or independently testable.
- `backend/app/schemas/`: request/response validation. Add cross-field validation here before invalid values reach financial services.
- `backend/app/services/`: billing, recurrence, bank balance, summaries, analytics, assets, salary/tax, forecasts, auth/OIDC, and seed logic.
- `backend/app/models/`: ORM schema. Import every new model in `models/__init__.py` so tests and Alembic register it.
- `backend/alembic/versions/`: ordered schema/data migrations. Model changes require a reviewed migration; do not use `Base.metadata.create_all()` as the production migration path.
- `backend/tests/`: pytest unit and FastAPI integration tests. Shared fixtures use in-memory SQLite with foreign keys enabled.
- `frontend/src/api/`: handwritten typed HTTP calls; keep them aligned with backend routes.
- `frontend/src/types/api.ts`: handwritten backend response contracts. There is no generated client.
- `frontend/src/components/`: feature UI and generic primitives; `pages/` owns route-level composition; `contexts/` owns auth/onboarding state.
- `frontend/tests/`: Vitest + Testing Library + MSW, arranged by `api/`, `components/`, and `pages/`.
- `e2e/`: manual Playwright tests; the configuration does not start the application.
- `docs/`: architecture, auth, configuration, development, and deployment references. Update the relevant document when behavior or setup changes.
- `deploy/` and root `Dockerfile`: production single-image deployment. Root `docker-compose.yml` is the two-container development setup.

## Toolchain and setup

Canonical versions come from CI and Dockerfiles: Python 3.14, Node 24, and npm 10+.

Dependency sources:

- Backend: `backend/requirements.txt` (runtime and test dependencies; no Python lockfile).
- Frontend: `frontend/package.json` + `frontend/package-lock.json` (npm lockfile v3).
- E2E: `e2e/package.json` + `e2e/package-lock.json`.

Backend setup and local run (`docs/development.md`, `.github/workflows/ci.yml`):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --requirement requirements.txt
mkdir -p data
uvicorn app.main:app --reload --port 8000
```

For a direct backend run, settings load `.env` relative to the process working directory. Because the command runs from `backend/`, place an ignored `backend/.env` there or export variables in the shell. At minimum use `DEVELOPMENT_MODE=true` for local placeholder secrets and set `DB_PATH` to a writable host path such as `./data/cashflow.db`. FastAPI lifespan applies migrations to that configured path.

Frontend setup and run (`frontend/package.json`, CI):

```bash
cd frontend
npm ci
npm run dev
```

The Vite server is `http://localhost:3000` and proxies `/api` to `http://localhost:8000`. `VITE_API_BASE_URL` is present in the example environment file but is currently unused; `api/client.ts` hard-codes the relative `/api/v1` base.

Development containers (`docs/development.md`):

```bash
cp .env.example .env
docker compose up
```

Do not commit `.env`, databases, coverage, Playwright reports, or build output.

## Verification gates

Use the commands defined by CI/package scripts. No lint or formatter command is configured; do not claim one has run.

Backend gate:

```bash
cd backend
python -m pytest --cov --cov-report=term-missing
```

Frontend gates:

```bash
cd frontend
npm run build
npm test -- --coverage
```

`npm run build` is the TypeScript gate (`tsc && vite build`); strict mode, unused locals/parameters, and fallthrough checks are enabled in `frontend/tsconfig.json`.

Useful focused commands:

```bash
cd backend && python -m pytest tests/test_transactions.py -v
cd frontend && npm test -- tests/pages/TransactionsPage.test.tsx
```

E2E is manual and requires backend + frontend already running:

```bash
cd e2e
npm ci
npx playwright install
npm test
```

For deployment changes also run the Compose gate from CI:

```bash
cp deploy/.env.example deploy/.env
docker compose -f deploy/docker-compose.yml config --quiet
rm deploy/.env
```

Before completion, run focused tests for the changed domain plus the full affected gate. Database changes also need migration tests and a fresh upgrade. E2E is not a current CI gate; state explicitly whether it was run.

## Repository conventions and invariants

- Every query or mutation of user-owned data must constrain `user_id`; add or extend cross-user isolation tests for new resources.
- API routes live under `/api/v1`. Cookie auth is supplied through `Depends(get_current_user)`.
- Keep backend schemas, router behavior, `frontend/src/types/api.ts`, domain API modules, MSW handlers, and tests synchronized. Frontend types do not validate runtime responses.
- Preserve `billing_month` as `YYYY-MM-01` and recompute it through `services/billing.py` whenever a transaction date changes. Payment method cannot be changed by transaction update because it would alter billing semantics.
- Logic assumes `tracking_start_date` and `MainBankHistory.valid_from` are first-of-month ISO dates. The current onboarding schema does not enforce this; validate or normalize at new write paths rather than relying on callers.
- Card/revolving transactions bill in the following month; bank, debit card, prepaid, and cash bill in the current month.
- Recurring edit/delete supports `single`, `future`, and `all`. Preserve root promotion and self-FK behavior when changing cascades.
- Use stable IDs for relationships. Name fields on transfers/settings include legacy account identity and are fragile under rename.
- SQLAlchemy `Numeric` values cross JSON as numbers. Use `Decimal` inside cumulative money calculations; avoid introducing additional float accumulation.
- React Query keys are domain state. Mutations that affect derived views must invalidate all affected keys (for example transactions/transfers can affect summary, analytics, assets, and forecasts).
- Follow existing naming: Python modules/functions `snake_case`, React components/types `PascalCase`, hooks `useX`, domain API exports `xApi`.
- PR titles must satisfy the Conventional Commit expression in `.github/workflows/ci.yml`; semantic-release consumes the squash title.

## Non-obvious failure modes

- `POST /api/v1/onboarding` currently wipes and recreates all setup and financial data for that user. Never treat it as a harmless update or call it twice outside an isolated test database.
- Direct `alembic` CLI reads the hard-coded URL in `backend/alembic.ini`; it does not honor `DB_PATH`. Application lifespan does override the URL. Confirm the target before any migration command.
- Startup and tests cache settings, engine, and session factories. Tests that change environment variables must clear the relevant `lru_cache`, following existing fixtures.
- The root `backend/conftest.py` prevents the local `backend/alembic/` directory from shadowing the installed `alembic` package; preserve it.
- SQLite foreign keys are enabled by connection event. Test databases must do the same or cascade/isolation behavior will differ from production.
- Production secrets are `SECRET_KEY` and `SESSION_ENCRYPTION_KEY`; never copy example values into real deployment. `DEVELOPMENT_MODE=true` bypasses the startup security check and is development-only.
- The production database is the bind-mounted SQLite file under `/app/data`; schema/data work must preserve upgrade and backup compatibility.

## OpenAPI status

FastAPI already exposes runtime Swagger at `/docs` and its schema at `/openapi.json`; no schema is checked in. Do **not** add a generated schema or generate frontend types from it yet: only a small subset of routes declares `response_model`, so many generated responses are incomplete and a committed artifact would provide false confidence.

If formalizing the contract, first add explicit response models/return contracts to all routes, then add deterministic schema export plus a CI drift check, and only then consider generating `frontend/src/types/api.ts`. Until that work is complete, backend schemas/router tests and the handwritten frontend types are the authoritative contract.
