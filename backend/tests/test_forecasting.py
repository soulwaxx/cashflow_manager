import pytest
from tests.test_onboarding import WIZARD_PAYLOAD

def _setup(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    pm_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyBank")
    cat_id = next(c["id"] for c in client.get("/api/v1/categories").json() if c["type"] == "Mobility")
    # Create a recurring expense in 2026 to use as base
    client.post("/api/v1/transactions", json={
        "date": "2026-01-05", "detail": "Car loan", "amount": 350,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit", "recurrence_months": 12,
    })
    return pm_id, cat_id


def _foreign_assets(client):
    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/register", json={
        "email": "bob@example.com", "password": "Password1!", "name": "Bob"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    pm_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyBank")
    cat_id = next(c["id"] for c in client.get("/api/v1/categories").json() if c["type"] == "Mobility")
    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={
        "email": "alice@example.com", "password": "Password1!"
    })
    return pm_id, cat_id

def test_create_forecast(client):
    _setup(client)
    r = client.post("/api/v1/forecasts", json={"name": "3-year plan", "base_year": 2026, "projection_years": 3})
    assert r.status_code == 200
    assert r.json()["name"] == "3-year plan"

def test_forecast_auto_generates_lines_from_recurring(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 3}).json()["id"]
    r = client.get(f"/api/v1/forecasts/{fc_id}")
    assert r.status_code == 200
    lines = r.json()["lines"]
    assert any(l["detail"] == "Car loan" for l in lines)

def test_forecast_projection_covers_correct_years(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 2}).json()["id"]
    r = client.get(f"/api/v1/forecasts/{fc_id}/projection")
    assert r.status_code == 200
    data = r.json()
    assert data["period"]["from"] == "2027-01"
    assert data["period"]["to"] == "2028-12"

def test_forecast_projection_uses_base_amount(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 1}).json()["id"]
    proj = client.get(f"/api/v1/forecasts/{fc_id}/projection").json()
    car_line = next((l for l in proj["lines"] if l["detail"] == "Car loan"), None)
    assert car_line is not None
    assert all(m["effective_amount"] == pytest.approx(350.0) for m in car_line["months"])

def test_adjustment_changes_amount_from_valid_from(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 2}).json()["id"]
    line_id = next(l["id"] for l in client.get(f"/api/v1/forecasts/{fc_id}").json()["lines"] if l["detail"] == "Car loan")
    client.post(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments", json={
        "valid_from": "2028-03-01", "new_amount": 450.0
    })
    proj = client.get(f"/api/v1/forecasts/{fc_id}/projection").json()
    car_line = next(l for l in proj["lines"] if l["detail"] == "Car loan")
    months = {m["month"]: m["effective_amount"] for m in car_line["months"]}
    assert months["2028-02"] == pytest.approx(350.0)
    assert months["2028-03"] == pytest.approx(450.0)
    assert months["2028-12"] == pytest.approx(450.0)

def test_reduce_projection_years_deletes_out_of_range_adjustments(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 3}).json()["id"]
    line_id = next(l["id"] for l in client.get(f"/api/v1/forecasts/{fc_id}").json()["lines"] if l["detail"] == "Car loan")
    client.post(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments", json={
        "valid_from": "2029-06-01", "new_amount": 500.0
    })
    client.put(f"/api/v1/forecasts/{fc_id}", json={"name": "Plan", "projection_years": 1})
    fc = client.get(f"/api/v1/forecasts/{fc_id}").json()
    for line in fc["lines"]:
        assert all(a["valid_from"] <= "2027-12-01" for a in line["adjustments"])

def test_delete_forecast(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 1}).json()["id"]
    assert client.delete(f"/api/v1/forecasts/{fc_id}").status_code == 200
    assert client.get(f"/api/v1/forecasts/{fc_id}").status_code == 404


def test_list_forecasts_returns_list(client):
    _setup(client)
    r = client.get("/api/v1/forecasts")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_forecasts_includes_created_forecast(client):
    _setup(client)
    client.post("/api/v1/forecasts", json={"name": "My Plan", "base_year": 2026, "projection_years": 1})
    r = client.get("/api/v1/forecasts")
    assert any(fc["name"] == "My Plan" for fc in r.json())


def test_update_forecast_not_found(client):
    _setup(client)
    r = client.put("/api/v1/forecasts/nonexistent-id", json={"name": "New Name"})
    assert r.status_code == 404


def test_delete_forecast_not_found(client):
    _setup(client)
    r = client.delete("/api/v1/forecasts/nonexistent-id")
    assert r.status_code == 404


def test_get_projection_not_found(client):
    _setup(client)
    r = client.get("/api/v1/forecasts/nonexistent-id/projection")
    assert r.status_code == 404


def test_add_line_to_forecast(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 1}).json()["id"]
    r = client.post(f"/api/v1/forecasts/{fc_id}/lines", json={
        "detail": "Extra expense", "base_amount": 100.0, "billing_day": 15,
    })
    assert r.status_code == 200
    assert r.json()["detail"] == "Extra expense"
    assert r.json()["base_amount"] == 100.0


