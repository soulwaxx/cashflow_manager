import pytest

from tests.test_onboarding import WIZARD_PAYLOAD

def _setup(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)

def test_create_transfer(client):
    _setup(client)
    r = client.post("/api/v1/transfers", json={
        "date": "2026-03-15", "detail": "Monthly savings",
        "amount": 500, "from_account_type": "bank",
        "from_account_name": "MyBank", "to_account_type": "saving",
        "to_account_name": "MySavings",
    })
    assert r.status_code == 200
    assert r.json()["billing_month"] == "2026-03-01"

def test_transfer_billing_month_is_always_current_month(client):
    # Transfers always use current month regardless of account type
    _setup(client)
    r = client.post("/api/v1/transfers", json={
        "date": "2026-12-20", "amount": 100,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    })
    assert r.json()["billing_month"] == "2026-12-01"

def test_create_recurring_transfer(client):
    _setup(client)
    client.post("/api/v1/transfers", json={
        "date": "2026-01-01", "amount": 200,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
        "recurrence_months": 3,
    })
    transfers = client.get("/api/v1/transfers", params={"limit": 1000}).json()
    assert len([t for t in transfers if t["from_account_name"] == "MyBank"]) == 3

def test_delete_single_transfer(client):
    _setup(client)
    tx_id = client.post("/api/v1/transfers", json={
        "date": "2026-03-01", "amount": 100,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    }).json()["id"]
    assert client.delete(f"/api/v1/transfers/{tx_id}", params={"cascade": "single"}).status_code == 200
    assert client.get(f"/api/v1/transfers/{tx_id}").status_code == 404


def test_delete_single_recurring_root_promotes_next_row(client):
    _setup(client)
    root_id = client.post("/api/v1/transfers", json={
        "date": "2026-01-01", "amount": 200,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
        "recurrence_months": 3,
    }).json()["id"]

    r = client.delete(f"/api/v1/transfers/{root_id}", params={"cascade": "single"})
    assert r.status_code == 200
    assert client.get(f"/api/v1/transfers/{root_id}").status_code == 404

    remaining = sorted(client.get("/api/v1/transfers", params={"limit": 1000}).json(), key=lambda t: t["date"])
    assert len(remaining) == 2
    promoted_root = remaining[0]
    assert promoted_root["parent_transfer_id"] is None
    for row in remaining[1:]:
        assert row["parent_transfer_id"] == promoted_root["id"]


def test_list_transfers_filter_by_billing_month(client):
    _setup(client)
    client.post("/api/v1/transfers", json={
        "date": "2026-03-01", "amount": 100,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    })
    client.post("/api/v1/transfers", json={
        "date": "2026-05-01", "amount": 200,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    })
    r = client.get("/api/v1/transfers", params={"billing_month": "2026-03"})
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 1
    assert results[0]["billing_month"].startswith("2026-03")


def test_list_transfers_filter_by_from_account(client):
    _setup(client)
    client.post("/api/v1/transfers", json={
        "date": "2026-03-01", "amount": 100,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    })
    r = client.get("/api/v1/transfers", params={"from_account": "MyBank"})
    assert r.status_code == 200
    assert all(t["from_account_name"] == "MyBank" for t in r.json())


def test_list_transfers_filter_by_to_account(client):
    _setup(client)
    client.post("/api/v1/transfers", json={
        "date": "2026-03-01", "amount": 100,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    })
    r = client.get("/api/v1/transfers", params={"to_account": "MySavings"})
    assert r.status_code == 200
    assert all(t["to_account_name"] == "MySavings" for t in r.json())


def test_get_transfer_not_found(client):
    _setup(client)
    r = client.get("/api/v1/transfers/nonexistent-id")
    assert r.status_code == 404


