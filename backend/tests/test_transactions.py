import pytest
from tests.test_onboarding import WIZARD_PAYLOAD

def _setup(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    pm_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyBank")
    cat_id = next(c["id"] for c in client.get("/api/v1/categories").json() if c["type"] == "Salary")
    return pm_id, cat_id

def test_create_transaction_sets_billing_month(client):
    pm_id, cat_id = _setup(client)
    r = client.post("/api/v1/transactions", json={
        "date": "2026-03-15", "detail": "Salary", "amount": 2500,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "income",
    })
    assert r.status_code == 200
    # bank type → billing_month = current month
    assert r.json()["billing_month"] == "2026-03-01"

def test_create_credit_card_transaction_next_month_billing(client):
    pm_id, cat_id = _setup(client)
    amex_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyCard")
    r = client.post("/api/v1/transactions", json={
        "date": "2026-03-15", "detail": "Dinner", "amount": 80,
        "payment_method_id": amex_id, "category_id": cat_id,
        "transaction_direction": "debit",
    })
    assert r.json()["billing_month"] == "2026-04-01"

def test_create_recurrence_generates_n_transactions(client):
    pm_id, cat_id = _setup(client)
    r = client.post("/api/v1/transactions", json={
        "date": "2026-01-05", "detail": "Gym", "amount": 50,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit", "recurrence_months": 6,
    })
    assert r.status_code == 200
    r2 = client.get("/api/v1/transactions", params={"billing_month": "2026-01"})
    assert any(t["detail"] == "Gym" for t in r2.json())
    all_gym = [t for t in client.get("/api/v1/transactions", params={"limit": 100}).json() if t["detail"] == "Gym"]
    assert len(all_gym) == 6

def test_delete_single(client):
    pm_id, cat_id = _setup(client)
    tx_id = client.post("/api/v1/transactions", json={
        "date": "2026-03-01", "detail": "Coffee", "amount": 3,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit",
    }).json()["id"]
    assert client.delete(f"/api/v1/transactions/{tx_id}", params={"cascade": "single"}).status_code == 200
    assert client.get(f"/api/v1/transactions/{tx_id}").status_code == 404


def test_delete_single_recurring_root_promotes_next_row(client):
    pm_id, cat_id = _setup(client)
    root_id = client.post("/api/v1/transactions", json={
        "date": "2026-01-10", "detail": "Subscription", "amount": 12,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit", "recurrence_months": 3,
    }).json()["id"]

    r = client.delete(f"/api/v1/transactions/{root_id}", params={"cascade": "single"})
    assert r.status_code == 200
    assert client.get(f"/api/v1/transactions/{root_id}").status_code == 404

    remaining = sorted(
        client.get("/api/v1/transactions", params={"limit": 100}).json(),
        key=lambda t: t["date"],
    )
    series = [t for t in remaining if t["detail"] == "Subscription"]
    assert len(series) == 2
    promoted_root = series[0]
    assert promoted_root["parent_transaction_id"] is None
    for row in series[1:]:
        assert row["parent_transaction_id"] == promoted_root["id"]


def test_delete_future_recurring(client):
    pm_id, cat_id = _setup(client)
    client.post("/api/v1/transactions", json={
        "date": "2026-01-10", "detail": "Sub", "amount": 10,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit", "recurrence_months": 4,
    })
    all_subs = [t for t in client.get("/api/v1/transactions", params={"limit": 100}).json() if t["detail"] == "Sub"]
    # Delete 2nd occurrence and future
    second = sorted(all_subs, key=lambda t: t["date"])[1]
    client.delete(f"/api/v1/transactions/{second['id']}", params={"cascade": "future"})
    remaining = [t for t in client.get("/api/v1/transactions", params={"limit": 100}).json() if t["detail"] == "Sub"]
    assert len(remaining) == 1

def test_list_filtered_by_billing_month(client):
    pm_id, cat_id = _setup(client)
    client.post("/api/v1/transactions", json={
        "date": "2026-02-10", "detail": "Feb tx", "amount": 50,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit",
    })
    r = client.get("/api/v1/transactions", params={"billing_month": "2026-02"})
    assert all(t["billing_month"].startswith("2026-02") for t in r.json())


# --- Filter tests ---

def test_list_filtered_by_payment_method(client):
    pm_id, cat_id = _setup(client)
    # Get a second payment method (MyCard)
    amex_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyCard")
    client.post("/api/v1/transactions", json={
        "date": "2026-03-10", "detail": "MyBank tx", "amount": 100,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit",
    })
    client.post("/api/v1/transactions", json={
        "date": "2026-03-10", "detail": "MyCard tx", "amount": 200,
        "payment_method_id": amex_id, "category_id": cat_id,
        "transaction_direction": "debit",
    })
    r = client.get("/api/v1/transactions", params={"payment_method_id": pm_id, "limit": 100})
    results = r.json()
    assert all(t["payment_method_id"] == pm_id for t in results)
    assert any(t["detail"] == "MyBank tx" for t in results)
    assert not any(t["detail"] == "MyCard tx" for t in results)


def test_list_filtered_by_parent_id(client):
    pm_id, cat_id = _setup(client)
    first = client.post("/api/v1/transactions", json={
        "date": "2026-01-05", "detail": "Rent", "amount": 800,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit", "recurrence_months": 3,
    }).json()
    parent_id = first["id"]
    r = client.get("/api/v1/transactions", params={"parent_id": parent_id, "limit": 100})
    children = r.json()
    # parent_id filter returns child transactions (not the root itself)
    assert len(children) == 2
    assert all(t["parent_transaction_id"] == parent_id for t in children)


# --- Invalid payment method ---

def test_create_transaction_invalid_payment_method(client):
    pm_id, cat_id = _setup(client)
    r = client.post("/api/v1/transactions", json={
        "date": "2026-03-10", "detail": "Bad PM", "amount": 50,
        "payment_method_id": "nonexistent-pm-id", "category_id": cat_id,
        "transaction_direction": "debit",
    })
    assert r.status_code == 422


@pytest.mark.parametrize("recurrence_months", [None, 3], ids=["single", "recurring"])
def test_create_transaction_rejects_inactive_payment_method_without_persisting(
    client, db, recurrence_months
):
    _, category_id = _setup(client)
    from app.models.payment_method import PaymentMethod
    from app.models.transaction import Transaction
    from app.models.user import User

    user = db.query(User).filter_by(email="alice@example.com").one()
    card = db.query(PaymentMethod).filter_by(user_id=user.id, name="MyCard").one()
    linked_bank = db.query(PaymentMethod).filter_by(user_id=user.id, name="MyBank").one()
    assert card.linked_bank_id == linked_bank.id
    assert linked_bank.is_active
    assert client.put(f"/api/v1/payment-methods/{card.id}", json={"is_active": False}).status_code == 200

    payload = {
        "date": "2026-03-10", "detail": "Inactive card activity", "amount": 50,
        "payment_method_id": card.id, "category_id": category_id,
        "transaction_direction": "debit",
    }
    if recurrence_months:
        payload["recurrence_months"] = recurrence_months
    response = client.post("/api/v1/transactions", json=payload)

    assert response.status_code == 422
    assert db.query(Transaction).filter_by(user_id=user.id).count() == 0


def test_create_transaction_rejects_foreign_category_id(client):
    """A user must not be able to create a transaction against another user's category."""
    pm_id, _ = _setup(client)

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/register", json={
        "email": "bob@example.com", "password": "Password1!", "name": "Bob"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    foreign_cat_id = next(c["id"] for c in client.get("/api/v1/categories").json() if c["type"] == "Salary")

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={
        "email": "alice@example.com", "password": "Password1!"
    })
    r = client.post("/api/v1/transactions", json={
        "date": "2026-03-10", "detail": "Bad category", "amount": 50,
        "payment_method_id": pm_id, "category_id": foreign_cat_id,
        "transaction_direction": "debit",
    })
    assert r.status_code == 422


