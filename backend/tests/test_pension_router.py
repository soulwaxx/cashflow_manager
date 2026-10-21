from tests.test_onboarding import WIZARD_PAYLOAD


def _setup(client, email="pension@example.com"):
    assert client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password1!", "name": "Pension",
    }).status_code == 200
    payload = {**WIZARD_PAYLOAD, "salary": None, "pension": None}
    assert client.post("/api/v1/onboarding", json=payload).status_code == 200
    response = client.post("/api/v1/accounts", json={
        "type": "pension", "name": "Pension Fund", "opening_balance": 0,
        "opening_balance_month": "2026-01-01",
    })
    assert response.status_code == 200
    return response.json()


def _config(account_id, valid_from="2026-01-01", **overrides):
    return {
        "account_id": account_id, "valid_from": valid_from,
        "employee_contrib_rate": 0.01, "employee_contrib_annual_base": 30000,
        "employer_contrib_rate": 0.02, "employer_contrib_annual_base": 20000,
        "tfr_contrib_annual": 2400, "contribution_periods_by_month": [1] * 12,
        **overrides,
    }


def test_pension_config_crud_duplicate_and_owner_isolation(client):
    account = _setup(client)
    created = client.post("/api/v1/pension/configs", json=_config(account["id"]))
    assert created.status_code == 201, created.text
    assert created.json()["employee_contrib_annual_base"] == 30000
    assert isinstance(created.json()["tfr_contrib_annual"], float)
    duplicate = client.post("/api/v1/pension/configs", json=_config(account["id"]))
    assert duplicate.status_code == 409
    assert len(client.get("/api/v1/pension/configs").json()) == 1

    assert client.post("/api/v1/auth/logout").status_code == 200
    other = _setup(client, "other-pension@example.com")
    assert client.put(f"/api/v1/pension/configs/{created.json()['id']}", json=_config(other["id"])).status_code == 404
    assert client.delete(f"/api/v1/pension/configs/{created.json()['id']}").status_code == 404


def test_opening_balance_update_requires_pair_and_active_owned_account(client, db):
    from app.models.account import Account

    account = _setup(client)
    update = client.patch(f"/api/v1/pension/accounts/{account['id']}/opening-balance",
                          json={"amount": 2500, "month": "2026-02-01"})
    assert update.status_code == 200
    assert update.json()["opening_balance"] == 2500
    assert update.json()["opening_balance_month"] == "2026-02-01"
    bad_month = client.patch(f"/api/v1/pension/accounts/{account['id']}/opening-balance",
                             json={"amount": 3000, "month": "2026-02-15"})
    assert bad_month.status_code == 422
    saved = db.query(Account).filter_by(id=account["id"]).one()
    assert float(saved.opening_balance) == 2500
    saved.is_active = False
    db.commit()
    assert client.patch(f"/api/v1/pension/accounts/{account['id']}/opening-balance",
                        json={"amount": 0, "month": "2026-03-01"}).status_code == 422


def test_inactive_destination_and_snapshot_before_opening_reject_without_mutation(client, db):
    from app.models.account import Account
    from app.models.pension import PensionConfig, PensionBalanceSnapshot

    account = _setup(client)
    account_id = account["id"]
    before = db.query(PensionConfig).count()
    assert client.post("/api/v1/pension/configs", json=_config(account_id, "2025-01-01")).status_code == 201
    assert db.query(PensionConfig).count() == before + 1
    before_snapshots = db.query(PensionBalanceSnapshot).count()
    older = {"account_id": account_id, "as_of_month": "2025-12-01", "balance": 100,
             "source": "manual"}
    response = client.put(f"/api/v1/pension/accounts/{account_id}/snapshots/2025-12-01", json=older)
    assert response.status_code == 422
    assert db.query(PensionBalanceSnapshot).count() == before_snapshots
    owned = db.query(Account).filter_by(id=account_id).one()
    owned.is_active = False
    db.commit()
    assert client.post("/api/v1/pension/configs", json=_config(account_id, "2026-01-01")).status_code == 422
    assert db.query(PensionConfig).count() == before + 1


