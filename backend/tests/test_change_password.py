import pytest


def test_change_password_success(client):
    client.post("/api/v1/auth/register", json={"email": "pw@test.com", "password": "password1", "name": "PW"})
    client.post("/api/v1/auth/login", json={"email": "pw@test.com", "password": "password1"})
    resp = client.put("/api/v1/users/me/password", json={"current_password": "password1", "new_password": "newpassword1"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_change_password_new_password_works(client):
    client.post("/api/v1/auth/register", json={"email": "pw2@test.com", "password": "password1", "name": "PW2"})
    client.post("/api/v1/auth/login", json={"email": "pw2@test.com", "password": "password1"})
    client.put("/api/v1/users/me/password", json={"current_password": "password1", "new_password": "newpassword1"})
    client.post("/api/v1/auth/logout")
    resp = client.post("/api/v1/auth/login", json={"email": "pw2@test.com", "password": "newpassword1"})
    assert resp.status_code == 200


def test_change_password_old_password_rejected_after_change(client):
    client.post("/api/v1/auth/register", json={"email": "pw3@test.com", "password": "password1", "name": "PW3"})
    client.post("/api/v1/auth/login", json={"email": "pw3@test.com", "password": "password1"})
    client.put("/api/v1/users/me/password", json={"current_password": "password1", "new_password": "newpassword1"})
    client.post("/api/v1/auth/logout")
    resp = client.post("/api/v1/auth/login", json={"email": "pw3@test.com", "password": "password1"})
    assert resp.status_code == 401


def test_change_password_wrong_current_returns_401(client):
    client.post("/api/v1/auth/register", json={"email": "pw4@test.com", "password": "password1", "name": "PW4"})
    client.post("/api/v1/auth/login", json={"email": "pw4@test.com", "password": "password1"})
    resp = client.put("/api/v1/users/me/password", json={"current_password": "wrongpassword", "new_password": "newpassword1"})
    assert resp.status_code == 401
    assert "incorrect" in resp.json()["detail"].lower()


def test_change_password_short_new_password_returns_422(client):
    client.post("/api/v1/auth/register", json={"email": "pw5@test.com", "password": "password1", "name": "PW5"})
    client.post("/api/v1/auth/login", json={"email": "pw5@test.com", "password": "password1"})
    resp = client.put("/api/v1/users/me/password", json={"current_password": "password1", "new_password": "short"})
    assert resp.status_code == 422


def test_change_password_unauthenticated_returns_401():
    import os
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.main import app
    from app.database import Base
    from app.deps import get_db
    from app.config import get_settings

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    os.environ["DEVELOPMENT_MODE"] = "true"
    get_settings.cache_clear()
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app, raise_server_exceptions=True) as anon:
            anon.cookies.clear()
            resp = anon.put("/api/v1/users/me/password", json={"current_password": "x", "new_password": "newpassword1"})
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        os.environ.pop("DEVELOPMENT_MODE", None)
        get_settings.cache_clear()


def test_change_password_oidc_only_user_returns_400(client, db):
    """An OIDC-only user (no hashed_password) cannot use change-password."""
    from app.models.user import User

    client.post("/api/v1/auth/register", json={"email": "oidcpw@test.com", "password": "password1", "name": "OIDCPW"})
    client.post("/api/v1/auth/login", json={"email": "oidcpw@test.com", "password": "password1"})

    user = db.query(User).filter_by(email="oidcpw@test.com").first()
    user.hashed_password = None
    user.oidc_sub = "google|oidc-pw-test"
    db.commit()

    resp = client.put("/api/v1/users/me/password", json={"current_password": "", "new_password": "newpassword1"})
    assert resp.status_code == 400
    assert "oidc" in resp.json()["detail"].lower()