def test_update_transaction_rejects_foreign_category_id(client):
    """A user must not be able to update a transaction to another user's category."""
    pm_id, cat_id = _setup(client)
    tx_id = client.post("/api/v1/transactions", json={
        "date": "2026-03-10", "detail": "Owned tx", "amount": 50,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit",
    }).json()["id"]

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/register", json={
        "email": "bob@example.com", "password": "Password1!", "name": "Bob"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    foreign_cat_id = next(c["id"] for c in client.get("/api/v1/categories").json() if c["type"] == "Salary")

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={
        "email": "alice@example.com", "password": "Password1!"
    })
    r = client.put(f"/api/v1/transactions/{tx_id}", json={"category_id": foreign_cat_id})
    assert r.status_code == 422


def test_update_transaction_can_clear_notes(client):
    pm_id, cat_id = _setup(client)
    tx_id = client.post("/api/v1/transactions", json={
        "date": "2026-03-10", "detail": "Owned tx", "amount": 50,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit", "notes": "remove me",
    }).json()["id"]

    r = client.put(f"/api/v1/transactions/{tx_id}", json={"notes": None})
    assert r.status_code == 200
    assert r.json()["notes"] is None
    assert client.get(f"/api/v1/transactions/{tx_id}").json()["notes"] is None


# --- GET single transaction 404 ---

