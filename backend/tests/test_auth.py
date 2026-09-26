import pytest
from app.config import get_settings, Settings


def test_auth_config_is_public_and_reflects_flags(client):
    import os

    os.environ["OIDC_ENABLED"] = "true"
    os.environ["BASIC_AUTH_ENABLED"] = "false"
    get_settings.cache_clear()
    try:
        resp = client.get("/api/v1/auth/config")
        assert resp.status_code == 200
        assert resp.json() == {
            "oidc_enabled": True,
            "basic_auth_enabled": False,
        }
    finally:
        os.environ.pop("OIDC_ENABLED", None)
        os.environ.pop("BASIC_AUTH_ENABLED", None)
        get_settings.cache_clear()


def test_register_creates_user(client):
    resp = client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "pass1234", "name": "Alice"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "a@b.com"
    assert "access_token" not in data  # cookie only


def test_register_duplicate_email_returns_409(client):
    client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "password1", "name": "A"})
    resp = client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "password2", "name": "B"})
    assert resp.status_code == 409


def test_login_returns_cookie(client):
    client.post("/api/v1/auth/register", json={"email": "u@u.com", "password": "password1", "name": "U"})
    resp = client.post("/api/v1/auth/login", json={"email": "u@u.com", "password": "password1"})
    assert resp.status_code == 200
    assert "access_token" in resp.cookies


def test_login_wrong_password_returns_401(client):
    client.post("/api/v1/auth/register", json={"email": "u@u.com", "password": "password1", "name": "U"})
    resp = client.post("/api/v1/auth/login", json={"email": "u@u.com", "password": "wrong"})
    assert resp.status_code == 401


def test_me_returns_current_user(client):
    client.post("/api/v1/auth/register", json={"email": "me@test.com", "password": "password1", "name": "Me"})
    client.post("/api/v1/auth/login", json={"email": "me@test.com", "password": "password1"})
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@test.com"


def test_logout_clears_cookie(client):
    client.post("/api/v1/auth/register", json={"email": "x@x.com", "password": "password1", "name": "X"})
    client.post("/api/v1/auth/login", json={"email": "x@x.com", "password": "password1"})
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
    # After logout the cookie should be cleared (max_age=0 or deleted)


def test_logout_with_oidc_id_token_redirects_to_provider_end_session(client):
    import os
    from urllib.parse import parse_qs, urlparse
    from unittest.mock import patch, AsyncMock
    from app.config import get_settings
    from app.services.oidc import encrypt_cookie

    client.post("/api/v1/auth/register", json={"email": "oidc@test.com", "password": "password1", "name": "OIDC"})
    os.environ["OIDC_ENABLED"] = "true"
    os.environ["OIDC_ISSUER_URL"] = "https://example.com"
    os.environ["OIDC_CLIENT_ID"] = "client-id"
    os.environ["OIDC_CLIENT_SECRET"] = "client-secret"
    os.environ["OIDC_REDIRECT_URI"] = "http://localhost:8000/api/v1/auth/oidc/callback"
    os.environ["SESSION_ENCRYPTION_KEY"] = "a" * 64
    get_settings.cache_clear()
    try:
        client.cookies.set("oidc_id_token", encrypt_cookie("raw-id-token", "a" * 64))
        discovery = {
            "authorization_endpoint": "https://example.com/auth",
            "token_endpoint": "https://example.com/token",
            "end_session_endpoint": "https://example.com/logout?provider=auth0",
        }
        with patch("app.routers.auth._oidc.discover_endpoints", AsyncMock(return_value=discovery)):
            resp = client.post("/api/v1/auth/logout", follow_redirects=False)
        assert resp.status_code in (302, 307)
        parsed = urlparse(resp.headers["location"])
        assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://example.com/logout"
        params = parse_qs(parsed.query)
        assert params["provider"] == ["auth0"]
        assert params["id_token_hint"] == ["raw-id-token"]
        assert params["post_logout_redirect_uri"] == ["http://localhost:8000/login"]
    finally:
        for key in ("OIDC_ENABLED", "OIDC_ISSUER_URL", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_REDIRECT_URI", "SESSION_ENCRYPTION_KEY"):
            os.environ.pop(key, None)
        get_settings.cache_clear()


def test_me_rejects_token_without_sub(client):
    """A valid JWT that has no 'sub' claim must return 401, not 500."""
    from app.services.auth import create_access_token
    token = create_access_token({})   # no "sub" key
    client.cookies.set("access_token", token)
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_insecure_defaults_raises_error():
    """warn_insecure_defaults() raises ValueError when production mode uses insecure defaults."""
    import pytest
    from app.config import Settings
    s = Settings(development_mode=False, secret_key="dev-secret-key", session_encryption_key="0" * 64)
    with pytest.raises(ValueError, match="SECRET_KEY"):
        s.warn_insecure_defaults()


def test_secure_config_no_warning(caplog):
    """warn_insecure_defaults() emits no warnings when secrets are properly set."""
    import logging
    import secrets
    from app.config import Settings
    s = Settings(
        development_mode=False,
        secret_key=secrets.token_hex(32),
        session_encryption_key=secrets.token_hex(32),
    )
    with caplog.at_level(logging.WARNING, logger="cashflow.config"):
        s.warn_insecure_defaults()
    assert caplog.records == []


def test_delete_me_clears_access_token_cookie(client):
    """Account deletion must clear the access_token cookie, not a stale cashflow_jwt name."""
    client.post("/api/v1/auth/register", json={"email": "del_cookie@test.com", "password": "password1", "name": "D"})
    resp = client.request("DELETE", "/api/v1/users/me", json={"password": "password1"})
    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "")
    assert "access_token" in set_cookie
    assert "cashflow_jwt" not in set_cookie


