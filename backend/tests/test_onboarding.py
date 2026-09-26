import pytest

WIZARD_PAYLOAD = {
    "tracking_start_date": "2026-01-01",
    "main_bank": {"name": "MyBank", "opening_balance": 5000.00},
    "additional_banks": [{"name": "SecondBank", "opening_balance": 1200.00}],
    "payment_methods": [
        {"name": "MyCard", "type": "credit_card", "linked_bank_name": "MyBank"},
        {"name": "MyBank Debit", "type": "debit_card", "linked_bank_name": "MyBank"},
    ],
    "saving_accounts": [{"name": "MySavings", "opening_balance": 3000.00}],
    "investment_accounts": [{"name": "MyBroker", "opening_balance": 8000.00}],
    "salary": {
        "ral": 42000,
        "employer_contrib_rate": 0.04,
        "voluntary_contrib_rate": 0.02,
        "regional_tax_rate": 0.0173,
        "municipal_tax_rate": 0.008,
        "meal_vouchers_annual": 1200,
        "welfare_annual": 500,
    },
}

INVALID_ONBOARDING_PAYLOADS = [
    pytest.param(
        {**WIZARD_PAYLOAD, "tracking_start_date": "20260101"},
        id="tracking-date-must-use-canonical-format",
    ),
    pytest.param(
        {**WIZARD_PAYLOAD, "tracking_start_date": "2026-01-15"},
        id="tracking-date-must-be-month-start",
    ),
    pytest.param(
        {
            **WIZARD_PAYLOAD,
            "additional_banks": [{"name": "MyBank", "opening_balance": 1200.00}],
        },
        id="duplicate-bank-name",
    ),
    pytest.param(
        {
            **WIZARD_PAYLOAD,
            "payment_methods": [
                {"name": "MyCard", "type": "credit_card", "linked_bank_name": "MissingBank"},
            ],
        },
        id="unknown-linked-bank",
    ),
    pytest.param(
        {
            **WIZARD_PAYLOAD,
            "payment_methods": [{"name": "MyCard", "type": "credit_card"}],
        },
        id="bank-funded-card-requires-linked-bank",
    ),
    pytest.param(
        {
            **WIZARD_PAYLOAD,
            "saving_accounts": [{"name": "   ", "opening_balance": 3000.00}],
        },
        id="blank-nested-name",
    ),
    pytest.param(
        {**WIZARD_PAYLOAD, "main_bank": {"name": "MyBank", "opening_balance": -1}},
        id="negative-opening-balance",
    ),
    pytest.param(
        {
            **WIZARD_PAYLOAD,
            "salary": {**WIZARD_PAYLOAD["salary"], "regional_tax_rate": 1.1},
        },
        id="out-of-range-salary-rate",
    ),
]


def test_onboarding_schema_rejects_compact_iso_tracking_start_date():
    from pydantic import ValidationError

    from app.schemas.onboarding import OnboardingPayload

    with pytest.raises(ValidationError, match="Tracking start date must be YYYY-MM-DD"):
        OnboardingPayload.model_validate({
            "tracking_start_date": "20260101",
            "main_bank": {"name": "MyBank"},
        })


