import pytest


def test_user_cannot_modify_system_seeded_tax_config(client):
    """System-seeded tax configs (user_id=NULL) must not be modifiable via the API."""
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    configs = client.get("/api/v1/tax-config").json()
    system_config = next((c for c in configs if not c.get("user_id")), None)
    if system_config is None:
        pytest.skip("No system-seeded tax configs found")
    resp = client.put(f"/api/v1/tax-config/{system_config['id']}", json={
        "valid_from": system_config["valid_from"],
        "inps_rate": 0.01,
    })
    assert resp.status_code == 403


def test_user_can_create_own_tax_config(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    created = client.post("/api/v1/tax-config", json={
        "valid_from": "2030-01-01",
        "inps_rate": 0.09,
    })
    assert created.status_code == 200
    assert created.json().get("user_id") is not None


def test_list_tax_config_returns_seeded_row(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    r = client.get("/api/v1/tax-config")
    assert r.status_code == 200
    assert len(r.json()) >= 1
    assert r.json()[0]["valid_from"] == "2026-01-01"

def test_create_new_tax_config_period(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    r = client.post("/api/v1/tax-config", json={"valid_from": "2027-01-01", "irpef_band2_rate": 0.35})
    assert r.status_code == 200
    assert r.json()["valid_from"] == "2027-01-01"

def test_update_tax_config(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    config_id = client.post("/api/v1/tax-config", json={"valid_from": "2027-01-01"}).json()["id"]
    r = client.put(f"/api/v1/tax-config/{config_id}", json={
        "valid_from": "2027-01-01", "irpef_band1_rate": 0.22
    })
    assert r.status_code == 200
    assert float(r.json()["irpef_band1_rate"]) == pytest.approx(0.22)

def test_delete_non_earliest_tax_config(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    # Create two user-owned configs; only the later one can be deleted
    client.post("/api/v1/tax-config", json={"valid_from": "2027-01-01"})
    config_id = client.post("/api/v1/tax-config", json={"valid_from": "2028-01-01"}).json()["id"]
    r = client.delete(f"/api/v1/tax-config/{config_id}")
    assert r.status_code == 200

def test_delete_system_seeded_tax_config_returns_403(client):
    """Deleting a system-seeded row (user_id=NULL) must be forbidden."""
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    earliest_id = client.get("/api/v1/tax-config").json()[0]["id"]
    r = client.delete(f"/api/v1/tax-config/{earliest_id}")
    assert r.status_code == 403


def test_delete_earliest_user_owned_tax_config_returns_400(client):
    """Deleting the earliest user-owned row (when it is the global earliest) returns 400."""
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    # Create a user-owned config with a date *before* the seeded 2026-01-01 row
    config_id = client.post("/api/v1/tax-config", json={"valid_from": "2020-01-01"}).json()["id"]
    r = client.delete(f"/api/v1/tax-config/{config_id}")
    assert r.status_code == 400


@pytest.mark.parametrize(
    "payload",
    [
        {"valid_from": "2027-01-01", "inps_rate": -0.01},
        {"valid_from": "2027-01-01", "irpef_band1_rate": 1.0001},
        {"valid_from": "2027-01-01", "irpef_band1_limit": 50000, "irpef_band2_limit": 28000},
        {
            "valid_from": "2027-01-01",
            "employment_deduction_band1_limit": 28000,
            "employment_deduction_band2_limit": 15000,
        },
        {"valid_from": "2027-01-01", "employment_deduction_band2_range": 0},
        {"valid_from": "2027-01-01", "employment_deduction_band3_range": "NaN"},
    ],
)
def test_tax_config_rejects_unsafe_tables(client, payload):
    client.post("/api/v1/auth/register", json={
        "email": "tax-validation@example.com", "password": "Password1!", "name": "Tax"
    })

    response = client.post("/api/v1/tax-config", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize("effective_date", ["not-a-date", "2027-01-15"])
def test_tax_config_rejects_noncanonical_effective_period_without_persisting(
    client, db, effective_date
):
    from app.models.tax import TaxConfig
    from app.models.user import User

    client.post("/api/v1/auth/register", json={
        "email": "tax-date@example.com", "password": "Password1!", "name": "Tax Date"
    })
    response = client.post("/api/v1/tax-config", json={"valid_from": effective_date})

    assert response.status_code == 422
    user = db.query(User).filter_by(email="tax-date@example.com").one()
    assert db.query(TaxConfig).filter_by(user_id=user.id).count() == 0


def test_resolve_tax_config_returns_user_row_when_present(client, db):
    """resolve_tax_config must return a user-specific row (line 16) instead of the system row."""
    from app.models.user import User
    from app.models.tax import TaxConfig
    from app.models.user import gen_uuid
    from app.services.tax import resolve_tax_config

    client.post("/api/v1/auth/register", json={
        "email": "taxuser@example.com", "password": "Password1!", "name": "Tax"
    })
    user = db.query(User).filter_by(email="taxuser@example.com").first()

    user_row = TaxConfig(
        id=gen_uuid(),
        user_id=user.id,
        valid_from="2026-01-01",
        inps_rate=0.05,
    )
    db.add(user_row)
    db.commit()

    result = resolve_tax_config(db, "2026-01", user.id)
    assert result is not None
    assert result.user_id == user.id
    assert abs(float(result.inps_rate) - 0.05) < 1e-6