def test_get_transaction_not_found(client):
    _setup(client)
    r = client.get("/api/v1/transactions/nonexistent-tx-id")
    assert r.status_code == 404


# --- Cascade update tests ---

def test_update_transaction_cascade_all(client):
    pm_id, cat_id = _setup(client)
    first = client.post("/api/v1/transactions", json={
        "date": "2026-01-10", "detail": "OldDetail", "amount": 40,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit", "recurrence_months": 3,
    }).json()
    parent_id = first["id"]
    client.put(f"/api/v1/transactions/{parent_id}", json={"detail": "NewDetail"}, params={"cascade": "all"})
    all_txs = [t for t in client.get("/api/v1/transactions", params={"limit": 100}).json()
               if t["id"] == parent_id or t.get("parent_transaction_id") == parent_id]
    assert len(all_txs) == 3
    assert all(t["detail"] == "NewDetail" for t in all_txs)


def test_update_transaction_cascade_future(client):
    pm_id, cat_id = _setup(client)
    first = client.post("/api/v1/transactions", json={
        "date": "2026-01-10", "detail": "Original", "amount": 40,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit", "recurrence_months": 3,
    }).json()
    parent_id = first["id"]
    # Get all 3 occurrences sorted by date
    all_txs = sorted(
        [t for t in client.get("/api/v1/transactions", params={"limit": 100}).json()
         if t["id"] == parent_id or t.get("parent_transaction_id") == parent_id],
        key=lambda t: t["date"],
    )
    second_id = all_txs[1]["id"]
    # Update from 2nd occurrence forward
    client.put(f"/api/v1/transactions/{second_id}", json={"detail": "Updated"}, params={"cascade": "future"})
    refreshed = {t["id"]: t for t in client.get("/api/v1/transactions", params={"limit": 100}).json()
                 if t["id"] == parent_id or t.get("parent_transaction_id") == parent_id}
    assert refreshed[all_txs[0]["id"]]["detail"] == "Original"  # 1st unchanged
    assert refreshed[all_txs[1]["id"]]["detail"] == "Updated"   # 2nd updated
    assert refreshed[all_txs[2]["id"]]["detail"] == "Updated"   # 3rd updated


# --- Cascade delete tests ---

def test_delete_transaction_cascade_all(client):
    pm_id, cat_id = _setup(client)
    first = client.post("/api/v1/transactions", json={
        "date": "2026-01-10", "detail": "AllGone", "amount": 20,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit", "recurrence_months": 3,
    }).json()
    parent_id = first["id"]
    all_before = [t for t in client.get("/api/v1/transactions", params={"limit": 100}).json()
                  if t["id"] == parent_id or t.get("parent_transaction_id") == parent_id]
    assert len(all_before) == 3
    client.delete(f"/api/v1/transactions/{parent_id}", params={"cascade": "all"})
    all_after = [t for t in client.get("/api/v1/transactions", params={"limit": 100}).json()
                 if t["id"] == parent_id or t.get("parent_transaction_id") == parent_id]
    assert len(all_after) == 0