def test_add_line_to_nonexistent_forecast(client):
    _setup(client)
    r = client.post("/api/v1/forecasts/nonexistent-id/lines", json={
        "detail": "Ghost", "base_amount": 50.0,
    })
    assert r.status_code == 404


@pytest.mark.parametrize("field_name", ["category_id", "payment_method_id"])
def test_add_line_rejects_foreign_owned_ids(client, field_name):
    alice_pm_id, alice_cat_id = _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 1}).json()["id"]
    foreign_pm_id, foreign_cat_id = _foreign_assets(client)
    payload = {
        "detail": "Cross-user line",
        "base_amount": 100.0,
        "billing_day": 10,
        "category_id": alice_cat_id,
        "payment_method_id": alice_pm_id,
    }
    if field_name == "category_id":
        payload["category_id"] = foreign_cat_id
    else:
        payload["payment_method_id"] = foreign_pm_id
    r = client.post(f"/api/v1/forecasts/{fc_id}/lines", json=payload)
    assert r.status_code == 422


def test_update_line(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 1}).json()["id"]
    line_id = client.post(f"/api/v1/forecasts/{fc_id}/lines", json={
        "detail": "Old name", "base_amount": 200.0,
    }).json()["id"]
    r = client.put(f"/api/v1/forecasts/{fc_id}/lines/{line_id}", json={
        "detail": "New name", "base_amount": 300.0, "billing_day": 20, "notes": "Updated",
    })
    assert r.status_code == 200
    assert r.json()["detail"] == "New name"
    assert r.json()["base_amount"] == 300.0
    assert r.json()["billing_day"] == 20
    assert r.json()["notes"] == "Updated"


@pytest.mark.parametrize("field_name", ["category_id", "payment_method_id"])
def test_update_line_rejects_foreign_owned_ids(client, field_name):
    alice_pm_id, alice_cat_id = _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 1}).json()["id"]
    line_id = client.post(f"/api/v1/forecasts/{fc_id}/lines", json={
        "detail": "Own line", "base_amount": 200.0,
        "category_id": alice_cat_id, "payment_method_id": alice_pm_id,
    }).json()["id"]
    foreign_pm_id, foreign_cat_id = _foreign_assets(client)
    payload = {
        "detail": "Own line updated",
        "base_amount": 225.0,
        "billing_day": 15,
        "notes": "updated",
        "category_id": alice_cat_id,
        "payment_method_id": alice_pm_id,
    }
    if field_name == "category_id":
        payload["category_id"] = foreign_cat_id
    else:
        payload["payment_method_id"] = foreign_pm_id
    r = client.put(f"/api/v1/forecasts/{fc_id}/lines/{line_id}", json=payload)
    assert r.status_code == 422


def test_update_line_requires_full_body(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 1}).json()["id"]
    line_id = client.post(f"/api/v1/forecasts/{fc_id}/lines", json={
        "detail": "Own line", "base_amount": 200.0,
    }).json()["id"]

    r = client.put(f"/api/v1/forecasts/{fc_id}/lines/{line_id}", json={
        "payment_method_id": None,
    })
    assert r.status_code == 422
    errors = {(err["loc"][-1], err["type"]) for err in r.json()["detail"]}
    assert ("detail", "missing") in errors
    assert ("base_amount", "missing") in errors


def test_update_line_response_includes_adjustments(client):
    """PUT /lines/{id} must return same shape as POST /lines — including adjustments list."""
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 3}).json()["id"]
    line_id = client.post(f"/api/v1/forecasts/{fc_id}/lines", json={
        "detail": "Expense", "base_amount": 100.0,
    }).json()["id"]
    # Add an adjustment to ensure it comes back in the update response
    client.post(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments", json={
        "valid_from": "2027-06-01", "new_amount": 150.0,
    })
    r = client.put(f"/api/v1/forecasts/{fc_id}/lines/{line_id}", json={
        "detail": "Expense updated", "base_amount": 120.0, "billing_day": 12,
    })
    assert r.status_code == 200
    body = r.json()
    assert "adjustments" in body, "update_line response must include adjustments key"
    assert len(body["adjustments"]) == 1
    assert body["adjustments"][0]["valid_from"] == "2027-06-01"


def test_update_line_not_found(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 1}).json()["id"]
    r = client.put(f"/api/v1/forecasts/{fc_id}/lines/nonexistent-line-id", json={
        "detail": "Ghost", "base_amount": 50.0, "billing_day": 1,
    })
    assert r.status_code == 404


def test_delete_line(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 1}).json()["id"]
    line_id = client.post(f"/api/v1/forecasts/{fc_id}/lines", json={
        "detail": "Temp line", "base_amount": 75.0,
    }).json()["id"]
    r = client.delete(f"/api/v1/forecasts/{fc_id}/lines/{line_id}")
    assert r.status_code == 200
    fc = client.get(f"/api/v1/forecasts/{fc_id}").json()
    assert not any(l["id"] == line_id for l in fc["lines"])


