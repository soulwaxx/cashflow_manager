from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Account, PensionBalanceSnapshot, PensionConfig, User


def _user(db, user_id):
    user = User(id=user_id, email=f"{user_id}@example.com", name=user_id)
    db.add(user)
    db.flush()
    return user


def _account(db, user_id, account_id):
    account = Account(
        id=account_id,
        user_id=user_id,
        type="pension",
        name=f"Fund {account_id}",
        opening_balance=Decimal("0.00"),
    )
    db.add(account)
    db.flush()
    return account


def _config(user_id, account_id, valid_from="2026-01-01"):
    return PensionConfig(
        user_id=user_id,
        account_id=account_id,
        valid_from=valid_from,
        employee_contrib_rate=Decimal("0.0100"),
        employee_contrib_annual_base=Decimal("30000.00"),
        employer_contrib_rate=Decimal("0.0200"),
        employer_contrib_annual_base=Decimal("20000.00"),
        tfr_contrib_annual=Decimal("0.00"),
        contribution_periods_by_month=[1] * 12,
    )


def test_account_opening_month_is_nullable_and_new_pension_rows_persist(db):
    _user(db, "user-1")
    account = _account(db, "user-1", "account-1")
    config = _config("user-1", account.id)
    snapshot = PensionBalanceSnapshot(
        user_id="user-1", account_id=account.id, as_of_month="2026-03-01",
        balance=Decimal("250.00"), source="manual",
    )
    db.add_all([config, snapshot])
    db.commit()

    assert account.opening_balance_month is None
    assert db.get(PensionConfig, config.id).contribution_periods_by_month == [1] * 12
    assert db.get(PensionBalanceSnapshot, snapshot.id).balance == Decimal("250.00")


def test_pension_config_and_snapshot_references_must_be_owned(db):
    _user(db, "owner")
    _user(db, "other")
    _account(db, "other", "other-account")
    db.add(_config("owner", "other-account"))

    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_pension_effective_period_is_unique(db):
    _user(db, "user-1")
    _account(db, "user-1", "account-1")
    db.commit()
    db.add_all([_config("user-1", "account-1"), _config("user-1", "account-1")])
    with pytest.raises(IntegrityError) as error:
        db.flush()
    assert "UNIQUE constraint failed: pension_configs.user_id, pension_configs.valid_from" in str(error.value)


def test_pension_snapshot_month_is_unique_with_persisted_parents(db):
    _user(db, "user-1")
    _account(db, "user-1", "account-1")
    db.commit()
    first = PensionBalanceSnapshot(
        user_id="user-1", account_id="account-1", as_of_month="2026-03-01",
        balance=Decimal("1.00"), source="statement",
    )
    db.add(first)
    db.commit()

    db.add(PensionBalanceSnapshot(
        user_id="user-1", account_id="account-1", as_of_month="2026-03-01",
        balance=Decimal("2.00"), source="manual",
    ))
    with pytest.raises(IntegrityError) as error:
        db.flush()
    assert "UNIQUE constraint failed: pension_balance_snapshots.user_id, pension_balance_snapshots.account_id, pension_balance_snapshots.as_of_month" in str(error.value)


def test_user_deletion_cascades_to_pension_rows_and_account(db):
    user = _user(db, "user-1")
    account = _account(db, user.id, "account-1")
    config = _config(user.id, account.id)
    snapshot = PensionBalanceSnapshot(
        user_id=user.id, account_id=account.id, as_of_month="2026-03-01",
        balance=Decimal("100.00"), source="statement",
    )
    db.add_all([config, snapshot])
    db.commit()

    db.delete(user)
    db.commit()

    assert db.query(PensionConfig).count() == 0
    assert db.query(PensionBalanceSnapshot).count() == 0
    assert db.query(Account).count() == 0
