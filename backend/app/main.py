from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.services.seed import seed_tax_config
from app.database import get_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.deps import get_db
    settings = get_settings()
    settings.warn_insecure_defaults()
    # Use dependency override if provided (e.g., during tests), else use default session factory
    if get_db in app.dependency_overrides:
        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            seed_tax_config(db)
        finally:
            db_gen.close()
    else:
        from alembic import command
        from alembic.config import Config
        import os
        # main.py is at backend/app/main.py; alembic.ini is at backend/alembic.ini
        alembic_ini = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
        )
        alembic_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "alembic")
        )
        cfg = Config(alembic_ini)
        cfg.set_main_option("script_location", alembic_dir)
        command.upgrade(cfg, "head")
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            seed_tax_config(db)
        finally:
            db.close()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CashFlow API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from app.routers.auth import router as auth_router
    app.include_router(auth_router, prefix="/api/v1")
    from app.routers import health as health_router
    app.include_router(health_router.router, prefix="/api/v1")
    from app.routers import onboarding as onboarding_router
    app.include_router(onboarding_router.router, prefix="/api/v1")
    from app.routers import accounts as accounts_router, payment_methods as pm_router, categories as cat_router
    app.include_router(accounts_router.router, prefix="/api/v1")
    app.include_router(pm_router.router, prefix="/api/v1")
    app.include_router(cat_router.router, prefix="/api/v1")
    from app.routers import salary as salary_router, tax_config as tax_router
    app.include_router(salary_router.router, prefix="/api/v1")
    app.include_router(tax_router.router, prefix="/api/v1")
    from app.routers import transactions as tx_router
    app.include_router(tx_router.router, prefix="/api/v1")
    from app.routers import transfers as transfer_router
    app.include_router(transfer_router.router, prefix="/api/v1")
    from app.routers import summary as summary_router
    app.include_router(summary_router.router, prefix="/api/v1")
    from app.routers import assets as assets_router
    app.include_router(assets_router.router, prefix="/api/v1")
    from app.routers import analytics as analytics_router
    app.include_router(analytics_router.router, prefix="/api/v1")
    from app.routers import user_settings as us_router, users as users_router
    app.include_router(us_router.router, prefix="/api/v1")
    app.include_router(users_router.router, prefix="/api/v1")
    return app


app = create_app()