def test_delete_line_not_found(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 1}).json()["id"]
    r = client.delete(f"/api/v1/forecasts/{fc_id}/lines/nonexistent-line-id")
    assert r.status_code == 404


def test_add_adjustment_forecast_not_found(client):
    _setup(client)
    r = client.post("/api/v1/forecasts/nonexistent-id/lines/some-line/adjustments", json={
        "valid_from": "2027-01-01", "new_amount": 500.0,
    })
    assert r.status_code == 404


def test_add_adjustment_line_not_found(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 2}).json()["id"]
    r = client.post(f"/api/v1/forecasts/{fc_id}/lines/nonexistent-line-id/adjustments", json={
        "valid_from": "2027-01-01", "new_amount": 500.0,
    })
    assert r.status_code == 404


def test_add_adjustment_valid_from_out_of_range(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 1}).json()["id"]
    line_id = next(l["id"] for l in client.get(f"/api/v1/forecasts/{fc_id}").json()["lines"] if l["detail"] == "Car loan")
    # valid_from is before the projection start (2027-01-01)
    r = client.post(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments", json={
        "valid_from": "2026-06-01", "new_amount": 999.0,
    })
    assert r.status_code == 422


def test_update_adjustment(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 2}).json()["id"]
    line_id = next(l["id"] for l in client.get(f"/api/v1/forecasts/{fc_id}").json()["lines"] if l["detail"] == "Car loan")
    adj_id = client.post(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments", json={
        "valid_from": "2027-06-01", "new_amount": 400.0,
    }).json()["id"]
    r = client.put(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments/{adj_id}", json={
        "valid_from": "2027-09-01", "new_amount": 550.0,
    })
    assert r.status_code == 200
    assert r.json()["new_amount"] == 550.0
    assert r.json()["valid_from"] == "2027-09-01"


def test_update_adjustment_accepts_partial_body(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 2}).json()["id"]
    line_id = next(l["id"] for l in client.get(f"/api/v1/forecasts/{fc_id}").json()["lines"] if l["detail"] == "Car loan")
    adj_id = client.post(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments", json={
        "valid_from": "2027-06-01", "new_amount": 400.0, "adjustment_type": "fixed",
    }).json()["id"]

    r = client.put(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments/{adj_id}", json={
        "new_amount": 575.0,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["new_amount"] == 575.0
    assert body["valid_from"] == "2027-06-01"
    assert body["adjustment_type"] == "fixed"


def test_update_adjustment_not_found(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 2}).json()["id"]
    line_id = next(l["id"] for l in client.get(f"/api/v1/forecasts/{fc_id}").json()["lines"] if l["detail"] == "Car loan")
    r = client.put(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments/nonexistent-adj-id", json={
        "valid_from": "2027-06-01", "new_amount": 400.0,
    })
    assert r.status_code == 404


