import pytest

from tests.test_onboarding import WIZARD_PAYLOAD


def _login(client, email="salary@example.com"):
    assert client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password1!", "name": "Salary",
    }).status_code == 200
    assert client.post("/api/v1/auth/login", json={
        "email": email, "password": "Password1!",
    }).status_code == 200


def _salary(valid_from="2026-01-01", **extra):
    return {
        "valid_from": valid_from, "ral": 36000,
        "regional_tax_rate": 0.0173, "municipal_tax_rate": 0.001,
        "meal_vouchers_annual": 0, "welfare_annual": 0, "salary_months": 12,
        **extra,
    }


def _preview(as_of="2026-01-01", pension=None, salary=None):
    return {
        "as_of": as_of,
        "salary": salary or {
            "ral": 36000, "regional_tax_rate": 0.0173,
            "municipal_tax_rate": 0.001, "meal_vouchers_annual": 0,
            "welfare_annual": 0, "salary_months": 12,
        },
        "pension": pension,
    }


def _onboard(client):
    payload = {**WIZARD_PAYLOAD, "salary": None, "pension": None}
    assert client.post("/api/v1/onboarding", json=payload).status_code == 200


def test_salary_crud_has_fresh_computed_net_and_preserves_manual_override(client):
    _login(client)
    response = client.post("/api/v1/salary", json=_salary(manual_net_override=1250))
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["computed_net_monthly"] > 1250
    assert saved["effective_net_monthly"] == 1250
    assert saved["calculated_as_of"] == saved["valid_from"] == "2026-01-01"
    assert "employer_contrib_rate" not in saved
    assert client.get("/api/v1/salary").json()[0]["effective_net_monthly"] == 1250

    updated = client.put(f"/api/v1/salary/{saved['id']}", json=_salary(ral=42000))
    assert updated.status_code == 200
    assert updated.json()["id"] == saved["id"]
    assert updated.json()["ral"] == 42000
    assert updated.json()["manual_net_override"] == 1250
    assert updated.json()["computed_net_monthly"] != saved["computed_net_monthly"]


def test_explicit_null_manual_override_clears_to_computed_effective_net(client):
    _login(client)
    created = client.post("/api/v1/salary", json=_salary(manual_net_override=1250))
    assert created.status_code == 201
    saved = created.json()
    cleared = client.put(f"/api/v1/salary/{saved['id']}", json=_salary(manual_net_override=None))
    assert cleared.status_code == 200
    assert cleared.json()["manual_net_override"] is None
    assert cleared.json()["effective_net_monthly"] == cleared.json()["computed_net_monthly"]
    persisted = client.get("/api/v1/salary").json()[0]
    assert persisted["manual_net_override"] is None
    assert persisted["effective_net_monthly"] == persisted["computed_net_monthly"]


def test_salary_delete_protects_earliest_and_deletes_later_row_with_204(client, db):
    from app.models.salary import SalaryConfig

    _login(client)
    earliest = client.post("/api/v1/salary", json=_salary("2026-01-01"))
    later = client.post("/api/v1/salary", json=_salary("2027-01-01"))
    assert earliest.status_code == later.status_code == 201
    assert db.query(SalaryConfig).count() == 2

    protected = client.delete(f"/api/v1/salary/{earliest.json()['id']}")
    assert protected.status_code == 400
    assert db.query(SalaryConfig).filter_by(id=earliest.json()["id"]).count() == 1

    deleted = client.delete(f"/api/v1/salary/{later.json()['id']}")
    assert deleted.status_code == 204
    assert db.query(SalaryConfig).count() == 1
    assert db.query(SalaryConfig).filter_by(id=earliest.json()["id"]).one().valid_from == "2026-01-01"


def test_salary_creation_does_not_create_or_assume_pension_account(client):
    _login(client)
    response = client.post("/api/v1/salary", json=_salary())
    assert response.status_code == 201
    assert not any(account["type"] == "pension" for account in client.get("/api/v1/accounts").json())


def test_create_salary_rejects_unknown_legacy_pension_rates(client):
    _login(client)
    response = client.post("/api/v1/salary", json=_salary(employer_contrib_rate=0.04))
    assert response.status_code == 422


