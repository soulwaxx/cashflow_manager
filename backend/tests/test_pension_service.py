from decimal import Decimal

import pytest
from sqlalchemy import event

from app.models.account import Account
from app.models.pension import PensionBalanceSnapshot, PensionConfig
from app.models.salary import SalaryConfig
from app.models.tax import TaxConfig
from app.models.transfer import Transfer
from app.models.user import User
from app.services.pension import (
    annualized_components,
    monthly_credit,
    pension_balances,
    payroll_effects,
    preview_payroll_effects,
    PensionPayrollInputs,
    resolve_pension_config,
)

D = Decimal
MONTHLY = [1] * 12
QUARTERLY = [0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1]


def _user(db, email=None):
    user = User(email=email, name="Synthetic")
    db.add(user)
    db.flush()
    return user


def _account(db, user_id, account_id, *, name=None, active=True, opening="0", opening_month="2025-01-01", kind="pension"):
    account = Account(
        id=account_id,
        user_id=user_id,
        type=kind,
        name=name or account_id,
        is_active=active,
        opening_balance=D(opening) if opening is not None else D("0"),
        opening_balance_month=opening_month,
    )
    db.add(account)
    db.flush()
    return account


def _config(
    db, user_id, account_id, *, valid_from="2025-01-01", employee_rate="0.0100",
    employee_base="30000", employer_rate="0.0300", employer_base="20000",
    tfr="2400", weights=None, config_id=None,
):
    config = PensionConfig(
        id=config_id,
        user_id=user_id,
        account_id=account_id,
        valid_from=valid_from,
        employee_contrib_rate=D(employee_rate),
        employee_contrib_annual_base=D(employee_base),
        employer_contrib_rate=D(employer_rate),
        employer_contrib_annual_base=D(employer_base),
        tfr_contrib_annual=D(tfr),
        contribution_periods_by_month=weights or MONTHLY.copy(),
    )
    db.add(config)
    db.flush()
    return config


def _tax(db, user_id, *, valid_from="2025-01-01", cap="5164.57", config_id=None):
    tax = TaxConfig(
        id=config_id,
        user_id=user_id,
        valid_from=valid_from,
        pension_deductibility_cap=D(cap),
    )
    db.add(tax)
    db.flush()
    return tax


def test_effective_configs_are_owner_scoped_and_missing_means_zero(db):
    from app.services.pension import PensionComponents

    alice, bob = _user(db, "alice@example.com"), _user(db, "bob@example.com")
    alice_old = _account(db, alice.id, "alice-old")
    alice_new = _account(db, alice.id, "alice-new")
    bob_account = _account(db, bob.id, "bob-account")
    _config(db, alice.id, alice_old.id, valid_from="2025-01-01", config_id="alice-jan")
    _config(db, alice.id, alice_new.id, valid_from="2025-07-01", config_id="alice-jul")
    _config(db, bob.id, bob_account.id, valid_from="2025-01-01", employee_base="999999")
    db.commit()

    assert resolve_pension_config(db, alice.id, "2025-06-01").id == "alice-jan"
    assert resolve_pension_config(db, alice.id, "2025-07-01").id == "alice-jul"
    assert resolve_pension_config(db, alice.id, "2024-12-01") is None
    assert annualized_components(None) == PensionComponents(D("0"), D("0"), D("0"))
    assert annualized_components(resolve_pension_config(db, alice.id, "2025-07-01")) == PensionComponents(
        D("300.00"), D("600.00"), D("2400.00")
    )


def test_independent_bases_midyear_destination_and_monthly_credit(db):
    user = _user(db)
    first = _account(db, user.id, "fund-first", opening="10000")
    second = _account(db, user.id, "fund-second", name="Renamed Fund", opening="0")
    _config(db, user.id, first.id, valid_from="2025-01-01")
    _config(
        db, user.id, second.id, valid_from="2025-07-01", employee_rate="0.0200",
        employee_base="25000", employer_rate="0.0100", employer_base="15000",
        tfr="1200", weights=MONTHLY, config_id="switch",
    )
    db.commit()

    credit_june = monthly_credit(resolve_pension_config(db, user.id, "2025-06-01"), "2025-06-01")
    credit_july = monthly_credit(resolve_pension_config(db, user.id, "2025-07-01"), "2025-07-01")
    assert (credit_june.employee, credit_june.employer, credit_june.tfr) == (D(25), D(50), D(200))
    assert (credit_july.employee, credit_july.employer, credit_july.tfr) == (D(500) / 12, D(150) / 12, D(100))
    assert credit_june.employee != D("60000") * D("0.01") / 12

    balances = {row.account_id: row for row in pension_balances(db, user.id, "2025-12-01")}
    assert balances[first.id].balance == D("11650.00")
    assert balances[second.id].balance == D("925.00")
    assert balances[first.id].employee_contributions == D("150.00")
    assert balances[second.id].employee_contributions == D("250.00")
    assert balances[second.id].account_name == "Renamed Fund"


