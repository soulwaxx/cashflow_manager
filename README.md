# CashFlow Manager

[![CI](https://github.com/soulwaxx/cashflow_manager/actions/workflows/ci.yml/badge.svg)](https://github.com/soulwaxx/cashflow_manager/actions/workflows/ci.yml)
[![Docker](https://img.shields.io/github/v/release/soulwaxx/cashflow_manager?label=ghcr.io&logo=docker)](https://github.com/soulwaxx/cashflow_manager/pkgs/container/cashflow-manager)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

CashFlow Manager is a self-hosted, multi-user app for personal finances. It runs in one Docker container and isolates each user's data. Users sign in with a password or OpenID Connect (OIDC).

## Features

- **Transactions:** Record income, purchases, refunds, categories, payment methods, and tags.
- **Recurring transactions:** Create weekly, monthly, or yearly transactions with optional end dates.
- **Transfers:** Move money between your accounts.
- **Assets:** Track savings, investments, pensions, and property.
- **Monthly summaries:** Review bank balances, net cash flow, and category totals.
- **Analytics:** Compare spending trends and category totals over a selected period.
- **Salary and tax:** Calculate net salary under Italian personal income tax (IRPEF) and social security (INPS) rules.
- **Forecasts:** Project future bank balances from recurring commitments.
- **Onboarding:** Configure accounts, payment methods, and salary through a guided setup.
- **Responsive interface:** Use the app on desktop and mobile devices.

## Production quick start

You need Docker Engine 24 or newer and Docker Compose v2.

1. Clone the repository and enter the deployment directory.

   ```bash
   git clone https://github.com/soulwaxx/cashflow_manager.git
   cd cashflow_manager/deploy
   ```

2. Create the environment file.

   ```bash
   cp .env.example .env
   ```

3. Generate two secrets.

   ```bash
   # SECRET_KEY
   python3 -c "import secrets; print(secrets.token_hex(32))"

   # SESSION_ENCRYPTION_KEY
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```

4. Edit `.env` and set the following values:

   - Set `SECRET_KEY` and `SESSION_ENCRYPTION_KEY` to the generated values.
   - Set `APP_UID` and `APP_GID` to the output of `id -u` and `id -g`.
   - Set `ALLOWED_ORIGINS` to the public origin that serves the app.

5. Start the container.

   ```bash
   docker compose up -d
   ```

The app listens at `http://localhost`. The `deploy/data/` directory contains the SQLite database. Follow the [backup procedure](docs/deployment.md#backup-and-restore) before upgrades or maintenance.

See the [deployment guide](docs/deployment.md) for HTTPS, reverse proxies, OIDC, upgrades, and restoration.

## Architecture

```text
Single Docker container (port 8080)
├── Nginx: serves the React single-page application and proxies /api/*
└── Uvicorn: runs the FastAPI backend
        │
        └── SQLite: /app/data/cashflow.db, bind-mounted from the host
```

`supervisord` manages Nginx and Uvicorn. FastAPI applies Alembic migrations before it accepts requests.

Development runs the frontend and backend as separate services. Read [docs/architecture.md](docs/architecture.md) for the system design and data flow.

## Configuration

Copy `deploy/.env.example` to `deploy/.env` and set the deployment values.

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | Required | JWT signing key with at least 32 random bytes |
| `SESSION_ENCRYPTION_KEY` | Required | OIDC session-encryption key containing 64 hexadecimal characters |
| `APP_UID` | `1000` | Host user ID that owns `deploy/data/` |
| `APP_GID` | `1000` | Host group ID that owns `deploy/data/` |
| `DB_PATH` | `/app/data/cashflow.db` | Database path inside the container |
| `JWT_EXPIRE_DAYS` | `30` | Authentication token lifetime in days |
| `BASIC_AUTH_ENABLED` | `true` | Turns password registration and sign-in on or off |
| `OIDC_ENABLED` | `false` | Turns OIDC sign-in on or off |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated browser origins allowed by the API |
| `TZ` | `Europe/Rome` | Container time zone |

Read [docs/configuration.md](docs/configuration.md) for every setting and the required OIDC variables.

## Authentication

CashFlow Manager supports two authentication methods:

- **Password authentication:** Users register with an email address and password. The backend stores bcrypt password hashes.
- **OpenID Connect:** Users sign in through an OIDC provider such as Authentik, Auth0, or Keycloak.

You can turn on either method or both methods. CashFlow Manager matches OIDC users by provider subject and does not link accounts by email. Read [docs/authentication.md](docs/authentication.md) for provider setup and account behavior.

## Development

Create the backend environment and start Uvicorn:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --requirement requirements.txt
cp ../.env.example .env
mkdir -p data
# Set DB_PATH=./data/cashflow.db in backend/.env
uvicorn app.main:app --reload --port 8000
```

Start the frontend in a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

The frontend runs at `http://localhost:3000` and proxies `/api` to the backend at `http://localhost:8000`. FastAPI applies pending migrations during startup.

From the repository root, run the same checks as continuous integration (CI):

```bash
cd backend
python -m pytest --cov --cov-report=term-missing

cd ../frontend
npm run build
npm test -- --coverage
```

Read [docs/development.md](docs/development.md) for Docker Compose development, focused tests, migrations, and troubleshooting.

## License

[MIT](LICENSE)