def test_delete_transaction_cascade_future(client):
    pm_id, cat_id = _setup(client)
    first = client.post("/api/v1/transactions", json={
        "date": "2026-01-10", "detail": "PartialGone", "amount": 20,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit", "recurrence_months": 3,
    }).json()
    parent_id = first["id"]
    all_txs = sorted(
        [t for t in client.get("/api/v1/transactions", params={"limit": 100}).json()
         if t["id"] == parent_id or t.get("parent_transaction_id") == parent_id],
        key=lambda t: t["date"],
    )
    second_id = all_txs[1]["id"]
    client.delete(f"/api/v1/transactions/{second_id}", params={"cascade": "future"})
    remaining = [t for t in client.get("/api/v1/transactions", params={"limit": 100}).json()
                 if t["id"] == parent_id or t.get("parent_transaction_id") == parent_id]
    assert len(remaining) == 1
    assert remaining[0]["id"] == all_txs[0]["id"]


def test_transactions_sorted_ascending(client):
    client.post("/api/v1/auth/register", json={"email": "asc@example.com", "password": "Password1!", "name": "Asc"})
    client.post("/api/v1/auth/login", json={"email": "asc@example.com", "password": "Password1!"})

    # Create a bank payment method and category (needed by transactions)
    pm_r = client.post("/api/v1/payment-methods", json={
        "name": "Bank", "type": "bank", "is_main_bank": True, "is_active": True, "opening_balance": 0
    })
    pm_id = pm_r.json()["id"]
    cat_r = client.post("/api/v1/categories", json={"type": "Expense", "sub_type": "General"})
    cat_id = cat_r.json()["id"]

    # Insert two transactions with different dates (later first to expose ordering)
    client.post("/api/v1/transactions", json={
        "date": "2026-01-15", "detail": "B", "amount": 10,
        "payment_method_id": pm_id, "category_id": cat_id, "transaction_direction": "debit"
    })
    client.post("/api/v1/transactions", json={
        "date": "2026-01-05", "detail": "A", "amount": 5,
        "payment_method_id": pm_id, "category_id": cat_id, "transaction_direction": "debit"
    })

    r = client.get("/api/v1/transactions?billing_month=2026-01")
    dates = [t["date"] for t in r.json()]
    assert dates == sorted(dates), f"Expected ascending, got {dates}"


def test_update_recomputes_billing_month(client):
    """Saving an edit must fix a stale billing_month (regression: update used to leave it untouched)."""
    _setup(client)
    pm_r = client.post("/api/v1/payment-methods", json={
        "name": "Bank", "type": "bank", "is_main_bank": True, "is_active": True, "opening_balance": 0
    })
    pm_id = pm_r.json()["id"]
    cat_r = client.get("/api/v1/categories")
    cat_id = cat_r.json()[0]["id"]

    tx_r = client.post("/api/v1/transactions", json={
        "date": "2026-01-01", "detail": "Salary", "amount": 4535,
        "payment_method_id": pm_id, "category_id": cat_id, "transaction_direction": "income"
    })
    tx_id = tx_r.json()["id"]
    assert tx_r.json()["billing_month"].startswith("2026-01"), "Should be January"

    # Simulate stale data: force billing_month to a wrong value via direct DB manipulation is not
    # available here, so instead verify that changing the date recomputes billing_month correctly.
    put_r = client.put(f"/api/v1/transactions/{tx_id}", json={"date": "2026-02-01"})
    assert put_r.status_code // 100 == 2
    assert put_r.json()["billing_month"].startswith("2026-02"), (
        f"billing_month should update to Feb after date change, got {put_r.json()['billing_month']}"
    )