def test_golden_crossyear_snapshot_inclusive_cutoff_and_projection(db):
    user = _user(db)
    account = _account(db, user.id, "golden", opening="10000", opening_month="2025-01-01")
    _config(db, user.id, account.id, valid_from="2025-01-01")
    db.add(PensionBalanceSnapshot(
        id="march-statement", user_id=user.id, account_id=account.id,
        as_of_month="2026-03-01", balance=D("20000.00"), source="statement",
    ))
    db.commit()

    dec_2025 = pension_balances(db, user.id, "2025-12-01")[0]
    jan_2026 = pension_balances(db, user.id, "2026-01-01")[0]
    march = pension_balances(db, user.id, "2026-03-01")[0]
    april = pension_balances(db, user.id, "2026-04-01")[0]
    before_open = pension_balances(db, user.id, "2024-12-01")

    assert dec_2025.balance == D("13300.00")
    assert jan_2026.balance == D("13575.00")
    assert march.balance == D("20000.00")  # March flows are already in statement.
    assert march.employee_contributions == D("0.00")
    assert april.balance == D("20275.00")
    assert april.valuation_status == "statement_reconciled"
    assert april.reconciled_as_of_month == "2026-03-01"
    assert april.reconciled_balance == D("20000.00")
    assert april.reconciliation_source == "statement"
    assert april.projected_through == "2026-04-01"
    assert before_open == []


def test_month_cutoff_includes_whole_opening_and_projection_month_but_not_next_month(db):
    user = _user(db)
    account = _account(db, user.id, "month-cutoff", opening="0", opening_month="2025-02-01")
    _config(db, user.id, account.id, valid_from="2025-02-01", employee_rate="0", employer_rate="0", tfr="0")
    transfers = [
        ("open-day1", "2025-02-01", "to", "10"),
        ("open-day2", "2025-02-02", "to", "20"),
        ("open-last", "2025-02-28", "to", "30"),
        ("open-out-last", "2025-02-28", "from", "5"),
        ("march-day1", "2025-03-01", "to", "7"),
        ("march-day2", "2025-03-02", "to", "11"),
        ("march-last", "2025-03-31", "to", "13"),
        ("april-day1", "2025-04-01", "to", "17"),
    ]
    for transfer_id, transfer_date, direction, amount in transfers:
        db.add(Transfer(
            id=transfer_id, user_id=user.id, date=transfer_date,
            billing_month=transfer_date[:7] + "-01", detail=transfer_id, amount=D(amount),
            from_account_type="pension" if direction == "from" else "bank",
            from_account_name="fund" if direction == "from" else "bank",
            from_account_id=account.id if direction == "from" else None,
            to_account_type="pension" if direction == "to" else "bank",
            to_account_name="fund" if direction == "to" else "bank",
            to_account_id=account.id if direction == "to" else None,
        ))
    db.commit()

    february = pension_balances(db, user.id, "2025-02-01")[0]
    march = pension_balances(db, user.id, "2025-03-01")[0]
    april = pension_balances(db, user.id, "2025-04-01")[0]
    assert (february.balance, february.net_transfers) == (D("55.00"), D("55.00"))
    assert (march.balance, march.net_transfers) == (D("86.00"), D("86.00"))
    assert (april.balance, april.net_transfers) == (D("103.00"), D("103.00"))


def test_snapshot_month_transfers_are_included_once_and_later_month_is_complete(db):
    user = _user(db)
    account = _account(db, user.id, "month-snapshot", opening="0", opening_month="2025-01-01")
    _config(db, user.id, account.id, valid_from="2025-01-01", employee_rate="0", employer_rate="0", tfr="0")
    db.add(PensionBalanceSnapshot(
        id="feb-month-end", user_id=user.id, account_id=account.id,
        as_of_month="2025-02-01", balance=D("200"), source="statement",
    ))
    for transfer_id, transfer_date, direction, amount in [
        ("snap-feb-day1", "2025-02-01", "to", "100"),
        ("snap-feb-day2", "2025-02-02", "to", "100"),
        ("snap-feb-last", "2025-02-28", "from", "10"),
        ("snap-mar-day1", "2025-03-01", "to", "3"),
        ("snap-mar-day2", "2025-03-02", "to", "5"),
        ("snap-mar-last", "2025-03-31", "to", "7"),
        ("snap-apr-day1", "2025-04-01", "to", "9"),
    ]:
        db.add(Transfer(
            id=transfer_id, user_id=user.id, date=transfer_date,
            billing_month=transfer_date[:7] + "-01", detail=transfer_id, amount=D(amount),
            from_account_type="pension" if direction == "from" else "bank",
            from_account_name="fund" if direction == "from" else "bank",
            from_account_id=account.id if direction == "from" else None,
            to_account_type="pension" if direction == "to" else "bank",
            to_account_name="fund" if direction == "to" else "bank",
            to_account_id=account.id if direction == "to" else None,
        ))
    db.commit()

    february = pension_balances(db, user.id, "2025-02-01")[0]
    march = pension_balances(db, user.id, "2025-03-01")[0]
    april = pension_balances(db, user.id, "2025-04-01")[0]
    assert february.balance == D("200.00")
    assert february.net_transfers == D("0.00")
    assert march.balance == D("215.00")
    assert march.net_transfers == D("15.00")
    assert april.balance == D("224.00")
    assert april.net_transfers == D("24.00")


