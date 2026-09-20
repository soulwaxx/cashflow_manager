"""
Cross-user isolation tests.

Verifies that User B cannot read, update, or delete resources that belong to User A
across all major domain endpoints. Each test follows the pattern:

1. Register + onboard User A (alice@example.com), create the resource.
2. Register User B (bob@example.com) and log in (cookie is replaced on the same client).
3. Attempt GET / PUT|PATCH / DELETE on User A's resource ID — expect 404.
"""

import pytest
from tests.test_onboarding import WIZARD_PAYLOAD

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_ALICE = {"email": "alice@example.com", "password": "Password1!", "name": "Alice"}
_BOB   = {"email": "bob@example.com",   "password": "Password1!", "name": "Bob"}

_MINIMAL_ONBOARDING = {
    "tracking_start_date": "2026-01-01",
    "main_bank": {"name": "BobBank", "opening_balance": 1000.0},
}


def _register_and_onboard_alice(client):
    """Register Alice, run full onboarding, return (pm_id, cat_id)."""
    client.post("/api/v1/auth/register", json=_ALICE)
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    pm_id  = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyBank")
    cat_id = next(c["id"]  for c  in client.get("/api/v1/categories").json()       if c["type"]  == "Salary")
    return pm_id, cat_id


def _switch_to_bob(client):
    """Register Bob (if not yet registered) and log in, replacing the session cookie."""
    client.post("/api/v1/auth/register", json=_BOB)
    client.post("/api/v1/auth/login",    json={"email": _BOB["email"], "password": _BOB["password"]})


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def _alice_transaction(client):
    """Set up Alice's data and return a transaction id owned by her."""
    pm_id, cat_id = _register_and_onboard_alice(client)
    r = client.post("/api/v1/transactions", json={
        "date": "2026-03-01", "detail": "Alice Coffee", "amount": 5,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit",
    })
    assert r.status_code == 200
    return r.json()["id"]


def test_transaction_get_by_other_user_returns_404(client):
    tx_id = _alice_transaction(client)
    _switch_to_bob(client)
    assert client.get(f"/api/v1/transactions/{tx_id}").status_code == 404


def test_transaction_patch_by_other_user_returns_404(client):
    tx_id = _alice_transaction(client)
    _switch_to_bob(client)
    r = client.put(f"/api/v1/transactions/{tx_id}", json={"detail": "Hacked"})
    assert r.status_code == 404


def test_transaction_delete_by_other_user_returns_404(client):
    tx_id = _alice_transaction(client)
    _switch_to_bob(client)
    assert client.delete(f"/api/v1/transactions/{tx_id}").status_code == 404


# ---------------------------------------------------------------------------
# Transfers
# ---------------------------------------------------------------------------

def _alice_transfer(client):
    """Set up Alice's data and return a transfer id owned by her."""
    _register_and_onboard_alice(client)
    r = client.post("/api/v1/transfers", json={
        "date": "2026-03-01", "detail": "Alice Transfer", "amount": 100,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    })
    assert r.status_code == 200
    return r.json()["id"]


def test_transfer_get_by_other_user_returns_404(client):
    tf_id = _alice_transfer(client)
    _switch_to_bob(client)
    assert client.get(f"/api/v1/transfers/{tf_id}").status_code == 404


def test_transfer_put_by_other_user_returns_404(client):
    tf_id = _alice_transfer(client)
    _switch_to_bob(client)
    r = client.put(f"/api/v1/transfers/{tf_id}", json={"detail": "Hacked"})
    assert r.status_code == 404


def test_transfer_delete_by_other_user_returns_404(client):
    tf_id = _alice_transfer(client)
    _switch_to_bob(client)
    assert client.delete(f"/api/v1/transfers/{tf_id}").status_code == 404


# ---------------------------------------------------------------------------
# Payment Methods
# ---------------------------------------------------------------------------

