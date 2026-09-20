import pytest
from tests.test_onboarding import WIZARD_PAYLOAD

def _setup(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)

@pytest.mark.parametrize("year", [2000, 2100])
def test_assets_accepts_supported_year_boundaries(client, year):
    _setup(client)
    response = client.get(f"/api/v1/assets/{year}?as_of={year}-12-01")
    assert response.status_code == 200


@pytest.mark.parametrize("year", [1999, 2101])
def test_assets_rejects_out_of_range_years(client, year):
    _setup(client)
    response = client.get(f"/api/v1/assets/{year}?as_of={year}-12-01")
    assert response.status_code == 422


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_assets_rejects_non_finite_manual_overrides(client, value):
    _setup(client)
    response = client.put(
        "/api/v1/assets/2026/saving/MySavings",
        json={"manual_override": value},
    )
    assert response.status_code == 422


def test_assets_includes_saving_account(client):
    _setup(client)
    r = client.get("/api/v1/assets/2026?as_of=2026-12-01")
    assert r.status_code == 200
    saving = next((a for a in r.json() if a["asset_name"] == "MySavings"), None)
    assert saving is not None
    assert saving["computed_amount"] == pytest.approx(3000.0)

def test_assets_saving_grows_with_transfer(client):
    _setup(client)
    client.post("/api/v1/transfers", json={
        "date": "2026-03-01", "amount": 500,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    })
    r = client.get("/api/v1/assets/2026?as_of=2026-12-01")
    caab = next(a for a in r.json() if a["asset_name"] == "MySavings")
    assert caab["computed_amount"] == pytest.approx(3500.0)

def test_assets_investment_computed_correctly(client):
    _setup(client)
    r = client.get("/api/v1/assets/2026?as_of=2026-12-01")
    directa = next(a for a in r.json() if a["asset_name"] == "MyBroker")
    assert directa["computed_amount"] == pytest.approx(8000.0)

def test_manual_override_replaces_computed(client):
    _setup(client)
    r = client.put("/api/v1/assets/2026/saving/MySavings", json={"manual_override": 9999.0})
    assert r.status_code == 200
    r2 = client.get("/api/v1/assets/2026?as_of=2026-12-01")
    caab = next(a for a in r2.json() if a["asset_name"] == "MySavings")
    assert caab["final_amount"] == pytest.approx(9999.0)
    assert caab["computed_amount"] == pytest.approx(3000.0)

def test_final_amount_falls_back_to_computed_without_override(client):
    _setup(client)
    r = client.get("/api/v1/assets/2026?as_of=2026-12-01")
    caab = next(a for a in r.json() if a["asset_name"] == "MySavings")
    assert caab["final_amount"] == caab["computed_amount"]


def test_stable_asset_override_can_clear_matching_legacy_override(client, db):
    """A null stable override takes precedence over a legacy name-based value."""
    from app.models.asset import Asset
    from app.models.payment_method import PaymentMethod

    _setup(client)
    bank_id = next(method["id"] for method in client.get("/api/v1/payment-methods").json() if method["name"] == "MyBank")
    user_id = db.get(PaymentMethod, bank_id).user_id
    db.add(Asset(
        user_id=user_id, year=2026, asset_type="saving", asset_name="MySavings",
        manual_override=9999,
    ))
    db.commit()

    initial = client.get("/api/v1/assets/2026?as_of=2026-12-01").json()
    assert next(asset for asset in initial if asset["asset_name"] == "MySavings")["final_amount"] == pytest.approx(9999.0)
    saving_id = next(account["id"] for account in client.get("/api/v1/accounts").json() if account["name"] == "MySavings")
    response = client.put(f"/api/v1/assets/2026/saving/{saving_id}", json={"manual_override": None})
    assert response.status_code == 200

    updated = client.get("/api/v1/assets/2026?as_of=2026-12-01").json()
    saving = next(asset for asset in updated if asset["account_id"] == saving_id)
    assert saving["manual_override"] is None
    assert saving["final_amount"] == saving["computed_amount"] == pytest.approx(3000.0)


def test_pension_month_count_uses_relativedelta(_standalone_db, make_user):
    """Pension months must be counted correctly across year boundaries."""
    from app.services.assets import compute_assets
    from app.models.salary import SalaryConfig
    from app.models.user import UserSetting

    user = make_user(email="pension@test.com")
    db = _standalone_db

    # Salary valid from 2025-07-01 — contributes for 6 months of 2025
    db.add(SalaryConfig(
        user_id=user.id, valid_from="2025-07-01", ral=36000,
        employer_contrib_rate=0.0693, voluntary_contrib_rate=0.02,
        regional_tax_rate=0.0123, municipal_tax_rate=0.008,
        meal_vouchers_annual=0, welfare_annual=0,
        salary_months=12, computed_net_monthly=0,
    ))
    db.add(UserSetting(user_id=user.id, key="tracking_start_date", value="2025-01-01"))
    db.commit()

    rows = compute_assets(user.id, 2025, db)
    pension_rows = [r for r in rows if r.asset_type == "pension"]
    assert len(pension_rows) == 1
    # 6 months (Jul–Dec), rate=0.0693+0.02=0.0893, ral=36000
    expected = round(0.0893 * 36000 * 6 / 12, 2)
    assert abs(pension_rows[0].computed_amount - expected) < 0.01