def test_date_month_filters_by_transaction_date(client):
    """date_month must filter by actual date, not billing_month (credit card shifts billing but not date)."""
    _setup(client)
    bank_r = client.post("/api/v1/payment-methods", json={
        "name": "Bank", "type": "bank", "is_main_bank": True, "is_active": True, "opening_balance": 0
    })
    cc_r = client.post("/api/v1/payment-methods", json={
        "name": "CC", "type": "credit_card", "linked_bank_id": bank_r.json()["id"],
        "is_main_bank": False, "is_active": True,
    })
    cat_id = client.get("/api/v1/categories").json()[0]["id"]

    # Credit card transaction dated January — billing_month will shift to February
    client.post("/api/v1/transactions", json={
        "date": "2026-01-15", "detail": "CC Jan", "amount": 50,
        "payment_method_id": cc_r.json()["id"], "category_id": cat_id, "transaction_direction": "debit"
    })
    # Bank transaction dated January — billing_month stays January
    client.post("/api/v1/transactions", json={
        "date": "2026-01-20", "detail": "Bank Jan", "amount": 100,
        "payment_method_id": bank_r.json()["id"], "category_id": cat_id, "transaction_direction": "debit"
    })

    # date_month=2026-01 must return BOTH (both dated in January)
    r = client.get("/api/v1/transactions?date_month=2026-01")
    details = [t["detail"] for t in r.json()]
    assert "CC Jan" in details, "CC Jan transaction should appear in January by date"
    assert "Bank Jan" in details

    # billing_month=2026-01 must return only the bank one (CC shifted to February)
    r2 = client.get("/api/v1/transactions?billing_month=2026-01")
    details2 = [t["detail"] for t in r2.json()]
    assert "Bank Jan" in details2
    assert "CC Jan" not in details2, "CC Jan should NOT appear in billing_month=January (shifted to Feb)"