def _alice_payment_method(client):
    """Set up Alice's data and return a payment method id owned by her."""
    _register_and_onboard_alice(client)
    r = client.post("/api/v1/payment-methods", json={"name": "AliceWallet", "type": "prepaid"})
    assert r.status_code == 200
    return r.json()["id"]


def test_payment_method_put_by_other_user_returns_404(client):
    pm_id = _alice_payment_method(client)
    _switch_to_bob(client)
    r = client.put(f"/api/v1/payment-methods/{pm_id}", json={"name": "Hacked"})
    assert r.status_code == 404


def test_payment_method_set_main_bank_by_other_user_returns_404(client):
    """Bob cannot promote Alice's bank to main-bank status."""
    _register_and_onboard_alice(client)
    # Get Alice's bank pm_id (bank type, needed for set-main-bank)
    alice_bank_id = next(
        pm["id"] for pm in client.get("/api/v1/payment-methods").json()
        if pm["name"] == "SecondBank"
    )
    _switch_to_bob(client)
    r = client.post(f"/api/v1/payment-methods/{alice_bank_id}/set-main-bank",
                    json={"opening_balance": 0})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

def _alice_category(client):
    """Set up Alice's data and return a category id owned by her."""
    _register_and_onboard_alice(client)
    r = client.post("/api/v1/categories", json={"type": "AliceCat", "sub_type": "Test"})
    assert r.status_code == 200
    return r.json()["id"]


def test_category_put_by_other_user_returns_404(client):
    cat_id = _alice_category(client)
    _switch_to_bob(client)
    r = client.put(f"/api/v1/categories/{cat_id}", json={"sub_type": "Hacked"})
    assert r.status_code == 404


def test_category_delete_by_other_user_returns_404(client):
    cat_id = _alice_category(client)
    _switch_to_bob(client)
    assert client.delete(f"/api/v1/categories/{cat_id}").status_code == 404


# ---------------------------------------------------------------------------
# Forecasts
# ---------------------------------------------------------------------------

def _alice_forecast(client):
    """Set up Alice's data and return a forecast id owned by her."""
    _register_and_onboard_alice(client)
    r = client.post("/api/v1/forecasts", json={
        "name": "Alice Plan", "base_year": 2026, "projection_years": 1,
    })
    assert r.status_code == 200
    return r.json()["id"]


def test_forecast_get_by_other_user_returns_404(client):
    fc_id = _alice_forecast(client)
    _switch_to_bob(client)
    assert client.get(f"/api/v1/forecasts/{fc_id}").status_code == 404


def test_forecast_put_by_other_user_returns_404(client):
    fc_id = _alice_forecast(client)
    _switch_to_bob(client)
    r = client.put(f"/api/v1/forecasts/{fc_id}", json={"name": "Hacked"})
    assert r.status_code == 404


def test_forecast_delete_by_other_user_returns_404(client):
    fc_id = _alice_forecast(client)
    _switch_to_bob(client)
    assert client.delete(f"/api/v1/forecasts/{fc_id}").status_code == 404


def test_forecast_projection_by_other_user_returns_404(client):
    fc_id = _alice_forecast(client)
    _switch_to_bob(client)
    assert client.get(f"/api/v1/forecasts/{fc_id}/projection").status_code == 404


def test_forecast_add_line_by_other_user_returns_404(client):
    fc_id = _alice_forecast(client)
    _switch_to_bob(client)
    r = client.post(f"/api/v1/forecasts/{fc_id}/lines", json={
        "detail": "Hacked line", "base_amount": 100,
    })
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------
# Assets use (year, asset_type, asset_name) as the "key", not a UUID.
# The PUT upserts into a row scoped to user_id, so Bob cannot read or
# overwrite Alice's manual_override — he would silently create his own row.
# We test that Bob's GET /assets/{year} does NOT expose Alice's named assets
# and that Bob's PUT only affects his own data.