def test_pension_snapshot_upsert_month_identity_and_opening_protection(client):
    account = _setup(client)
    account_id = account["id"]
    req = {"account_id": account_id, "as_of_month": "2026-03-01", "balance": 12000,
           "source": "statement", "notes": "quarter close"}
    response = client.put(f"/api/v1/pension/accounts/{account_id}/snapshots/2026-03-01", json=req)
    assert response.status_code == 200, response.text
    assert response.json()["balance"] == 12000
    mismatch = client.put(f"/api/v1/pension/accounts/{account_id}/snapshots/2026-04-01",
                          json={**req, "as_of_month": "2026-03-01"})
    assert mismatch.status_code == 422
    rows = client.get(f"/api/v1/pension/accounts/{account_id}/snapshots").json()
    assert len(rows) == 1
    compatible = client.patch(f"/api/v1/pension/accounts/{account_id}/opening-balance",
                              json={"amount": 500, "month": "2026-01-01"})
    assert compatible.status_code == 200, compatible.text
    assert client.delete(f"/api/v1/pension/accounts/{account_id}/snapshots/2026-03-01").status_code == 204


def test_opening_correction_conflicts_only_when_snapshot_precedes_new_opening_month(client, db):
    from app.models.account import Account
    from app.models.pension import PensionBalanceSnapshot

    account = _setup(client)
    account_id = account["id"]
    body = {"account_id": account_id, "as_of_month": "2026-03-01", "balance": 20000,
            "source": "statement", "notes": "unchanged"}
    assert client.put(f"/api/v1/pension/accounts/{account_id}/snapshots/2026-03-01", json=body).status_code == 200

    same_month = client.patch(f"/api/v1/pension/accounts/{account_id}/opening-balance",
                              json={"amount": 300, "month": "2026-01-01"})
    assert same_month.status_code == 200
    february = client.patch(f"/api/v1/pension/accounts/{account_id}/opening-balance",
                            json={"amount": 400, "month": "2026-02-01"})
    assert february.status_code == 200
    snapshot = db.query(PensionBalanceSnapshot).filter_by(account_id=account_id).one()
    assert snapshot.as_of_month == "2026-03-01"
    assert float(snapshot.balance) == 20000
    assert snapshot.notes == "unchanged"
    assert next(row for row in client.get("/api/v1/assets/2026?as_of=2026-03-01").json()
                if row["account_id"] == account_id)["computed_amount"] == 20000

    before = db.query(Account).filter_by(id=account_id).one()
    original = (before.opening_balance, before.opening_balance_month)
    conflict = client.patch(f"/api/v1/pension/accounts/{account_id}/opening-balance",
                            json={"amount": 999, "month": "2026-04-01"})
    assert conflict.status_code == 409
    db.expire_all()
    unchanged = db.query(Account).filter_by(id=account_id).one()
    assert (unchanged.opening_balance, unchanged.opening_balance_month) == original
    assert db.query(PensionBalanceSnapshot).filter_by(account_id=account_id).one().notes == "unchanged"


def test_snapshot_is_authoritative_for_assets_and_later_month_projects_from_it(client):
    account = _setup(client)
    account_id = account["id"]
    assert client.post("/api/v1/pension/configs", json=_config(account_id)).status_code == 201
    request = {"account_id": account_id, "as_of_month": "2026-03-01", "balance": 20000,
               "source": "statement", "notes": "statement"}
    assert client.put(f"/api/v1/pension/accounts/{account_id}/snapshots/2026-03-01", json=request).status_code == 200
    march = client.get("/api/v1/assets/2026?as_of=2026-03-01").json()
    april = client.get("/api/v1/assets/2026?as_of=2026-04-01").json()
    assert next(row for row in march if row["account_id"] == account_id)["computed_amount"] == 20000
    april_row = next(row for row in april if row["account_id"] == account_id)
    assert april_row["computed_amount"] == 20258.33
    assert april_row["valuation_status"] == "statement_reconciled"
    assert april_row["projected_through"] == "2026-04-01"