def test_delete_adjustment(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 2}).json()["id"]
    line_id = next(l["id"] for l in client.get(f"/api/v1/forecasts/{fc_id}").json()["lines"] if l["detail"] == "Car loan")
    adj_id = client.post(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments", json={
        "valid_from": "2027-03-01", "new_amount": 420.0,
    }).json()["id"]
    r = client.delete(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments/{adj_id}")
    assert r.status_code == 200
    fc = client.get(f"/api/v1/forecasts/{fc_id}").json()
    line = next(l for l in fc["lines"] if l["id"] == line_id)
    assert not any(a["id"] == adj_id for a in line["adjustments"])


def test_delete_adjustment_not_found(client):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Plan", "base_year": 2026, "projection_years": 2}).json()["id"]
    line_id = next(l["id"] for l in client.get(f"/api/v1/forecasts/{fc_id}").json()["lines"] if l["detail"] == "Car loan")
    r = client.delete(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments/nonexistent-adj-id")
    assert r.status_code == 404


def test_forecast_detail_bulk_loads_adjustments(client):
    """GET /{fc_id} must return all adjustments regardless of how many lines exist."""
    from tests.test_onboarding import WIZARD_PAYLOAD

    client.post("/api/v1/auth/register", json={
        "email": "fc_bulk@test.com", "password": "Password1!", "name": "FcBulk"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)

    fc = client.post("/api/v1/forecasts", json={
        "name": "BulkTest", "base_year": 2025, "projection_years": 1
    }).json()
    fc_id = fc["id"]

    # Add 3 manual lines
    line_ids = []
    for i in range(3):
        line = client.post(f"/api/v1/forecasts/{fc_id}/lines", json={
            "detail": f"Line {i}", "base_amount": 100.0
        }).json()
        line_ids.append(line["id"])

    # Add one adjustment per line
    for line_id in line_ids:
        client.post(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments", json={
            "valid_from": "2026-06-01", "new_amount": 200.0
        })

    detail = client.get(f"/api/v1/forecasts/{fc_id}").json()
    # Every line must have its adjustment
    for line in detail["lines"]:
        if line["id"] in line_ids:
            assert len(line["adjustments"]) == 1, \
                f"Line {line['id']} missing adjustment"


# ---------------------------------------------------------------------------
# H-4: project_forecast must respect user_id — another user cannot trigger it
# ---------------------------------------------------------------------------
def test_project_forecast_wrong_user_returns_404(client):
    """Projection endpoint must 404 when the forecast belongs to a different user."""
    from tests.test_onboarding import WIZARD_PAYLOAD

    # Alice creates a forecast
    client.post("/api/v1/auth/register", json={
        "email": "alice_h4@test.com", "password": "Password1!", "name": "Alice"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    fc_id = client.post("/api/v1/forecasts", json={
        "name": "Alice plan", "base_year": 2026, "projection_years": 1
    }).json()["id"]

    # Bob registers and logs in (cookie is now Bob's session)
    client.post("/api/v1/auth/register", json={
        "email": "bob_h4@test.com", "password": "Password1!", "name": "Bob"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)

    # Bob tries to access Alice's projection — must get 404
    r = client.get(f"/api/v1/forecasts/{fc_id}/projection")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# H-5: updating a forecast name to empty string must be accepted
# ---------------------------------------------------------------------------
def test_update_forecast_name_to_empty_string(client):
    """Setting name='' is a valid update and must not be silently skipped."""
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={
        "name": "Original Name", "base_year": 2026, "projection_years": 1
    }).json()["id"]

    r = client.put(f"/api/v1/forecasts/{fc_id}", json={"name": ""})
    assert r.status_code == 200
    assert r.json()["name"] == ""


# ---------------------------------------------------------------------------
# H-6: add_line response must contain the expected dict fields
# ---------------------------------------------------------------------------
def test_add_line_response_has_expected_fields(client):
    """add_line must return a dict with the same fields as _forecast_detail line entries."""
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={
        "name": "Plan", "base_year": 2026, "projection_years": 1
    }).json()["id"]

    r = client.post(f"/api/v1/forecasts/{fc_id}/lines", json={
        "detail": "New line", "base_amount": 123.45, "billing_day": 10,
    })
    assert r.status_code == 200
    body = r.json()
    for field in ("id", "detail", "base_amount", "billing_day", "category_id",
                  "payment_method_id", "notes", "adjustments"):
        assert field in body, f"Missing field: {field}"
    assert body["detail"] == "New line"
    assert body["base_amount"] == pytest.approx(123.45)
    assert body["billing_day"] == 10
    assert body["adjustments"] == []


# --- Group 3: percentage adjustments ---

def _make_forecast_with_line(client, base_amount: float, projection_years: int = 1) -> tuple[str, str]:
    """Create a forecast with a single manual line; return (fc_id, line_id)."""
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={
        "name": "PctTest", "base_year": 2026, "projection_years": projection_years,
    }).json()["id"]
    line_id = client.post(f"/api/v1/forecasts/{fc_id}/lines", json={
        "detail": "PctLine", "base_amount": base_amount,
    }).json()["id"]
    return fc_id, line_id


def test_percentage_adjustment_positive(client):
    """A 10% adjustment on base_amount=1000 must yield effective_amount=1100.0 in the projection."""
    fc_id, line_id = _make_forecast_with_line(client, base_amount=1000.0)
    client.post(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments", json={
        "valid_from": "2027-01-01", "new_amount": 10.0, "adjustment_type": "percentage",
    })
    proj = client.get(f"/api/v1/forecasts/{fc_id}/projection").json()
    pct_line = next(l for l in proj["lines"] if l["detail"] == "PctLine")
    # All months from 2027-01 onward should show 1100
    for m in pct_line["months"]:
        assert m["effective_amount"] == pytest.approx(1100.0), (
            f"Expected 1100.0 for month {m['month']}, got {m['effective_amount']}"
        )


def test_percentage_adjustment_zero_percent(client):
    """A 0% adjustment on base_amount=1000 must leave effective_amount unchanged at 1000.0."""
    fc_id, line_id = _make_forecast_with_line(client, base_amount=1000.0)
    client.post(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments", json={
        "valid_from": "2027-01-01", "new_amount": 0.0, "adjustment_type": "percentage",
    })
    proj = client.get(f"/api/v1/forecasts/{fc_id}/projection").json()
    pct_line = next(l for l in proj["lines"] if l["detail"] == "PctLine")
    for m in pct_line["months"]:
        assert m["effective_amount"] == pytest.approx(1000.0), (
            f"Expected 1000.0 for month {m['month']}, got {m['effective_amount']}"
        )


def test_percentage_adjustment_negative_percent(client):
    """A -20% adjustment on base_amount=1000 must yield effective_amount=800.0."""
    fc_id, line_id = _make_forecast_with_line(client, base_amount=1000.0)
    client.post(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments", json={
        "valid_from": "2027-01-01", "new_amount": -20.0, "adjustment_type": "percentage",
    })
    proj = client.get(f"/api/v1/forecasts/{fc_id}/projection").json()
    pct_line = next(l for l in proj["lines"] if l["detail"] == "PctLine")
    for m in pct_line["months"]:
        assert m["effective_amount"] == pytest.approx(800.0), (
            f"Expected 800.0 for month {m['month']}, got {m['effective_amount']}"
        )