def test_assets_list_does_not_expose_other_user_data(client, db):
    """Bob's asset list must not contain Alice's personal savings account."""
    _register_and_onboard_alice(client)
    # Alice has "MySavings" from onboarding
    alice_assets = client.get("/api/v1/assets/2026").json()
    assert any(a["asset_name"] == "MySavings" for a in alice_assets)

    _switch_to_bob(client)
    client.post("/api/v1/onboarding", json=_MINIMAL_ONBOARDING)
    bob_assets = client.get("/api/v1/assets/2026").json()
    asset_names = [a["asset_name"] for a in bob_assets]
    assert "MySavings" not in asset_names, (
        f"Bob can see Alice's MySavings asset: {asset_names}"
    )


def test_tax_config_does_not_leak_across_users(client):
    """resolve_tax_config must not return another user's tax config.

    User A creates a tax config row at 2026-07-01 (after the system seed at 2026-01-01)
    with absurdly high 99% IRPEF rates.  Without the user_id filter, resolve_tax_config
    picks up A's row when B queries for a salary in July 2026, producing near-zero net.
    After the fix the fallback is to the system seed row, yielding a realistic net.
    """
    # Register user A and create a custom tax config with absurdly high IRPEF rates.
    # Use valid_from AFTER the system seed date (2026-01-01) so A's row wins the
    # "most recent valid row" ordering and there is no ambiguity with the system row.
    client.post("/api/v1/auth/register", json={"email": "a@x.com", "password": "Password1!", "name": "A"})
    client.post("/api/v1/auth/login", json={"email": "a@x.com", "password": "Password1!"})
    r_tax = client.post("/api/v1/tax-config", json={
        "valid_from": "2026-07-01",
        "irpef_band1_rate": 0.99,
        "irpef_band2_rate": 0.99,
        "irpef_band3_rate": 0.99,
        "inps_rate": 0.0,
    })
    assert r_tax.status_code == 200

    # Log out A, register user B
    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/register", json={"email": "b@x.com", "password": "Password1!", "name": "B"})
    client.post("/api/v1/auth/login", json={"email": "b@x.com", "password": "Password1!"})

    # B creates a salary config valid from July 2026 — this is the period where A's
    # poisoned 99% row is the most recent match (ahead of the 2026-01-01 seed row).
    r = client.post("/api/v1/salary", json={
        "valid_from": "2026-07-01",
        "ral": 36000,
        "employer_contrib_rate": 0.04,
        "voluntary_contrib_rate": 0.0,
        "regional_tax_rate": 0.0173,
        "municipal_tax_rate": 0.001,
        "salary_months": 12,
        "meal_vouchers_annual": 0,
        "welfare_annual": 0,
    })
    assert r.status_code == 200
    net = float(r.json().get("computed_net_monthly", 0))
    # With IRPEF at 99%, net would be essentially 0 (or negative). For RAL=36000, normal net is ~1700–2200.
    assert net > 500, f"B's salary computed with A's absurd 99% IRPEF rate: net={net}"


def test_assets_put_override_does_not_affect_other_user(client, db):
    """Bob setting a manual override on an asset name that Alice also has must not affect Alice."""
    from app.models.asset import Asset
    from app.models.user import User

    _register_and_onboard_alice(client)

    _switch_to_bob(client)
    client.post("/api/v1/onboarding", json=_MINIMAL_ONBOARDING)
    # Bob sets a manual override on a fictional shared asset name
    r = client.put("/api/v1/assets/2026/saving/MySavings",
                   json={"manual_override": 9999.0, "notes": "Bob override"})
    assert r.status_code == 200

    # Verify in DB that Alice's asset row (if it exists) is unaffected
    alice_user = db.query(User).filter_by(email=_ALICE["email"]).first()
    alice_row = db.query(Asset).filter_by(
        user_id=alice_user.id, year=2026, asset_type="saving", asset_name="MySavings"
    ).first()
    # Alice should have no manual override row (the PUT only touches Bob's row)
    if alice_row is not None:
        assert alice_row.manual_override is None, (
            f"Bob's PUT leaked manual_override={alice_row.manual_override} into Alice's asset row"
        )


