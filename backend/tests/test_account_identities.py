from tests.test_onboarding import WIZARD_PAYLOAD


def _setup(client, email="alice@example.com"):
    client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password1!", "name": "Alice",
    })
    assert client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD).status_code == 200


def _account_id(client, account_type, name):
    accounts = client.get("/api/v1/accounts").json()
    return next(account["id"] for account in accounts if account["type"] == account_type and account["name"] == name)


def _bank_id(client, name="MyBank"):
    return next(method["id"] for method in client.get("/api/v1/payment-methods").json() if method["name"] == name)


def test_transfers_persist_owned_stable_account_ids(client):
    _setup(client)
    saving_id = _account_id(client, "saving", "MySavings")
    bank_id = _bank_id(client)

    response = client.post("/api/v1/transfers", json={
        "date": "2026-03-01", "amount": 100,
        "from_account_type": "bank", "from_account_id": bank_id,
        "to_account_type": "saving", "to_account_id": saving_id,
    })

    assert response.status_code == 200
    transfer = response.json()
    assert transfer["from_payment_method_id"] == bank_id
    assert transfer["to_account_id"] == saving_id
    assert transfer["from_account_name"] == "MyBank"
    assert transfer["to_account_name"] == "MySavings"


def test_account_rename_preserves_transfer_asset_history(client, db):
    _setup(client)
    saving_id = _account_id(client, "saving", "MySavings")
    bank_id = _bank_id(client)
    assert client.post("/api/v1/transfers", json={
        "date": "2026-03-01", "amount": 500,
        "from_account_type": "bank", "from_account_id": bank_id,
        "to_account_type": "saving", "to_account_id": saving_id,
    }).status_code == 200

    from app.models.account import Account
    account = db.query(Account).filter_by(id=saving_id).one()
    account.name = "Renamed savings"
    db.commit()

    assets = client.get("/api/v1/assets/2026?as_of=2026-12-01").json()
    renamed = next(asset for asset in assets if asset["account_id"] == saving_id)
    assert renamed["asset_name"] == "Renamed savings"
    assert renamed["computed_amount"] == 3500.0


def test_transfer_rejects_cross_user_or_stale_nonbank_account_ids(client):
    _setup(client)
    alice_saving_id = _account_id(client, "saving", "MySavings")
    assert client.post("/api/v1/auth/logout").status_code == 200
    _setup(client, "bob@example.com")
    bob_bank_id = _bank_id(client)

    cross_user = client.post("/api/v1/transfers", json={
        "date": "2026-03-01", "amount": 100,
        "from_account_type": "bank", "from_account_id": bob_bank_id,
        "to_account_type": "saving", "to_account_id": alice_saving_id,
    })
    assert cross_user.status_code == 422

    stale = client.post("/api/v1/transfers", json={
        "date": "2026-03-01", "amount": 100,
        "from_account_type": "bank", "from_account_id": bob_bank_id,
        "to_account_type": "saving", "to_account_id": "missing-account-id",
    })
    assert stale.status_code == 422


def test_legacy_name_input_is_bounded_to_existing_owned_account(client):
    _setup(client)
    response = client.post("/api/v1/transfers", json={
        "date": "2026-03-01", "amount": 100,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    })
    assert response.status_code == 200
    assert response.json()["to_account_id"] == _account_id(client, "saving", "MySavings")

    phantom = client.post("/api/v1/transfers", json={
        "date": "2026-03-01", "amount": 100,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "Stale savings",
    })
    assert phantom.status_code == 422