def test_update_forecast_trims_out_of_range_adjustments(client):
    """Reducing projection_years must delete adjustments beyond the new end date."""
    client.post("/api/v1/auth/register", json={"email": "u@x.com", "password": "Password1!", "name": "U"})
    client.post("/api/v1/auth/login", json={"email": "u@x.com", "password": "Password1!"})

    # Create forecast: base_year=2026, 3 projection years → end 2029-12-01
    fc = client.post("/api/v1/forecasts", json={
        "name": "Plan", "base_year": 2026, "projection_years": 3,
    }).json()
    fc_id = fc["id"]

    # Add a line
    line = client.post(f"/api/v1/forecasts/{fc_id}/lines", json={
        "detail": "Test line", "base_amount": 100,
    }).json()
    line_id = line["id"]

    # Add two adjustments: one in 2028 (will be kept) and one in 2029 (will be trimmed)
    client.post(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments", json={
        "valid_from": "2028-01-01", "new_amount": 200,
    })
    client.post(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments", json={
        "valid_from": "2029-06-01", "new_amount": 300,
    })

    # Reduce projection to 2 years → end 2028-12-01; 2029 adjustment must be deleted
    r = client.put(f"/api/v1/forecasts/{fc_id}", json={"projection_years": 2})
    assert r.status_code == 200

    # Fetch the forecast and check adjustments
    detail = client.get(f"/api/v1/forecasts/{fc_id}").json()
    line_data = next(l for l in detail["lines"] if l["id"] == line_id)
    adj_dates = [a["valid_from"] for a in line_data["adjustments"]]

    assert "2028-01-01" in adj_dates, "In-range adjustment must be kept"
    assert "2029-06-01" not in adj_dates, "Out-of-range adjustment must be deleted"


def _make_two_forecasts(client):
    """Helper: set up Alice's account, create two forecasts A and B.
    Returns (fc_a_id, fc_b_id, line_a_id, adj_a_id).
    """
    _setup(client)
    fc_a = client.post("/api/v1/forecasts", json={"name": "A", "base_year": 2026, "projection_years": 2}).json()
    fc_b = client.post("/api/v1/forecasts", json={"name": "B", "base_year": 2026, "projection_years": 2}).json()
    fc_a_id = fc_a["id"]
    fc_b_id = fc_b["id"]
    line_a_id = fc_a["lines"][0]["id"]
    # Create adjustment on forecast A's line
    adj_resp = client.post(
        f"/api/v1/forecasts/{fc_a_id}/lines/{line_a_id}/adjustments",
        json={"valid_from": "2027-06-01", "new_amount": 999.0}
    )
    assert adj_resp.status_code == 200
    adj_a_id = adj_resp.json()["id"]
    return fc_a_id, fc_b_id, line_a_id, adj_a_id


def test_update_adjustment_rejects_wrong_forecast_id(client):
    """IDOR: updating an adjustment via forecast B's URL (when adj belongs to forecast A) must return 404."""
    fc_a_id, fc_b_id, line_a_id, adj_a_id = _make_two_forecasts(client)
    # Attempt to update adj_a via forecast B's URL — must fail
    r = client.put(
        f"/api/v1/forecasts/{fc_b_id}/lines/{line_a_id}/adjustments/{adj_a_id}",
        json={"valid_from": "2027-06-01", "new_amount": 1234.0}
    )
    assert r.status_code == 404
    # Verify amount was NOT changed
    fc_a = client.get(f"/api/v1/forecasts/{fc_a_id}").json()
    line = next(l for l in fc_a["lines"] if l["id"] == line_a_id)
    assert line["adjustments"][0]["new_amount"] == 999.0


def test_update_adjustment_valid_from_outside_period_returns_422(client):
    """update_adjustment must reject valid_from outside the forecast's projection period."""
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "P", "base_year": 2026, "projection_years": 2}).json()["id"]
    line_id = client.get(f"/api/v1/forecasts/{fc_id}").json()["lines"][0]["id"]
    adj_id = client.post(
        f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments",
        json={"valid_from": "2027-06-01", "new_amount": 500.0}
    ).json()["id"]
    # Try to move valid_from outside the 2027-2028 window
    r = client.put(
        f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments/{adj_id}",
        json={"valid_from": "2030-01-01", "new_amount": 500.0}
    )
    assert r.status_code == 422


def test_delete_adjustment_rejects_wrong_forecast_id(client):
    """IDOR: deleting an adjustment via forecast B's URL (when adj belongs to forecast A) must return 404."""
    fc_a_id, fc_b_id, line_a_id, adj_a_id = _make_two_forecasts(client)
    r = client.delete(
        f"/api/v1/forecasts/{fc_b_id}/lines/{line_a_id}/adjustments/{adj_a_id}"
    )
    assert r.status_code == 404
    # Verify adj was NOT deleted
    fc_a = client.get(f"/api/v1/forecasts/{fc_a_id}").json()
    line = next(l for l in fc_a["lines"] if l["id"] == line_a_id)
    assert len(line["adjustments"]) == 1