def test_post_calculate_explicit_pension_preview_and_null_are_distinct(client):
    _login(client)
    pension = {
        "employee_contrib_rate": 0.01, "employee_contrib_annual_base": 30000,
        "employer_contrib_rate": 0.02, "employer_contrib_annual_base": 20000,
        "tfr_contrib_annual": 2400,
    }
    with_pension = client.post("/api/v1/salary/calculate", json=_preview(pension=pension))
    without_pension = client.post("/api/v1/salary/calculate", json=_preview(pension=None))
    assert with_pension.status_code == without_pension.status_code == 200
    data = with_pension.json()
    assert data["employee_pension_contribution_annual"] == 300
    assert data["employer_pension_contribution_annual"] == 400
    assert data["tfr_contribution_annual"] == 2400
    assert "pension_deductible" not in data
    assert data["net_annual"] != without_pension.json()["net_annual"]


def test_preview_null_ignores_saved_pension_and_preview_validates_referenced_account(client):
    _login(client)
    payload = {**WIZARD_PAYLOAD, "salary": None}
    assert client.post("/api/v1/onboarding", json=payload).status_code == 200
    null_preview = client.post("/api/v1/salary/calculate", json=_preview(pension=None))
    assert null_preview.status_code == 200
    assert null_preview.json()["employee_pension_contribution_annual"] == 0
    invalid = {
        "employee_contrib_rate": 0, "employee_contrib_annual_base": 0,
        "employer_contrib_rate": 0, "employer_contrib_annual_base": 0,
        "tfr_contrib_annual": 0, "account_id": "foreign-or-missing",
    }
    response = client.post("/api/v1/salary/calculate", json=_preview(pension=invalid))
    assert response.status_code == 422


@pytest.mark.parametrize("effective_date", ["not-a-date", "2026-01-15"])
def test_salary_create_and_post_preview_reject_noncanonical_periods(client, db, effective_date):
    from app.models.salary import SalaryConfig

    _login(client)
    created = client.post("/api/v1/salary", json=_salary(effective_date))
    preview = client.post("/api/v1/salary/calculate", json=_preview(as_of=effective_date))
    assert created.status_code == 422
    assert preview.status_code == 422
    assert db.query(SalaryConfig).count() == 0


def test_salary_breakdown_resolves_independent_effective_periods_without_salary_write(client, db):
    from app.models.account import Account
    from app.models.pension import PensionConfig
    from app.models.tax import TaxConfig
    from app.models.user import User

    _login(client)
    _onboard(client)
    salary = client.post("/api/v1/salary", json=_salary())
    assert salary.status_code == 201
    user = db.query(User).filter_by(email="salary@example.com").one()
    account = Account(user_id=user.id, type="pension", name="Fund", opening_balance=0,
                      opening_balance_month="2026-01-01")
    db.add(account)
    db.flush()
    db.add(PensionConfig(
        user_id=user.id, account_id=account.id, valid_from="2026-01-01",
        employee_contrib_rate=0, employee_contrib_annual_base=0,
        employer_contrib_rate=0, employer_contrib_annual_base=0,
        tfr_contrib_annual=0, contribution_periods_by_month=[1] * 12,
    ))
    db.commit()
    count = client.get("/api/v1/salary").json()
    prior_net = count[0]["computed_net_monthly"]

    db.add(PensionConfig(
        user_id=user.id, account_id=account.id, valid_from="2026-03-01",
        employee_contrib_rate=0.01, employee_contrib_annual_base=30000,
        employer_contrib_rate=0, employer_contrib_annual_base=0,
        tfr_contrib_annual=0, contribution_periods_by_month=[1] * 12,
    ))
    db.commit()
    response = client.get("/api/v1/salary/breakdown?as_of=2026-03-01")
    assert response.status_code == 200
    assert response.json()["employee_pension_contribution_annual"] == 300
    assert response.json()["salary_config_valid_from"] == "2026-01-01"
    assert response.json()["pension_config_valid_from"] == "2026-03-01"
    assert response.json()["computed_net_monthly"] != prior_net
    assert len(client.get("/api/v1/salary").json()) == 1


