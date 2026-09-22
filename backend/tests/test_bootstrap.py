import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base
from app.deps import get_db
from app.config import get_settings
from app.models.tax import TaxConfig


@pytest.fixture
def bootstrap_client():
    # StaticPool ensures all connections share the same in-memory DB
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

    # Set before TestClient.__enter__ so lifespan sees it when
    # warn_insecure_defaults() runs at startup.
    os.environ["DEVELOPMENT_MODE"] = "true"
    get_settings.cache_clear()

    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client, Session
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        os.environ.pop("DEVELOPMENT_MODE", None)
        get_settings.cache_clear()


def test_docs_endpoint(bootstrap_client):
    client, _ = bootstrap_client
    resp = client.get("/docs")
    assert resp.status_code == 200


def test_tax_config_seeded(bootstrap_client):
    client, Session = bootstrap_client
    client.get("/docs")
    with Session() as db:
        tc = db.query(TaxConfig).first()
        assert tc is not None
        assert abs(float(tc.inps_rate) - 0.0919) < 1e-4


def test_get_default_categories_returns_all_entries():
    """get_default_categories() must return the full DEFAULT_CATEGORIES list."""
    from app.services.seed import get_default_categories, DEFAULT_CATEGORIES
    result = get_default_categories()
    assert result == list(DEFAULT_CATEGORIES)
    assert len(result) > 0


def test_seed_user_categories_creates_categories(_standalone_db, make_user):
    """seed_user_categories() must create one Category row per DEFAULT_CATEGORIES entry."""
    from app.services.seed import seed_user_categories, DEFAULT_CATEGORIES
    from app.models.category import Category

    user = make_user(email="seed_cat@test.com")
    db = _standalone_db

    seed_user_categories(user.id, db)

    cats = db.query(Category).filter_by(user_id=user.id).all()
    assert len(cats) == len(DEFAULT_CATEGORIES)

    # Saving categories must be inactive
    saving_cats = [c for c in cats if c.type == "Saving"]
    assert all(not c.is_active for c in saving_cats)

    # All other categories must be active
    non_saving = [c for c in cats if c.type != "Saving"]
    assert all(c.is_active for c in non_saving)
