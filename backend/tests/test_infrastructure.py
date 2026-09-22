"""Tests for database.py and deps.py infrastructure that is always overridden in API tests."""
import os
from pathlib import Path

import pytest


def test_get_engine_creates_sqlite_engine(tmp_path):
    """get_engine() must create an engine pointing at settings.db_path."""
    from app.database import get_engine
    from app.config import get_settings

    db_file = str(tmp_path / "test.db")
    os.environ["DB_PATH"] = db_file
    os.environ["DEVELOPMENT_MODE"] = "true"
    get_settings.cache_clear()
    get_engine.cache_clear()
    engine = None
    try:
        engine = get_engine()
        assert engine is not None
        assert "sqlite" in str(engine.url)
    finally:
        if engine is not None:
            engine.dispose()
        get_engine.cache_clear()
        os.environ.pop("DB_PATH", None)
        os.environ.pop("DEVELOPMENT_MODE", None)
        get_settings.cache_clear()


def test_get_session_factory_returns_callable(tmp_path):
    """get_session_factory() must return a sessionmaker bound to get_engine()."""
    from app.database import get_engine, get_session_factory, Base
    from app.config import get_settings

    db_file = str(tmp_path / "test2.db")
    os.environ["DB_PATH"] = db_file
    os.environ["DEVELOPMENT_MODE"] = "true"
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = None
    try:
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        factory = get_session_factory()
        session = factory()
        session.close()
        Base.metadata.drop_all(bind=engine)
    finally:
        if engine is not None:
            engine.dispose()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        os.environ.pop("DB_PATH", None)
        os.environ.pop("DEVELOPMENT_MODE", None)
        get_settings.cache_clear()


def test_get_db_yields_and_closes(tmp_path):
    """get_db() must yield a session and close it on exit."""
    from app.database import get_engine, get_session_factory, Base
    from app.deps import get_db
    from app.config import get_settings

    db_file = str(tmp_path / "test3.db")
    os.environ["DB_PATH"] = db_file
    os.environ["DEVELOPMENT_MODE"] = "true"
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = None
    try:
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        gen = get_db()
        session = next(gen)
        assert session is not None
        try:
            gen.close()
        except StopIteration:
            pass
        Base.metadata.drop_all(bind=engine)
    finally:
        if engine is not None:
            engine.dispose()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        os.environ.pop("DB_PATH", None)
        os.environ.pop("DEVELOPMENT_MODE", None)
        get_settings.cache_clear()


def test_sqlite_foreign_key_pragma_enforced(tmp_path):
    """get_engine() must enable FK constraints — inserting a Category with a non-existent user_id must fail."""
    import os
    from sqlalchemy.exc import IntegrityError
    from app.database import get_engine, get_session_factory, Base
    from app.config import get_settings
    from app.models.category import Category

    db_file = str(tmp_path / "fk_pragma.db")
    os.environ["DB_PATH"] = db_file
    os.environ["DEVELOPMENT_MODE"] = "true"
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = None
    try:
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        factory = get_session_factory()
        session = factory()
        session.add(Category(user_id="nonexistent-user-id", type="Test", sub_type="Sub"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.close()
        Base.metadata.drop_all(bind=engine)
    finally:
        if engine is not None:
            engine.dispose()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        os.environ.pop("DB_PATH", None)
        os.environ.pop("DEVELOPMENT_MODE", None)
        get_settings.cache_clear()


def test_user_settings_cascade_on_user_delete(tmp_path):
    """Deleting a User must cascade-delete all UserSetting rows for that user."""
    import os
    from app.database import get_engine, get_session_factory, Base
    from app.config import get_settings
    from app.models.user import User, UserSetting

    db_file = str(tmp_path / "cascade_user_settings.db")
    os.environ["DB_PATH"] = db_file
    os.environ["DEVELOPMENT_MODE"] = "true"
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = None
    try:
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        factory = get_session_factory()
        session = factory()

        user = User(id="test-user-uuid-0001", name="Test User")
        session.add(user)
        session.commit()

        setting = UserSetting(user_id="test-user-uuid-0001", key="theme", value="dark")
        session.add(setting)
        session.commit()

        session.delete(user)
        session.commit()

        result = session.get(UserSetting, ("test-user-uuid-0001", "theme"))
        assert result is None, "UserSetting row should have been cascade-deleted with the user"

        session.close()
        Base.metadata.drop_all(bind=engine)
    finally:
        if engine is not None:
            engine.dispose()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        os.environ.pop("DB_PATH", None)
        os.environ.pop("DEVELOPMENT_MODE", None)
        get_settings.cache_clear()


def test_main_lifespan_runs_alembic_migration(tmp_path):
    """When no get_db override is set, the lifespan runs Alembic migrations and seeds tax config."""
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.config import get_settings
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from app.database import get_engine, get_session_factory

    db_file = str(tmp_path / "lifespan_alembic.db")
    os.environ["DB_PATH"] = db_file
    os.environ["DEVELOPMENT_MODE"] = "true"
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    # Create a fresh app with no dependency overrides — triggers the Alembic else-branch
    fresh_app = create_app()
    assert not fresh_app.dependency_overrides

    engine = None
    try:
        with TestClient(fresh_app, raise_server_exceptions=True) as c:
            resp = c.get("/docs")
            assert resp.status_code == 200
        engine = get_engine()
        with engine.connect() as connection:
            revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
        alembic_cfg = Config(Path(__file__).resolve().parents[1] / "alembic.ini")
        alembic_cfg.set_main_option(
            "script_location", str(Path(__file__).resolve().parents[1] / "alembic")
        )
        assert revision == ScriptDirectory.from_config(alembic_cfg).get_current_head()
    finally:
        if engine is not None:
            engine.dispose()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        os.environ.pop("DB_PATH", None)
        os.environ.pop("DEVELOPMENT_MODE", None)
        get_settings.cache_clear()


def test_production_entrypoint_leaves_migrations_to_fastapi_lifespan():
    """start.sh launches Uvicorn; the FastAPI lifespan is the sole migration owner."""
    repo_root = Path(__file__).resolve().parents[2]
    start_script = (repo_root / "start.sh").read_text()
    main_source = (repo_root / "backend" / "app" / "main.py").read_text()

    assert "alembic upgrade" not in start_script
    assert "exec uvicorn app.main:app" in start_script
    assert main_source.count('command.upgrade(cfg, "head")') == 1
