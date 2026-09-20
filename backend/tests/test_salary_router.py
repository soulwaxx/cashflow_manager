
import pytest


CAPPED_DEDUCTION_NEGATIVE_NET = {
    "ral": 36000,
    "employer_contrib_rate": 0,
    "voluntary_contrib_rate": 1,
    "regional_tax_rate": 0,
    "municipal_tax_rate": 0,
}


def _make_user_and_login(client):
    client.post("/api/v1/auth/register", json={"email": "u@x.com", "password": "Password1!", "name": "U"})
    client.post("/api/v1/auth/login", json={"email": "u@x.com", "password": "Password1!"})


def test_create_salary_with_salary_months_13(client):
    _make_user_and_login(client)
    resp = client.post("/api/v1/salary", json={
        "valid_from": "2026-01-01",
        "ral": 36000,
        "employer_contrib_rate": 0.02,
        "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173,
        "municipal_tax_rate": 0.001,
        "meal_vouchers_annual": 0,
        "welfare_annual": 0,
        "salary_months": 13,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["salary_months"] == 13


def test_calculate_endpoint_returns_english_field_names(client):
    _make_user_and_login(client)
    resp = client.get("/api/v1/salary/calculate", params={
        "as_of": "2026-01-01",
        "ral": 36000,
        "employer_contrib_rate": 0.02,
        "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173,
        "municipal_tax_rate": 0.001,
        "salary_months": 12,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "net_monthly" in data
    assert "gross_annual" in data
    assert "netto_mensile" not in data  # old Italian name gone


def test_calculate_salary_months_affects_net_monthly(client):
    _make_user_and_login(client)
    base = {"as_of": "2026-01-01", "ral": 36000, "employer_contrib_rate": 0.02,
            "voluntary_contrib_rate": 0.01, "regional_tax_rate": 0.0173,
            "municipal_tax_rate": 0.001}
    r12 = client.get("/api/v1/salary/calculate", params={**base, "salary_months": 12}).json()
    r13 = client.get("/api/v1/salary/calculate", params={**base, "salary_months": 13}).json()
    assert r12["net_monthly"] > r13["net_monthly"]
    assert abs(r12["net_monthly"] / r13["net_monthly"] - 13 / 12) < 0.01


def test_preview_salary_returns_422_when_no_tax_config(client):
    _make_user_and_login(client)
    # Tax config is seeded starting 2026-01-01; use a date before that
    r = client.get("/api/v1/salary/calculate", params={
        "as_of": "1990-01-01",
        "ral": 36000,
        "employer_contrib_rate": 0.02,
        "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173,
        "municipal_tax_rate": 0.001,
        "salary_months": 12,
    })
    assert r.status_code == 422


def test_update_salary(client):
    _make_user_and_login(client)
    salary_id = client.post("/api/v1/salary", json={
        "valid_from": "2026-01-01",
        "ral": 36000,
        "employer_contrib_rate": 0.02,
        "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173,
        "municipal_tax_rate": 0.001,
        "salary_months": 12,
    }).json()["id"]
    r = client.put(f"/api/v1/salary/{salary_id}", json={
        "valid_from": "2026-01-01",
        "ral": 42000,
        "employer_contrib_rate": 0.02,
        "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173,
        "municipal_tax_rate": 0.001,
        "salary_months": 12,
    })
    assert r.status_code == 200
    assert r.json()["ral"] == 42000


def test_update_salary_not_found(client):
    _make_user_and_login(client)
    r = client.put("/api/v1/salary/nonexistent-id", json={
        "valid_from": "2026-01-01",
        "ral": 36000,
        "employer_contrib_rate": 0.02,
        "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173,
        "municipal_tax_rate": 0.001,
        "salary_months": 12,
    })
    assert r.status_code == 404


def test_delete_salary_not_earliest(client):
    _make_user_and_login(client)
    # Create the earliest salary entry
    client.post("/api/v1/salary", json={
        "valid_from": "2026-01-01",
        "ral": 30000,
        "employer_contrib_rate": 0.02,
        "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173,
        "municipal_tax_rate": 0.001,
        "salary_months": 12,
    })
    # Create a second (later) salary entry
    second_id = client.post("/api/v1/salary", json={
        "valid_from": "2027-01-01",
        "ral": 36000,
        "employer_contrib_rate": 0.02,
        "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173,
        "municipal_tax_rate": 0.001,
        "salary_months": 12,
    }).json()["id"]
    # Deleting the non-earliest should succeed
    r = client.delete(f"/api/v1/salary/{second_id}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_delete_salary_earliest_returns_400(client):
    _make_user_and_login(client)
    # Create two salary entries
    earliest_id = client.post("/api/v1/salary", json={
        "valid_from": "2026-01-01",
        "ral": 30000,
        "employer_contrib_rate": 0.02,
        "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173,
        "municipal_tax_rate": 0.001,
        "salary_months": 12,
    }).json()["id"]
    client.post("/api/v1/salary", json={
        "valid_from": "2027-01-01",
        "ral": 36000,
        "employer_contrib_rate": 0.02,
        "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173,
        "municipal_tax_rate": 0.001,
        "salary_months": 12,
    })
    # Deleting the earliest should be rejected
    r = client.delete(f"/api/v1/salary/{earliest_id}")
    assert r.status_code == 400


def test_delete_salary_not_found(client):
    _make_user_and_login(client)
    r = client.delete("/api/v1/salary/nonexistent-id")
    assert r.status_code == 404


def test_create_salary_months_zero_returns_422(client):
    _make_user_and_login(client)
    resp = client.post("/api/v1/salary", json={
        "valid_from": "2026-01-01", "ral": 36000,
        "employer_contrib_rate": 0.0, "voluntary_contrib_rate": 0.0,
        "regional_tax_rate": 0.0, "municipal_tax_rate": 0.0,
        "salary_months": 0,
    })
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"ral": 0},
        {"ral": "NaN"},
        {"employer_contrib_rate": 1.0001},
        {"regional_tax_rate": -0.0001},
        {"salary_months": 11},
        {"meal_vouchers_annual": "100.001"},
    ],
)
def test_calculate_rejects_invalid_salary_values_before_calculation(client, params):
    _make_user_and_login(client)
    response = client.get("/api/v1/salary/calculate", params={
        "as_of": "2026-01-01", "ral": 36000,
        "employer_contrib_rate": 0.02, "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173, "municipal_tax_rate": 0.001,
        **params,
    })
    assert response.status_code == 422


def test_lower_salary_override_is_returned_as_effective_monthly_net(client):
    _make_user_and_login(client)
    response = client.post("/api/v1/salary", json={
        "valid_from": "2026-01-01", "ral": 36000,
        "employer_contrib_rate": 0.02, "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173, "municipal_tax_rate": 0.001,
        "manual_net_override": 1000,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["computed_net_monthly"] > 1000
    assert data["manual_net_override"] == 1000
    assert data["effective_net_monthly"] == 1000


def test_explicit_null_clears_salary_override_and_uses_computed_net(client):
    _make_user_and_login(client)
    created = client.post("/api/v1/salary", json={
        "valid_from": "2026-01-01", "ral": 36000,
        "employer_contrib_rate": 0.02, "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173, "municipal_tax_rate": 0.001,
        "manual_net_override": 2500,
    }).json()

    response = client.put(f"/api/v1/salary/{created['id']}", json={
        "valid_from": "2026-01-01", "ral": 36000,
        "employer_contrib_rate": 0.02, "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173, "municipal_tax_rate": 0.001,
        "manual_net_override": None,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["manual_net_override"] is None
    assert data["effective_net_monthly"] == data["computed_net_monthly"]


def test_omitted_salary_override_preserves_existing_override(client):
    _make_user_and_login(client)
    created = client.post("/api/v1/salary", json={
        "valid_from": "2026-01-01", "ral": 36000,
        "employer_contrib_rate": 0.02, "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173, "municipal_tax_rate": 0.001,
        "manual_net_override": 2500,
    }).json()

    response = client.put(f"/api/v1/salary/{created['id']}", json={
        "valid_from": "2026-01-01", "ral": 42000,
        "employer_contrib_rate": 0.02, "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173, "municipal_tax_rate": 0.001,
    })

    assert response.status_code == 200
    assert response.json()["manual_net_override"] == 2500


def test_create_salary_without_tax_config_returns_422_without_persisting(client, db):
    from app.models.salary import SalaryConfig

    _make_user_and_login(client)
    response = client.post("/api/v1/salary", json={
        "valid_from": "1990-01-01", "ral": 36000,
        "employer_contrib_rate": 0.02, "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173, "municipal_tax_rate": 0.001,
    })

    assert response.status_code == 422
    assert db.query(SalaryConfig).count() == 0


def test_update_salary_without_tax_config_returns_422_without_changing_salary(client):
    _make_user_and_login(client)
    created = client.post("/api/v1/salary", json={
        "valid_from": "2026-01-01", "ral": 36000,
        "employer_contrib_rate": 0.02, "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173, "municipal_tax_rate": 0.001,
    }).json()

    response = client.put(f"/api/v1/salary/{created['id']}", json={
        "valid_from": "1990-01-01", "ral": 42000,
        "employer_contrib_rate": 0.02, "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173, "municipal_tax_rate": 0.001,
    })

    assert response.status_code == 422
    assert client.get("/api/v1/salary").json()[0]["ral"] == 36000


@pytest.mark.parametrize("effective_date", ["not-a-date", "2026-01-15"])
def test_salary_create_rejects_noncanonical_effective_period_without_persisting(
    client, db, effective_date
):
    from app.models.salary import SalaryConfig

    _make_user_and_login(client)
    response = client.post("/api/v1/salary", json={
        "valid_from": effective_date, "ral": 36000,
    })

    assert response.status_code == 422
    assert db.query(SalaryConfig).count() == 0


@pytest.mark.parametrize("effective_date", ["not-a-date", "2026-01-15"])
def test_salary_preview_rejects_noncanonical_effective_period(client, effective_date):
    _make_user_and_login(client)
    response = client.get("/api/v1/salary/calculate", params={
        "as_of": effective_date, "ral": 36000,
    })

    assert response.status_code == 422


def test_salary_create_rejects_negative_taxable_base_without_persisting(client, db):
    from app.models.salary import SalaryConfig

    _make_user_and_login(client)
    response = client.post("/api/v1/salary", json={
        "valid_from": "2026-01-01", "ral": 100,
        "employer_contrib_rate": 1, "voluntary_contrib_rate": 1,
        "regional_tax_rate": 1, "municipal_tax_rate": 1,
    })

    assert response.status_code == 422
    assert db.query(SalaryConfig).count() == 0


def test_salary_preview_rejects_capped_deduction_negative_net(client):
    _make_user_and_login(client)

    response = client.get("/api/v1/salary/calculate", params={
        "as_of": "2026-01-01",
        **CAPPED_DEDUCTION_NEGATIVE_NET,
    })

    assert response.status_code == 422
    assert response.json()["detail"] == "Computed net annual salary must not be negative"


def test_salary_create_rejects_capped_deduction_negative_net_without_persisting(client, db):
    from app.models.salary import SalaryConfig

    _make_user_and_login(client)
    response = client.post("/api/v1/salary", json={
        "valid_from": "2026-01-01",
        **CAPPED_DEDUCTION_NEGATIVE_NET,
    })

    assert response.status_code == 422
    assert db.query(SalaryConfig).count() == 0


def test_salary_update_rejects_capped_deduction_negative_net_without_changing_salary(client):
    _make_user_and_login(client)
    created = client.post("/api/v1/salary", json={
        "valid_from": "2026-01-01", "ral": 36000,
        "employer_contrib_rate": 0.02, "voluntary_contrib_rate": 0.01,
        "regional_tax_rate": 0.0173, "municipal_tax_rate": 0.001,
    }).json()

    response = client.put(f"/api/v1/salary/{created['id']}", json={
        "valid_from": "2026-01-01",
        **CAPPED_DEDUCTION_NEGATIVE_NET,
    })

    assert response.status_code == 422
    saved = client.get("/api/v1/salary").json()[0]
    assert saved["ral"] == 36000
    assert saved["voluntary_contrib_rate"] == 0.01


def test_calculate_salary_months_zero_returns_422(client):
    _make_user_and_login(client)
    resp = client.get("/api/v1/salary/calculate", params={
        "as_of": "2026-01-01", "ral": 36000,
        "employer_contrib_rate": 0.0, "voluntary_contrib_rate": 0.0,
        "regional_tax_rate": 0.0, "municipal_tax_rate": 0.0,
        "salary_months": 0,
    })
    assert resp.status_code == 422