def test_snapshot_precedence_manual_legacy_deletion_fallback_and_opening_provenance(db):
    user = _user(db)
    account = _account(db, user.id, "snapshots", opening="500", opening_month="2025-01-01")
    _config(db, user.id, account.id, valid_from="2025-01-01", employee_rate="0", employer_rate="0", tfr="0")
    older = PensionBalanceSnapshot(
        id="older", user_id=user.id, account_id=account.id, as_of_month="2025-06-01",
        balance=D("700"), source="manual",
    )
    newest = PensionBalanceSnapshot(
        id="newest", user_id=user.id, account_id=account.id, as_of_month="2025-09-01",
        balance=D("900"), source="legacy_override",
    )
    future = PensionBalanceSnapshot(
        id="future", user_id=user.id, account_id=account.id, as_of_month="2026-01-01",
        balance=D("1200"), source="statement",
    )
    db.add_all([older, newest, future])
    db.commit()

    assert pension_balances(db, user.id, "2025-08-01")[0].balance == D("700.00")
    result = pension_balances(db, user.id, "2025-12-01")[0]
    assert result.balance == D("900.00")
    assert result.valuation_status == "legacy_reconciled"
    assert result.reconciled_as_of_month == "2025-09-01"
    db.delete(newest)
    db.commit()
    result_after_delete = pension_balances(db, user.id, "2025-12-01")[0]
    assert result_after_delete.balance == D("700.00")
    assert result_after_delete.valuation_status == "manual_reconciled"
    assert pension_balances(db, user.id, "2026-01-01")[0].balance == D("1200.00")


def test_zero_contribution_opening_transfers_and_snapshot_still_return_active_accounts(db):
    user = _user(db)
    account = _account(db, user.id, "zero", opening="0", opening_month="2025-01-01")
    inactive = _account(db, user.id, "inactive", active=False, opening="100", opening_month="2025-01-01")
    _config(db, user.id, account.id, valid_from="2025-01-01", employee_rate="0", employer_rate="0", tfr="0")
    db.add(Transfer(
        id="owned-in", user_id=user.id, date="2025-02-10", billing_month="2025-02-01",
        detail="transfer in", amount=D("50.00"), from_account_type="bank", from_account_name="x",
        to_account_type="pension", to_account_name="old name", to_account_id=account.id,
    ))
    db.add(Transfer(
        id="owned-out", user_id=user.id, date="2025-03-01", billing_month="2025-03-01",
        detail="transfer out", amount=D("12.00"), from_account_type="pension", from_account_name="old name",
        from_account_id=account.id, to_account_type="bank", to_account_name="x",
    ))
    db.add(PensionBalanceSnapshot(
        id="manual-zero", user_id=user.id, account_id=account.id, as_of_month="2025-04-01",
        balance=D("40"), source="manual",
    ))
    db.commit()

    result = {row.account_id: row for row in pension_balances(db, user.id, "2025-04-01")}
    assert set(result) == {account.id}
    assert result[account.id].balance == D("40.00")
    assert result[account.id].net_transfers == D("0.00")  # The April snapshot resets prior flows.
    assert result[account.id].valuation_status == "manual_reconciled"


