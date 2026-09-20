# Configuration Reference

All configuration is via environment variables. In production, place them in `deploy/.env`. In development, use the root `.env` file (see `.env.example`).

---

## Required Variables

These have no safe default and **must** be set in production.

| Variable | Description | How to generate |
|---|---|---|
| `SECRET_KEY` | JWT signing key. Must contain at least 32 bytes of cryptographically random data; rotating it logs all users out. | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `SESSION_ENCRYPTION_KEY` | AES-GCM key for encrypting OIDC `id_token` cookies. Must be 64 hexadecimal characters (32 bytes) generated randomly; rotating it invalidates all OIDC sessions. | `python3 -c "import secrets; print(secrets.token_hex(32))"` |

---

## Database

| Variable | Default | Description |
|---|---|---|
| `DB_PATH` | `/app/data/cashflow.db` | SQLite path used by both FastAPI and direct Alembic commands. In the container it must be writable and bind-mounted from the host. |

---

## Security & Sessions

| Variable | Default | Description |
|---|---|---|
| `JWT_EXPIRE_DAYS` | `30` | JWT token lifetime in days. Users are logged out after this period. |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated list of CORS-allowed origins. In production set to your exact domain, e.g. `https://cashflow.example.com`. |

---

## Authentication

| Variable | Default | Description |
|---|---|---|
| `BASIC_AUTH_ENABLED` | `true` | Enable username/password registration (`POST /api/v1/auth/register`) and login (`POST /api/v1/auth/login`). Set to `false` to disable password auth entirely or force OIDC-only. |
| `OIDC_ENABLED` | `false` | Enable OIDC login. Requires the four `OIDC_*` variables below. |
| `OIDC_ISSUER_URL` | — | Base URL of the OIDC provider, e.g. `https://auth.example.com/realms/myrealm/`. Must include trailing slash. Used for OIDC discovery (appends `.well-known/openid-configuration`). |
| `OIDC_CLIENT_ID` | — | Client ID registered with the OIDC provider. |
| `OIDC_CLIENT_SECRET` | — | Client secret. |
| `OIDC_REDIRECT_URI` | — | Callback URL that the OIDC provider redirects to after authentication. Must be registered with the provider. Example: `https://cashflow.example.com/api/v1/auth/oidc/callback`. The logout flow also uses this value to derive the absolute post-logout return target (typically `/login` on the same origin). |

---

## Container & Runtime

| Variable | Default | Description |
|---|---|---|
| `APP_UID` | `1000` | Host UID that the container process runs as. Must own `deploy/data/`. |
| `APP_GID` | `1000` | Host GID that the container process runs as. |
| `TZ` | `Europe/Rome` | Container timezone. Affects timestamp display, billing month boundaries, and recurring transaction scheduling. Use a valid TZ database name (e.g. `America/New_York`, `UTC`). |

---

## Development-only

These variables are read by Vite during the frontend build and are not used at runtime.

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | — | API base URL for the frontend. Only needed when running Vite's dev server against a remote backend. In production the Nginx proxy makes this unnecessary. |
| `DEVELOPMENT_MODE` | `false` | When `true`, bypasses the startup insecure-defaults check and sets `COOKIE_SECURE` default to `false`. Required for local development when using non-production `SECRET_KEY`/`SESSION_ENCRYPTION_KEY`. |
| `COOKIE_SECURE` | derived | When `true`, sets the `Secure` flag on the auth cookie (browser only sends it over HTTPS). Defaults to `true` unless `DEVELOPMENT_MODE=true`. Set to `false` when serving over plain HTTP on a non-localhost hostname (e.g. a Tailscale/LAN hostname). |

---

## Full `.env` Template

See `deploy/.env.example` for the production template, or `.env.example` at the repo root for the development template.

---

## Notes

- `SECRET_KEY` and `SESSION_ENCRYPTION_KEY` are required in production. The startup guard rejects missing/template values, low-entropy values, a `SECRET_KEY` shorter than 32 bytes, and malformed `SESSION_ENCRYPTION_KEY` values. `DEVELOPMENT_MODE=true` bypasses this guard for local development only.
- `BASIC_AUTH_ENABLED` and `OIDC_ENABLED` can be toggled independently without data loss. OIDC users are matched by provider subject (`oidc_sub`); the backend does not auto-link them to an existing password-auth account by shared email.
- FastAPI lifespan is the sole automatic migration owner and upgrades `DB_PATH` before serving requests. `start.sh` only launches Uvicorn. Direct Alembic commands use the same settings and may be run only when no other app process is starting against that SQLite database; deploy a single startup process per database to avoid concurrent SQLite migration attempts.
- Changing `TZ` does not retroactively shift stored timestamps; it affects how new timestamps and billing boundaries are computed.