# ---------------------------------------------------------------------------
# Perf #5: bisect-based adjustment lookup must select the correct adjustment
# ---------------------------------------------------------------------------
def test_forecast_projection_bisect_adjustment(client):
    """Two adjustments at different valid_from dates: bisect must pick the right one per month."""
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={
        "name": "BisectTest", "base_year": 2026, "projection_years": 2,
    }).json()["id"]

    # Add a manual line with base_amount=100
    line_id = client.post(f"/api/v1/forecasts/{fc_id}/lines", json={
        "detail": "BisectLine", "base_amount": 100.0,
    }).json()["id"]

    # Adjustment 1: valid from 2027-03-01 → fixed amount 200
    client.post(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments", json={
        "valid_from": "2027-03-01", "new_amount": 200.0,
    })
    # Adjustment 2: valid from 2027-09-01 → fixed amount 300
    client.post(f"/api/v1/forecasts/{fc_id}/lines/{line_id}/adjustments", json={
        "valid_from": "2027-09-01", "new_amount": 300.0,
    })

    proj = client.get(f"/api/v1/forecasts/{fc_id}/projection").json()
    bisect_line = next(l for l in proj["lines"] if l["detail"] == "BisectLine")
    months = {m["month"]: m["effective_amount"] for m in bisect_line["months"]}

    # Before first adjustment: base_amount applies
    assert months["2027-01"] == pytest.approx(100.0), f"2027-01 should be base 100, got {months['2027-01']}"
    assert months["2027-02"] == pytest.approx(100.0), f"2027-02 should be base 100, got {months['2027-02']}"

    # From 2027-03 onward (but before 2027-09): first adjustment (200) applies
    assert months["2027-03"] == pytest.approx(200.0), f"2027-03 should be 200, got {months['2027-03']}"
    assert months["2027-08"] == pytest.approx(200.0), f"2027-08 should be 200, got {months['2027-08']}"

    # From 2027-09 onward: second adjustment (300) applies
    assert months["2027-09"] == pytest.approx(300.0), f"2027-09 should be 300, got {months['2027-09']}"
    assert months["2028-12"] == pytest.approx(300.0), f"2028-12 should be 300, got {months['2028-12']}"


def test_import_only_december_debit_commitments_and_latest_amount(client):
    pm_id, cat_id = _setup(client)
    card_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyCard")
    for date, detail, direction, method, count in [
        ("2026-02-10", "Expired loan", "debit", pm_id, 2),
        ("2027-01-10", "Future loan", "debit", pm_id, 12),
        ("2026-12-15", "Salary", "income", pm_id, 1),
        ("2026-12-16", "Card payment", "credit", card_id, 1),
        ("2026-12-18", "One occurrence", "debit", pm_id, 1),
    ]:
        response = client.post("/api/v1/transactions", json={
            "date": date, "detail": detail, "transaction_direction": direction,
            "payment_method_id": method, "category_id": cat_id,
            "amount": 100, "recurrence_months": count,
        })
        assert response.status_code == 200, response.text

    root = client.post("/api/v1/transactions", json={
        "date": "2023-01-20", "detail": "Old ongoing loan", "amount": 50,
        "payment_method_id": pm_id, "category_id": cat_id,
        "transaction_direction": "debit", "recurrence_months": 48,
    })
    assert root.status_code == 200, root.text
    december = next(tx for tx in client.get("/api/v1/transactions?date_month=2026-12").json()
                    if tx["detail"] == "Old ongoing loan")
    assert client.put(f"/api/v1/transactions/{december['id']}", json={"amount": 75}).status_code == 200

    fc_id = client.post("/api/v1/forecasts", json={
        "name": "Boundary", "base_year": 2026, "projection_years": 1,
    }).json()["id"]
    lines = {line["detail"]: line for line in client.get(f"/api/v1/forecasts/{fc_id}").json()["lines"]}
    assert set(lines) == {"Car loan", "One occurrence", "Old ongoing loan"}
    assert lines["Old ongoing loan"]["base_amount"] == 75
    assert lines["Old ongoing loan"]["billing_day"] == 20
    projection = client.get(f"/api/v1/forecasts/{fc_id}/projection").json()
    old_line = next(line for line in projection["lines"] if line["detail"] == "Old ongoing loan")
    assert len(old_line["months"]) == 12
    assert all(month["effective_amount"] == 75 for month in old_line["months"])


def test_import_uses_occurrence_not_credit_card_billing_month(client):
    _setup(client)
    card_id = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyCard")
    assert client.post("/api/v1/transactions", json={
        "date": "2026-12-22", "detail": "Card subscription", "amount": 12,
        "payment_method_id": card_id, "transaction_direction": "debit", "recurrence_months": 1,
    }).status_code == 200
    fc = client.post("/api/v1/forecasts", json={"name": "Cards", "base_year": 2026, "projection_years": 1})
    assert "Card subscription" in {line["detail"] for line in fc.json()["lines"]}


