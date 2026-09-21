# Authentication

CashFlow Manager supports password authentication and OpenID Connect (OIDC). You can configure each method independently or use both methods.

---

## Password authentication

Password authentication is active when `BASIC_AUTH_ENABLED=true` (the default).

### Registration

`POST /api/v1/auth/register` is a public endpoint.

```json
{ "email": "user@example.com", "password": "secret" }
```

A successful request returns `200` and sets an `access_token` cookie with the `HttpOnly` attribute. A duplicate email returns `409`.

### Sign in

`POST /api/v1/auth/login`

```json
{ "email": "user@example.com", "password": "secret" }
```

A successful request returns `200` and sets the `access_token` cookie. Invalid credentials return `401`. Setting `BASIC_AUTH_ENABLED=false` makes the endpoint return `403`.

### Password storage

The backend stores passwords as bcrypt hashes with random salts. It does not store or log plaintext passwords.

### Change password

`PUT /api/v1/users/me/password`

```json
{ "current_password": "old-secret", "new_password": "new-secret" }
```

Requires the authenticated user to supply their current password. Returns:
- `200 {"ok": true}` on success
- `401` if `current_password` is wrong
- `422` if `new_password` is shorter than 8 characters
- `400` if the account is OIDC-only (no password to change)

The "Change password" button in **Settings → Account** is visible only to users who have `has_password: true`.

### Current user

`GET /api/v1/auth/me` returns the authenticated user.

The response includes `has_password` and `has_oidc` fields. See [UserOut fields](#userout-fields).

### Public auth config

`GET /api/v1/auth/config` is a public endpoint. The login page uses it to determine which sign-in methods are active.

Response:

```json
{ "oidc_enabled": true, "basic_auth_enabled": true }
```

### Disabling

Setting `BASIC_AUTH_ENABLED=false` disables both `/register` and `/login`. OIDC sign-in remains active when configured. Password users cannot sign in again until you set `BASIC_AUTH_ENABLED=true`.

---

## OIDC

Set `OIDC_ENABLED=true` to activate OIDC. This method requires a configured OIDC provider.

### Required environment variables

```env
OIDC_ENABLED=true
OIDC_ISSUER_URL=https://auth.example.com/realms/myrealm/
OIDC_CLIENT_ID=cashflow
OIDC_CLIENT_SECRET=<client-secret>
OIDC_REDIRECT_URI=https://cashflow.example.com/api/v1/auth/oidc/callback
```

### Provider setup

Register a confidential client in your OIDC provider with:

- **Redirect URI:** `https://cashflow.example.com/api/v1/auth/oidc/callback`
- **Scopes:** `openid email profile`
- **Grant type:** Authorization Code

The application discovers provider endpoints automatically from `{OIDC_ISSUER_URL}/.well-known/openid-configuration`.

### Sign-in flow

The sign-in page reads `GET /api/v1/auth/config` and shows the single sign-on (SSO) entry point when `oidc_enabled=true`. When `basic_auth_enabled=false`, it hides the password form and states that password sign-in is disabled.

1. The user selects **Sign in with SSO**.
2. The browser requests `GET /api/v1/auth/oidc/login` and redirects to the provider authorization endpoint.
3. The user authenticates with the provider.
4. The provider sends an authorization code to `OIDC_REDIRECT_URI`.
5. The backend exchanges the code for tokens, validates the ID token, and matches the user by `oidc_sub`. It creates a user when the provider subject does not match an existing account.
6. The backend sets two cookies with the `HttpOnly` attribute:
   - `access_token`: JSON Web Token (JWT) used for application authentication
   - `oidc_id_token`: encrypted raw ID token used for provider logout

### Logout flow

Two logout entrypoints exist:

- `POST /api/v1/auth/logout`: General logout endpoint used by API clients
- `GET /api/v1/auth/oidc/logout`: Browser redirect entry point

Both endpoints clear the `access_token` and `oidc_id_token` cookies. When the provider advertises `end_session_endpoint` and the encrypted `oidc_id_token` cookie is present, the backend redirects to the provider with `id_token_hint` and `post_logout_redirect_uri`. Otherwise, it performs a local sign-out.

The backend builds the logout redirect from `OIDC_REDIRECT_URI`. It derives an absolute `/login` return URL from the callback origin, preserves existing query parameters on `end_session_endpoint`, and percent-encodes the added parameters. Failed endpoint discovery, token decryption, or redirect construction also results in a local sign-out.

---

## Account matching

Accounts are linked by OIDC subject (`oidc_sub`), not by email.

The backend does not link an incoming OIDC login to an existing password account that shares the same email. This prevents account takeover through an identity-provider-controlled email claim.

If the OIDC provider returns a verified email and that email is not already used by another account, it is stored on the OIDC user row. If the email is missing, unverified, or already claimed by another user, the account is still created and identified only by `oidc_sub`.

---

## JWT

- `HttpOnly` cookie named `access_token`
- HS256 signature created with `SECRET_KEY`
- Expiry set by `JWT_EXPIRE_DAYS` (default: 30 days)
- No refresh token. The user signs in again after expiry.
- All authenticated endpoints read the cookie automatically; the frontend never handles the token directly

---

## UserOut fields

`UserOut` is returned by `/auth/register`, `/auth/login`, and `/auth/me`. In addition to `id`, `email`, and `name`, it includes:

| Field | Type | Description |
|---|---|---|
| `has_password` | `bool` | Whether the user has a password. |
| `has_oidc` | `bool` | Whether the user has an OIDC link (`oidc_sub` is set). |

These fields control frontend behavior, including whether account deletion requires a password prompt.

---

## Account deletion

`DELETE /api/v1/users/me`

Permanently deletes the authenticated user's account and all associated data.

- **Request body (JSON):** `{"password": "<current_password>"}` for password accounts, or `{}` for OIDC-only accounts
- Returns `401` if a password account supplies an incorrect or missing password
- On success: clears the `access_token` and `oidc_id_token` cookies and returns `{"ok": true}`

**OIDC-only users** (no password set) must supply an empty `{}` body (the field is optional). They are exempt from the password check.

---

## No administrator role

All authenticated users have equal access to their own data. Access control is purely by ownership (`user_id`). There is no separate administrator concept.

---

## Common provider examples

### Authentik

```env
OIDC_ISSUER_URL=https://authentik.example.com/application/o/cashflow/
OIDC_CLIENT_ID=cashflow
OIDC_CLIENT_SECRET=<secret>
OIDC_REDIRECT_URI=https://cashflow.example.com/api/v1/auth/oidc/callback
```

Create an OAuth2/OIDC provider in Authentik pointing to the redirect URI above, with scopes `openid email profile`.

### Keycloak

```env
OIDC_ISSUER_URL=https://keycloak.example.com/realms/myrealm/
OIDC_CLIENT_ID=cashflow
OIDC_CLIENT_SECRET=<secret>
OIDC_REDIRECT_URI=https://cashflow.example.com/api/v1/auth/oidc/callback
```

Create a confidential client in the realm with the redirect URI and scopes `openid email profile`.

### Auth0

```env
OIDC_ISSUER_URL=https://your-tenant.auth0.com/
OIDC_CLIENT_ID=<client-id>
OIDC_CLIENT_SECRET=<client-secret>
OIDC_REDIRECT_URI=https://cashflow.example.com/api/v1/auth/oidc/callback
```

Add the redirect URI to the allowed callback URLs in the Auth0 application settings.
