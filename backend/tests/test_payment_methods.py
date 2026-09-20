import pytest


def _setup(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    from tests.test_onboarding import WIZARD_PAYLOAD
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)

def test_list_payment_methods(client):
    _setup(client)
    r = client.get("/api/v1/payment-methods")
    assert r.status_code == 200
    assert any(pm["name"] == "MyBank" for pm in r.json())

def test_create_payment_method(client):
    _setup(client)
    r = client.post("/api/v1/payment-methods", json={"name": "MyPrepaid", "type": "prepaid"})
    assert r.status_code == 200
    assert r.json()["name"] == "MyPrepaid"

def test_create_bank_funded_card_requires_linked_bank(client):
    _setup(client)
    response = client.post("/api/v1/payment-methods", json={"name": "Unlinked", "type": "credit_card"})
    assert response.status_code == 422


def test_create_card_rejects_inactive_linked_bank(client):
    _setup(client)
    inactive_bank_id = next(
        pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "SecondBank"
    )
    assert client.put(f"/api/v1/payment-methods/{inactive_bank_id}", json={"is_active": False}).status_code == 200

    response = client.post("/api/v1/payment-methods", json={
        "name": "Inactive linked card", "type": "credit_card", "linked_bank_id": inactive_bank_id,
    })

    assert response.status_code == 422


def test_rename_payment_method(client):
    _setup(client)
    pm_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyBank")
    client.put(f"/api/v1/payment-methods/{pm_id}", json={"name": "MyBankRenamed"})
    names = [pm["name"] for pm in client.get("/api/v1/payment-methods").json()]
    assert "MyBankRenamed" in names

def test_deactivate_payment_method(client):
    _setup(client)
    pm_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyCard")
    client.put(f"/api/v1/payment-methods/{pm_id}", json={"is_active": False})
    pm = next(m for m in client.get("/api/v1/payment-methods?active_only=false").json() if m["id"] == pm_id)
    assert pm["is_active"] is False

def test_set_main_bank_switches_flag(client):
    _setup(client)
    methods = client.get("/api/v1/payment-methods").json()
    bbva_id = next(pm["id"] for pm in methods if pm["name"] == "SecondBank")
    r = client.post(f"/api/v1/payment-methods/{bbva_id}/set-main-bank", json={"opening_balance": 2000.0})
    assert r.status_code == 200
    methods = client.get("/api/v1/payment-methods").json()
    assert not next(pm for pm in methods if pm["name"] == "MyBank")["is_main_bank"]
    assert next(pm for pm in methods if pm["name"] == "SecondBank")["is_main_bank"]

def test_set_main_bank_on_non_bank_type_returns_422(client):
    _setup(client)
    amex_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyCard")
    r = client.post(f"/api/v1/payment-methods/{amex_id}/set-main-bank", json={"opening_balance": 0})
    assert r.status_code == 422

def test_main_bank_history_contains_two_rows_after_switch(client):
    _setup(client)
    bbva_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "SecondBank")
    client.post(f"/api/v1/payment-methods/{bbva_id}/set-main-bank", json={"opening_balance": 2000.0})
    r = client.get("/api/v1/payment-methods/main-bank-history")
    assert len(r.json()) == 2


def test_set_main_bank_replaces_same_month_history_row(client):
    _setup(client)
    methods = client.get("/api/v1/payment-methods").json()
    second_id = next(pm["id"] for pm in methods if pm["name"] == "SecondBank")
    main_id = next(pm["id"] for pm in methods if pm["name"] == "MyBank")

    assert client.post(f"/api/v1/payment-methods/{second_id}/set-main-bank", json={"opening_balance": 2000.0}).status_code == 200
    assert client.post(f"/api/v1/payment-methods/{main_id}/set-main-bank", json={"opening_balance": 3000.0}).status_code == 200

    history = client.get("/api/v1/payment-methods/main-bank-history").json()
    current_month_rows = [row for row in history if row["valid_from"] != "2026-01-01"]
    assert len(current_month_rows) == 1
    assert current_month_rows[0]["payment_method_id"] == main_id


