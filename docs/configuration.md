# Configuration reference

All configuration is via environment variables. In production, place them in `deploy/.env`. In development, use the root `.env` file (see `.env.example`).

---

## Required variables

These have no safe default and **must** be set in production.

| Variable | Description | How to generate |
|---|---|---|
| `SECRET_KEY` | JSON Web Token (JWT) signing key. It must contain at least 32 bytes of cryptographically random data. Rotating it signs out every user. | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `SESSION_ENCRYPTION_KEY` | Encryption key for OpenID Connect (OIDC) session cookies. It must contain 64 randomly generated hexadecimal characters (32 bytes). Rotating it invalidates every OIDC session. | `python3 -c "import secrets; print(secrets.token_hex(32))"` |

---

## Database

| Variable | Default | Description |
|---|---|---|
| `DB_PATH` | `/app/data/cashflow.db` | SQLite path used by both FastAPI and direct Alembic commands. In the container it must be writable and bind-mounted from the host. |

---

## Security and sessions

| Variable | Default | Description |
|---|---|---|
| `JWT_EXPIRE_DAYS` | `30` | JWT token lifetime in days. Users are logged out after this period. |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated list of CORS-allowed origins. In production set this to your exact domain, e.g. `https://cashflow.example.com`. |
| `COOKIE_SECURE` | Derived | Sets the `Secure` flag on authentication cookies. The default is `true`, or `false` when `DEVELOPMENT_MODE=true`. Set it to `false` only when serving plain HTTP on a non-localhost hostname. |

---

## Authentication

| Variable | Default | Description |
|---|---|---|
| `BASIC_AUTH_ENABLED` | `true` | Turns password registration (`POST /api/v1/auth/register`) and sign-in (`POST /api/v1/auth/login`) on or off. Set it to `false` for OIDC-only authentication. |
| `OIDC_ENABLED` | `false` | Turns OIDC sign-in on or off. OIDC requires the four variables below. |
| `OIDC_ISSUER_URL` | Empty | Base URL of the OIDC provider, such as `https://auth.example.com/realms/myrealm/`. Include the trailing slash. Discovery appends `.well-known/openid-configuration`. |
| `OIDC_CLIENT_ID` | Empty | Client ID registered with the OIDC provider. |
| `OIDC_CLIENT_SECRET` | Empty | Client secret. |
| `OIDC_REDIRECT_URI` | Empty | Registered callback URL for the OIDC provider. For example: `https://cashflow.example.com/api/v1/auth/oidc/callback`. The logout flow derives its absolute return URL from this origin. |

---

## Container and runtime

| Variable | Default | Description |
|---|---|---|
| `APP_UID` | `1000` | Host UID that the container process runs as. Must own `deploy/data/`. |
| `APP_GID` | `1000` | Host GID that the container process runs as. |
| `TZ` | `Europe/Rome` | Container timezone. Affects timestamp display, billing month boundaries, and recurring transaction scheduling. Use a valid TZ database name (e.g. `America/New_York`, `UTC`). |

---

## Development-only

| Variable | Default | Description |
|---|---|---|
| `DEVELOPMENT_MODE` | `false` | When `true`, bypasses the startup secret check and sets the default for `COOKIE_SECURE` to `false`. Use it only for local development with non-production secrets. |

The frontend always sends API requests to the relative `/api/v1` path. Vite proxies those requests to `http://localhost:8000` during development.

---

## Full `.env` template

See `deploy/.env.example` for the production template, or `.env.example` at the repo root for the development template.

---

## Notes

- `SECRET_KEY` and `SESSION_ENCRYPTION_KEY` are required in production. The startup guard rejects missing/template values, low-entropy values, a `SECRET_KEY` shorter than 32 bytes, and malformed `SESSION_ENCRYPTION_KEY` values. `DEVELOPMENT_MODE=true` bypasses this guard for local development only.
- You can change `BASIC_AUTH_ENABLED` and `OIDC_ENABLED` independently without losing data. The backend matches OIDC users by provider subject (`oidc_sub`) and does not link them to existing password accounts by email.
- FastAPI lifespan is the sole automatic migration owner and upgrades `DB_PATH` before serving requests. `start.sh` only launches Uvicorn. Run direct Alembic commands only when no application process is starting against the same SQLite database. Use one startup process per database.
- Changing `TZ` does not retroactively shift stored timestamps; it affects how new timestamps and billing boundaries are computed.