def test_update_transfer_cascade_single(client):
    _setup(client)
    first_id = client.post("/api/v1/transfers", json={
        "date": "2026-01-01", "amount": 200, "detail": "Original",
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
        "recurrence_months": 3,
    }).json()["id"]
    all_transfers = client.get("/api/v1/transfers", params={"limit": 1000}).json()
    second = next(t for t in all_transfers if t["id"] != first_id and t["parent_transfer_id"] == first_id and t["date"].startswith("2026-02"))
    # Update only the second occurrence
    r = client.put(f"/api/v1/transfers/{second['id']}", json={"amount": 999.0}, params={"cascade": "single"})
    assert r.status_code == 200
    updated = client.get(f"/api/v1/transfers/{second['id']}").json()
    assert updated["amount"] == 999.0
    # First occurrence should be unchanged
    first = client.get(f"/api/v1/transfers/{first_id}").json()
    assert first["amount"] == 200.0


def test_update_transfer_can_clear_notes(client):
    _setup(client)
    transfer_id = client.post("/api/v1/transfers", json={
        "date": "2026-01-01",
        "amount": 200,
        "detail": "With note",
        "from_account_type": "bank",
        "from_account_name": "MyBank",
        "to_account_type": "saving",
        "to_account_name": "MySavings",
        "notes": "remove me",
    }).json()["id"]

    r = client.put(f"/api/v1/transfers/{transfer_id}", json={"notes": None})
    assert r.status_code == 200
    assert r.json()["notes"] is None
    assert client.get(f"/api/v1/transfers/{transfer_id}").json()["notes"] is None


def test_update_transfer_cascade_all(client):
    _setup(client)
    first_id = client.post("/api/v1/transfers", json={
        "date": "2026-01-01", "amount": 200, "detail": "Recurrent",
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
        "recurrence_months": 3,
    }).json()["id"]
    second_id = next(
        t["id"] for t in client.get("/api/v1/transfers", params={"limit": 1000}).json()
        if t["id"] != first_id and t["parent_transfer_id"] == first_id
    )
    r = client.put(f"/api/v1/transfers/{second_id}", json={"amount": 777.0}, params={"cascade": "all"})
    assert r.status_code == 200
    all_amounts = [t["amount"] for t in client.get("/api/v1/transfers", params={"limit": 1000}).json()]
    assert all(a == 777.0 for a in all_amounts)


def test_update_transfer_cascade_future(client):
    _setup(client)
    first_id = client.post("/api/v1/transfers", json={
        "date": "2026-01-01", "amount": 200, "detail": "Recurrent",
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
        "recurrence_months": 3,
    }).json()["id"]
    all_transfers = client.get("/api/v1/transfers", params={"limit": 1000}).json()
    second = next(t for t in all_transfers if t["id"] != first_id and t["parent_transfer_id"] == first_id and t["date"].startswith("2026-02"))
    r = client.put(f"/api/v1/transfers/{second['id']}", json={"amount": 555.0}, params={"cascade": "future"})
    assert r.status_code == 200
    # First occurrence (before the updated one) should remain unchanged
    first = client.get(f"/api/v1/transfers/{first_id}").json()
    assert first["amount"] == 200.0
    # The updated and later occurrences should be 555
    updated = client.get(f"/api/v1/transfers/{second['id']}").json()
    assert updated["amount"] == 555.0


def test_delete_transfer_cascade_all(client):
    _setup(client)
    first_id = client.post("/api/v1/transfers", json={
        "date": "2026-01-01", "amount": 200,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
        "recurrence_months": 3,
    }).json()["id"]
    r = client.delete(f"/api/v1/transfers/{first_id}", params={"cascade": "all"})
    assert r.status_code == 200
    remaining = client.get("/api/v1/transfers", params={"limit": 1000}).json()
    assert len(remaining) == 0


