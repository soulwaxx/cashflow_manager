import pytest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import Base
from app.deps import get_db
from app.config import get_settings


@pytest.fixture()
def oidc_client(monkeypatch):
    monkeypatch.setenv("DEVELOPMENT_MODE", "true")
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://example.com/")
    monkeypatch.setenv("OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "http://localhost:8000/api/v1/auth/oidc/callback")
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("SECRET_KEY", "oidc-test-secret-key-with-at-least-32-bytes")
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app, raise_server_exceptions=False, follow_redirects=False) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def test_oidc_login_redirects(oidc_client):
    discovery = {
        "authorization_endpoint": "https://example.com/auth",
        "token_endpoint": "https://example.com/token",
        "end_session_endpoint": "https://example.com/logout",
    }
    with patch("app.services.oidc.discover_endpoints", return_value=discovery):
        resp = oidc_client.get("/api/v1/auth/oidc/login")
    assert resp.status_code in (302, 307)
    parsed = urlparse(resp.headers["location"])
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://example.com/auth"
    params = parse_qs(parsed.query)
    assert params["response_type"] == ["code"]
    assert params["client_id"] == ["client-id"]
    assert params["redirect_uri"] == ["http://localhost:8000/api/v1/auth/oidc/callback"]
    assert params["scope"] == ["openid email profile"]
    assert "state" in params and params["state"][0]
    assert "nonce" in params and params["nonce"][0]
    assert oidc_client.cookies.get("oidc_state")
    assert oidc_client.cookies.get("oidc_nonce")


def test_oidc_login_respects_cookie_secure_override(oidc_client, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "true")
    get_settings.cache_clear()
    discovery = {
        "authorization_endpoint": "https://example.com/auth",
        "token_endpoint": "https://example.com/token",
        "end_session_endpoint": "https://example.com/logout",
    }
    with patch("app.services.oidc.discover_endpoints", return_value=discovery):
        resp = oidc_client.get("/api/v1/auth/oidc/login")

    set_cookie_headers = resp.headers.get_list("set-cookie")
    assert any("oidc_state=" in h and "Secure" in h for h in set_cookie_headers)
    assert any("oidc_nonce=" in h and "Secure" in h for h in set_cookie_headers)


def test_oidc_logout_reads_id_token_from_cookie(oidc_client):
    """oidc_id_token must be read from the cookie jar, not as a URL query parameter."""
    from unittest.mock import patch
    # Register and login to be authenticated
    oidc_client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "pass1234", "name": "Alice"})
    discovery = {
        "authorization_endpoint": "https://example.com/auth",
        "token_endpoint": "https://example.com/token",
        "end_session_endpoint": "https://example.com/end-session?logout_hint=keep-me",
    }
    from app.services.oidc import encrypt_cookie
    encrypted = encrypt_cookie("raw id/token+?", "a" * 64)
    oidc_client.cookies.set("oidc_id_token", encrypted)
    with patch("app.services.oidc.discover_endpoints", return_value=discovery):
        resp = oidc_client.get("/api/v1/auth/oidc/logout")
    oidc_client.cookies.delete("oidc_id_token")
    # Should redirect to end_session_endpoint with id_token_hint
    assert resp.status_code in (302, 307)
    parsed = urlparse(resp.headers["location"])
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://example.com/end-session"
    params = parse_qs(parsed.query)
    assert params["logout_hint"] == ["keep-me"]
    assert params["id_token_hint"] == ["raw id/token+?"]
    assert params["post_logout_redirect_uri"] == ["http://localhost:8000/login"]


def test_aes_encrypt_decrypt_roundtrip():
    from app.services.oidc import encrypt_cookie, decrypt_cookie
    plaintext = "my-id-token"
    enc = encrypt_cookie(plaintext, "a" * 64)
    dec = decrypt_cookie(enc, "a" * 64)
    assert dec == plaintext


def test_decrypt_cookie_returns_none_on_bad_input():
    """decrypt_cookie must return None (not raise) when the ciphertext is invalid."""
    from app.services.oidc import decrypt_cookie
    assert decrypt_cookie("not-valid-ciphertext!!", "a" * 64) is None


def test_verify_id_token_uses_jwks_audience_and_issuer_validation():
    """ID token verification must validate with provider JWKS, client audience, and issuer."""
    from app.services.oidc import verify_id_token

    signing_key = MagicMock()
    signing_key.key = "public-key"
    jwks_client = MagicMock()
    jwks_client.get_signing_key_from_jwt.return_value = signing_key
    claims = {"sub": "subject-1", "email": "user@example.com"}

    with patch("app.services.oidc.PyJWKClient", return_value=jwks_client) as jwks, \
         patch("app.services.oidc.pyjwt.decode", return_value=claims) as decode:
        result = verify_id_token(
            "id-token",
            "https://example.com/jwks",
            "client-id",
            "https://example.com/",
        )

    jwks.assert_called_once_with("https://example.com/jwks")
    jwks_client.get_signing_key_from_jwt.assert_called_once_with("id-token")
    decode.assert_called_once_with(
        "id-token",
        "public-key",
        algorithms=["RS256", "ES256"],
        audience="client-id",
        issuer="https://example.com/",
    )
    assert result == claims


