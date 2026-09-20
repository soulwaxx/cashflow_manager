import pytest

from tests.test_onboarding import WIZARD_PAYLOAD


def _snapshot_user_rows(db, user_id):
    from app.models.asset import Asset
    from app.models.category import Category
    from app.models.forecast import Forecast, ForecastAdjustment, ForecastLine
    from app.models.payment_method import MainBankHistory, PaymentMethod
    from app.models.salary import SalaryConfig
    from app.models.tax import TaxConfig
    from app.models.transaction import Transaction
    from app.models.transfer import Transfer
    from app.models.user import UserSetting

    models = (
        UserSetting, PaymentMethod, MainBankHistory, Category, SalaryConfig, TaxConfig,
        Transaction, Transfer, Asset, Forecast, ForecastLine, ForecastAdjustment,
    )
    return {
        model.__tablename__: [
            tuple(getattr(row, column.name) for column in model.__table__.columns)
            for row in db.query(model)
            .filter_by(user_id=user_id)
            .order_by(*model.__table__.primary_key.columns)
        ]
        for model in models
    }


def _setup(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)

def test_get_user_settings_returns_all_keys(client):
    _setup(client)
    r = client.get("/api/v1/user-settings")
    assert r.status_code == 200
    keys = {item["key"] for item in r.json()}
    assert "tracking_start_date" in keys
    assert "onboarding_complete" in keys

def test_update_user_setting(client):
    _setup(client)
    client.put("/api/v1/user-settings", json=[{"key": "theme", "value": "dark"}])
    r = client.get("/api/v1/user-settings")
    keys = {item["key"]: item["value"] for item in r.json()}
    assert keys.get("theme") == "dark"

def test_update_user_setting_invalid_key_returns_422(client):
    """Backend must reject unknown setting keys with 422."""
    _setup(client)
    r = client.put("/api/v1/user-settings", json=[{"key": "injected_key", "value": "x"}])
    assert r.status_code == 422


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("onboarding_complete", "false"),
        ("tracking_start_date", "2027-01-01"),
    ],
)
def test_generic_settings_cannot_bypass_completed_onboarding(client, db, key, value):
    """Protected settings cannot enable a second onboarding reset or alter user rows."""
    from app.models.asset import Asset
    from app.models.category import Category
    from app.models.forecast import Forecast, ForecastAdjustment, ForecastLine
    from app.models.payment_method import PaymentMethod
    from app.models.tax import TaxConfig
    from app.models.transaction import Transaction
    from app.models.transfer import Transfer
    from app.models.user import User

    _setup(client)
    user = db.query(User).filter_by(email="alice@example.com").one()
    main_bank = db.query(PaymentMethod).filter_by(user_id=user.id, name="MyBank").one()
    category = db.query(Category).filter_by(user_id=user.id).first()

    db.add(Transaction(
        user_id=user.id, date="2026-01-15", detail="Existing transaction", amount=100,
        payment_method_id=main_bank.id, category_id=category.id, transaction_direction="debit",
        billing_month="2026-01-01",
    ))
    db.add(Transfer(
        user_id=user.id, date="2026-01-15", detail="Existing transfer", amount=50,
        from_account_type="bank", from_account_name="MyBank",
        to_account_type="saving", to_account_name="MySavings", billing_month="2026-01-01",
        from_payment_method_id=main_bank.id,
    ))
    db.add(Asset(user_id=user.id, year=2026, asset_type="saving", asset_name="Manual", manual_override=123))
    forecast = Forecast(user_id=user.id, name="Existing forecast", base_year=2026, projection_years=1)
    db.add(forecast)
    db.flush()
    line = ForecastLine(user_id=user.id, forecast_id=forecast.id, detail="Existing line", base_amount=10)
    db.add(line)
    db.flush()
    db.add(ForecastAdjustment(
        user_id=user.id, forecast_line_id=line.id, valid_from="2027-01-01", new_amount=20,
    ))
    db.add(TaxConfig(user_id=user.id, valid_from="2027-01-01"))
    db.commit()
    before = _snapshot_user_rows(db, user.id)

    response = client.put("/api/v1/user-settings", json=[{"key": key, "value": value}])

    assert response.status_code == 422
    assert client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD).status_code == 409
    db.expire_all()
    assert _snapshot_user_rows(db, user.id) == before

def test_update_asset_opening_balance_settings(client):
    """Saving/investment account opening balances are dynamic but intentionally allowed."""
    _setup(client)
    r = client.put("/api/v1/user-settings", json=[
        {"key": "opening_saving_balance_Emergency", "value": "1000"},
        {"key": "opening_investment_balance_Broker", "value": "2500"},
    ])
    assert r.status_code == 200
    settings = {item["key"]: item["value"] for item in client.get("/api/v1/user-settings").json()}
    assert settings["opening_saving_balance_Emergency"] == "1000"
    assert settings["opening_investment_balance_Broker"] == "2500"

def test_update_empty_asset_opening_balance_suffix_returns_422(client):
    _setup(client)
    r = client.put("/api/v1/user-settings", json=[{"key": "opening_saving_balance_", "value": "0"}])
    assert r.status_code == 422

def test_users_me_returns_profile(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "alice@example.com"

def test_delete_own_account(client, db):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    r = client.request("DELETE", "/api/v1/users/me", json={"password": "Password1!"})
    assert r.status_code == 200
    # Should now be unauthenticated
    assert client.get("/api/v1/auth/me").status_code == 401