def test_update_transfer_date_does_not_cascade_to_siblings(client):
    """CRIT-1 + CRIT-2: updating a date on one recurring row must not change sibling dates,
    and billing_month must be recomputed correctly for every row from its own date."""
    _setup(client)
    # Create a 3-month recurring transfer starting 2026-01-10
    first_id = client.post("/api/v1/transfers", json={
        "date": "2026-01-10", "amount": 300, "detail": "Recurring",
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
        "recurrence_months": 3,
    }).json()["id"]
    all_transfers = client.get("/api/v1/transfers", params={"limit": 1000}).json()

    # Identify the three rows by their month
    def row_for_month(prefix):
        return next(t for t in all_transfers if t["date"].startswith(prefix))

    jan = row_for_month("2026-01")
    feb = row_for_month("2026-02")
    mar = row_for_month("2026-03")

    # Update only the January row's date (cascade=single)
    r = client.put(f"/api/v1/transfers/{jan['id']}", json={"date": "2026-01-20"}, params={"cascade": "single"})
    assert r.status_code == 200

    # Re-fetch all three rows
    jan_updated = client.get(f"/api/v1/transfers/{jan['id']}").json()
    feb_updated = client.get(f"/api/v1/transfers/{feb['id']}").json()
    mar_updated = client.get(f"/api/v1/transfers/{mar['id']}").json()

    # CRIT-1: siblings must keep their own original dates
    assert jan_updated["date"] == "2026-01-20", "target row date should be updated"
    assert feb_updated["date"] == "2026-02-10", "sibling date must not change"
    assert mar_updated["date"] == "2026-03-10", "sibling date must not change"

    # CRIT-2: billing_month must reflect each row's own date
    assert jan_updated["billing_month"] == "2026-01-01"
    assert feb_updated["billing_month"] == "2026-02-01"
    assert mar_updated["billing_month"] == "2026-03-01"


def test_cascade_all_recomputes_billing_month_per_row(client):
    """CRIT-2 (cascade=all): all rows get billing_month recomputed from their own date."""
    _setup(client)
    first_id = client.post("/api/v1/transfers", json={
        "date": "2026-04-05", "amount": 100, "detail": "Multi",
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
        "recurrence_months": 3,
    }).json()["id"]
    all_transfers = client.get("/api/v1/transfers", params={"limit": 1000}).json()
    any_id = all_transfers[0]["id"]

    # Update amount on all rows — this must not corrupt billing_month
    r = client.put(f"/api/v1/transfers/{any_id}", json={"amount": 150.0}, params={"cascade": "all"})
    assert r.status_code == 200

    refreshed = client.get("/api/v1/transfers", params={"limit": 1000}).json()
    for t in refreshed:
        expected_bm = t["date"][:7] + "-01"
        assert t["billing_month"] == expected_bm, (
            f"billing_month {t['billing_month']!r} does not match date {t['date']!r}"
        )


def test_delete_transfer_cascade_future(client):
    _setup(client)
    first_id = client.post("/api/v1/transfers", json={
        "date": "2026-01-01", "amount": 200,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
        "recurrence_months": 3,
    }).json()["id"]
    all_transfers = client.get("/api/v1/transfers", params={"limit": 1000}).json()
    second = next(t for t in all_transfers if t["id"] != first_id and t["parent_transfer_id"] == first_id and t["date"].startswith("2026-02"))
    r = client.delete(f"/api/v1/transfers/{second['id']}", params={"cascade": "future"})
    assert r.status_code == 200
    # Only the first occurrence should remain
    remaining = client.get("/api/v1/transfers", params={"limit": 1000}).json()
    assert len(remaining) == 1
    assert remaining[0]["id"] == first_id


def test_transfers_list_returns_all_without_explicit_limit(client):
    """Default list must return all transfers when no limit is specified."""
    client.post("/api/v1/auth/register", json={"email": "u@x.com", "password": "Password1!", "name": "U"})
    client.post("/api/v1/auth/login", json={"email": "u@x.com", "password": "Password1!"})
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)

    # Create 55 transfers between owned accounts.
    for i in range(55):
        r = client.post("/api/v1/transfers", json={
            "date": "2026-03-01",
            "detail": f"Transfer {i}",
            "amount": 10,
            "from_account_type": "bank",
            "from_account_name": "MyBank",
            "to_account_type": "saving",
            "to_account_name": "MySavings",
        })
        assert r.status_code == 200

    # Without explicit limit, must return all 55
    r = client.get("/api/v1/transfers", params={"billing_month": "2026-03"})
    assert r.status_code == 200
    assert len(r.json()) == 55, f"Expected 55 transfers, got {len(r.json())}"


