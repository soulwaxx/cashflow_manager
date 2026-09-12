# Development Guide

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.14+ |
| Node.js | 24+ |
| npm | 10+ |
| Docker + Compose | Optional — for running the full stack containerized |

---

## Local Setup (Recommended)

Run the backend and frontend as separate processes with hot-reload.

### Backend

```bash
cd backend

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start the dev server
uvicorn app.main:app --reload --port 8000
```

The API is available at `http://localhost:8000`. Swagger UI at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend

npm install
npm run dev
```

The app is available at `http://localhost:3000`. Vite proxies `/api/*` requests to `http://localhost:8000`.

---

## Docker Compose (Alternative)

Builds and runs the backend and frontend as separate containers. No hot-reload.

```bash
# From repo root
cp .env.example .env
docker compose up
```

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`

The root `data/` directory is bind-mounted into the backend container.

---

## Environment Variables (Development)

Copy `.env.example` to `.env` at the repo root:

```bash
cp .env.example .env
```

The backend reads variables from this file. The defaults in `.env.example` are suitable for local development (insecure keys, SQLite at `/app/data/cashflow.db` — adjust `DB_PATH` if running outside Docker).

For running the backend directly (not in Docker), set:

```env
DB_PATH=./data/cashflow.db
```

---

## Running Tests

### Backend

```bash
cd backend
pytest                                          # run all tests
pytest tests/test_auth.py -v                   # run a single file
pytest tests/test_auth.py::test_register -v    # run a single test
pytest --cov --cov-report=term-missing         # with coverage
```

Tests use an in-memory SQLite database. `conftest.py` creates a fresh DB per test and overrides the `get_db` FastAPI dependency.

### Frontend

```bash
cd frontend
npm test              # run once
npm run test:watch    # watch mode
npm run test -- src/tests/transactions.test.ts   # single file
```

Tests use Vitest + Testing Library. API calls are mocked with MSW (Mock Service Worker).
In jsdom, logout redirects still emit harmless "navigation to another Document" warnings because the browser environment is mocked.

### E2E (Playwright, manual only)

```bash
# Requires the full app running (backend + frontend)
cd e2e
npx playwright install   # first time only
npx playwright test
npx playwright test --ui  # interactive mode
```

---

## Database Migrations

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

Migration files live in `backend/alembic/versions/`. Always review auto-generated migrations before committing — Alembic may not detect all changes correctly (e.g. column type changes).

---

## Project Structure

```
cashflow-manager/
├── backend/                 ← FastAPI application
│   ├── app/
│   │   ├── main.py          ← App init + router registration
│   │   ├── config.py        ← Settings (Pydantic BaseSettings)
│   │   ├── database.py      ← SQLAlchemy engine + session factory
│   │   ├── deps.py          ← FastAPI dependencies
│   │   ├── models/          ← SQLAlchemy ORM models
│   │   ├── routers/         ← HTTP route handlers
│   │   ├── schemas/         ← Pydantic request/response schemas
│   │   └── services/        ← Business logic
│   ├── alembic/             ← Migration scripts
│   ├── tests/               ← pytest test suite
│   ├── alembic.ini
│   └── requirements.txt
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
└── start.sh                 ← Container entrypoint (runs migrations then Uvicorn)
```

---

## Code Conventions

- **Conventional PR titles** are required. CI validates the PR title (including an optional scope and `!`); squash merging uses that title as the commit message consumed by semantic-release.
  - `feat:` → minor version bump
  - `fix:` → patch version bump
  - `feat!:` or `BREAKING CHANGE:` footer → major version bump
  - `chore:`, `docs:`, `test:`, `refactor:` → no version bump
- Release notes are published with the GitHub Release; this repository does not maintain a generated `CHANGELOG.md`.

- **Backend:** PEP 8, type hints on all function signatures, Pydantic schemas for all API I/O
- **Frontend:** TypeScript strict mode, all API responses typed via `types/api.ts`

---

## Common Issues

**`alembic upgrade head` fails with "table already exists"**
The DB was created before migrations were applied. Delete `data/cashflow.db` and re-run.

**Frontend shows `Network Error` on API calls**
Ensure the backend is running on port 8000 and Vite's proxy is active (run `npm run dev`, not a static build).

**`ALLOWED_ORIGINS` CORS error in browser**
In dev, `ALLOWED_ORIGINS` must include `http://localhost:3000`. Check your `.env`.

**Container permission denied on `cashflow.db`**
`APP_UID`/`APP_GID` in `deploy/.env` must match the owner of `deploy/data/`. Run `id -u && id -g` and update the values.