def test_owned_transfers_cutoff_and_cross_user_transfer_attack(db):
    alice, bob = _user(db, "transfer-alice@example.com"), _user(db, "transfer-bob@example.com")
    alice_fund = _account(db, alice.id, "alice-fund", name="Renamed Fund", opening="100", opening_month="2025-01-01")
    bob_fund = _account(db, bob.id, "bob-fund", opening="900", opening_month="2025-01-01")
    inactive_fund = _account(db, alice.id, "alice-inactive-fund", active=False)
    saving_account = _account(db, alice.id, "alice-saving", kind="saving")
    stale_fund = _account(db, alice.id, "alice-stale-fund")
    _config(db, alice.id, alice_fund.id, valid_from="2025-01-01", employee_rate="0.0100",
            employee_base="30000", employer_rate="0", employer_base="0", tfr="0")
    db.add_all([
        Transfer(
            id="alice-in", user_id=alice.id, date="2025-02-28", billing_month="2025-02-01",
            detail="in", amount=D("25"), from_account_type="bank", from_account_name="b",
            to_account_type="pension", to_account_name="renamed", to_account_id=alice_fund.id,
        ),
        Transfer(
            id="alice-future", user_id=alice.id, date="2025-04-01", billing_month="2025-04-01",
            detail="future", amount=D("99"), from_account_type="bank", from_account_name="b",
            to_account_type="pension", to_account_name="renamed", to_account_id=alice_fund.id,
        ),
        Transfer(
            id="alice-mismatched-in", user_id=alice.id, date="2025-02-05", billing_month="2025-02-01",
            detail="type mismatch incoming", amount=D("700"), from_account_type="bank", from_account_name="b",
            to_account_type="saving", to_account_name="renamed", to_account_id=alice_fund.id,
        ),
        Transfer(
            id="alice-mismatched-out", user_id=alice.id, date="2025-02-06", billing_month="2025-02-01",
            detail="type mismatch outgoing", amount=D("800"), from_account_type="saving",
            from_account_name="renamed", from_account_id=alice_fund.id,
            to_account_type="bank", to_account_name="b",
        ),
        Transfer(
            id="alice-null-endpoint", user_id=alice.id, date="2025-02-07", billing_month="2025-02-01",
            detail="missing endpoint", amount=D("900"), from_account_type="bank", from_account_name="b",
            to_account_type="pension", to_account_name="deleted", to_account_id=None,
        ),
        Transfer(
            id="alice-inactive-endpoint", user_id=alice.id, date="2025-02-08", billing_month="2025-02-01",
            detail="inactive fund", amount=D("1000"), from_account_type="bank", from_account_name="b",
            to_account_type="pension", to_account_name="inactive", to_account_id=inactive_fund.id,
        ),
        Transfer(
            id="alice-saving-id", user_id=alice.id, date="2025-02-09", billing_month="2025-02-01",
            detail="non-pension id", amount=D("1100"), from_account_type="bank", from_account_name="b",
            to_account_type="pension", to_account_name="saving", to_account_id=saving_account.id,
        ),
        Transfer(
            id="alice-stale-id", user_id=alice.id, date="2025-02-10", billing_month="2025-02-01",
            detail="deleted account", amount=D("1200"), from_account_type="bank", from_account_name="b",
            to_account_type="pension", to_account_name="stale", to_account_id=stale_fund.id,
        ),
        Transfer(
            id="bob-transfer", user_id=bob.id, date="2025-02-01", billing_month="2025-02-01",
            detail="foreign", amount=D("500"), from_account_type="bank", from_account_name="b",
            to_account_type="pension", to_account_name="x", to_account_id=alice_fund.id,
        ),
        Transfer(
            id="alice-foreign-account", user_id=alice.id, date="2025-02-15", billing_month="2025-02-01",
            detail="foreign account id", amount=D("700"), from_account_type="bank", from_account_name="b",
            to_account_type="pension", to_account_name="foreign", to_account_id=bob_fund.id,
        ),
    ])
    db.commit()
    db.delete(stale_fund)  # The account FK's SET NULL leaves only a stale/null endpoint.
    db.commit()
    assert db.get(Transfer, "alice-stale-id").to_account_id is None

    result = pension_balances(db, alice.id, "2025-03-01")[0]
    assert result.balance == D("200.00")  # 75 scheduled credits + 25 net owned transfer.
    assert result.net_transfers == D("25.00")
    assert result.employee_contributions == D("75.00")
    assert result.account_name == "Renamed Fund"


def test_combined_cap_historical_current_employer_excess_and_tfr_exclusion(db):
    user = _user(db)
    fund = _account(db, user.id, "cap-fund")
    _config(db, user.id, fund.id, valid_from="2025-01-01", employee_rate="0", employee_base="0",
            employer_rate="0", employer_base="0", tfr="9000")
    _tax(db, user.id, valid_from="2025-01-01", cap="5164.57", config_id="tax-2025")
    _tax(db, user.id, valid_from="2026-01-01", cap="5300", config_id="tax-2026")
    db.commit()

    def effects(year, employee, employer):
        config = PensionConfig(
            user_id=user.id, account_id=fund.id, valid_from=f"{year}-01-01",
            employee_contrib_rate=D(1 if D(employee) else 0),
            employee_contrib_annual_base=D(employee),
            employer_contrib_rate=D(1 if D(employer) else 0),
            employer_contrib_annual_base=D(employer),
            tfr_contrib_annual=D(9000), contribution_periods_by_month=MONTHLY.copy(),
        )
        return payroll_effects(db, user.id, f"{year}-01-01", config=config)

    below = effects(2025, "1000", "1000")
    at = effects(2025, "3000", "2164.57")
    above = effects(2026, "4000", "2000")
    employer_only = effects(2026, "0", "6000")

    assert below.deductibility_cap == D("5164.57")
    assert (below.cap_used, below.cap_excess, below.payroll_deduction, below.employer_taxable_excess) == (
        D("2000.00"), D("0.00"), D("1000.00"), D("0.00")
    )
    assert (at.cap_used, at.cap_excess, at.payroll_deduction) == (D("5164.57"), D("0.00"), D("3000.00"))
    assert above.deductibility_cap == D("5300.00")
    assert (above.cap_used, above.cap_excess, above.payroll_deduction, above.employer_taxable_excess) == (
        D("5300.00"), D("700.00"), D("3300.00"), D("0.00")
    )
    assert (employer_only.cap_used, employer_only.cap_excess, employer_only.payroll_deduction,
            employer_only.employer_taxable_excess) == (D("5300.00"), D("700.00"), D("0.00"), D("700.00"))
    assert employer_only.components.tfr_annual == D("9000.00")
    assert employer_only.cap_scope.startswith("configured ordinary payroll")