def test_active_only_excludes_inactive(client):
    _setup(client)
    # Create a payment method
    bank_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["type"] == "bank")
    r = client.post("/api/v1/payment-methods", json={
        "name": "My Card", "type": "credit_card", "linked_bank_id": bank_id,
        "is_main_bank": False, "is_active": True,
    })
    pm_id = r.json()["id"]
    # Deactivate it
    r = client.put(f"/api/v1/payment-methods/{pm_id}", json={"is_active": False})
    assert r.status_code // 100 == 2
    # Default (active_only=true) should not include it
    r = client.get("/api/v1/payment-methods")
    names = [m["name"] for m in r.json()]
    assert "My Card" not in names
    # Explicit false should include it
    r = client.get("/api/v1/payment-methods?active_only=false")
    names = [m["name"] for m in r.json()]
    assert "My Card" in names


def test_duplicate_pm_name_returns_422(client):
    """Creating two payment methods with the same name for the same user must return 422."""
    _setup(client)
    resp1 = client.post("/api/v1/payment-methods", json={"name": "DupTest", "type": "bank"})
    assert resp1.status_code == 200
    resp2 = client.post("/api/v1/payment-methods", json={"name": "DupTest", "type": "bank"})
    assert resp2.status_code == 422


def test_stamp_duty_appears_in_monthly_summary(client):
    """Credit card with has_stamp_duty=True and spend > 77.47 → stamp_duty == 2.0 in summary."""
    client.post("/api/v1/auth/register", json={
        "email": "stamp@example.com", "password": "Password1!", "name": "Stamp"
    })
    from tests.test_onboarding import WIZARD_PAYLOAD
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)

    # Create a credit card with stamp duty enabled
    bank_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["type"] == "bank")
    r = client.post("/api/v1/payment-methods", json={
        "name": "StampCard", "type": "credit_card", "linked_bank_id": bank_id, "has_stamp_duty": True
    })
    assert r.status_code == 200
    card_id = r.json()["id"]

    # Create a category for the transactions
    cat_r = client.post("/api/v1/categories", json={"type": "expense", "sub_type": "general"})
    assert cat_r.status_code == 200
    cat_id = cat_r.json()["id"]

    # Post two transactions on this card dated in March 2026.
    # Credit cards bill next month, so billing_month will be 2026-04-01.
    for amount in [50.00, 30.00]:
        tx_r = client.post("/api/v1/transactions", json={
            "date": "2026-03-15",
            "detail": "Purchase",
            "amount": amount,
            "payment_method_id": card_id,
            "category_id": cat_id,
            "transaction_direction": "debit",
        })
        assert tx_r.status_code == 200

    # Query the monthly summary for April 2026 (credit card billing month)
    r = client.get("/api/v1/summary/2026/4")
    assert r.status_code == 200
    data = r.json()
    assert data["stamp_duty"] == 2.0


def test_rename_collision_returns_422(client):
    """Renaming PM2 to PM1's existing name must return 422."""
    _setup(client)

    # Create two distinct payment methods
    r1 = client.post("/api/v1/payment-methods", json={"name": "Alpha", "type": "prepaid"})
    assert r1.status_code == 200

    r2 = client.post("/api/v1/payment-methods", json={"name": "Beta", "type": "prepaid"})
    assert r2.status_code == 200
    beta_id = r2.json()["id"]

    # Try to rename Beta → Alpha (collision)
    resp = client.put(f"/api/v1/payment-methods/{beta_id}", json={"name": "Alpha"})
    assert resp.status_code == 422


def test_set_main_bank_on_inactive_pm_returns_422(client):
    """set-main-bank on an inactive bank-type PM must be rejected with 422."""
    _setup(client)

    # Create a bank PM and immediately deactivate it
    r = client.post("/api/v1/payment-methods", json={"name": "InactiveBank", "type": "bank"})
    assert r.status_code == 200
    pm_id = r.json()["id"]

    client.put(f"/api/v1/payment-methods/{pm_id}", json={"is_active": False})

    # Attempt to make it main bank
    resp = client.post(f"/api/v1/payment-methods/{pm_id}/set-main-bank", json={"opening_balance": 0})
    assert resp.status_code == 422