def test_oidc_callback_state_mismatch_returns_400(oidc_client):
    """callback with no oidc_state cookie must reject with 400."""
    resp = oidc_client.get("/api/v1/auth/oidc/callback?code=abc&state=wrongstate")
    assert resp.status_code == 400


def test_oidc_callback_creates_new_user(oidc_client):
    """Successful OIDC callback must create the user and redirect to /."""
    from unittest.mock import patch, AsyncMock
    discovery = {
        "authorization_endpoint": "https://example.com/auth",
        "token_endpoint": "https://example.com/token",
        "userinfo_endpoint": "https://example.com/userinfo",
        "end_session_endpoint": "https://example.com/logout",
        "jwks_uri": "https://example.com/jwks",
        "issuer": "https://example.com/",
    }
    tokens = {"access_token": "at-123", "id_token": "it-abc"}
    userinfo = {"sub": "sub-new-user", "email": "oidcnew@example.com", "name": "New User", "email_verified": True}
    id_token_claims = {"nonce": "test-nonce", "sub": "sub-new-user"}

    oidc_client.cookies.set("oidc_state", "test-state-value")
    oidc_client.cookies.set("oidc_nonce", "test-nonce")
    with patch("app.services.oidc.discover_endpoints", AsyncMock(return_value=discovery)), \
         patch("app.services.oidc.exchange_code", AsyncMock(return_value=tokens)), \
         patch("app.services.oidc.get_userinfo", AsyncMock(return_value=userinfo)), \
         patch("app.services.oidc.verify_id_token", return_value=id_token_claims) as verify:
        resp = oidc_client.get("/api/v1/auth/oidc/callback?code=abc&state=test-state-value")
    oidc_client.cookies.delete("oidc_state")
    oidc_client.cookies.delete("oidc_nonce")

    assert resp.status_code in (200, 302, 307)
    verify.assert_called_once_with(
        "it-abc",
        "https://example.com/jwks",
        "client-id",
        "https://example.com/",
    )
    assert oidc_client.cookies.get("access_token")
    assert oidc_client.cookies.get("oidc_id_token")
    assert oidc_client.cookies.get("oidc_state") is None
    assert oidc_client.cookies.get("oidc_nonce") is None


def test_oidc_callback_rejects_id_token_subject_mismatch(oidc_client):
    """UserInfo subject must match the verified ID token subject."""
    from unittest.mock import patch, AsyncMock

    discovery = {
        "authorization_endpoint": "https://example.com/auth",
        "token_endpoint": "https://example.com/token",
        "userinfo_endpoint": "https://example.com/userinfo",
        "jwks_uri": "https://example.com/jwks",
        "issuer": "https://example.com/",
    }
    tokens = {"access_token": "at-sub", "id_token": "it-sub"}
    userinfo = {
        "sub": "userinfo-sub",
        "email": "subject@example.com",
        "name": "Subject",
        "email_verified": True,
    }

    oidc_client.cookies.set("oidc_state", "subject-state")
    oidc_client.cookies.set("oidc_nonce", "nonce")
    with patch("app.services.oidc.discover_endpoints", AsyncMock(return_value=discovery)), \
         patch("app.services.oidc.exchange_code", AsyncMock(return_value=tokens)), \
         patch("app.services.oidc.get_userinfo", AsyncMock(return_value=userinfo)), \
         patch(
             "app.services.oidc.verify_id_token",
             return_value={"sub": "id-token-sub", "nonce": "nonce"},
         ):
        resp = oidc_client.get("/api/v1/auth/oidc/callback?code=abc&state=subject-state")
    oidc_client.cookies.delete("oidc_state")
    oidc_client.cookies.delete("oidc_nonce")

    assert resp.status_code == 400
    assert resp.json()["detail"] == "OIDC subject mismatch"