def test_owner_tax_override_is_used_and_missing_tax_is_explicit(db):
    alice, bob = _user(db, "tax-alice@example.com"), _user(db, "tax-bob@example.com")
    alice_fund = _account(db, alice.id, "tax-alice-fund")
    bob_fund = _account(db, bob.id, "tax-bob-fund")
    config = _config(db, alice.id, alice_fund.id)
    system_tax = _tax(db, None, valid_from="2025-01-01", cap="9999", config_id="system-tax")
    _tax(db, alice.id, valid_from="2025-01-01", cap="100", config_id="alice-tax")
    _tax(db, bob.id, valid_from="2025-01-01", cap="1", config_id="bob-tax")
    _config(db, bob.id, bob_fund.id, valid_from="2025-01-01")
    db.commit()

    result = payroll_effects(db, alice.id, "2025-01-01", config=config)
    assert result.tax_config_id == "alice-tax"
    assert result.deductibility_cap == D("100.00")
    assert result.tax_config_valid_from == "2025-01-01"
    no_pension = payroll_effects(db, alice.id, "2025-01-01", config=None)
    assert no_pension.components == type(result.components)(D("0.00"), D("0.00"), D("0.00"))
    preview_none = preview_payroll_effects(db, alice.id, "2025-01-01", None)
    assert preview_none.components == no_pension.components
    assert preview_none.deductibility_cap == D("100")
    with pytest.raises(ValueError, match="must belong"):
        payroll_effects(db, alice.id, "2025-01-01", config=resolve_pension_config(db, bob.id, "2025-01-01"))
    db.delete(system_tax)
    db.commit()
    with pytest.raises(ValueError, match="No applicable tax configuration"):
        payroll_effects(db, "no-tax-owner", "2025-01-01")


def test_unsaved_preview_reads_only_selected_tax_and_never_reads_or_writes_account_config(db):
    user = _user(db, "unsaved-preview@example.com")
    user_id = user.id
    _tax(db, user_id, valid_from="2025-01-01", cap="5300", config_id="preview-cap")
    db.commit()
    pension = PensionPayrollInputs(
        employee_contrib_rate=D("0.0001"), employee_contrib_annual_base=D("150"),
        employer_contrib_rate=D(0), employer_contrib_annual_base=D(0),
        tfr_contrib_annual=D("0.015"),
    )
    statements = []

    def record_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.strip().lower())

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", record_sql)
    try:
        result = preview_payroll_effects(db, user_id, "2025-01-01", pension)
    finally:
        event.remove(engine, "before_cursor_execute", record_sql)

    assert result.components.employee_annual == D("0.0150")
    assert result.components.tfr_annual == D("0.015")
    assert result.cap_used == D("0.0150")
    assert result.payroll_deduction == D("0.0150")
    assert result.tax_config_id == "preview-cap"
    assert statements and all("tax_config" in statement for statement in statements)
    assert not any("accounts" in statement or "pension_configs" in statement for statement in statements)
    assert not any(statement.startswith(("insert", "update", "delete")) for statement in statements)
    assert db.query(Account).filter(Account.user_id == user.id).count() == 0
    assert db.query(PensionConfig).filter(PensionConfig.user_id == user.id).count() == 0