def test_projection_totals_are_rounded_monthly_and_include_empty_months(client):
    _setup(client)
    fc = client.post("/api/v1/forecasts", json={"name": "Cents", "base_year": 2025, "projection_years": 1}).json()
    assert len(client.get(f"/api/v1/forecasts/{fc['id']}/projection").json()["monthly_totals"]) == 12
    line = client.post(f"/api/v1/forecasts/{fc['id']}/lines", json={
        "detail": "Cents", "base_amount": 0.01,
    }).json()
    client.post(f"/api/v1/forecasts/{fc['id']}/lines/{line['id']}/adjustments", json={
        "valid_from": "2026-01-01", "new_amount": 50, "adjustment_type": "percentage",
    })
    result = client.get(f"/api/v1/forecasts/{fc['id']}/projection").json()
    assert len(result["monthly_totals"]) == 12
    assert result["monthly_totals"][0]["total"] == 0.02
    assert result["yearly_totals"][0]["total"] == 0.24


@pytest.mark.parametrize("payload", [
    {"base_year": 1999, "projection_years": 1},
    {"base_year": 2101, "projection_years": 1},
    {"base_year": 2026, "projection_years": 0},
    {"base_year": 2026, "projection_years": 11},
])
def test_forecast_rejects_invalid_years(client, payload):
    _setup(client)
    response = client.post("/api/v1/forecasts", json={"name": "Invalid", **payload})
    assert response.status_code == 422


@pytest.mark.parametrize("amount", [-1, "NaN", "Infinity", 1.234, 10000000000])
def test_forecast_line_rejects_invalid_amounts(client, amount):
    _setup(client)
    fc_id = client.post("/api/v1/forecasts", json={"name": "Valid", "base_year": 2026, "projection_years": 1}).json()["id"]
    response = client.post(f"/api/v1/forecasts/{fc_id}/lines", json={"detail": "Line", "base_amount": amount})
    assert response.status_code == 422


@pytest.mark.parametrize("date_value", ["2027-02-02", "2027-02-30", "2027-13-01", "20270201", "2026-12-01", "2028-01-01"])
def test_forecast_adjustment_rejects_invalid_dates(client, date_value):
    _setup(client)
    fc = client.post("/api/v1/forecasts", json={"name": "Dates", "base_year": 2026, "projection_years": 1}).json()
    response = client.post(f"/api/v1/forecasts/{fc['id']}/lines/{fc['lines'][0]['id']}/adjustments", json={
        "valid_from": date_value, "new_amount": 10,
    })
    assert response.status_code == 422


@pytest.mark.parametrize("adj_type,amount", [
    ("fixed", -1), ("fixed", "NaN"), ("fixed", 1.234),
    ("percentage", -100.01), ("percentage", "Infinity"), ("percentage", 1.234),
])
def test_forecast_adjustment_rejects_invalid_amounts(client, adj_type, amount):
    _setup(client)
    fc = client.post("/api/v1/forecasts", json={"name": "Values", "base_year": 2026, "projection_years": 1}).json()
    response = client.post(f"/api/v1/forecasts/{fc['id']}/lines/{fc['lines'][0]['id']}/adjustments", json={
        "valid_from": "2027-01-01", "new_amount": amount, "adjustment_type": adj_type,
    })
    assert response.status_code == 422


def test_forecast_adjustment_duplicate_month_rejected_on_create_and_update(client):
    _setup(client)
    fc = client.post("/api/v1/forecasts", json={"name": "Duplicates", "base_year": 2026, "projection_years": 1}).json()
    url = f"/api/v1/forecasts/{fc['id']}/lines/{fc['lines'][0]['id']}/adjustments"
    first = client.post(url, json={"valid_from": "2027-01-01", "new_amount": 10})
    assert first.status_code == 200
    assert client.post(url, json={"valid_from": "2027-01-01", "new_amount": 20}).status_code == 422
    second = client.post(url, json={"valid_from": "2027-02-01", "new_amount": 20})
    assert second.status_code == 200
    assert client.put(f"{url}/{second.json()['id']}", json={"valid_from": "2027-01-01"}).status_code == 422
    assert client.put(f"{url}/{second.json()['id']}", json={"adjustment_type": "percentage", "new_amount": -100}).status_code == 200
    assert client.put(f"{url}/{second.json()['id']}", json={"adjustment_type": "fixed"}).status_code == 422