def test_tax_only_change_refreshes_breakdown_without_salary_write(client, db):
    from app.models.tax import TaxConfig
    from app.models.user import User

    _login(client)
    _onboard(client)
    created = client.post("/api/v1/salary", json=_salary())
    assert created.status_code == 201
    user = db.query(User).filter_by(email="salary@example.com").one()
    before = client.get("/api/v1/salary/breakdown?as_of=2026-01-01").json()
    db.add(TaxConfig(user_id=user.id, valid_from="2026-01-01", inps_rate=0.2))
    db.commit()
    after = client.get("/api/v1/salary/breakdown?as_of=2026-01-01").json()
    assert after["computed_net_monthly"] != before["computed_net_monthly"]
    assert len(client.get("/api/v1/salary").json()) == 1


def test_salary_create_and_update_without_tax_config_are_atomic(client, db):
    from app.models.salary import SalaryConfig
    from app.models.tax import TaxConfig

    _login(client)
    created = client.post("/api/v1/salary", json=_salary(manual_net_override=1100))
    assert created.status_code == 201
    original = created.json()
    db.query(TaxConfig).delete()
    db.commit()

    missing_tax_create = client.post("/api/v1/salary", json=_salary("1990-01-01"))
    assert missing_tax_create.status_code == 422
    assert db.query(SalaryConfig).filter_by(user_id=original["user_id"]).count() == 1

    missing_tax_update = client.put(f"/api/v1/salary/{original['id']}", json=_salary("1990-01-01", ral=42000))
    assert missing_tax_update.status_code == 422
    db.expire_all()
    persisted = db.query(SalaryConfig).filter_by(id=original["id"]).one()
    assert str(persisted.ral) == "36000.00"
    assert str(persisted.manual_net_override) == "1100.00"
    assert persisted.valid_from == original["valid_from"]


def test_preview_requires_an_applicable_tax_config(client, db):
    from app.models.tax import TaxConfig

    _login(client)
    db.query(TaxConfig).delete()
    db.commit()
    response = client.post("/api/v1/salary/calculate", json=_preview())
    assert response.status_code == 422
    assert "tax config" in response.json()["detail"].lower()


def test_onboarding_preview_and_saved_breakdown_are_consistent(client):
    _login(client)
    pension = {
        "name": "Preview Fund", "opening_balance": 1000, "opening_balance_month": "2026-01-01",
        "employee_contrib_rate": 0.01, "employee_contrib_annual_base": 30000,
        "employer_contrib_rate": 0.02, "employer_contrib_annual_base": 20000,
        "tfr_contrib_annual": 2400, "contribution_periods_by_month": [1] * 12,
    }
    salary_fields = {
        "ral": 36000, "regional_tax_rate": 0.0173, "municipal_tax_rate": 0.001,
        "meal_vouchers_annual": 0, "welfare_annual": 0, "salary_months": 13,
    }
    preview = client.post("/api/v1/salary/calculate", json={
        "as_of": "2026-01-01", "salary": salary_fields,
        "pension": {key: value for key, value in pension.items() if key != "name" and key not in {"opening_balance", "opening_balance_month", "contribution_periods_by_month"}},
    })
    assert preview.status_code == 200, preview.text
    assert client.post("/api/v1/onboarding", json={
        **WIZARD_PAYLOAD, "tracking_start_date": "2026-01-01",
        "salary": salary_fields, "pension": pension,
    }).status_code == 200
    saved = client.get("/api/v1/salary/breakdown?as_of=2026-01-01")
    assert saved.status_code == 200, saved.text
    for key in ("taxable_base", "net_annual", "computed_net_monthly",
                "employee_pension_contribution_annual", "pension_cap_used_annual"):
        assert saved.json()[key] == preview.json()[key]


def test_onboarding_pension_without_salary_and_preview_save_match(client):
    _login(client)
    payload = {
        **WIZARD_PAYLOAD, "salary": None,
        "pension": {**WIZARD_PAYLOAD["pension"], "name": "New Fund"},
    }
    response = client.post("/api/v1/onboarding", json=payload)
    assert response.status_code == 200, response.text
    assert client.get("/api/v1/salary").json() == []
    accounts = client.get("/api/v1/accounts?type=pension").json()
    assert len(accounts) == 1 and accounts[0]["opening_balance_month"] == "2026-01-01"
    assert client.get("/api/v1/pension/configs").json()[0]["account_id"] == accounts[0]["id"]