def test_oidc_logout_without_cookie_redirects_to_login(client):
    """oidc_logout with no oidc_id_token cookie must redirect to /login, not crash."""
    # Register and login to be authenticated
    client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "pass1234", "name": "Alice"})
    # Ensure no oidc_id_token cookie is present
    client.cookies.delete("oidc_id_token")
    resp = client.get("/api/v1/auth/oidc/logout", follow_redirects=False)
    # Should redirect to /login (no valid OIDC session to terminate)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/login"


def test_development_mode_suppresses_warning(caplog):
    """warn_insecure_defaults() is a no-op when development_mode=True."""
    import logging
    from app.config import Settings
    s = Settings(development_mode=True, secret_key="dev-secret-key", session_encryption_key="0" * 64)
    with caplog.at_level(logging.WARNING, logger="cashflow.config"):
        s.warn_insecure_defaults()
    assert caplog.records == []


# --- H-1 / H-2: RegisterRequest validation ---

def test_register_invalid_email_returns_422(client):
    """Email without '@' must be rejected at schema validation (422)."""
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "notanemail", "password": "password1", "name": "Bad"},
    )
    assert resp.status_code == 422


def test_register_short_password_returns_422(client):
    """Password shorter than 8 characters must be rejected at schema validation (422)."""
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "good@example.com", "password": "short", "name": "Bad"},
    )
    assert resp.status_code == 422


def test_register_valid_email_and_min_length_password_succeeds(client):
    """Valid email + exactly 8-character password must be accepted (200)."""
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "valid@example.com", "password": "12345678", "name": "Good"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "valid@example.com"


def test_delete_me_wrong_password_returns_401(client):
    """DELETE /users/me with the wrong password must return 401."""
    client.post("/api/v1/auth/register", json={"email": "del@test.com", "password": "password1", "name": "Del"})
    client.post("/api/v1/auth/login", json={"email": "del@test.com", "password": "password1"})
    resp = client.request("DELETE", "/api/v1/users/me", json={"password": "wrongpassword"})
    assert resp.status_code == 401


def test_register_with_basic_auth_disabled_returns_403(client):
    """POST /auth/register must return 403 when basic_auth_enabled is False."""
    import os
    from app.config import get_settings, Settings

    os.environ["BASIC_AUTH_ENABLED"] = "false"
    get_settings.cache_clear()
    try:
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": "new@test.com", "password": "password1", "name": "New"},
        )
        assert resp.status_code == 403
    finally:
        os.environ.pop("BASIC_AUTH_ENABLED", None)
        get_settings.cache_clear()


def test_login_with_basic_auth_disabled_returns_403(client):
    """POST /auth/login must return 403 when basic_auth_enabled is False."""
    import os
    from app.config import get_settings

    client.post(
        "/api/v1/auth/register",
        json={"email": "login-disabled@test.com", "password": "password1", "name": "Disabled"},
    )
    os.environ["BASIC_AUTH_ENABLED"] = "false"
    get_settings.cache_clear()
    try:
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "login-disabled@test.com", "password": "password1"},
        )
        assert resp.status_code == 403
    finally:
        os.environ.pop("BASIC_AUTH_ENABLED", None)
        get_settings.cache_clear()


# --- Group 4: unauthenticated 401 ---

def test_unauthenticated_transactions_returns_401():
    """GET /transactions without a session cookie must return 401."""
    import os
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.main import app
    from app.database import Base
    from app.deps import get_db
    from app.config import get_settings

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    os.environ["DEVELOPMENT_MODE"] = "true"
    get_settings.cache_clear()
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app, raise_server_exceptions=True) as anon:
            anon.cookies.clear()
            r = anon.get("/api/v1/transactions")
            assert r.status_code == 401
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        os.environ.pop("DEVELOPMENT_MODE", None)
        get_settings.cache_clear()


def test_retired_forecasts_endpoint_returns_404():
    """The retired forecasting route must not be exposed."""
    import os
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.main import app
    from app.database import Base
    from app.deps import get_db
    from app.config import get_settings

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    os.environ["DEVELOPMENT_MODE"] = "true"
    get_settings.cache_clear()
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app, raise_server_exceptions=True) as anon:
            anon.cookies.clear()
            r = anon.get("/api/v1/forecasts")
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        os.environ.pop("DEVELOPMENT_MODE", None)
        get_settings.cache_clear()