def test_preview_resolves_selected_historical_tax_override_system_fallback_and_missing_tax(db):
    owner = _user(db, "preview-tax-owner@example.com")
    system_only = _user(db, "preview-system-only@example.com")
    no_tax = _user(db, "preview-no-tax@example.com")
    _tax(db, None, valid_from="2025-01-01", cap="5000", config_id="system-2025")
    _tax(db, None, valid_from="2026-01-01", cap="5300", config_id="system-2026")
    _tax(db, owner.id, valid_from="2025-01-01", cap="5164.57", config_id="owner-2025")
    _tax(db, owner.id, valid_from="2026-01-01", cap="6000", config_id="owner-2026")
    db.commit()
    pension = PensionPayrollInputs(
        employee_contrib_rate=D(1), employee_contrib_annual_base=D("4000"),
        employer_contrib_rate=D(1), employer_contrib_annual_base=D("2000"),
        tfr_contrib_annual=D("8000"),
    )

    historical = preview_payroll_effects(db, owner.id, "2025-12-01", pension)
    current = preview_payroll_effects(db, owner.id, "2026-01-01", pension)
    fallback = preview_payroll_effects(db, system_only.id, "2025-12-01", pension)
    assert (historical.deductibility_cap, historical.tax_config_id, historical.tax_config_valid_from) == (
        D("5164.57"), "owner-2025", "2025-01-01"
    )
    assert (current.deductibility_cap, current.tax_config_id) == (D("6000"), "owner-2026")
    assert (fallback.deductibility_cap, fallback.tax_config_id) == (D("5000"), "system-2025")
    db.query(TaxConfig).filter(TaxConfig.user_id.is_(None)).delete(synchronize_session=False)
    db.commit()
    with pytest.raises(ValueError, match="No applicable tax configuration for 2025-12-01"):
        preview_payroll_effects(db, no_tax.id, "2025-12-01", pension)


def test_saved_payroll_helper_keeps_destination_ownership_checks(db):
    owner, foreign = _user(db, "saved-owner@example.com"), _user(db, "saved-foreign@example.com")
    foreign_fund = _account(db, foreign.id, "foreign-fund")
    _tax(db, owner.id, valid_from="2025-01-01", cap="5300", config_id="saved-owner-tax")
    db.commit()

    forged_foreign_destination = PensionConfig(
        user_id=owner.id, account_id=foreign_fund.id, valid_from="2025-01-01",
        employee_contrib_rate=D(0), employee_contrib_annual_base=D(0),
        employer_contrib_rate=D(0), employer_contrib_annual_base=D(0),
        tfr_contrib_annual=D(0), contribution_periods_by_month=MONTHLY.copy(),
    )
    unknown_destination = PensionConfig(
        user_id=owner.id, account_id="no-such-owned-account", valid_from="2025-01-01",
        employee_contrib_rate=D(0), employee_contrib_annual_base=D(0),
        employer_contrib_rate=D(0), employer_contrib_annual_base=D(0),
        tfr_contrib_annual=D(0), contribution_periods_by_month=MONTHLY.copy(),
    )
    with pytest.raises(ValueError, match="destination must be an owned pension account"):
        payroll_effects(db, owner.id, "2025-01-01", config=forged_foreign_destination)
    with pytest.raises(ValueError, match="destination must be an owned pension account"):
        payroll_effects(db, owner.id, "2025-01-01", config=unknown_destination)
    with pytest.raises(ValueError, match="must belong to the requested user"):
        payroll_effects(db, owner.id, "2025-01-01", config=PensionConfig(
            user_id=foreign.id, account_id=foreign_fund.id, valid_from="2025-01-01",
            employee_contrib_rate=D(0), employee_contrib_annual_base=D(0),
            employer_contrib_rate=D(0), employer_contrib_annual_base=D(0),
            tfr_contrib_annual=D(0), contribution_periods_by_month=MONTHLY.copy(),
        ))


def test_payroll_effects_preserve_fractional_cents_until_downstream_net_rounding(db):
    user = _user(db)
    fund = _account(db, user.id, "fractional-payroll")
    _tax(db, user.id, valid_from="2026-01-01", cap="5300", config_id="fractional-cap")
    db.commit()

    def preview(employee, employer):
        return PensionConfig(
            user_id=user.id, account_id=fund.id, valid_from="2026-01-01",
            employee_contrib_rate=D("0.0001"), employee_contrib_annual_base=D(employee),
            employer_contrib_rate=D("0.0001") if D(employer) else D(0),
            employer_contrib_annual_base=D(employer), tfr_contrib_annual=D("0.015"),
            contribution_periods_by_month=MONTHLY.copy(),
        )

    employee_only = payroll_effects(db, user.id, "2026-01-01", config=preview("150", "0"))
    assert annualized_components(preview("150", "0")).employee_annual == D("0.0150")
    assert employee_only.components.employee_annual == D("0.0150")
    assert employee_only.components.tfr_annual == D("0.015")
    assert employee_only.cap_used == D("0.0150")
    assert employee_only.payroll_deduction == D("0.0150")

    ral = D("10000")
    employee_left = ral + employee_only.components.employer_annual - employee_only.cap_used
    employee_right = ral - employee_only.payroll_deduction + employee_only.employer_taxable_excess
    assert employee_left == employee_right == ral - D("0.015")
    taxable_base = ral - employee_only.payroll_deduction
    unrounded_net = ral - employee_only.components.employee_annual - taxable_base * D("0.23")
    assert unrounded_net.quantize(D("0.01")) == D("7699.99")

    both = payroll_effects(db, user.id, "2026-01-01", config=preview("150", "150"))
    assert both.components.employee_annual == D("0.0150")
    assert both.components.employer_annual == D("0.0150")
    assert both.cap_used == D("0.0300")
    assert both.payroll_deduction == D("0.0150")
    both_left = ral + both.components.employer_annual - both.cap_used
    both_right = ral - both.payroll_deduction + both.employer_taxable_excess
    assert both_left == both_right == ral - D("0.015")
    assert both.cap_used != D("0.02") + D("0.02")

    excess = payroll_effects(db, user.id, "2026-01-01", config=preview("150", "53000150"))
    left_taxable = ral + excess.components.employer_annual - excess.cap_used
    right_taxable = ral - excess.payroll_deduction + excess.employer_taxable_excess
    assert excess.cap_used == D("5300")
    assert excess.cap_excess == D("0.0300")
    assert excess.employer_taxable_excess == D("0.0150")
    assert left_taxable == right_taxable == ral + D("0.0150")