def test_pension_fractional_month_rounds_up_at_15_days(_standalone_db, make_user):
    """A period with >= 15 leftover days must round up to the next whole month."""
    from app.services.assets import compute_assets
    from app.models.salary import SalaryConfig
    from app.models.user import UserSetting

    user = make_user(email="pension_round_up@test.com")
    db = _standalone_db

    # valid_from=2026-01-16 → active 2026-01-16..2027-01-01 = 11 months 16 days → rounds to 12
    db.add(SalaryConfig(
        user_id=user.id, valid_from="2026-01-16", ral=12000,
        employer_contrib_rate=0.10, voluntary_contrib_rate=0.0,
        regional_tax_rate=0.0, municipal_tax_rate=0.0,
        meal_vouchers_annual=0, welfare_annual=0,
        salary_months=12, computed_net_monthly=0,
    ))
    db.add(UserSetting(user_id=user.id, key="tracking_start_date", value="2026-01-01"))
    db.commit()

    rows = compute_assets(user.id, 2026, db)
    pension_rows = [r for r in rows if r.asset_type == "pension"]
    assert len(pension_rows) == 1
    # 12 months (rounded up from 11m16d), rate=0.10, ral=12000
    expected = round(0.10 * 12000 * 12 / 12, 2)
    assert abs(pension_rows[0].computed_amount - expected) < 0.01


def test_pension_fractional_month_drops_below_15_days(_standalone_db, make_user):
    """A period with < 15 leftover days must NOT round up."""
    from app.services.assets import compute_assets
    from app.models.salary import SalaryConfig
    from app.models.user import UserSetting

    user = make_user(email="pension_no_round@test.com")
    db = _standalone_db

    # valid_from=2026-01-18 → active 2026-01-18..2027-01-01 = 11 months 14 days → stays 11
    db.add(SalaryConfig(
        user_id=user.id, valid_from="2026-01-18", ral=12000,
        employer_contrib_rate=0.10, voluntary_contrib_rate=0.0,
        regional_tax_rate=0.0, municipal_tax_rate=0.0,
        meal_vouchers_annual=0, welfare_annual=0,
        salary_months=12, computed_net_monthly=0,
    ))
    db.add(UserSetting(user_id=user.id, key="tracking_start_date", value="2026-01-01"))
    db.commit()

    rows = compute_assets(user.id, 2026, db)
    pension_rows = [r for r in rows if r.asset_type == "pension"]
    assert len(pension_rows) == 1
    # 11 months (14 leftover days < 15 threshold), rate=0.10, ral=12000
    expected = round(0.10 * 12000 * 11 / 12, 2)
    assert abs(pension_rows[0].computed_amount - expected) < 0.01


def test_assets_transfer_balance_multiple_accounts(_standalone_db, make_user):
    """compute_assets must correctly aggregate transfers across multiple saving accounts."""
    from app.services.assets import compute_assets
    from app.models.user import UserSetting
    from app.models.transfer import Transfer

    user = make_user(email="multi_asset@test.com")
    db = _standalone_db

    db.add(UserSetting(user_id=user.id, key="tracking_start_date", value="2026-01-01"))
    db.add(UserSetting(user_id=user.id, key="opening_saving_balance_Alpha", value="1000"))
    db.add(UserSetting(user_id=user.id, key="opening_saving_balance_Beta", value="500"))

    db.add(Transfer(
        user_id=user.id, date="2026-03-01", detail="deposit",
        amount=200, from_account_type="bank", from_account_name="Main",
        to_account_type="saving", to_account_name="Alpha",
        billing_month="2026-03-01",
    ))
    db.add(Transfer(
        user_id=user.id, date="2026-06-01", detail="withdraw",
        amount=100, from_account_type="saving", from_account_name="Beta",
        to_account_type="bank", to_account_name="Main",
        billing_month="2026-06-01",
    ))
    db.commit()

    rows = compute_assets(user.id, 2026, db)
    alpha = next(r for r in rows if r.asset_name == "Alpha")
    beta = next(r for r in rows if r.asset_name == "Beta")
    assert alpha.computed_amount == 1200.0   # 1000 + 200 in
    assert beta.computed_amount == 400.0     # 500 - 100 out