def test_pension_summary_rounds_money_half_even_only_at_response_boundary(client):
    account = _setup(client)
    config = _config(
        account["id"], valid_from="2026-02-01",
        employee_contrib_rate=0.0001, employee_contrib_annual_base=250,
        employer_contrib_rate=0.0001, employer_contrib_annual_base=150,
        tfr_contrib_annual=0.02,
        contribution_periods_by_month=[0, 12] + [0] * 10,
    )
    assert client.post("/api/v1/pension/configs", json=config).status_code == 201
    response = client.get("/api/v1/pension/summary?year=2026&as_of=2026-02-01")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["annualized"]["employee"] == 0.02
    assert data["annualized"]["employer"] == 0.02
    assert data["annualized"]["tfr"] == 0.02
    assert data["annualized"]["eligible_contributions"] == 0.04
    assert data["annualized"]["cap_used"] == 0.04
    assert data["annualized"]["cap_excess"] == 0.0
    assert all(isinstance(value, (int, float)) for value in data["annualized"].values()
               if not isinstance(value, str))
    assert data["year_to_date"] == {"employee": 0.02, "employer": 0.02, "tfr": 0.02}


def test_pension_summary_reports_dated_flows_and_cap_scope(client):
    account = _setup(client)
    response = client.post("/api/v1/pension/configs", json=_config(account["id"]))
    assert response.status_code == 201
    summary = client.get("/api/v1/pension/summary?year=2026&as_of=2026-03-01")
    assert summary.status_code == 200, summary.text
    data = summary.json()
    assert data["year_to_date"] == {"employee": 75, "employer": 100, "tfr": 600}
    assert data["annualized"]["cap_scope"].startswith("configured ordinary payroll")
    assert data["annualized"]["tfr"] == 2400


def test_pension_read_write_reference_isolation_and_user_cascade(client, db):
    from app.models.account import Account
    from app.models.pension import PensionBalanceSnapshot, PensionConfig
    from app.models.user import User

    alice_account = _setup(client, "alice-pension@example.com")
    alice_config = client.post("/api/v1/pension/configs", json=_config(alice_account["id"])).json()
    snap_body = {"account_id": alice_account["id"], "as_of_month": "2026-03-01",
                 "balance": 100, "source": "manual"}
    assert client.put(f"/api/v1/pension/accounts/{alice_account['id']}/snapshots/2026-03-01", json=snap_body).status_code == 200

    assert client.post("/api/v1/auth/logout").status_code == 200
    bob_account = _setup(client, "bob-pension@example.com")
    assert client.get("/api/v1/pension/configs").json() == []
    assert client.get(f"/api/v1/pension/accounts/{alice_account['id']}/snapshots").status_code == 422
    assert client.post("/api/v1/pension/configs", json=_config(alice_account["id"])).status_code == 422
    bad_snapshot = {**snap_body, "account_id": bob_account["id"]}
    assert client.put(f"/api/v1/pension/accounts/{bob_account['id']}/snapshots/2026-03-01", json=bad_snapshot).status_code == 200

    alice = db.query(User).filter_by(email="alice-pension@example.com").one()
    db.delete(alice)
    db.commit()
    assert db.query(PensionConfig).filter_by(id=alice_config["id"]).count() == 0
    assert db.query(PensionBalanceSnapshot).filter_by(user_id=alice.id).count() == 0
    assert db.query(Account).filter_by(user_id=alice.id).count() == 0


def test_account_creation_accepts_pension_only_with_canonical_opening_date(client):
    _setup(client)
    bad = client.post("/api/v1/accounts", json={"type": "pension", "name": "Bad", "opening_balance": 1})
    assert bad.status_code == 422
    good = client.post("/api/v1/accounts", json={
        "type": "pension", "name": "New fund", "opening_balance": 0,
        "opening_balance_month": "2026-05-01",
    })
    assert good.status_code == 200
    assert good.json()["opening_balance_month"] == "2026-05-01"
    assert client.post("/api/v1/accounts", json={
        "type": "saving", "name": "Bad saving", "opening_balance": 0,
        "opening_balance_month": "2026-01-01",
    }).status_code == 422