def test_salary_payment_counts_do_not_change_monthly_or_quarterly_pension_credits(db):
    observed = {}
    for salary_months in (12, 13, 14):
        for schedule, weights in (("monthly", MONTHLY), ("quarterly", QUARTERLY)):
            user = _user(db, f"salary-{salary_months}-{schedule}@example.com")
            db.add(SalaryConfig(
                user_id=user.id, valid_from="2025-01-01", ral=D("60000"),
                salary_months=salary_months,
            ))
            fund = _account(db, user.id, f"{salary_months}-{schedule}", opening="0")
            config = _config(db, user.id, fund.id, weights=weights)
            db.commit()

            saved_salary = db.query(SalaryConfig).filter_by(user_id=user.id).one()
            assert saved_salary.salary_months == salary_months
            jan_credit = monthly_credit(config, "2025-01-01")
            march_credit = monthly_credit(config, "2025-03-01")
            dec_credit = monthly_credit(config, "2025-12-01")
            balance = pension_balances(db, user.id, "2025-12-01")[0]
            observed[(salary_months, schedule)] = (
                jan_credit, march_credit, dec_credit, balance.balance,
                balance.employee_contributions, balance.employer_contributions,
                balance.tfr_contributions,
            )

    for salary_months in (12, 13, 14):
        monthly = observed[(salary_months, "monthly")]
        quarterly = observed[(salary_months, "quarterly")]
        assert monthly[0] == type(monthly[0])(D(25), D(50), D(200))
        assert quarterly[0] == type(quarterly[0])(D(0), D(0), D(0))
        assert monthly[1] == type(monthly[1])(D(25), D(50), D(200))
        assert quarterly[1] == type(quarterly[1])(D(75), D(150), D(600))
        assert monthly[2] == monthly[1]
        assert quarterly[2] == quarterly[1]
        assert monthly[3:] == quarterly[3:] == (
            D("3300.00"), D("300.00"), D("600.00"), D("2400.00")
        )
    assert observed[(12, "monthly")] == observed[(13, "monthly")] == observed[(14, "monthly")]
    assert observed[(12, "quarterly")] == observed[(13, "quarterly")] == observed[(14, "quarterly")]


def test_midyear_calendar_change_preserves_prior_quarterly_credits(db):
    user = _user(db)
    fund = _account(db, user.id, "calendar-change", opening="0")
    _config(db, user.id, fund.id, valid_from="2025-01-01", weights=QUARTERLY)
    _config(db, user.id, fund.id, valid_from="2025-05-01", weights=MONTHLY, config_id="monthly-may")
    db.commit()

    march = pension_balances(db, user.id, "2025-03-01")[0]
    april = pension_balances(db, user.id, "2025-04-01")[0]
    may = pension_balances(db, user.id, "2025-05-01")[0]
    december = pension_balances(db, user.id, "2025-12-01")[0]
    assert march.balance == D("825.00")
    assert april.balance == D("825.00")
    assert may.balance == D("1100.00")
    assert december.balance == D("3025.00")
    assert (december.employee_contributions, december.employer_contributions,
            december.tfr_contributions) == (D("275.00"), D("550.00"), D("2200.00"))


def test_double_december_weight_uses_calendar_year_anchored_denominator(db):
    user = _user(db)
    fund = _account(db, user.id, "double-december", opening="0")
    weights = [1] * 11 + [2]
    config = _config(db, user.id, fund.id, weights=weights)
    db.commit()

    november_credit = monthly_credit(config, "2025-11-01")
    december_credit = monthly_credit(config, "2025-12-01")
    november = pension_balances(db, user.id, "2025-11-01")[0]
    december = pension_balances(db, user.id, "2025-12-01")[0]
    assert november_credit == type(november_credit)(D(300) / 13, D(600) / 13, D(2400) / 13)
    assert december_credit == type(december_credit)(D(600) / 13, D(1200) / 13, D(4800) / 13)
    assert november.balance == D("2792.31")
    assert december.balance == D("3300.00")