def test_transfer_carries_forward_across_years(_standalone_db, make_user):
    """A transfer in year N must persist in N+1 and N+2 with no new transfers."""
    from app.services.assets import compute_assets
    from app.models.user import UserSetting
    from app.models.transfer import Transfer

    user = make_user(email="carry_forward@test.com")
    db = _standalone_db

    db.add(UserSetting(user_id=user.id, key="tracking_start_date", value="2025-01-01"))
    db.add(UserSetting(user_id=user.id, key="opening_saving_balance_Nest", value="3000"))
    db.add(Transfer(
        user_id=user.id, date="2025-05-01", detail="deposit",
        amount=500, from_account_type="bank", from_account_name="Main",
        to_account_type="saving", to_account_name="Nest",
        billing_month="2025-05-01",
    ))
    db.commit()

    for year in (2025, 2026, 2027):
        rows = compute_assets(user.id, year, db)
        nest = next(r for r in rows if r.asset_name == "Nest")
        assert nest.computed_amount == 3500.0, f"year {year}"


def test_year_before_first_transfer_shows_opening(_standalone_db, make_user):
    """A year before any transfer shows the plain opening balance."""
    from app.services.assets import compute_assets
    from app.models.user import UserSetting
    from app.models.transfer import Transfer

    user = make_user(email="before_transfer@test.com")
    db = _standalone_db

    db.add(UserSetting(user_id=user.id, key="tracking_start_date", value="2025-01-01"))
    db.add(UserSetting(user_id=user.id, key="opening_saving_balance_Nest", value="3000"))
    db.add(Transfer(
        user_id=user.id, date="2026-05-01", detail="deposit",
        amount=500, from_account_type="bank", from_account_name="Main",
        to_account_type="saving", to_account_name="Nest",
        billing_month="2026-05-01",
    ))
    db.commit()

    rows = compute_assets(user.id, 2025, db)
    nest = next(r for r in rows if r.asset_name == "Nest")
    assert nest.computed_amount == 3000.0


def test_transfers_in_two_years_accumulate(_standalone_db, make_user):
    """Transfers made in different years accumulate into later-year balances."""
    from app.services.assets import compute_assets
    from app.models.user import UserSetting
    from app.models.transfer import Transfer

    user = make_user(email="accumulate@test.com")
    db = _standalone_db

    db.add(UserSetting(user_id=user.id, key="tracking_start_date", value="2025-01-01"))
    db.add(UserSetting(user_id=user.id, key="opening_saving_balance_Nest", value="3000"))
    db.add(Transfer(
        user_id=user.id, date="2025-05-01", detail="deposit",
        amount=500, from_account_type="bank", from_account_name="Main",
        to_account_type="saving", to_account_name="Nest",
        billing_month="2025-05-01",
    ))
    db.add(Transfer(
        user_id=user.id, date="2026-05-01", detail="deposit",
        amount=200, from_account_type="bank", from_account_name="Main",
        to_account_type="saving", to_account_name="Nest",
        billing_month="2026-05-01",
    ))
    db.commit()

    assert next(r for r in compute_assets(user.id, 2025, db) if r.asset_name == "Nest").computed_amount == 3500.0
    assert next(r for r in compute_assets(user.id, 2026, db) if r.asset_name == "Nest").computed_amount == 3700.0


def test_transfer_out_carries_forward(_standalone_db, make_user):
    """A transfer OUT in year N reduces the balance in year N+1."""
    from app.services.assets import compute_assets
    from app.models.user import UserSetting
    from app.models.transfer import Transfer

    user = make_user(email="transfer_out@test.com")
    db = _standalone_db

    db.add(UserSetting(user_id=user.id, key="tracking_start_date", value="2025-01-01"))
    db.add(UserSetting(user_id=user.id, key="opening_saving_balance_Nest", value="3000"))
    db.add(Transfer(
        user_id=user.id, date="2025-05-01", detail="withdraw",
        amount=800, from_account_type="saving", from_account_name="Nest",
        to_account_type="bank", to_account_name="Main",
        billing_month="2025-05-01",
    ))
    db.commit()

    rows = compute_assets(user.id, 2026, db)
    nest = next(r for r in rows if r.asset_name == "Nest")
    assert nest.computed_amount == 2200.0   # 3000 - 800 out


