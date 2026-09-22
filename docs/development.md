# Development guide

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.14+ |
| Node.js | 24+ |
| npm | 11.19+ |
| Docker Engine and Compose | Optional. Use them to run the full stack in containers. |

---

## Local setup

Run the backend and frontend as separate processes with hot-reload.

### Backend

```bash
cd backend

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
python -m pip install -r requirements-dev.txt

# The backend reads .env from the process working directory
cp ../.env.example .env
mkdir -p data
# Edit backend/.env and set DB_PATH=./data/cashflow.db

# Start the dev server (FastAPI lifespan applies migrations to DB_PATH)
uvicorn app.main:app --reload --port 8000
```

The API is available at `http://localhost:8000`. The Swagger UI is available at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend

npm ci
npm run dev
```

The app is available at `http://localhost:3000`. Vite proxies `/api/*` requests to `http://localhost:8000`.

---

## Docker Compose

Docker Compose builds and runs the backend and frontend as separate containers. This setup does not provide hot reload.

```bash
# From repo root
cp .env.example .env
docker compose up
```

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`

The root `data/` directory is bind-mounted into the backend container.

---

## Development environment variables

For the root Docker Compose workflow, copy `.env.example` to `.env` at the repository root:

```bash
cp .env.example .env
```

For a direct backend process started from `backend/`, `Settings(env_file=".env")` instead reads `backend/.env`. Copy the same template there and change the database to a writable host path:

```bash
cd backend
cp ../.env.example .env
mkdir -p data
# In backend/.env: DB_PATH=./data/cashflow.db
```

The development template intentionally uses insecure keys with `DEVELOPMENT_MODE=true`; never reuse those values in production.

---

## Run tests

### Backend

```bash
cd backend
python -m pytest                                          # run all tests
python -m pytest tests/test_auth.py -v                   # run one file
python -m pytest tests/test_auth.py::test_register -v    # run one test
python -m pytest --cov --cov-report=term-missing         # run with coverage
```

Tests use an in-memory SQLite database. `conftest.py` creates a fresh DB per test and overrides the `get_db` FastAPI dependency.

### Frontend

```bash
cd frontend
npm test              # run once
npm run test:watch    # watch mode
npm test -- tests/pages/TransactionsPage.test.tsx   # single file
```

Tests use Vitest + Testing Library. API calls are mocked with MSW (Mock Service Worker).
In jsdom, logout redirects still emit harmless "navigation to another Document" warnings because the browser environment is mocked.

### End-to-end tests (Playwright, manual only)

```bash
# Requires the full app running (backend + frontend)
cd e2e
npm ci
npx playwright install   # first time only
npm test
npm run test:ui          # interactive mode
```

---

## Database migrations

> **Migration ownership and target path:** FastAPI lifespan is the sole automatic migration owner and applies migrations before serving requests. Direct Alembic CLI commands resolve `DB_PATH` through the same application settings as FastAPI.
>
> Settings read `.env` from the process working directory, so commands run from `backend/` use `backend/.env`. You can export `DB_PATH` explicitly instead. Do not run a direct Alembic command or start multiple application processes concurrently against the same SQLite database.

```bash
cd backend

# Apply all pending migrations
alembic upgrade head

# Create a new migration after modifying models
alembic revision --autogenerate -m "add column foo to transactions"

# Check current migration status
alembic current

# Downgrade one step
alembic downgrade -1
```

Migration files live in `backend/alembic/versions/`. Review every generated migration before committing. Alembic does not detect every change, including some column-type changes.

---

## Project structure

```
cashflow-manager/
├── backend/                 ← FastAPI application
│   ├── app/
│   │   ├── main.py          ← App init + router registration
│   │   ├── config.py        ← Settings (Pydantic BaseSettings)
│   │   ├── database.py      ← SQLAlchemy engine + session factory
│   │   ├── deps.py          ← FastAPI dependencies
│   │   ├── models/          ← SQLAlchemy ORM models
│   │   ├── routers/         ← HTTP handlers and small endpoint-specific request models
│   │   ├── schemas/         ← Shared and domain Pydantic request/response models
│   │   └── services/        ← Business logic
│   ├── alembic/             ← Migration scripts
│   ├── tests/               ← pytest test suite
│   ├── alembic.ini
│   ├── requirements.txt     ← Production dependencies
│   └── requirements-dev.txt ← Production plus test dependencies
├── frontend/                ← React + TypeScript application
│   ├── src/
│   │   ├── api/             ← Typed API functions (one per domain)
│   │   ├── components/      ← UI components
│   │   ├── contexts/        ← React contexts (auth, onboarding)
│   │   ├── hooks/           ← React Query hooks
│   │   ├── pages/           ← Page-level components
│   │   ├── types/api.ts     ← Shared TypeScript interfaces
│   │   └── utils/           ← Formatting helpers
│   ├── package.json
│   └── vite.config.ts
├── e2e/                     ← Playwright end-to-end tests
├── deploy/                  ← Production deployment files
│   ├── docker-compose.yml   ← Single-image production setup
│   ├── .env.example         ← Production env template
│   └── data/                ← Bind-mount target for SQLite DB
├── docs/                    ← Documentation
├── .github/                 ← CI/CD workflows + Renovate config
├── Dockerfile               ← Multi-stage production build
├── docker-compose.yml       ← Development multi-service setup
├── nginx.conf               ← Nginx config (used inside production image)
├── supervisord.conf         ← Process supervisor config (prod image)
└── start.sh                 ← Container entrypoint (launches Uvicorn; lifespan runs migrations)
```

---

## Code conventions

- **Conventional PR titles** are required. CI validates the PR title (including an optional scope and `!`); squash merging uses that title as the commit message consumed by semantic-release.
  - `feat:` → minor version bump
  - `fix:` → patch version bump
  - `feat!:` or `BREAKING CHANGE:` footer → major version bump
  - `chore:`, `docs:`, `test:`, `refactor:` → no version bump
- Release notes are published with the GitHub Release; this repository does not maintain a generated `CHANGELOG.md`.

- **Backend:** Follow existing PEP 8 style; use type hints and Pydantic schemas at HTTP interfaces
- **Frontend:** TypeScript strict mode, all API responses typed via `types/api.ts`

---

## Common issues

**`alembic upgrade head` fails with "table already exists"**
The database was created outside the migration history. Delete `data/cashflow.db` only when it is a disposable development database. Back up any database that contains data you need, then inspect its schema and Alembic revision before changing it.

**Frontend shows `Network Error` on API calls**
Ensure the backend is running on port 8000 and Vite's proxy is active (run `npm run dev`, not a static build).

**`ALLOWED_ORIGINS` CORS error in browser**
In development, `ALLOWED_ORIGINS` must include `http://localhost:3000`. Check your `.env`.

**Production container reports permission denied for `cashflow.db`**
`APP_UID` and `APP_GID` in `deploy/.env` must match the owner of `deploy/data/`. Run `id -u` and `id -g`, then update both values.
