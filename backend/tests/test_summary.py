import pytest
from tests.test_onboarding import WIZARD_PAYLOAD

def _setup(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)

def test_summary_year_returns_12_months(client):
    _setup(client)
    r = client.get("/api/v1/summary/2026")
    assert r.status_code == 200
    assert len(r.json()) == 12

@pytest.mark.parametrize("month", [1, 12])
def test_summary_accepts_boundary_months(client, month):
    _setup(client)
    response = client.get(f"/api/v1/summary/2026/{month}")
    assert response.status_code == 200


@pytest.mark.parametrize("month", [0, 13])
def test_summary_rejects_out_of_range_months(client, month):
    _setup(client)
    response = client.get(f"/api/v1/summary/2026/{month}")
    assert response.status_code == 422


@pytest.mark.parametrize("year", [2000, 2100])
def test_summary_accepts_supported_year_boundaries(client, year):
    _setup(client)
    response = client.get(f"/api/v1/summary/{year}")
    assert response.status_code == 200


@pytest.mark.parametrize("year", [1999, 2101])
def test_summary_rejects_out_of_range_years(client, year):
    _setup(client)
    response = client.get(f"/api/v1/summary/{year}")
    assert response.status_code == 422


def test_summary_month_contains_bank_balance(client):
    _setup(client)
    r = client.get("/api/v1/summary/2026/1")
    assert r.status_code == 200
    data = r.json()
    assert "bank_balance" in data
    assert data["bank_balance"] == pytest.approx(5000.0)

def test_summary_month_shows_income_and_outcomes(client):
    _setup(client)
    pm_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyBank")
    cat_id = next(c["id"] for c in client.get("/api/v1/categories").json() if c["type"] == "Salary")
    client.post("/api/v1/transactions", json={
        "date": "2026-01-25", "detail": "Salary", "amount": 2500,
        "payment_method_id": pm_id, "category_id": cat_id, "transaction_direction": "income",
    })
    r = client.get("/api/v1/summary/2026/1")
    assert r.json()["incomes"] == pytest.approx(2500.0)


def test_bank_balance_includes_cc_credit_payoffs(client):
    """CC 'credit'-direction transactions (bank paying off CC) must reduce bank_balance."""
    _setup(client)
    pms = client.get("/api/v1/payment-methods").json()
    cc_id = next(pm["id"] for pm in pms if pm["name"] == "MyCard")
    cat_id = next(c["id"] for c in client.get("/api/v1/categories").json() if c["type"] == "Housing")
    # CC payoff entered in December 2025 — bills in January 2026
    client.post("/api/v1/transactions", json={
        "date": "2025-12-15", "detail": "CC Payoff", "amount": 500,
        "payment_method_id": cc_id, "category_id": cat_id, "transaction_direction": "credit",
    })
    r = client.get("/api/v1/summary/2026/1")
    assert r.status_code == 200
    # Opening balance is 5000; the CC payoff reduces it to 4500
    assert r.json()["bank_balance"] == pytest.approx(4500.0)


def test_summary_month_shows_outcomes_by_method(client):
    _setup(client)
    pm_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyBank")
    cat_id = next(c["id"] for c in client.get("/api/v1/categories").json() if c["type"] == "Housing")
    client.post("/api/v1/transactions", json={
        "date": "2026-01-15", "detail": "Rent", "amount": 750,
        "payment_method_id": pm_id, "category_id": cat_id, "transaction_direction": "debit",
    })
    r = client.get("/api/v1/summary/2026/1")
    assert r.status_code == 200
    outcomes = r.json()["outcomes_by_method"]
    assert "MyBank" in outcomes
    assert outcomes["MyBank"] == pytest.approx(750.0)


def test_year_summary_stamp_duty_credit_card(client):
    """year_monthly_summaries inline loop: CC with has_stamp_duty=True and spend > €77.47
    should produce stamp_duty == 2.0 for months with high enough spend, 0.0 otherwise."""
    _setup(client)

    # Create a credit card with stamp duty enabled
    bank_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["type"] == "bank")
    r = client.post("/api/v1/payment-methods", json={
        "name": "StampCC", "type": "credit_card", "linked_bank_id": bank_id, "has_stamp_duty": True
    })
    assert r.status_code == 200
    card_id = r.json()["id"]

    cat_id = next(c["id"] for c in client.get("/api/v1/categories").json() if c["type"] == "Housing")

    # Transactions dated in Feb 2026 → billing_month = 2026-03-01 (credit cards bill next month)
    for amount in [50.0, 30.0]:  # total 80.0 > 77.47
        client.post("/api/v1/transactions", json={
            "date": "2026-02-10", "detail": "CC spend",
            "amount": amount, "payment_method_id": card_id,
            "category_id": cat_id, "transaction_direction": "debit",
        })

    # Transactions dated in Apr 2026 → billing_month = 2026-05-01; total 40.0 < 77.47
    client.post("/api/v1/transactions", json={
        "date": "2026-04-10", "detail": "Small CC spend",
        "amount": 40.0, "payment_method_id": card_id,
        "category_id": cat_id, "transaction_direction": "debit",
    })

    r = client.get("/api/v1/summary/2026")
    assert r.status_code == 200
    months = r.json()

    # March (month=3) should have stamp_duty == 2.0
    march = next(m for m in months if m["month"] == 3)
    assert march["stamp_duty"] == pytest.approx(2.0)

    # May (month=5) should have stamp_duty == 0.0 (spend below threshold)
    may = next(m for m in months if m["month"] == 5)
    assert may["stamp_duty"] == pytest.approx(0.0)

    # January (no CC spend) should have stamp_duty == 0.0
    january = next(m for m in months if m["month"] == 1)
    assert january["stamp_duty"] == pytest.approx(0.0)


