import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base
from app.models import (  # noqa: F401 — ensure all models registered
    User, UserSetting,
    PaymentMethod, MainBankHistory,
    Category,
    Transaction,
    Transfer,
    Asset,
    SalaryConfig,
    TaxConfig,
)


# ---------------------------------------------------------------------------
# Standalone db fixture (no HTTP client) — used by unit tests
# ---------------------------------------------------------------------------
@pytest.fixture(scope="function")
def _standalone_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(conn, _record):
        conn.execute("PRAGMA foreign_keys = ON")

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# ---------------------------------------------------------------------------
# Shared StaticPool engine for integration tests that need both client + db
# ---------------------------------------------------------------------------
@pytest.fixture(scope="function")
def _shared_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(conn, _record):
        conn.execute("PRAGMA foreign_keys = ON")

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def client(_shared_engine):
    """HTTP test client with dependency-overridden in-memory DB."""
    import os
    from app.main import app
    from app.deps import get_db
    from app.config import get_settings

    Session = sessionmaker(autocommit=False, autoflush=False, bind=_shared_engine)

    def override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    # Set DEVELOPMENT_MODE=true so cookies don't get the Secure flag over plain
    # HTTP in the test client (TestClient uses http://testserver).
    # Use a 32-byte key to satisfy PyJWT's minimum key length requirement.
    os.environ["DEVELOPMENT_MODE"] = "true"
    os.environ["SECRET_KEY"] = "test-secret-key-long-enough-for-hs256!"
    get_settings.cache_clear()

    app.dependency_overrides[get_db] = override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()

    os.environ.pop("DEVELOPMENT_MODE", None)
    os.environ.pop("SECRET_KEY", None)
    get_settings.cache_clear()


@pytest.fixture(scope="function")
def db(request, _shared_engine):
    """DB session — shares engine with `client` if both are used in the same test."""
    Session = sessionmaker(autocommit=False, autoflush=False, bind=_shared_engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# make_user helper (used by some unit tests)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="function")
def make_user(_standalone_db):
    def _make(email="test@example.com", name="Test User", password_hash=None):
        from app.models.user import User, gen_uuid
        user = User(
            id=gen_uuid(),
            email=email,
            name=name,
            hashed_password=password_hash,
        )
        _standalone_db.add(user)
        _standalone_db.commit()
        _standalone_db.refresh(user)
        return user
    return _make