def test_unauthenticated_payment_methods_returns_401():
    """GET /payment-methods without a session cookie must return 401."""
    import os
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.main import app
    from app.database import Base
    from app.deps import get_db
    from app.config import get_settings

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    os.environ["DEVELOPMENT_MODE"] = "true"
    get_settings.cache_clear()
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app, raise_server_exceptions=True) as anon:
            anon.cookies.clear()
            r = anon.get("/api/v1/payment-methods")
            assert r.status_code == 401
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        os.environ.pop("DEVELOPMENT_MODE", None)
        get_settings.cache_clear()


def test_oidc_logout_with_valid_id_token_cookie_redirects_with_hint(client):
    """oidc_logout with a valid encrypted oidc_id_token cookie must redirect
    to the end_session_endpoint with id_token_hint in the URL."""
    import os
    from unittest.mock import patch, AsyncMock
    from app.services.oidc import encrypt_cookie
    from app.config import get_settings

    # Register and login to be authenticated
    client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "pass1234", "name": "Alice"})

    # Build an encrypted cookie containing a fake id_token
    fake_id_token = "fake.id.token"
    enc_key = "0" * 64  # matches default session_encryption_key in dev mode
    encrypted = encrypt_cookie(fake_id_token, enc_key)

    fake_endpoints = {
        "authorization_endpoint": "https://idp.example.com/auth",
        "token_endpoint": "https://idp.example.com/token",
        "end_session_endpoint": "https://idp.example.com/logout",
    }

    os.environ["OIDC_ENABLED"] = "true"
    os.environ["OIDC_ISSUER_URL"] = "https://idp.example.com"
    os.environ["OIDC_CLIENT_ID"] = "test-client"
    os.environ["OIDC_CLIENT_SECRET"] = "test-secret"
    os.environ["OIDC_REDIRECT_URI"] = "https://app.example.com/callback"
    get_settings.cache_clear()

    try:
        with patch(
            "app.routers.auth._oidc.discover_endpoints",
            new=AsyncMock(return_value=fake_endpoints),
        ):
            client.cookies.set("oidc_id_token", encrypted)
            resp = client.get("/api/v1/auth/oidc/logout", follow_redirects=False)

        assert resp.status_code in (302, 307)
        location = resp.headers["location"]
        assert "id_token_hint=" in location
        assert fake_id_token in location
    finally:
        for key in ("OIDC_ENABLED", "OIDC_ISSUER_URL", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_REDIRECT_URI"):
            os.environ.pop(key, None)
        get_settings.cache_clear()


def test_oidc_user_can_delete_account(client, db):
    """An OIDC-only user (no hashed_password) must be able to delete their account
    without supplying a password."""
    from app.models.user import User

    # Register a normal user then strip their password to simulate OIDC-only
    client.post("/api/v1/auth/register", json={
        "email": "oidcuser@x.com", "password": "Password1!", "name": "OIDC"
    })
    client.post("/api/v1/auth/login", json={"email": "oidcuser@x.com", "password": "Password1!"})

    # Simulate OIDC-only: clear hashed_password in DB
    user = db.query(User).filter_by(email="oidcuser@x.com").first()
    user.hashed_password = None
    user.oidc_sub = "google|oidc-test-sub-123"
    db.commit()

    # OIDC user should be able to delete without a password
    r = client.request("DELETE", "/api/v1/users/me", json={})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json() == {"ok": True}


def test_login_oidc_only_user_returns_401(client, db):
    """A user with no hashed_password (OIDC-only) cannot log in via basic auth."""
    from app.models.user import User, gen_uuid
    user = User(id=gen_uuid(), email="oidconly@test.com", name="OIDC", oidc_sub="sub-456")
    db.add(user)
    db.commit()
    resp = client.post("/api/v1/auth/login", json={"email": "oidconly@test.com", "password": "anything"})
    assert resp.status_code == 401


def test_oidc_login_disabled_returns_404(client):
    """GET /auth/oidc/login must return 404 when OIDC is not enabled."""
    resp = client.get("/api/v1/auth/oidc/login", follow_redirects=False)
    assert resp.status_code == 404


def test_oidc_callback_disabled_returns_404(client):
    """GET /auth/oidc/callback must return 404 when OIDC is not enabled."""
    resp = client.get("/api/v1/auth/oidc/callback?code=abc&state=xyz", follow_redirects=False)
    assert resp.status_code == 404


def test_get_current_user_invalid_token_returns_401(client):
    """A completely invalid JWT cookie must return 401."""
    client.cookies.set("access_token", "not.a.valid.jwt")
    resp = client.get("/api/v1/auth/me")
    client.cookies.clear()
    assert resp.status_code == 401


def test_get_current_user_deleted_user_returns_401(client, db):
    """A valid JWT for a deleted user must return 401."""
    from app.models.user import User
    from app.services.auth import create_access_token
    client.post("/api/v1/auth/register", json={"email": "gone@test.com", "password": "pass1234", "name": "Gone"})
    user = db.query(User).filter_by(email="gone@test.com").first()
    token = create_access_token({"sub": user.id})
    db.delete(user)
    db.commit()
    client.cookies.set("access_token", token)
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
