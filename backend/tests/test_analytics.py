import pytest
from tests.test_onboarding import WIZARD_PAYLOAD

def _setup(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    pm_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyBank")
    cat_id = next(c["id"] for c in client.get("/api/v1/categories").json() if c["type"] == "Housing")
    return pm_id, cat_id

def test_analytics_returns_per_category_per_month(client):
    pm_id, cat_id = _setup(client)
    client.post("/api/v1/transactions", json={
        "date": "2026-01-10", "detail": "Rent", "amount": 900,
        "payment_method_id": pm_id, "category_id": cat_id, "transaction_direction": "debit",
    })
    r = client.get("/api/v1/analytics/categories", params={"from": "2026-01", "to": "2026-01"})
    assert r.status_code == 200
    row = next((x for x in r.json() if x["type"] == "Housing"), None)
    assert row is not None
    assert row["total_amount"] == pytest.approx(900.0)

def test_analytics_direction_filter_debit_only(client):
    pm_id, cat_id = _setup(client)
    sal_cat_id = next(c["id"] for c in client.get("/api/v1/categories").json() if c["type"] == "Salary")
    client.post("/api/v1/transactions", json={
        "date": "2026-01-25", "detail": "Income", "amount": 2500,
        "payment_method_id": pm_id, "category_id": sal_cat_id, "transaction_direction": "income",
    })
    client.post("/api/v1/transactions", json={
        "date": "2026-01-10", "detail": "Rent", "amount": 900,
        "payment_method_id": pm_id, "category_id": cat_id, "transaction_direction": "debit",
    })
    r = client.get("/api/v1/analytics/categories", params={"from": "2026-01", "to": "2026-01", "direction": "debit"})
    types = {row["type"] for row in r.json()}
    assert "Salary" not in types
    assert "Housing" in types

def test_analytics_spans_multiple_months(client):
    pm_id, cat_id = _setup(client)
    for month in ["2026-01", "2026-02", "2026-03"]:
        client.post("/api/v1/transactions", json={
            "date": f"{month}-10", "detail": "Rent", "amount": 900,
            "payment_method_id": pm_id, "category_id": cat_id, "transaction_direction": "debit",
        })
    r = client.get("/api/v1/analytics/categories", params={"from": "2026-01", "to": "2026-03"})
    housing_rows = [x for x in r.json() if x["type"] == "Housing"]
    assert len(housing_rows) == 3  # one row per month

def test_analytics_no_data_returns_empty(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    r = client.get("/api/v1/analytics/categories", params={"from": "2026-01", "to": "2026-12"})
    assert r.status_code == 200
    assert r.json() == []


def test_transfer_analytics_returns_saving_transfers(client):
    """Transfers to saving accounts must appear in /analytics/transfers."""
    _setup(client)
    client.post("/api/v1/transfers", json={
        "date": "2026-02-01", "detail": "Monthly saving",
        "amount": 400,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    })
    r = client.get("/api/v1/analytics/transfers", params={"from": "2026-02", "to": "2026-02"})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["to_account_type"] == "saving"
    assert rows[0]["to_account_name"] == "MySavings"
    assert rows[0]["total_amount"] == pytest.approx(400.0)
    assert rows[0]["month"] == "2026-02"


def test_transfer_analytics_excludes_bank_to_bank(client):
    """Transfers between bank accounts must NOT appear in /analytics/transfers."""
    _setup(client)
    client.post("/api/v1/transfers", json={
        "date": "2026-02-01", "detail": "Internal move",
        "amount": 200,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "bank", "to_account_name": "MyBank",
    })
    r = client.get("/api/v1/analytics/transfers", params={"from": "2026-02", "to": "2026-02"})
    assert r.status_code == 200
    assert r.json() == []


def test_transfer_analytics_aggregates_multiple_transfers(client):
    """Multiple transfers to the same account in the same month must be summed."""
    _setup(client)
    for amount in [100, 200, 300]:
        client.post("/api/v1/transfers", json={
            "date": "2026-03-15", "detail": "Saving top-up",
            "amount": amount,
            "from_account_type": "bank", "from_account_name": "MyBank",
            "to_account_type": "saving", "to_account_name": "MySavings",
        })
    r = client.get("/api/v1/analytics/transfers", params={"from": "2026-03", "to": "2026-03"})
    assert r.status_code == 200
    row = next((x for x in r.json() if x["to_account_name"] == "MySavings"), None)
    assert row is not None
    assert row["total_amount"] == pytest.approx(600.0)


def test_transfer_analytics_no_data_returns_empty(client):
    _setup(client)
    r = client.get("/api/v1/analytics/transfers", params={"from": "2025-01", "to": "2025-12"})
    assert r.status_code == 200
    assert r.json() == []


def test_category_spending_aggregates_correctly(client):
    """SQL GROUP BY aggregation should sum amounts correctly."""
    pm_id, cat_id = _setup(client)
    n = 5
    for i in range(n):
        client.post("/api/v1/transactions", json={
            "date": f"2026-03-{10 + i:02d}",
            "detail": f"Expense {i}",
            "amount": 100,
            "payment_method_id": pm_id,
            "category_id": cat_id,
            "transaction_direction": "debit",
        })
    r = client.get("/api/v1/analytics/categories", params={"from": "2026-03", "to": "2026-03"})
    assert r.status_code == 200
    row = next((x for x in r.json() if x["type"] == "Housing"), None)
    assert row is not None
    assert row["total_amount"] == pytest.approx(n * 100.0)


def test_analytics_payment_method_ids_filter(client):
    """payment_method_ids filter returns only transactions for the specified PM."""
    pm_id, cat_id = _setup(client)

    # Create a second payment method
    r2 = client.post(
        "/api/v1/payment-methods",
        json={"name": "SecondCard", "type": "credit_card", "linked_bank_id": pm_id},
    )
    assert r2.status_code == 200
    pm2_id = r2.json()["id"]

    # Transaction on pm1
    client.post("/api/v1/transactions", json={
        "date": "2026-01-10", "detail": "PM1 expense",
        "amount": 100, "payment_method_id": pm_id,
        "category_id": cat_id, "transaction_direction": "debit",
    })
    # Transaction on pm2 (credit card → billing_month = 2026-02-01)
    client.post("/api/v1/transactions", json={
        "date": "2026-01-10", "detail": "PM2 expense",
        "amount": 200, "payment_method_id": pm2_id,
        "category_id": cat_id, "transaction_direction": "debit",
    })

    # Filter by pm1 only, spanning both potential billing months
    r = client.get(
        "/api/v1/analytics/categories",
        params={"from": "2026-01", "to": "2026-02", "payment_method_ids": pm_id},
    )
    assert r.status_code == 200
    rows = r.json()
    # All returned rows must be from pm1 only; total should be 100, not 300
    total = sum(row["total_amount"] for row in rows if row["type"] == "Housing")
    assert total == pytest.approx(100.0)


def test_analytics_direction_income_filter(client):
    """direction=income filter returns income transactions and not debit ones."""
    pm_id, cat_id = _setup(client)
    sal_cat_id = next(c["id"] for c in client.get("/api/v1/categories").json() if c["type"] == "Salary")

    # Income transaction
    client.post("/api/v1/transactions", json={
        "date": "2026-01-25", "detail": "Salary",
        "amount": 2500, "payment_method_id": pm_id,
        "category_id": sal_cat_id, "transaction_direction": "income",
    })
    # Debit transaction
    client.post("/api/v1/transactions", json={
        "date": "2026-01-10", "detail": "Rent",
        "amount": 900, "payment_method_id": pm_id,
        "category_id": cat_id, "transaction_direction": "debit",
    })

    r_income = client.get(
        "/api/v1/analytics/categories",
        params={"from": "2026-01", "to": "2026-01", "direction": "income"},
    )
    assert r_income.status_code == 200
    types_income = {row["type"] for row in r_income.json()}
    assert "Salary" in types_income
    assert "Housing" not in types_income

    r_debit = client.get(
        "/api/v1/analytics/categories",
        params={"from": "2026-01", "to": "2026-01", "direction": "debit"},
    )
    assert r_debit.status_code == 200
    types_debit = {row["type"] for row in r_debit.json()}
    assert "Housing" in types_debit
    assert "Salary" not in types_debit


def test_analytics_does_not_resolve_another_users_category_metadata(client, db):
    """Even if corrupt data points at another user's category id, analytics must not leak its labels."""
    from app.models.user import User, gen_uuid
    from app.models.category import Category
    from app.models.payment_method import PaymentMethod
    from app.models.transaction import Transaction

    pm_id, _ = _setup(client)
    alice_user_id = db.get(PaymentMethod, pm_id).user_id
    bob = User(id=gen_uuid(), email="bob-analytics@example.com", name="Bob")
    db.add(bob)
    db.flush()
    foreign_cat = Category(user_id=bob.id, type="Secret", sub_type="Private")
    db.add(foreign_cat)
    db.flush()
    foreign_cat_id = foreign_cat.id
    db.add(Transaction(
        user_id=alice_user_id,
        date="2026-01-10",
        detail="Corrupt row",
        amount=123,
        payment_method_id=pm_id,
        category_id=foreign_cat_id,
        transaction_direction="debit",
        billing_month="2026-01-01",
    ))
    db.commit()

    r = client.get("/api/v1/analytics/categories", params={"from": "2026-01", "to": "2026-01"})
    assert r.status_code == 200
    row = next((x for x in r.json() if x["category_id"] == foreign_cat_id), None)
    assert row is not None
    assert row["type"] is None
    assert row["sub_type"] is None
