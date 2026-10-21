from tests.test_onboarding import WIZARD_PAYLOAD


def test_pension_balances_include_historical_compact_transfer_dates(client, db):
    from app.models.transfer import Transfer

    assert client.post("/api/v1/auth/register", json={
        "email": "pension-date@example.com", "password": "Password1!", "name": "Pension",
    }).status_code == 200
    payload = {**WIZARD_PAYLOAD, "salary": None, "pension": None}
    assert client.post("/api/v1/onboarding", json=payload).status_code == 200
    account = client.post("/api/v1/accounts", json={
        "type": "pension", "name": "Pension Fund", "opening_balance": 0,
        "opening_balance_month": "2026-01-01",
    }).json()
    response = client.post("/api/v1/transfers", json={
        "date": "2026-01-20", "amount": 100,
        "from_account_type": "saving", "from_account_name": "MySavings",
        "to_account_type": "pension", "to_account_id": account["id"],
    })
    assert response.status_code == 200, response.text
    transfer = db.query(Transfer).filter_by(id=response.json()["id"]).one()
    transfer.date = "20260120"
    db.commit()
    next_month = client.post("/api/v1/transfers", json={
        "date": "2026-02-05", "amount": 50,
        "from_account_type": "saving", "from_account_name": "MySavings",
        "to_account_type": "pension", "to_account_id": account["id"],
    })
    assert next_month.status_code == 200, next_month.text

    january = client.get("/api/v1/assets/2026?as_of=2026-01-01")
    assert january.status_code == 200, january.text
    row = next(row for row in january.json() if row["account_id"] == account["id"])
    assert row["computed_amount"] == 100

    february = client.get("/api/v1/assets/2026?as_of=2026-02-01")
    assert february.status_code == 200, february.text
    row = next(row for row in february.json() if row["account_id"] == account["id"])
    assert row["computed_amount"] == 150

    december = client.get("/api/v1/assets/2025?as_of=2025-12-01")
    assert december.status_code == 200, december.text
    assert all(row["account_id"] != account["id"] for row in december.json())
