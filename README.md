# CashFlow Manager

[![CI](https://github.com/soulwaxx/cashflow_manager/actions/workflows/ci.yml/badge.svg)](https://github.com/soulwaxx/cashflow_manager/actions/workflows/ci.yml)
[![Docker](https://img.shields.io/github/v/release/soulwaxx/cashflow_manager?label=ghcr.io&logo=docker)](https://github.com/soulwaxx/cashflow_manager/pkgs/container/cashflow-manager)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A self-hosted personal cash flow manager. Track transactions, transfers, recurring expenses, salary, assets, and monthly forecasts — all in a single Docker container.

Multi-user with per-user data isolation. Supports both local (username/password) and OIDC authentication.

---

## Features

- **Transaction tracking** — income and expenses with categories, payment methods, and tags
- **Recurring transactions** — weekly, monthly, yearly with configurable end dates
- **Transfers** — move money between your own accounts
- **Asset tracking** — track value of savings, investments, and property
- **Monthly summary** — bank balance, net cashflow, category breakdown
- **Analytics** — spending trends, category charts, time-range filters
- **Salary & tax calculator** — Italian tax law (IRPEF + INPS), net-from-gross calculation
- **Forecasting** — project future bank balance based on recurring commitments
- **Onboarding wizard** — guided setup for accounts, payment methods, and salary
- **Multi-user** — each user sees only their own data
- **OIDC support** — integrate with any OIDC provider (Keycloak, Auth0, Authentik, etc.)
- **Responsive** — works on desktop and mobile

---

## Quick Start (Production)

The production image bundles the React frontend (served by Nginx) and the FastAPI backend (Uvicorn) in a single container.

```bash
# 1. Clone the deploy directory (or just copy these two files)
git clone https://github.com/soulwaxx/cashflow_manager.git
cd cashflow_manager/deploy

# 2. Create your environment file from the template
cp .env.example .env

# 3. Generate secrets and edit .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"   # SESSION_ENCRYPTION_KEY
#   Also set APP_UID/APP_GID to your host user (run: id -u && id -g)

# 4. Start
docker compose up -d

# App is now available at http://localhost:80
```

The `data/` directory next to `docker-compose.yml` holds the SQLite database — back it up to preserve your data.

See [docs/deployment.md](docs/deployment.md) for reverse proxy setup, OIDC configuration, and upgrade instructions.

---

## Architecture

```
Single Docker container (port 8080)
├── Nginx          — serves React SPA, proxies /api/* to Uvicorn
└── Uvicorn        — FastAPI backend
        │
        └── SQLite  (/app/data/cashflow.db, bind-mounted from host)
```

Nginx and Uvicorn are managed by `supervisord` inside the container. On startup, Alembic migrations run automatically before the API becomes available.

For local development, the frontend and backend run as separate services with hot-reload. See [docs/development.md](docs/development.md).

Full architecture details: [docs/architecture.md](docs/architecture.md).

---

## Configuration

All configuration is via environment variables. Copy `deploy/.env.example` to `deploy/.env` and edit:

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | — | **Required.** JWT signing key (32+ random bytes) |
| `SESSION_ENCRYPTION_KEY` | — | **Required.** AES-GCM key for OIDC session cookies (32 random bytes as hex) |
| `APP_UID` / `APP_GID` | `1000` | Host UID/GID that owns the `data/` directory |
| `DB_PATH` | `/app/data/cashflow.db` | Path inside container |
| `JWT_EXPIRE_DAYS` | `30` | Token lifetime |
| `BASIC_AUTH_ENABLED` | `true` | Enable username/password registration and login |
| `OIDC_ENABLED` | `false` | Enable OIDC login |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS allowed origins (comma-separated) |
| `TZ` | `Europe/Rome` | Container timezone |

Full reference with OIDC variables: [docs/configuration.md](docs/configuration.md).

---

## Authentication

Two modes, independently configurable:

- **Basic auth** — self-registration with email + password, bcrypt-hashed
- **OIDC** — any OIDC-compliant provider; users are matched by provider subject (`oidc_sub`) and are not auto-linked to existing password accounts by email

Both can be active simultaneously. See [docs/authentication.md](docs/authentication.md).

---

## Development

Prerequisites: Python 3.14+, Node 24+, Docker (optional).

```bash
# Backend
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev          # Vite dev server at http://localhost:3000

# Or run both via Docker Compose (separate containers, hot-reload not available)
docker compose up
```

Run tests:

```bash
# Backend
cd backend && pytest

# Frontend
cd frontend && npm test
```

Full guide: [docs/development.md](docs/development.md).

---

## Deployment

See [docs/deployment.md](docs/deployment.md) for:

- Production checklist
- Reverse proxy (Nginx/Caddy/Traefik) examples
- HTTPS/TLS setup
- Upgrading to a new version
- Backup and restore

---

## License

[MIT](LICENSE)