def test_onboarding_status_incomplete_for_new_user(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    r = client.get("/api/v1/onboarding/status")
    assert r.status_code == 200
    assert r.json()["complete"] is False

def test_onboarding_submit_sets_complete(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    r = client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    assert r.status_code == 200
    r2 = client.get("/api/v1/onboarding/status")
    assert r2.json()["complete"] is True

def test_onboarding_creates_payment_methods(client, db):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    from app.models.payment_method import PaymentMethod
    methods = db.query(PaymentMethod).all()
    names = {m.name for m in methods}
    assert "MyBank" in names
    assert "SecondBank" in names
    assert "MyCard" in names

def test_onboarding_creates_main_bank_history(client, db):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    from app.models.payment_method import MainBankHistory
    history = db.query(MainBankHistory).all()
    assert len(history) == 1
    assert float(history[0].opening_balance) == pytest.approx(5000.00)
    assert history[0].valid_from == "2026-01-01"

def test_onboarding_creates_stable_nonbank_accounts(client, db):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    from app.models.account import Account
    accounts = {(account.type, account.name): float(account.opening_balance) for account in db.query(Account).all()}
    assert accounts[("saving", "MySavings")] == 3000.0
    assert accounts[("investment", "MyBroker")] == 8000.0
    assert accounts[("pension", "Pension")] == 0.0

def test_onboarding_seeds_default_categories(client, db):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    from app.models.category import Category
    cats = db.query(Category).all()
    assert len(cats) > 0
    types = {c.type for c in cats}
    assert "Housing" in types
    assert "Salary" in types
    assert "Bills" not in types, "Bills must not be a top-level category type"

def test_repeated_onboarding_returns_conflict(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    assert client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD).status_code == 200

    r2 = client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)

    assert r2.status_code == 409
    assert r2.json()["detail"] == "Onboarding has already been completed"

def test_resubmit_onboarding_preserves_existing_transactions(client, db):
    """A rejected repeat submission must not change existing financial data."""
    from app.models.transaction import Transaction
    from app.models.transfer import Transfer

    client.post("/api/v1/auth/register", json={
        "email": "resubmit@example.com", "password": "Password1!", "name": "Resubmit"
    })
    r1 = client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    assert r1.status_code == 200

    # Fetch the main bank payment method id so we can create a transaction
    from app.models.payment_method import PaymentMethod
    db.expire_all()
    main_pm = db.query(PaymentMethod).filter_by(name="MyBank").first()
    assert main_pm is not None

    # Directly insert a Transaction row to simulate existing data
    from app.models.user import User
    user = db.query(User).filter_by(email="resubmit@example.com").first()
    txn = Transaction(
        user_id=user.id,
        date="2026-01-15",
        detail="Test expense",
        amount=100.0,
        payment_method_id=main_pm.id,
        transaction_direction="debit",
        billing_month="2026-01",
    )
    db.add(txn)
    db.commit()

    assert db.query(Transaction).filter_by(user_id=user.id).count() == 1

    # A repeat submission is rejected before it can change any setup or transaction rows.
    r2 = client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    assert r2.status_code == 409

    db.expire_all()
    assert db.query(Transaction).filter_by(user_id=user.id).count() == 1
    assert db.query(Transfer).filter_by(user_id=user.id).count() == 0


def test_resubmit_onboarding_preserves_assets_and_user_tax_config(client, db):
    """A repeat submission must leave all existing financial rows intact."""
    from app.models.asset import Asset
    from app.models.tax import TaxConfig
    from app.models.user import User

    client.post("/api/v1/auth/register", json={
        "email": "fullreset@example.com", "password": "Password1!", "name": "Full Reset"
    })
    assert client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD).status_code == 200

    user = db.query(User).filter_by(email="fullreset@example.com").first()
    assert user is not None

    db.add(Asset(
        user_id=user.id,
        year=2026,
        asset_type="saving",
        asset_name="Manual",
        manual_override=123.0,
    ))
    db.add(TaxConfig(user_id=user.id, valid_from="2027-01-01", inps_rate=0.05))
    db.commit()

    assert db.query(Asset).filter_by(user_id=user.id).count() == 1
    assert db.query(TaxConfig).filter_by(user_id=user.id).count() == 1

    assert client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD).status_code == 409
    db.expire_all()

    assert db.query(Asset).filter_by(user_id=user.id).count() == 1
    assert db.query(TaxConfig).filter_by(user_id=user.id).count() == 1


@pytest.mark.parametrize("payload", INVALID_ONBOARDING_PAYLOADS)
def test_onboarding_rejects_malformed_nested_payloads(client, db, payload):
    from app.models.payment_method import PaymentMethod

    client.post("/api/v1/auth/register", json={
        "email": "invalid@example.com", "password": "Password1!", "name": "Invalid"
    })

    response = client.post("/api/v1/onboarding", json=payload)

    assert response.status_code == 422
    assert db.query(PaymentMethod).count() == 0
    assert client.get("/api/v1/onboarding/status").json()["complete"] is False


def test_onboarding_salary_months_stored(client):
    client.post("/api/v1/auth/register", json={
        "email": "bob@example.com", "password": "Password1!", "name": "Bob"
    })
    payload = {
        "tracking_start_date": "2026-01-01",
        "main_bank": {"name": "MyBank", "opening_balance": 5000},
        "salary": {
            "ral": 42000,
            "employer_contrib_rate": 0.04,
            "voluntary_contrib_rate": 0.0,
            "regional_tax_rate": 0.0173,
            "municipal_tax_rate": 0.001,
            "meal_vouchers_annual": 0,
            "welfare_annual": 0,
            "salary_months": 13,
        },
    }
    r = client.post("/api/v1/onboarding", json=payload)
    assert r.status_code == 200
    configs = client.get("/api/v1/salary").json()
    assert len(configs) == 1
    assert configs[0]["salary_months"] == 13


def test_onboarding_without_tax_config_returns_422_without_partial_persistence(client, db):
    from app.models.category import Category
    from app.models.payment_method import MainBankHistory, PaymentMethod
    from app.models.salary import SalaryConfig
    from app.models.user import UserSetting

    client.post("/api/v1/auth/register", json={
        "email": "no-tax@example.com", "password": "Password1!", "name": "No Tax"
    })
    payload = {
        **WIZARD_PAYLOAD,
        "tracking_start_date": "1990-01-01",
    }

    response = client.post("/api/v1/onboarding", json=payload)

    assert response.status_code == 422
    assert db.query(UserSetting).count() == 0
    assert db.query(PaymentMethod).count() == 0
    assert db.query(MainBankHistory).count() == 0
    assert db.query(Category).count() == 0
    assert db.query(SalaryConfig).count() == 0
    assert client.get("/api/v1/onboarding/status").json() == {"complete": False}