# ---------------------------------------------------------------------------
# Salary isolation
# ---------------------------------------------------------------------------

def _alice_salary(client):
    """Register Alice, onboard, create a salary config. Returns salary_id."""
    _register_and_onboard_alice(client)
    # First need a tax config for the period
    client.post("/api/v1/tax-config", json={"valid_from": "2026-01-01"})
    # Tax config creation may already exist from seed — ignore 409
    r = client.post("/api/v1/salary", json={
        "valid_from": "2026-01-01",
        "ral": 40000,
        "employer_contrib_rate": 0.0919,
    })
    assert r.status_code == 200
    return r.json()["id"]


def test_salary_list_by_other_user_is_empty(client):
    """Bob listing salary configs sees only his own (Alice's must not appear)."""
    _alice_salary(client)
    _switch_to_bob(client)
    client.post("/api/v1/onboarding", json=_MINIMAL_ONBOARDING)
    r = client.get("/api/v1/salary")
    assert r.status_code == 200
    assert r.json() == []


def test_salary_update_by_other_user_returns_404(client):
    """Bob cannot update Alice's salary config."""
    salary_id = _alice_salary(client)
    _switch_to_bob(client)
    r = client.put(f"/api/v1/salary/{salary_id}", json={
        "valid_from": "2026-01-01", "ral": 99999, "employer_contrib_rate": 0.0
    })
    assert r.status_code == 404


def test_salary_delete_by_other_user_returns_404(client):
    """Bob cannot delete Alice's salary config."""
    salary_id = _alice_salary(client)
    _switch_to_bob(client)
    assert client.delete(f"/api/v1/salary/{salary_id}").status_code == 404


# ---------------------------------------------------------------------------
# User settings isolation
# ---------------------------------------------------------------------------

def test_user_settings_list_by_other_user_shows_only_own(client):
    """Bob's GET /user-settings must not return Alice's settings."""
    _register_and_onboard_alice(client)
    # Alice sets a distinctive tracking_start_date value
    client.put("/api/v1/user-settings", json=[{"key": "tracking_start_date", "value": "1990-01-01"}])

    _switch_to_bob(client)
    client.post("/api/v1/onboarding", json=_MINIMAL_ONBOARDING)
    r = client.get("/api/v1/user-settings")
    assert r.status_code == 200
    # Alice's distinctive value must not appear in Bob's settings
    values = {item["value"] for item in r.json()}
    assert "1990-01-01" not in values
    # Bob must still have his own settings
    keys = {item["key"] for item in r.json()}
    assert "onboarding_complete" in keys


# ---------------------------------------------------------------------------
# Analytics isolation
# ---------------------------------------------------------------------------

def test_analytics_does_not_return_other_user_transactions(client):
    """Alice's transactions must not appear in Bob's analytics response."""
    pm_id, cat_id = _register_and_onboard_alice(client)
    client.post("/api/v1/transactions", json={
        "date": "2026-03-15", "detail": "Alice Secret Expense", "amount": 12345.67,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit",
    })

    # Confirm Alice can see her own transaction in analytics
    alice_r = client.get("/api/v1/analytics/categories?from=2026-01&to=2026-12")
    assert alice_r.status_code == 200
    alice_amounts = [row.get("total_amount", 0) for row in alice_r.json()]
    assert any(abs(float(a) - 12345.67) < 0.01 for a in alice_amounts), (
        "Alice's transaction should appear in her own analytics"
    )

    _switch_to_bob(client)
    client.post("/api/v1/onboarding", json=_MINIMAL_ONBOARDING)
    bob_r = client.get("/api/v1/analytics/categories?from=2026-01&to=2026-12")
    assert bob_r.status_code == 200
    # Alice's distinctive amount must not appear in Bob's analytics
    bob_amounts = [row.get("total_amount", 0) for row in bob_r.json()]
    assert not any(abs(float(a) - 12345.67) < 0.01 for a in bob_amounts), (
        "Alice's transaction must not appear in Bob's analytics"
    )