def test_oidc_callback_does_not_link_to_existing_email_user(oidc_client):
    """Callback must NOT attach oidc_sub to a pre-existing password-auth account (account-takeover prevention)."""
    from unittest.mock import patch, AsyncMock
    from app.models.user import User as UserModel

    # Pre-seed a password-auth user (oidc_sub will be None)
    reg_resp = oidc_client.post(
        "/api/v1/auth/register",
        json={"email": "link@example.com", "password": "pass1234", "name": "Link"},
    )
    assert reg_resp.status_code == 200
    original_user_id = reg_resp.json()["id"]

    discovery = {
        "authorization_endpoint": "https://example.com/auth",
        "token_endpoint": "https://example.com/token",
        "userinfo_endpoint": "https://example.com/userinfo",
    }
    tokens = {"access_token": "at-xyz"}
    # Same email as registered above — provider returns email_verified: True
    userinfo = {"sub": "sub-link-new", "email": "link@example.com", "name": "Link", "email_verified": True}

    oidc_client.cookies.set("oidc_state", "link-state")
    # No id_token in tokens so nonce check is skipped
    with patch("app.services.oidc.discover_endpoints", AsyncMock(return_value=discovery)), \
         patch("app.services.oidc.exchange_code", AsyncMock(return_value=tokens)), \
         patch("app.services.oidc.get_userinfo", AsyncMock(return_value=userinfo)):
        resp = oidc_client.get("/api/v1/auth/oidc/callback?code=code&state=link-state")
    oidc_client.cookies.delete("oidc_state")

    # The callback should succeed (new OIDC user created, email set to None due to collision)
    assert resp.status_code in (200, 302, 307)

    # The original password-auth user must NOT have gained an oidc_sub
    login_resp = oidc_client.post(
        "/api/v1/auth/login",
        json={"email": "link@example.com", "password": "pass1234"},
    )
    assert login_resp.status_code == 200
    me_resp = oidc_client.get("/api/v1/auth/me")
    assert me_resp.json()["id"] == original_user_id
    assert me_resp.json()["has_oidc"] is False


def test_oidc_callback_rejects_unverified_email(oidc_client):
    """When email_verified is False the created user must have email=None."""
    from unittest.mock import patch, AsyncMock
    from app.models.user import User as UserModel
    from app.deps import get_db as _get_db
    from app.main import app as _app

    discovery = {
        "authorization_endpoint": "https://example.com/auth",
        "token_endpoint": "https://example.com/token",
        "userinfo_endpoint": "https://example.com/userinfo",
    }
    tokens = {"access_token": "at-unverified"}
    userinfo = {"sub": "sub-unverified", "email": "unverified@example.com", "name": "Unverified", "email_verified": False}

    oidc_client.cookies.set("oidc_state", "unverified-state")
    with patch("app.services.oidc.discover_endpoints", AsyncMock(return_value=discovery)), \
         patch("app.services.oidc.exchange_code", AsyncMock(return_value=tokens)), \
         patch("app.services.oidc.get_userinfo", AsyncMock(return_value=userinfo)):
        resp = oidc_client.get("/api/v1/auth/oidc/callback?code=abc&state=unverified-state")
    oidc_client.cookies.delete("oidc_state")

    assert resp.status_code in (200, 302, 307)

    # Verify the created OIDC user has no email by querying via the DB override
    db_gen = _app.dependency_overrides[_get_db]()
    db = next(db_gen)
    try:
        oidc_user = db.query(UserModel).filter_by(oidc_sub="sub-unverified").first()
        assert oidc_user is not None
        assert oidc_user.email is None
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


def test_oidc_callback_invalid_nonce_rejected(oidc_client):
    """Callback with a nonce mismatch between cookie and ID token must return 400."""
    from unittest.mock import patch, AsyncMock

    discovery = {
        "authorization_endpoint": "https://example.com/auth",
        "token_endpoint": "https://example.com/token",
        "userinfo_endpoint": "https://example.com/userinfo",
        "jwks_uri": "https://example.com/jwks",
        "issuer": "https://example.com/",
    }
    tokens = {"access_token": "at-nonce", "id_token": "it-nonce"}
    userinfo = {"sub": "sub-nonce", "email": "nonce@example.com", "name": "Nonce", "email_verified": True}

    oidc_client.cookies.set("oidc_state", "nonce-state")
    oidc_client.cookies.set("oidc_nonce", "correct-nonce")
    with patch("app.services.oidc.discover_endpoints", AsyncMock(return_value=discovery)), \
         patch("app.services.oidc.exchange_code", AsyncMock(return_value=tokens)), \
         patch("app.services.oidc.get_userinfo", AsyncMock(return_value=userinfo)), \
         patch(
             "app.services.oidc.verify_id_token",
             return_value={"sub": "sub-nonce", "nonce": "wrong-nonce"},
         ):
        resp = oidc_client.get("/api/v1/auth/oidc/callback?code=abc&state=nonce-state")
    oidc_client.cookies.delete("oidc_state")
    oidc_client.cookies.delete("oidc_nonce")

    assert resp.status_code == 400