def test_onboarding_invalid_legacy_tax_table_returns_422_without_partial_persistence(client, db):
    from app.models.category import Category
    from app.models.payment_method import CardBankLinkHistory, MainBankHistory, PaymentMethod
    from app.models.salary import SalaryConfig
    from app.models.tax import TaxConfig
    from app.models.user import User, UserSetting

    client.post("/api/v1/auth/register", json={
        "email": "legacy-tax@example.com", "password": "Password1!", "name": "Legacy Tax"
    })
    user = db.query(User).filter_by(email="legacy-tax@example.com").one()
    db.add(TaxConfig(
        user_id=user.id,
        valid_from="2026-01-01",
        employment_deduction_band2_range=0,
    ))
    db.commit()

    response = client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)

    assert response.status_code == 422
    assert db.query(UserSetting).filter_by(user_id=user.id).count() == 0
    assert db.query(PaymentMethod).filter_by(user_id=user.id).count() == 0
    assert db.query(MainBankHistory).filter_by(user_id=user.id).count() == 0
    assert db.query(CardBankLinkHistory).filter_by(user_id=user.id).count() == 0
    assert db.query(Category).filter_by(user_id=user.id).count() == 0
    assert db.query(SalaryConfig).filter_by(user_id=user.id).count() == 0
    assert client.get("/api/v1/onboarding/status").json() == {"complete": False}


def test_onboarding_rejects_negative_taxable_base_without_partial_persistence(client, db):
    from app.models.category import Category
    from app.models.payment_method import CardBankLinkHistory, MainBankHistory, PaymentMethod
    from app.models.salary import SalaryConfig
    from app.models.user import User, UserSetting

    client.post("/api/v1/auth/register", json={
        "email": "salary-boundary@example.com", "password": "Password1!", "name": "Salary Boundary"
    })
    user = db.query(User).filter_by(email="salary-boundary@example.com").one()
    payload = {
        **WIZARD_PAYLOAD,
        "salary": {
            **WIZARD_PAYLOAD["salary"],
            "ral": 100,
            "employer_contrib_rate": 1,
            "voluntary_contrib_rate": 1,
            "regional_tax_rate": 1,
            "municipal_tax_rate": 1,
        },
    }

    response = client.post("/api/v1/onboarding", json=payload)

    assert response.status_code == 422
    assert db.query(UserSetting).filter_by(user_id=user.id).count() == 0
    assert db.query(PaymentMethod).filter_by(user_id=user.id).count() == 0
    assert db.query(MainBankHistory).filter_by(user_id=user.id).count() == 0
    assert db.query(CardBankLinkHistory).filter_by(user_id=user.id).count() == 0
    assert db.query(Category).filter_by(user_id=user.id).count() == 0
    assert db.query(SalaryConfig).filter_by(user_id=user.id).count() == 0
    assert client.get("/api/v1/onboarding/status").json() == {"complete": False}


def test_onboarding_rejects_capped_deduction_negative_net_without_partial_persistence(client, db):
    from app.models.category import Category
    from app.models.payment_method import CardBankLinkHistory, MainBankHistory, PaymentMethod
    from app.models.salary import SalaryConfig
    from app.models.user import User, UserSetting

    client.post("/api/v1/auth/register", json={
        "email": "negative-net@example.com", "password": "Password1!", "name": "Negative Net"
    })
    user = db.query(User).filter_by(email="negative-net@example.com").one()
    payload = {
        **WIZARD_PAYLOAD,
        "salary": {
            **WIZARD_PAYLOAD["salary"],
            "ral": 36000,
            "employer_contrib_rate": 0,
            "voluntary_contrib_rate": 1,
            "regional_tax_rate": 0,
            "municipal_tax_rate": 0,
        },
    }

    response = client.post("/api/v1/onboarding", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"] == "Computed net annual salary must not be negative"
    assert db.query(UserSetting).filter_by(user_id=user.id).count() == 0
    assert db.query(PaymentMethod).filter_by(user_id=user.id).count() == 0
    assert db.query(MainBankHistory).filter_by(user_id=user.id).count() == 0
    assert db.query(CardBankLinkHistory).filter_by(user_id=user.id).count() == 0
    assert db.query(Category).filter_by(user_id=user.id).count() == 0
    assert db.query(SalaryConfig).filter_by(user_id=user.id).count() == 0
    assert client.get("/api/v1/onboarding/status").json() == {"complete": False}