def test_update_transaction_fails_if_pm_deleted(client, db):
    """Updating a transaction whose PM has been deleted should return 422."""
    from app.models.payment_method import PaymentMethod

    client.post("/api/v1/auth/register", json={
        "email": "h2@example.com", "password": "Password1!", "name": "H2"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)

    pms = client.get("/api/v1/payment-methods").json()
    pm_id = next(pm["id"] for pm in pms if pm["name"] == "MyBank")
    cat_id = next(c["id"] for c in client.get("/api/v1/categories").json() if c["type"] == "Salary")

    r = client.post("/api/v1/transactions", json={
        "date": "2026-03-10", "detail": "Test", "amount": 100,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "income",
    })
    tx_id = r.json()["id"]

    # Directly delete the PM from DB to simulate orphan state
    pm_obj = db.get(PaymentMethod, pm_id)
    db.delete(pm_obj)
    db.commit()

    r2 = client.put(f"/api/v1/transactions/{tx_id}", json={"detail": "Updated"})
    assert r2.status_code == 422


def test_cascade_all_update_does_not_change_sibling_dates(client):
    """Cascade-updating amount on a recurring series must not collapse all dates to one."""
    pm_id, cat_id = _setup(client)
    client.post("/api/v1/transactions", json={
        "date": "2026-01-10", "detail": "RentCascadeTest", "amount": 800,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit", "recurrence_months": 3,
    })
    txs = sorted(
        [t for t in client.get("/api/v1/transactions", params={"limit": 100}).json() if t["detail"] == "RentCascadeTest"],
        key=lambda t: t["date"],
    )
    assert len(txs) == 3
    first_id = txs[0]["id"]
    # Update amount for all, include a date — date should NOT propagate to siblings
    client.put(f"/api/v1/transactions/{first_id}",
               params={"cascade": "all"},
               json={"amount": 850, "date": "2026-01-15"})
    updated = sorted(
        [t for t in client.get("/api/v1/transactions", params={"limit": 100}).json() if t["detail"] == "RentCascadeTest"],
        key=lambda t: t["date"],
    )
    assert len(updated) == 3
    dates = {t["date"] for t in updated}
    assert len(dates) == 3, f"Cascade update collapsed dates: {dates}"


def test_create_credit_on_bank_pm_returns_422(client):
    """A 'credit' direction on a bank PM is nonsense (only income/debit allowed) — reject it."""
    pm_id, cat_id = _setup(client)
    r = client.post("/api/v1/transactions", json={
        "date": "2026-03-10", "detail": "Bad credit on bank", "amount": 50,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "credit",
    })
    assert r.status_code == 422


def test_create_credit_on_cash_pm_returns_422(client):
    """A 'credit' direction on a cash PM must be rejected server-side."""
    pm_id, cat_id = _setup(client)
    cash = client.post("/api/v1/payment-methods", json={"name": "Wallet", "type": "cash"}).json()
    r = client.post("/api/v1/transactions", json={
        "date": "2026-03-10", "detail": "Bad credit on cash", "amount": 20,
        "payment_method_id": cash["id"], "category_id": cat_id,
        "transaction_direction": "credit",
    })
    assert r.status_code == 422


def test_create_income_on_credit_card_returns_422(client):
    """A credit_card PM only accepts 'debit' — income must be rejected."""
    pm_id, cat_id = _setup(client)
    amex_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyCard")
    r = client.post("/api/v1/transactions", json={
        "date": "2026-03-10", "detail": "Bad income on CC", "amount": 50,
        "payment_method_id": amex_id, "category_id": cat_id,
        "transaction_direction": "income",
    })
    assert r.status_code == 422


def test_create_valid_direction_combinations_succeed(client):
    """Valid (pm type, direction) combinations still create transactions."""
    pm_id, cat_id = _setup(client)
    amex_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyCard")
    # income on bank
    assert client.post("/api/v1/transactions", json={
        "date": "2026-03-10", "detail": "Salary", "amount": 2500,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "income",
    }).status_code == 200
    # debit on bank
    assert client.post("/api/v1/transactions", json={
        "date": "2026-03-11", "detail": "Rent", "amount": 900,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit",
    }).status_code == 200
    # debit on credit_card
    assert client.post("/api/v1/transactions", json={
        "date": "2026-03-12", "detail": "Dinner", "amount": 80,
        "payment_method_id": amex_id, "category_id": cat_id,
        "transaction_direction": "debit",
    }).status_code == 200


def test_create_credit_on_revolving_pm_succeeds(client):
    """revolving PMs accept both debit and credit."""
    pm_id, cat_id = _setup(client)
    rev = client.post(
        "/api/v1/payment-methods",
        json={"name": "Revolving", "type": "revolving", "linked_bank_id": pm_id},
    ).json()
    assert client.post("/api/v1/transactions", json={
        "date": "2026-03-10", "detail": "Payoff", "amount": 100,
        "payment_method_id": rev["id"], "category_id": cat_id,
        "transaction_direction": "credit",
    }).status_code == 200


def test_create_credit_on_credit_card_succeeds(client):
    """credit_card PMs accept credit (payoff/refund) — bank_balance gives it defined semantics."""
    pm_id, cat_id = _setup(client)
    cc = client.post(
        "/api/v1/payment-methods",
        json={"name": "CreditCC", "type": "credit_card", "linked_bank_id": pm_id},
    ).json()
    assert client.post("/api/v1/transactions", json={
        "date": "2026-03-10", "detail": "CC payoff", "amount": 100,
        "payment_method_id": cc["id"], "category_id": cat_id,
        "transaction_direction": "credit",
    }).status_code == 200


def test_update_to_invalid_direction_row_returns_422(client, db):
    """Editing a transaction whose stored (pm type, direction) is invalid must be rejected."""
    from app.models.transaction import Transaction

    pm_id, cat_id = _setup(client)
    tx_id = client.post("/api/v1/transactions", json={
        "date": "2026-03-10", "detail": "Legit", "amount": 50,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit",
    }).json()["id"]

    # Simulate a legacy/corrupt row: credit directly on a bank PM.
    tx = db.get(Transaction, tx_id)
    tx.transaction_direction = "credit"
    db.commit()

    r = client.put(f"/api/v1/transactions/{tx_id}", json={"detail": "Edited"})
    assert r.status_code == 422


def test_create_transaction_rejects_zero_amount(client):
    pm_id, cat_id = _setup(client)
    resp = client.post("/api/v1/transactions", json={
        "date": "2026-03-01", "detail": "BadZero", "amount": 0,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit",
    })
    assert resp.status_code == 422


def test_create_transaction_rejects_negative_amount(client):
    pm_id, cat_id = _setup(client)
    resp = client.post("/api/v1/transactions", json={
        "date": "2026-03-01", "detail": "BadNeg", "amount": -50,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit",
    })
    assert resp.status_code == 422


def test_transaction_list_order_is_stable(client):
    """Two transactions with the same date must always appear in the same order."""
    client.post("/api/v1/auth/register", json={
        "email": "stable@test.com", "password": "Password1!", "name": "Stable"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)

    pms = client.get("/api/v1/payment-methods").json()
    pm_id = next(pm["id"] for pm in pms if pm["name"] == "MyBank")
    cat_id = next(c["id"] for c in client.get("/api/v1/categories").json() if c["type"] == "Salary")

    for detail in ["Alpha", "Beta", "Gamma"]:
        client.post("/api/v1/transactions", json={
            "date": "2026-03-15", "detail": detail, "amount": 10,
            "payment_method_id": pm_id, "category_id": cat_id,
            "transaction_direction": "debit",
        })

    r1 = client.get("/api/v1/transactions", params={"billing_month": "2026-03"}).json()
    r2 = client.get("/api/v1/transactions", params={"billing_month": "2026-03"}).json()
    assert [t["id"] for t in r1] == [t["id"] for t in r2], "Order is not stable"


# --- Group 1 new tests ---

def test_list_filtered_by_date_month(client):
    """date_month=YYYY-MM returns only transactions whose date falls in that month."""
    pm_id, cat_id = _setup(client)
    client.post("/api/v1/transactions", json={
        "date": "2026-03-10", "detail": "March tx", "amount": 100,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit",
    })
    client.post("/api/v1/transactions", json={
        "date": "2026-04-05", "detail": "April tx", "amount": 200,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit",
    })
    r = client.get("/api/v1/transactions", params={"date_month": "2026-03"})
    details = [t["detail"] for t in r.json()]
    assert "March tx" in details
    assert "April tx" not in details


def test_list_limit_and_offset(client):
    """limit and offset work correctly for pagination."""
    pm_id, cat_id = _setup(client)
    for i in range(1, 4):
        client.post("/api/v1/transactions", json={
            "date": f"2026-03-{i:02d}", "detail": f"tx{i}", "amount": i * 10,
            "payment_method_id": pm_id, "category_id": cat_id,
            "transaction_direction": "debit",
        })
    # limit=2 returns at most 2 rows
    r_limit = client.get("/api/v1/transactions", params={"limit": 2})
    assert len(r_limit.json()) == 2

    # offset=2 with a large limit returns the remaining 1 row
    r_offset = client.get("/api/v1/transactions", params={"offset": 2, "limit": 10})
    assert len(r_offset.json()) == 1


def test_update_transaction_plain_single(client):
    """PUT with cascade=single updates only the target transaction's amount."""
    pm_id, cat_id = _setup(client)
    tx = client.post("/api/v1/transactions", json={
        "date": "2026-03-15", "detail": "SingleUpdate", "amount": 50,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit",
    }).json()
    tx_id = tx["id"]
    r = client.put(f"/api/v1/transactions/{tx_id}", json={"amount": 75}, params={"cascade": "single"})
    assert r.status_code == 200
    updated = r.json()
    assert float(updated["amount"]) == pytest.approx(75.0)
    # Other fields unchanged
    assert updated["detail"] == "SingleUpdate"
    assert updated["payment_method_id"] == pm_id


@pytest.mark.parametrize("cascade_val", ["FUTURE", "futur", "ALL", "SINGLE", "bogus"])
def test_update_transaction_invalid_cascade_returns_422(client, cascade_val):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    from tests.test_onboarding import WIZARD_PAYLOAD
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    pm_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyBank")
    tx = client.post("/api/v1/transactions", json={
        "date": "2026-01-10", "detail": "Test", "amount": 10,
        "payment_method_id": pm_id, "transaction_direction": "debit",
    }).json()
    r = client.put(f"/api/v1/transactions/{tx['id']}?cascade={cascade_val}", json={"detail": "x"})
    assert r.status_code == 422


@pytest.mark.parametrize("cascade_val", ["FUTURE", "futur", "ALL", "SINGLE", "bogus"])
def test_delete_transaction_invalid_cascade_returns_422(client, cascade_val):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    from tests.test_onboarding import WIZARD_PAYLOAD
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    pm_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyBank")
    tx = client.post("/api/v1/transactions", json={
        "date": "2026-01-10", "detail": "Test", "amount": 10,
        "payment_method_id": pm_id, "transaction_direction": "debit",
    }).json()
    r = client.delete(f"/api/v1/transactions/{tx['id']}?cascade={cascade_val}")
    assert r.status_code == 422


def test_create_transaction_invalid_date_returns_422(client):
    """An unparseable date string must return 422, not 500."""
    pm_id, cat_id = _setup(client)
    r = client.post("/api/v1/transactions", json={
        "date": "not-a-date", "detail": "X", "amount": 10,
        "payment_method_id": pm_id, "transaction_direction": "debit",
    })
    assert r.status_code == 422


@pytest.mark.parametrize(
    ("payment_method_type", "direction", "expected_status"),
    [
        ("bank", "income", 200), ("bank", "debit", 200), ("bank", "credit", 422),
        ("debit_card", "income", 422), ("debit_card", "debit", 200), ("debit_card", "credit", 200),
        ("credit_card", "income", 422), ("credit_card", "debit", 200), ("credit_card", "credit", 200),
        ("revolving", "income", 422), ("revolving", "debit", 200), ("revolving", "credit", 200),
        ("prepaid", "income", 200), ("prepaid", "debit", 200), ("prepaid", "credit", 422),
        ("cash", "income", 200), ("cash", "debit", 200), ("cash", "credit", 422),
    ],
)
def test_transaction_api_enforces_payment_method_direction_matrix(
    client, payment_method_type, direction, expected_status
):
    """Every payment-method/direction pair is accepted or rejected by the documented matrix."""
    bank_id, category_id = _setup(client)
    methods = client.get("/api/v1/payment-methods").json()
    payment_method_id = next(
        (method["id"] for method in methods if method["type"] == payment_method_type),
        None,
    )
    if payment_method_id is None:
        payload = {"name": f"{payment_method_type}-method", "type": payment_method_type}
        if payment_method_type in {"debit_card", "credit_card", "revolving"}:
            payload["linked_bank_id"] = bank_id
        payment_method_id = client.post("/api/v1/payment-methods", json=payload).json()["id"]

    response = client.post("/api/v1/transactions", json={
        "date": "2026-01-15", "detail": "Matrix transaction", "amount": 10,
        "payment_method_id": payment_method_id, "category_id": category_id,
        "transaction_direction": direction,
    })

    assert response.status_code == expected_status


def test_unlinked_bank_funded_card_activity_is_rejected(client, db):
    _, category_id = _setup(client)
    from app.models.payment_method import PaymentMethod
    from app.models.user import User

    user = db.query(User).filter_by(email="alice@example.com").one()
    card = PaymentMethod(user_id=user.id, name="Legacy unlinked card", type="credit_card")
    db.add(card)
    db.commit()

    response = client.post("/api/v1/transactions", json={
        "date": "2026-01-15", "detail": "Unsupported card activity", "amount": 10,
        "payment_method_id": card.id, "category_id": category_id,
        "transaction_direction": "debit",
    })

    assert response.status_code == 422


def test_inactive_current_card_link_preserves_historical_activity_but_rejects_new_activity(client, db):
    _, category_id = _setup(client)
    from app.models.user import User
    from app.services.bank_balance import compute_bank_balance

    methods = client.get("/api/v1/payment-methods").json()
    card_id = next(pm["id"] for pm in methods if pm["name"] == "MyBank Debit")
    second_bank_id = next(pm["id"] for pm in methods if pm["name"] == "SecondBank")

    historical = client.post("/api/v1/transactions", json={
        "date": "2026-01-15", "detail": "Historical card purchase", "amount": 10,
        "payment_method_id": card_id, "category_id": category_id,
        "transaction_direction": "debit",
    })
    assert historical.status_code == 200
    assert client.put(f"/api/v1/payment-methods/{card_id}", json={
        "linked_bank_id": second_bank_id, "effective_billing_month": "2026-02-01",
    }).status_code == 200
    assert client.put(
        f"/api/v1/payment-methods/{second_bank_id}", json={"is_active": False}
    ).status_code == 200

    response = client.post("/api/v1/transactions", json={
        "date": "2026-02-15", "detail": "Inactive linked bank purchase", "amount": 20,
        "payment_method_id": card_id, "category_id": category_id,
        "transaction_direction": "debit",
    })

    assert response.status_code == 422
    user = db.query(User).filter_by(email="alice@example.com").one()
    assert compute_bank_balance(user.id, 2026, 2, db) == pytest.approx(4990.0)


def test_list_transactions_requires_filter(client):
    """GET /transactions with no billing_month, date_month, or limit must return HTTP 400."""
    _setup(client)
    r = client.get("/api/v1/transactions")
    assert r.status_code == 400
    assert "billing_month" in r.json()["detail"] or "required" in r.json()["detail"].lower()
