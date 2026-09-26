from sqlalchemy import create_engine, inspect
from app.models import Base


def test_all_tables_created():
    engine = create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(bind=engine)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        expected = [
            "users", "user_settings", "payment_methods", "main_bank_history",
            "categories", "transactions", "transfers", "assets",
            "salary_config", "tax_config",
        ]
        for table in expected:
            assert table in tables, f"Missing table: {table}"
    finally:
        engine.dispose()