def test_forecast_response_contract_is_consistent_across_endpoints(client):
    _setup(client)
    created = client.post("/api/v1/forecasts", json={
        "name": "Contract", "base_year": 2026, "projection_years": 1,
    }).json()
    fc_id = created["id"]
    listed = next(fc for fc in client.get("/api/v1/forecasts").json() if fc["id"] == fc_id)
    detail = client.get(f"/api/v1/forecasts/{fc_id}").json()
    assert set(listed) == set(created) - {"lines"}
    assert set(detail) == set(created)
    line = detail["lines"][0]
    assert set(line) == {
        "id", "source_transaction_id", "detail", "category_id", "base_amount",
        "billing_day", "payment_method_id", "notes", "adjustments",
    }
    adj = client.post(f"/api/v1/forecasts/{fc_id}/lines/{line['id']}/adjustments", json={
        "valid_from": "2027-03-01", "new_amount": 500,
    }).json()
    assert set(adj) == {"id", "forecast_line_id", "valid_from", "new_amount", "adjustment_type"}
    projection = client.get(f"/api/v1/forecasts/{fc_id}/projection").json()
    projected = next(row for row in projection["lines"] if row["line_id"] == line["id"])
    assert projected["adjustments"][0]["valid_from"] == adj["valid_from"]
    assert set(projection) == {"forecast_id", "base_year", "projection_years", "period", "lines", "monthly_totals", "yearly_totals"}
    assert len(projected["months"]) == len(projection["monthly_totals"]) == 12


def test_forecast_line_can_clear_nullable_references_and_returns_consistent_contract(client):
    pm_id, cat_id = _setup(client)
    fc = client.post("/api/v1/forecasts", json={"name": "References", "base_year": 2026, "projection_years": 1}).json()
    assert fc["user_id"] and fc["created_at"] and fc["updated_at"]
    imported = fc["lines"][0]
    assert imported["source_transaction_id"] is not None
    response = client.put(f"/api/v1/forecasts/{fc['id']}/lines/{imported['id']}", json={
        "detail": "Repaired", "base_amount": 100, "category_id": None,
        "payment_method_id": None, "notes": None,
    })
    assert response.status_code == 200
    assert response.json()["category_id"] is None
    assert response.json()["payment_method_id"] is None
    assert response.json()["source_transaction_id"] == imported["source_transaction_id"]
    assert client.get(f"/api/v1/forecasts/{fc['id']}").json()["lines"][0]["detail"] == "Repaired"
    assert pm_id and cat_id


def test_imported_forecast_is_not_changed_by_later_transaction_edits(client):
    _setup(client)
    fc = client.post("/api/v1/forecasts", json={"name": "Snapshot", "base_year": 2026, "projection_years": 1}).json()
    line = fc["lines"][0]
    tx_id = line["source_transaction_id"]
    assert client.put(f"/api/v1/transactions/{tx_id}", json={"amount": 999}).status_code == 200
    assert client.get(f"/api/v1/forecasts/{fc['id']}").json()["lines"][0]["base_amount"] == 350


def test_import_ignores_cross_user_parent_links(client, db):
    from app.models.transaction import Transaction
    from app.models.user import User

    alice_pm, _ = _setup(client)
    alice_id = db.query(User).filter_by(email="alice@example.com").one().id
    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/register", json={
        "email": "forecast-parent@example.com", "password": "Password1!", "name": "Parent"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    bob_pm = next(pm["id"] for pm in client.get("/api/v1/payment-methods").json() if pm["name"] == "MyBank")
    bob_root = client.post("/api/v1/transactions", json={
        "date": "2026-12-03", "detail": "Other user's loan", "amount": 10,
        "payment_method_id": bob_pm, "transaction_direction": "debit", "recurrence_months": 1,
    }).json()["id"]
    db.add(Transaction(
        user_id=alice_id, date="2026-12-04", detail="Corrupt cross-user child", amount=99,
        payment_method_id=alice_pm, transaction_direction="debit", billing_month="2026-12-01",
        recurrence_months=2, parent_transaction_id=bob_root,
    ))
    db.commit()
    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={
        "email": "alice@example.com", "password": "Password1!"
    })
    fc = client.post("/api/v1/forecasts", json={"name": "Owned roots", "base_year": 2026, "projection_years": 1}).json()
    assert "Corrupt cross-user child" not in {line["detail"] for line in fc["lines"]}


def test_forecast_line_and_adjustment_cross_user_mutations_are_isolated(client):
    _setup(client)
    fc = client.post("/api/v1/forecasts", json={"name": "Private", "base_year": 2026, "projection_years": 1}).json()
    line_id = fc["lines"][0]["id"]
    adj_id = client.post(f"/api/v1/forecasts/{fc['id']}/lines/{line_id}/adjustments", json={
        "valid_from": "2027-01-01", "new_amount": 500,
    }).json()["id"]
    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/register", json={
        "email": "forecast-other@example.com", "password": "Password1!", "name": "Other"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    base = f"/api/v1/forecasts/{fc['id']}/lines/{line_id}"
    assert client.get(f"/api/v1/forecasts/{fc['id']}").status_code == 404
    assert client.put(base, json={"detail": "Hijack", "base_amount": 1}).status_code == 404
    assert client.delete(base).status_code == 404
    assert client.put(f"{base}/adjustments/{adj_id}", json={"new_amount": 1}).status_code == 404
    assert client.delete(f"{base}/adjustments/{adj_id}").status_code == 404