def test_pm_rename_cascades_to_transfers(client):
    """Renaming a PM must update all Transfer rows referencing its old name."""
    from tests.test_onboarding import WIZARD_PAYLOAD

    client.post("/api/v1/auth/register", json={
        "email": "rename@test.com", "password": "Password1!", "name": "Rename"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)

    pms = client.get("/api/v1/payment-methods").json()
    fineco = next(pm for pm in pms if pm["name"] == "MyBank")

    # Create a transfer FROM MyBank
    client.post("/api/v1/transfers", json={
        "date": "2026-03-10", "detail": "To savings", "amount": 500,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    })

    # Rename MyBank → NewBank
    r = client.put(f"/api/v1/payment-methods/{fineco['id']}", json={"name": "NewBank"})
    assert r.status_code == 200

    # The transfer's from_account_name must now be "NewBank"
    transfers = client.get("/api/v1/transfers", params={"limit": 100}).json()
    assert any(t["from_account_name"] == "NewBank" for t in transfers), \
        "Transfer not updated after PM rename"
    assert not any(t["from_account_name"] == "MyBank" for t in transfers), \
        "Old PM name still present in transfers after rename"


def test_bank_rename_updates_only_matching_bank_transfer_endpoints(client, db):
    """A bank rename cannot rewrite same-named non-bank transfer snapshots."""
    _setup(client)
    from app.models.payment_method import PaymentMethod
    from app.models.transfer import Transfer

    methods = client.get("/api/v1/payment-methods").json()
    bank_id = next(method["id"] for method in methods if method["name"] == "MyBank")
    saving_id = client.post("/api/v1/accounts", json={
        "type": "saving", "name": "MyBank", "opening_balance": 0,
    }).json()["id"]
    owner_id = db.get(PaymentMethod, bank_id).user_id

    transfers = [
        Transfer(
            user_id=owner_id, date="2026-03-01", detail="stable from", amount=1,
            from_account_type="bank", from_account_name="MyBank", from_payment_method_id=bank_id,
            to_account_type="saving", to_account_name="MyBank", to_account_id=saving_id,
            billing_month="2026-03-01",
        ),
        Transfer(
            user_id=owner_id, date="2026-03-01", detail="stable to", amount=1,
            from_account_type="saving", from_account_name="MyBank", from_account_id=saving_id,
            to_account_type="bank", to_account_name="MyBank", to_payment_method_id=bank_id,
            billing_month="2026-03-01",
        ),
        Transfer(
            user_id=owner_id, date="2026-03-01", detail="legacy from", amount=1,
            from_account_type="bank", from_account_name="MyBank",
            to_account_type="saving", to_account_name="MyBank", to_account_id=saving_id,
            billing_month="2026-03-01",
        ),
        Transfer(
            user_id=owner_id, date="2026-03-01", detail="legacy to", amount=1,
            from_account_type="saving", from_account_name="MyBank", from_account_id=saving_id,
            to_account_type="bank", to_account_name="MyBank",
            billing_month="2026-03-01",
        ),
    ]
    db.add_all(transfers)
    db.commit()
    transfer_ids = [transfer.id for transfer in transfers]

    response = client.put(f"/api/v1/payment-methods/{bank_id}", json={"name": "RenamedBank"})
    assert response.status_code == 200

    db.expire_all()
    stable_from, stable_to, legacy_from, legacy_to = [db.get(Transfer, transfer_id) for transfer_id in transfer_ids]
    assert stable_from.from_account_name == "RenamedBank"
    assert stable_from.to_account_name == "MyBank"
    assert stable_to.from_account_name == "MyBank"
    assert stable_to.to_account_name == "RenamedBank"
    assert legacy_from.from_account_name == "RenamedBank"
    assert legacy_from.to_account_name == "MyBank"
    assert legacy_to.from_account_name == "MyBank"
    assert legacy_to.to_account_name == "RenamedBank"


def test_create_payment_method_invalid_type_returns_422(client):
    _setup(client)
    r = client.post("/api/v1/payment-methods", json={"name": "X", "type": "crypto"})
    assert r.status_code == 422


def test_update_payment_method_rejects_foreign_linked_bank_id(client):
    """linked_bank_id on update must belong to the current user."""
    _setup(client)
    card_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyCard")

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/register", json={
        "email": "bob@example.com", "password": "Password1!", "name": "Bob"
    })
    from tests.test_onboarding import WIZARD_PAYLOAD
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    foreign_bank_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["type"] == "bank")

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={
        "email": "alice@example.com", "password": "Password1!"
    })
    r = client.put(f"/api/v1/payment-methods/{card_id}", json={
        "linked_bank_id": foreign_bank_id, "effective_billing_month": "2026-02-01",
    })
    assert r.status_code == 422