def test_oidc_callback_missing_nonce_cookie_with_id_token_rejected(oidc_client):
    """If an ID token is returned, the nonce cookie must be present and match."""
    from unittest.mock import patch, AsyncMock

    discovery = {
        "authorization_endpoint": "https://example.com/auth",
        "token_endpoint": "https://example.com/token",
        "userinfo_endpoint": "https://example.com/userinfo",
        "jwks_uri": "https://example.com/jwks",
        "issuer": "https://example.com/",
    }
    tokens = {"access_token": "at-nonce", "id_token": "it-nonce"}
    userinfo = {"sub": "sub-nonce", "email": "nonce@example.com", "name": "Nonce", "email_verified": True}

    oidc_client.cookies.set("oidc_state", "nonce-state")
    oidc_client.cookies.delete("oidc_nonce")
    with patch("app.services.oidc.discover_endpoints", AsyncMock(return_value=discovery)), \
         patch("app.services.oidc.exchange_code", AsyncMock(return_value=tokens)), \
         patch("app.services.oidc.get_userinfo", AsyncMock(return_value=userinfo)), \
         patch("app.services.oidc.verify_id_token", return_value={"sub": "sub-nonce", "nonce": "nonce"}):
        resp = oidc_client.get("/api/v1/auth/oidc/callback?code=abc&state=nonce-state")
    oidc_client.cookies.delete("oidc_state")

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid nonce"


def test_oidc_logout_corrupted_cookie_redirects_to_login(oidc_client):
    """oidc_logout with an undecryptable cookie must redirect to /login."""
    from unittest.mock import patch, AsyncMock
    # Register and login to be authenticated
    oidc_client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "pass1234", "name": "Alice"})
    discovery = {"end_session_endpoint": "https://example.com/logout"}
    oidc_client.cookies.set("oidc_id_token", "totally-corrupt-value")
    with patch("app.services.oidc.discover_endpoints", AsyncMock(return_value=discovery)):
        resp = oidc_client.get("/api/v1/auth/oidc/logout")
    oidc_client.cookies.delete("oidc_id_token")
    assert resp.status_code in (302, 307)
    assert "/login" in resp.headers["location"]
    assert oidc_client.cookies.get("access_token") is None
    assert oidc_client.cookies.get("oidc_id_token") is None


def test_oidc_logout_discover_exception_redirects_to_login(oidc_client):
    """oidc_logout must fall back to /login redirect when discover_endpoints raises."""
    from unittest.mock import patch, AsyncMock
    from app.services.oidc import encrypt_cookie
    # Register and login to be authenticated
    oidc_client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "pass1234", "name": "Alice"})
    encrypted = encrypt_cookie("id-token", "a" * 64)
    oidc_client.cookies.set("oidc_id_token", encrypted)
    with patch("app.services.oidc.discover_endpoints", AsyncMock(side_effect=Exception("network"))):
        resp = oidc_client.get("/api/v1/auth/oidc/logout")
    oidc_client.cookies.delete("oidc_id_token")
    assert resp.status_code in (302, 307)
    assert "/login" in resp.headers["location"]


def test_discover_endpoints_calls_well_known_url():
    """discover_endpoints must GET /.well-known/openid-configuration."""
    import asyncio
    from unittest.mock import patch, AsyncMock, MagicMock
    from app.services.oidc import discover_endpoints

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"authorization_endpoint": "https://idp/auth"}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.services.oidc.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
        result = asyncio.run(discover_endpoints("https://idp.example.com/"))

    mock_client.get.assert_called_once_with(
        "https://idp.example.com/.well-known/openid-configuration", timeout=10
    )
    assert result["authorization_endpoint"] == "https://idp/auth"


def test_exchange_code_posts_to_token_endpoint():
    """exchange_code must POST the authorization_code grant to the token endpoint."""
    import asyncio
    from unittest.mock import patch, AsyncMock, MagicMock
    from app.services.oidc import exchange_code

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"access_token": "at-xyz", "id_token": "it-abc"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("app.services.oidc.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
        result = asyncio.run(
            exchange_code("code123", "https://idp/token", "https://app/cb", "cid", "csecret")
        )

    assert result["access_token"] == "at-xyz"
    mock_client.post.assert_called_once()


def test_get_userinfo_calls_userinfo_endpoint():
    """get_userinfo must GET the userinfo endpoint with a Bearer token."""
    import asyncio
    from unittest.mock import patch, AsyncMock, MagicMock
    from app.services.oidc import get_userinfo

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"sub": "u1", "email": "u@example.com"}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.services.oidc.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
        result = asyncio.run(get_userinfo("https://idp/userinfo", "at-token"))

    mock_client.get.assert_called_once_with(
        "https://idp/userinfo",
        headers={"Authorization": "Bearer at-token"},
        timeout=10,
    )
    assert result["sub"] == "u1"


def test_oidc_logout_requires_auth(client):
    """OIDC logout must reject unauthenticated requests with 401.
    Uses client (not oidc_client) because oidc_logout enforces auth
    regardless of whether OIDC is enabled — get_current_user fires first.
    """
    r = client.get("/api/v1/auth/oidc/logout")
    assert r.status_code == 401