def test_manual_override_does_not_leak_to_next_year(_standalone_db, make_user):
    """A manual override for year N must not affect year N+1's computed amount."""
    from app.services.assets import compute_assets
    from app.models.user import UserSetting
    from app.models.asset import Asset

    user = make_user(email="override_leak@test.com")
    db = _standalone_db

    db.add(UserSetting(user_id=user.id, key="tracking_start_date", value="2025-01-01"))
    db.add(UserSetting(user_id=user.id, key="opening_saving_balance_Nest", value="3000"))
    db.add(Asset(
        user_id=user.id, year=2025, asset_type="saving",
        asset_name="Nest", manual_override=9999.0,
    ))
    db.commit()

    override_year = next(r for r in compute_assets(user.id, 2025, db) if r.asset_name == "Nest")
    assert override_year.final_amount == 9999.0
    assert override_year.computed_amount == 3000.0

    next_year = next(r for r in compute_assets(user.id, 2026, db) if r.asset_name == "Nest")
    assert next_year.computed_amount == 3000.0
    assert next_year.manual_override is None
    assert next_year.final_amount == 3000.0


@pytest.mark.parametrize("as_of", ["20260101", "2026-02-30", "2026-01-15", "1999-01-01", "2101-01-01"])
def test_assets_rejects_invalid_as_of_month(client, as_of):
    _setup(client)
    response = client.get(f"/api/v1/assets/2026?as_of={as_of}")
    assert response.status_code == 422


def test_assets_rejects_as_of_for_another_year(client):
    _setup(client)
    response = client.get("/api/v1/assets/2026?as_of=2025-12-01")
    assert response.status_code == 422


def test_assets_january_snapshot_excludes_later_transfers_and_pension(client):
    _setup(client)
    response = client.post("/api/v1/transfers", json={
        "date": "2026-03-01", "amount": 500,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    })
    assert response.status_code == 200

    january = client.get("/api/v1/assets/2026?as_of=2026-01-01")
    assert january.status_code == 200
    january_saving = next(asset for asset in january.json() if asset["asset_name"] == "MySavings")
    january_pension = next(asset for asset in january.json() if asset["asset_type"] == "pension")
    assert january_saving["computed_amount"] == pytest.approx(3000.0)
    assert january_pension["computed_amount"] == pytest.approx(210.0)

    december = client.get("/api/v1/assets/2026?as_of=2026-12-01")
    december_saving = next(asset for asset in december.json() if asset["asset_name"] == "MySavings")
    december_pension = next(asset for asset in december.json() if asset["asset_type"] == "pension")
    assert december_saving["computed_amount"] == pytest.approx(3500.0)
    assert december_pension["computed_amount"] == pytest.approx(2520.0)


def test_assets_pension_uses_salary_config_effective_periods(_standalone_db, make_user):
    from app.models.salary import SalaryConfig
    from app.services.assets import compute_assets

    user = make_user(email="asset-salary-period@test.com")
    db = _standalone_db
    db.add_all([
        SalaryConfig(
            user_id=user.id, valid_from="2026-01-01", ral=12000,
            employer_contrib_rate=0.10, voluntary_contrib_rate=0,
            regional_tax_rate=0, municipal_tax_rate=0,
            meal_vouchers_annual=0, welfare_annual=0,
            salary_months=12, computed_net_monthly=0,
        ),
        SalaryConfig(
            user_id=user.id, valid_from="2026-03-01", ral=24000,
            employer_contrib_rate=0.10, voluntary_contrib_rate=0,
            regional_tax_rate=0, municipal_tax_rate=0,
            meal_vouchers_annual=0, welfare_annual=0,
            salary_months=12, computed_net_monthly=0,
        ),
    ])
    db.commit()

    february = next(
        row for row in compute_assets(user.id, 2026, db, "2026-02-01")
        if row.asset_type == "pension"
    )
    march = next(
        row for row in compute_assets(user.id, 2026, db, "2026-03-01")
        if row.asset_type == "pension"
    )
    assert february.computed_amount == pytest.approx(200.0)
    assert march.computed_amount == pytest.approx(400.0)


def test_assets_december_as_of_matches_annual_service_behavior(_standalone_db, make_user):
    from app.models.salary import SalaryConfig
    from app.models.transfer import Transfer
    from app.models.user import UserSetting
    from app.services.assets import compute_assets

    user = make_user(email="asset-year-end@test.com")
    db = _standalone_db
    db.add(UserSetting(user_id=user.id, key="opening_saving_balance_Nest", value="3000"))
    db.add(Transfer(
        user_id=user.id, date="2026-03-01", detail="deposit", amount=500,
        from_account_type="bank", from_account_name="Main",
        to_account_type="saving", to_account_name="Nest", billing_month="2026-03-01",
    ))
    db.add(SalaryConfig(
        user_id=user.id, valid_from="2026-01-01", ral=12000,
        employer_contrib_rate=0.10, voluntary_contrib_rate=0,
        regional_tax_rate=0, municipal_tax_rate=0,
        meal_vouchers_annual=0, welfare_annual=0,
        salary_months=12, computed_net_monthly=0,
    ))
    db.commit()

    annual = compute_assets(user.id, 2026, db)
    december = compute_assets(user.id, 2026, db, "2026-12-01")
    assert annual == december