def test_update_payment_method_rejects_non_bank_linked_bank_id(client):
    _setup(client)
    card_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyCard")
    wallet_id = client.post("/api/v1/payment-methods", json={"name": "Wallet", "type": "prepaid"}).json()["id"]

    r = client.put(f"/api/v1/payment-methods/{card_id}", json={
        "linked_bank_id": wallet_id, "effective_billing_month": "2026-02-01",
    })
    assert r.status_code == 422


def test_update_payment_method_cannot_clear_linked_bank_id_for_bank_funded_card(client):
    _setup(client)
    methods = client.get("/api/v1/payment-methods").json()
    bank_id = next(pm["id"] for pm in methods if pm["type"] == "bank")
    card_id = next(pm["id"] for pm in methods if pm["name"] == "MyCard")

    r = client.put(f"/api/v1/payment-methods/{card_id}", json={
        "linked_bank_id": None, "effective_billing_month": "2026-02-01",
    })
    assert r.status_code == 422


@pytest.mark.parametrize("effective_billing_month", ["20260201", "2026-02-02", "invalid-date", None])
def test_relink_requires_a_first_of_month_billing_period(client, effective_billing_month):
    _setup(client)
    methods = client.get("/api/v1/payment-methods").json()
    card_id = next(pm["id"] for pm in methods if pm["name"] == "MyCard")
    second_bank_id = next(pm["id"] for pm in methods if pm["name"] == "SecondBank")

    response = client.put(f"/api/v1/payment-methods/{card_id}", json={
        "linked_bank_id": second_bank_id,
        "effective_billing_month": effective_billing_month,
    })

    assert response.status_code == 422


def test_relink_requires_effective_period_and_rejects_overlapping_period(client):
    _setup(client)
    methods = client.get("/api/v1/payment-methods").json()
    card_id = next(pm["id"] for pm in methods if pm["name"] == "MyCard")
    main_bank_id = next(pm["id"] for pm in methods if pm["name"] == "MyBank")
    second_bank_id = next(pm["id"] for pm in methods if pm["name"] == "SecondBank")

    assert client.put(f"/api/v1/payment-methods/{card_id}", json={
        "linked_bank_id": second_bank_id,
    }).status_code == 422
    assert client.put(f"/api/v1/payment-methods/{card_id}", json={
        "linked_bank_id": second_bank_id, "effective_billing_month": "2026-03-01",
    }).status_code == 200
    overlap = client.put(f"/api/v1/payment-methods/{card_id}", json={
        "linked_bank_id": main_bank_id, "effective_billing_month": "2026-02-01",
    })
    assert overlap.status_code == 422


def test_relink_rejects_nonexistent_bank(client):
    _setup(client)
    card_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyCard")

    response = client.put(f"/api/v1/payment-methods/{card_id}", json={
        "linked_bank_id": "missing-bank", "effective_billing_month": "2026-02-01",
    })

    assert response.status_code == 422


def test_relink_rejects_inactive_bank(client):
    _setup(client)
    methods = client.get("/api/v1/payment-methods").json()
    card_id = next(pm["id"] for pm in methods if pm["name"] == "MyCard")
    inactive_bank_id = next(pm["id"] for pm in methods if pm["name"] == "SecondBank")
    assert client.put(f"/api/v1/payment-methods/{inactive_bank_id}", json={"is_active": False}).status_code == 200

    response = client.put(f"/api/v1/payment-methods/{card_id}", json={
        "linked_bank_id": inactive_bank_id, "effective_billing_month": "2026-02-01",
    })

    assert response.status_code == 422