def test_fractional_credit_rounds_only_at_balance_output_half_even(db):
    user = _user(db)
    fund = _account(db, user.id, "fractional", opening="0", opening_month="2025-01-01")
    _config(
        db, user.id, fund.id, employee_rate="0.0001", employee_base="1",
        employer_rate="0", employer_base="0", tfr="0", weights=MONTHLY,
    )
    db.commit()

    # Twelve raw 0.004166... monthly credits carry to five cents; rounding
    # each scheduled month first would incorrectly produce zero.
    config = db.query(PensionConfig).filter_by(account_id=fund.id).one()
    config.employee_contrib_annual_base = D("500")
    db.commit()
    assert pension_balances(db, user.id, "2025-12-01")[0].employee_contributions == D("0.05")
    assert pension_balances(db, user.id, "2025-12-01")[0].balance == D("0.05")


def test_half_even_cent_rounding_is_applied_only_to_final_balance(db):
    user = _user(db)
    tie_down = _account(db, user.id, "half-even-down", opening="0", opening_month="2025-01-01")
    tie_up = _account(db, user.id, "half-even-up", opening="0", opening_month="2025-01-01")
    _config(db, user.id, tie_down.id, employee_rate="0.0001", employee_base="600",
            employer_rate="0", employer_base="0", tfr="0", weights=MONTHLY)
    _config(db, user.id, tie_up.id, valid_from="2025-02-01", employee_rate="0.0001",
            employee_base="1800", employer_rate="0", employer_base="0", tfr="0", weights=MONTHLY)
    db.commit()

    jan_balances = {row.account_id: row.balance for row in pension_balances(db, user.id, "2025-01-01")}
    feb_balances = {row.account_id: row.balance for row in pension_balances(db, user.id, "2025-02-01")}
    assert jan_balances[tie_down.id] == D("0.00")  # 0.005 rounds to even zero.
    assert feb_balances[tie_up.id] == D("0.02")  # 0.015 rounds to even two cents.


def test_invalid_dates_negative_amounts_and_bad_calendars_are_rejected(db):
    user = _user(db)
    fund = _account(db, user.id, "invalid", opening="-1", opening_month="2025-01-01")
    _config(db, user.id, fund.id, weights=MONTHLY)
    db.commit()
    with pytest.raises(ValueError, match="opening balance"):
        pension_balances(db, user.id, "2025-01-01")
    with pytest.raises(ValueError, match="canonical"):
        pension_balances(db, user.id, "2025-01-15")

    fund.opening_balance = D(0)
    db.add(Transfer(
        id="negative-transfer", user_id=user.id, date="2025-01-01", billing_month="2025-01-01",
        detail="invalid", amount=D("-1"), from_account_type="bank", from_account_name="bank",
        to_account_type="pension", to_account_name=fund.name, to_account_id=fund.id,
    ))
    db.commit()
    with pytest.raises(ValueError, match="transfer amount"):
        pension_balances(db, user.id, "2025-01-01")
    db.delete(db.get(Transfer, "negative-transfer"))
    config = db.query(PensionConfig).filter_by(account_id=fund.id).one()
    config.contribution_periods_by_month = [0] * 12
    db.commit()
    with pytest.raises(ValueError, match="Contribution calendar"):
        pension_balances(db, user.id, "2025-01-01")


def test_history_queries_are_bounded_and_calculation_is_read_only(db):
    user = _user(db)
    fund = _account(db, user.id, "query-count", opening="0", opening_month="2000-01-01")
    _config(db, user.id, fund.id, valid_from="2000-01-01")
    db.commit()
    statement_count = 0

    def count_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        nonlocal statement_count
        if statement.lstrip().upper().startswith(("SELECT", "INSERT", "UPDATE", "DELETE")):
            statement_count += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", count_sql)
    try:
        rows = pension_balances(db, user.id, "2025-12-01")
    finally:
        event.remove(engine, "before_cursor_execute", count_sql)

    assert len(rows) == 1
    assert statement_count == 5  # fixed account/config/snapshot/transfer loads; no monthly SQL.
    assert db.query(PensionBalanceSnapshot).count() == 0
    assert db.query(Transfer).count() == 0
    assert db.query(PensionConfig).count() == 1


def test_inactive_and_untracked_pension_accounts_are_not_invented(db):
    user = _user(db)
    _account(db, user.id, "no-opening", opening=None, opening_month=None)
    _account(db, user.id, "inactive-funded", active=False, opening="100", opening_month="2025-01-01")
    db.commit()
    assert pension_balances(db, user.id, "2025-12-01") == []