def test_year_summary_transfers_in_bank(client):
    """transfers_in_bank should be non-zero when a transfer targets a bank-type account."""
    _setup(client)

    # Create a second bank account to receive a transfer
    r = client.post("/api/v1/payment-methods", json={"name": "SavingsBank", "type": "bank"})
    assert r.status_code == 200

    # Post a transfer with to_account_type = "bank"
    client.post("/api/v1/transfers", json={
        "date": "2026-03-15", "detail": "Transfer in",
        "amount": 300.0,
        "from_account_type": "saving", "from_account_name": "MySavings",
        "to_account_type": "bank", "to_account_name": "SavingsBank",
    })

    r = client.get("/api/v1/summary/2026")
    assert r.status_code == 200
    months = r.json()

    march = next(m for m in months if m["month"] == 3)
    assert march["transfers_in_bank"] == pytest.approx(300.0)

    # Other months should have zero transfers_in_bank
    january = next(m for m in months if m["month"] == 1)
    assert january["transfers_in_bank"] == pytest.approx(0.0)


def test_monthly_summary_no_double_query(client):
    """
    After the perf refactor, ``monthly_summary`` loads each dataset once and shares it
    with ``compute_bank_balance`` via the ``_preloaded`` hook. This test is informational:
    it exercises a month that contains both transactions and transfers to verify the
    refactor did not regress any values.
    """
    _setup(client)
    pm_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyBank")
    cat_id = next(c["id"] for c in client.get("/api/v1/categories").json() if c["type"] == "Salary")
    # Income
    client.post("/api/v1/transactions", json={
        "date": "2026-02-25", "detail": "Salary Feb", "amount": 2000,
        "payment_method_id": pm_id, "category_id": cat_id, "transaction_direction": "income",
    })
    # Debit
    housing_cat = next(c["id"] for c in client.get("/api/v1/categories").json() if c["type"] == "Housing")
    client.post("/api/v1/transactions", json={
        "date": "2026-02-05", "detail": "Rent", "amount": 800,
        "payment_method_id": pm_id, "category_id": housing_cat, "transaction_direction": "debit",
    })
    # Transfer out
    client.post("/api/v1/transfers", json={
        "date": "2026-02-10", "detail": "Savings",
        "amount": 300.0,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    })

    r = client.get("/api/v1/summary/2026/2")
    assert r.status_code == 200
    data = r.json()

    # 5000 opening + 2000 income - 800 debit - 300 transfer_out = 5900
    assert data["bank_balance"] == pytest.approx(5900.0)
    assert data["incomes"] == pytest.approx(2000.0)
    assert data["outcomes_by_method"].get("MyBank") == pytest.approx(800.0)
    assert data["transfers_out_bank"] == pytest.approx(300.0)
    assert data["transfers_in_bank"] == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("payment_method_type", "direction", "expected_balance", "expected_income", "expected_outcome"),
    [
        ("bank", "income", 5100.0, 100.0, 0.0),
        ("bank", "debit", 4900.0, 0.0, 100.0),
        ("debit_card", "debit", 4900.0, 0.0, 100.0),
        ("debit_card", "credit", 5100.0, 0.0, -100.0),
        ("credit_card", "debit", 4900.0, 0.0, 100.0),
        ("credit_card", "credit", 4900.0, 0.0, 100.0),
        ("revolving", "debit", 4900.0, 0.0, 100.0),
        ("revolving", "credit", 4900.0, 0.0, 100.0),
        ("prepaid", "income", 5000.0, 100.0, 0.0),
        ("prepaid", "debit", 5000.0, 0.0, 100.0),
        ("cash", "income", 5000.0, 100.0, 0.0),
        ("cash", "debit", 5000.0, 0.0, 100.0),
    ],
)
def test_summary_and_bank_balance_follow_transaction_matrix(
    client,
    payment_method_type,
    direction,
    expected_balance,
    expected_income,
    expected_outcome,
):
    """Valid matrix entries have matching main-bank and summary effects."""
    _setup(client)
    methods = client.get("/api/v1/payment-methods").json()
    bank_id = next(method["id"] for method in methods if method["type"] == "bank")
    payment_method = next(
        (method for method in methods if method["type"] == payment_method_type),
        None,
    )
    if payment_method is None:
        payload = {"name": f"{payment_method_type}-method", "type": payment_method_type}
        if payment_method_type in {"debit_card", "credit_card", "revolving"}:
            payload["linked_bank_id"] = bank_id
        payment_method = client.post("/api/v1/payment-methods", json=payload).json()

    response = client.post("/api/v1/transactions", json={
        "date": "2026-01-15", "detail": "Matrix transaction", "amount": 100,
        "payment_method_id": payment_method["id"],
        "transaction_direction": direction,
    })
    assert response.status_code == 200

    billing_month = response.json()["billing_month"]
    year, month, _ = billing_month.split("-")
    summary = client.get(f"/api/v1/summary/{year}/{int(month)}").json()

    assert summary["bank_balance"] == pytest.approx(expected_balance)
    assert summary["incomes"] == pytest.approx(expected_income)
    assert summary["outcomes_by_method"].get(payment_method["name"], 0.0) == pytest.approx(expected_outcome)


def test_monthly_summary_returns_stamp_duty_field(client):
    """
    monthly_summary must return a stamp_duty field of type float.
    """
    _setup(client)
    r = client.get("/api/v1/summary/2026/1")
    assert r.status_code == 200
    assert "stamp_duty" in r.json()
    assert isinstance(r.json()["stamp_duty"], float)