@pytest.mark.parametrize("cascade_val", ["FUTURE", "futur", "ALL", "SINGLE", "bogus"])
def test_update_transfer_invalid_cascade_returns_422(client, cascade_val):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    t = client.post("/api/v1/transfers", json={
        "date": "2026-01-10", "detail": "Test", "amount": 100,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    }).json()
    r = client.put(f"/api/v1/transfers/{t['id']}?cascade={cascade_val}", json={"detail": "x"})
    assert r.status_code == 422


@pytest.mark.parametrize("cascade_val", ["FUTURE", "futur", "ALL", "SINGLE", "bogus"])
def test_delete_transfer_invalid_cascade_returns_422(client, cascade_val):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    client.post("/api/v1/onboarding", json=WIZARD_PAYLOAD)
    t = client.post("/api/v1/transfers", json={
        "date": "2026-01-10", "detail": "Test", "amount": 100,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    }).json()
    r = client.delete(f"/api/v1/transfers/{t['id']}?cascade={cascade_val}")
    assert r.status_code == 422


def test_create_transfer_invalid_account_type_returns_422(client):
    _setup(client)
    r = client.post("/api/v1/transfers", json={
        "date": "2026-01-10", "detail": "T", "amount": 50,
        "from_account_type": "wallet",   # invalid
        "from_account_name": "MyBank",
        "to_account_type": "saving",
        "to_account_name": "MySavings",
    })
    assert r.status_code == 422


def test_create_transfer_invalid_date_returns_422(client):
    """An unparseable date string must return 422, not 500."""
    _setup(client)
    r = client.post("/api/v1/transfers", json={
        "date": "not-a-date", "detail": "T", "amount": 50,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    })
    assert r.status_code == 422


def test_create_transfer_rejects_identical_endpoints(client):
    _setup(client)

    response = client.post("/api/v1/transfers", json={
        "date": "2026-01-10", "amount": 50,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "bank", "to_account_name": "MyBank",
    })

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("account_type", "account_name"),
    [
        ("bank", "MissingBank"),
        ("saving", "MissingSavings"),
        ("investment", "MissingBroker"),
        ("pension", "MissingPension"),
    ],
)
def test_create_transfer_rejects_phantom_account(client, account_type, account_name):
    _setup(client)

    response = client.post("/api/v1/transfers", json={
        "date": "2026-01-10", "amount": 50,
        "from_account_type": account_type, "from_account_name": account_name,
        "to_account_type": "saving", "to_account_name": "MySavings",
    })

    assert response.status_code == 422


def test_create_transfer_rejects_inactive_bank_account(client):
    _setup(client)
    bank = client.post("/api/v1/payment-methods", json={
        "name": "ClosedBank", "type": "bank",
    }).json()
    assert client.put(f"/api/v1/payment-methods/{bank['id']}", json={"is_active": False}).status_code == 200

    response = client.post("/api/v1/transfers", json={
        "date": "2026-01-10", "amount": 50,
        "from_account_type": "bank", "from_account_name": "ClosedBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    })

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["from_account_name", "to_account_name"])
def test_create_transfer_rejects_blank_account_name(client, field):
    _setup(client)
    payload = {
        "date": "2026-01-10", "amount": 50,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    }
    payload[field] = "   "

    response = client.post("/api/v1/transfers", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize("amount", [0, -1, "NaN", "Infinity", "1.001", "10000000000"])
def test_create_transfer_rejects_invalid_amount(client, amount):
    _setup(client)

    response = client.post("/api/v1/transfers", json={
        "date": "2026-01-10", "amount": amount,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": "saving", "to_account_name": "MySavings",
    })

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("account_type", "account_name"),
    [
        ("saving", "MySavings"),
        ("investment", "MyBroker"),
        ("pension", "Pension"),
    ],
)
def test_create_transfer_accepts_owned_account_types(client, account_type, account_name):
    _setup(client)

    response = client.post("/api/v1/transfers", json={
        "date": "2026-01-10", "amount": 50,
        "from_account_type": "bank", "from_account_name": "MyBank",
        "to_account_type": account_type, "to_account_name": account_name,
    })

    assert response.status_code == 200
