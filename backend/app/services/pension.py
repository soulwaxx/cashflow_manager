"""Pension contribution estimates and reconciled cumulative balances.

This module is a calculation seam for the later salary/assets integrations. It
never persists derived credits or changes account, transfer, or tax rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN
from fractions import Fraction
from typing import Any

from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.pension import PensionBalanceSnapshot, PensionConfig
from app.models.tax import TaxConfig
from app.models.transfer import Transfer
from app.services.tax import resolve_tax_config

ZERO = Decimal("0")
CENT = Decimal("0.01")
_UNSET = object()


@dataclass(frozen=True)
class PensionComponents:
    employee_annual: Decimal
    employer_annual: Decimal
    tfr_annual: Decimal


@dataclass(frozen=True)
class PensionPayrollInputs:
    """Explicit annual contribution inputs for a non-persistent preview."""

    employee_contrib_rate: Decimal
    employee_contrib_annual_base: Decimal
    employer_contrib_rate: Decimal
    employer_contrib_annual_base: Decimal
    tfr_contrib_annual: Decimal


@dataclass(frozen=True)
class PensionPayrollEffects:
    components: PensionComponents
    deductibility_cap: Decimal
    cap_used: Decimal
    cap_excess: Decimal
    payroll_deduction: Decimal
    employer_taxable_excess: Decimal
    tax_config_id: str
    tax_config_valid_from: str
    cap_scope: str = "configured ordinary payroll contributions only; TFR excluded"


@dataclass(frozen=True)
class PensionMonthlyCredit:
    employee: Decimal
    employer: Decimal
    tfr: Decimal


@dataclass(frozen=True)
class PensionAccountBalance:
    account_id: str
    account_name: str
    balance: Decimal
    employee_contributions: Decimal
    employer_contributions: Decimal
    tfr_contributions: Decimal
    net_transfers: Decimal
    valuation_status: str
    reconciled_as_of_month: str | None
    reconciled_balance: Decimal | None
    reconciliation_source: str | None
    projected_through: str


def _month(value: str, *, name: str = "month") -> date:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a canonical YYYY-MM-01 date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{name} must be a canonical YYYY-MM-01 date") from None
    if parsed.day != 1 or parsed.isoformat() != value:
        raise ValueError(f"{name} must be a canonical YYYY-MM-01 date")
    return parsed


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_EVEN)


def _round_fraction_money(value: Fraction) -> Decimal:
    cents, remainder = divmod(value.numerator * 100, value.denominator)
    doubled_remainder = remainder * 2
    if doubled_remainder > value.denominator or (
        doubled_remainder == value.denominator and cents % 2
    ):
        cents += 1
    return Decimal(cents).scaleb(-2)


def _monthly_credit_fractions(
    config: PensionConfig | None, month: date
) -> tuple[Fraction, Fraction, Fraction]:
    if config is None or config.valid_from > month.isoformat():
        return Fraction(0), Fraction(0), Fraction(0)
    weights = _calendar(config)
    weight, total_weight = weights[month.month - 1], sum(weights)
    annual = _annualized_components(config)
    return tuple(
        Fraction(amount) * weight / total_weight
        for amount in (annual.employee_annual, annual.employer_annual, annual.tfr_annual)
    )


def _finite_nonnegative(value: Any, label: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception:
        raise ValueError(f"{label} must be a finite nonnegative amount") from None
    if not result.is_finite() or result < ZERO:
        raise ValueError(f"{label} must be a finite nonnegative amount")
    return result


def resolve_pension_config(db: Session, user_id: str, as_of_month: str) -> PensionConfig | None:
    """Resolve the latest owner-owned configuration effective in ``as_of_month``.

    Periods are start-inclusive and next-period-exclusive. Missing configuration
    deliberately resolves to ``None`` (zero credits), never to salary/RAL.
    """
    cutoff = _month(as_of_month, name="as_of_month").isoformat()
    config = (
        db.query(PensionConfig)
        .filter(PensionConfig.user_id == user_id, PensionConfig.valid_from <= cutoff)
        .order_by(PensionConfig.valid_from.desc(), PensionConfig.id.asc())
        .first()
    )
    if config is not None:
        _month(config.valid_from, name="configuration valid_from")
        destination = db.query(Account.id).filter(
            Account.id == config.account_id,
            Account.user_id == user_id,
            Account.type == "pension",
        ).first()
        if destination is None:
            raise ValueError("Pension configuration destination must be an owned pension account")
        annualized_components(config)
        _calendar(config)
    return config


def _components_from_values(
    employee_rate: Any,
    employee_base: Any,
    employer_rate: Any,
    employer_base: Any,
    tfr: Any,
) -> PensionComponents:
    employee_rate = _finite_nonnegative(employee_rate, "employee rate")
    employer_rate = _finite_nonnegative(employer_rate, "employer rate")
    employee_base = _finite_nonnegative(employee_base, "employee base")
    employer_base = _finite_nonnegative(employer_base, "employer base")
    tfr = _finite_nonnegative(tfr, "TFR annual amount")
    if employee_rate > 1 or employer_rate > 1:
        raise ValueError("Contribution rates must be between zero and one")
    return PensionComponents(employee_rate * employee_base, employer_rate * employer_base, tfr)


def _annualized_components(config: PensionConfig | None) -> PensionComponents:
    if config is None:
        return PensionComponents(ZERO, ZERO, ZERO)
    return _components_from_values(
        config.employee_contrib_rate,
        config.employee_contrib_annual_base,
        config.employer_contrib_rate,
        config.employer_contrib_annual_base,
        config.tfr_contrib_annual,
    )


def annualized_components(config: PensionConfig | None) -> PensionComponents:
    """Return full-year E/H/T Decimal values without display rounding."""
    return _annualized_components(config)


def _calendar(config: PensionConfig) -> tuple[int, ...]:
    weights = config.contribution_periods_by_month
    if not isinstance(weights, (list, tuple)) or len(weights) != 12:
        raise ValueError("Contribution calendar must contain twelve monthly weights")
    if any(type(weight) is not int or weight < 0 for weight in weights) or sum(weights) <= 0:
        raise ValueError("Contribution calendar must have nonnegative integer weights and a positive sum")
    return tuple(weights)


def monthly_credit(config: PensionConfig | None, month: str) -> PensionMonthlyCredit:
    """Calculate one calendar-anchored credit month without intermediate rounding."""
    parsed = _month(month)
    if config is None:
        return PensionMonthlyCredit(ZERO, ZERO, ZERO)
    _month(config.valid_from, name="configuration valid_from")
    if config.valid_from > parsed.isoformat():
        return PensionMonthlyCredit(ZERO, ZERO, ZERO)
    weight = _calendar(config)[parsed.month - 1]
    total_weight = sum(config.contribution_periods_by_month)
    annual = _annualized_components(config)
    return PensionMonthlyCredit(
        annual.employee_annual * weight / total_weight,
        annual.employer_annual * weight / total_weight,
        annual.tfr_annual * weight / total_weight,
    )


def payroll_effects(
    db: Session,
    user_id: str,
    as_of_month: str,
    *,
    config: PensionConfig | None | object = _UNSET,
) -> PensionPayrollEffects:
    """Compute ordinary combined-cap effects, or fail when tax is unresolved.

    TaxConfig resolution is delegated to the existing owner-aware resolver;
    its global system fallback is preserved. A missing applicable tax config is
    an explicit error rather than an assumed zero or guessed cap.
    """
    cutoff = _month(as_of_month, name="as_of_month").isoformat()
    if config is _UNSET:
        config = resolve_pension_config(db, user_id, cutoff)
    elif config is not None:
        if config.user_id != user_id:
            raise ValueError("Pension configuration must belong to the requested user")
        _month(config.valid_from, name="configuration valid_from")
        destination = db.query(Account.id).filter(
            Account.id == config.account_id,
            Account.user_id == user_id,
            Account.type == "pension",
        ).first()
        if destination is None:
            raise ValueError("Pension configuration destination must be an owned pension account")
        _calendar(config)
    return _payroll_effects_from_components(db, user_id, cutoff, _annualized_components(config))


def preview_payroll_effects(
    db: Session,
    user_id: str,
    as_of_month: str,
    pension: PensionPayrollInputs | None,
) -> PensionPayrollEffects:
    """Calculate an unsaved preview without reading account/config rows.

    ``pension=None`` explicitly means zero contributions, even if the owner has
    a saved pension configuration. The caller is responsible for transport-level
    validation/ownership of any account reference; no account ID is accepted by
    this calculation-only interface. Tax is resolved for the selected month.
    """
    cutoff = _month(as_of_month, name="as_of_month").isoformat()
    if pension is None:
        components = PensionComponents(ZERO, ZERO, ZERO)
    else:
        components = _components_from_values(
            pension.employee_contrib_rate,
            pension.employee_contrib_annual_base,
            pension.employer_contrib_rate,
            pension.employer_contrib_annual_base,
            pension.tfr_contrib_annual,
        )
    return _payroll_effects_from_components(db, user_id, cutoff, components)


def _payroll_effects_from_components(
    db: Session,
    user_id: str,
    cutoff: str,
    raw_components: PensionComponents,
) -> PensionPayrollEffects:
    tax_config: TaxConfig | None = resolve_tax_config(db, cutoff, user_id)
    if tax_config is None:
        raise ValueError(f"No applicable tax configuration for {cutoff}")
    cap = _finite_nonnegative(tax_config.pension_deductibility_cap, "pension deductibility cap")
    eligible = raw_components.employee_annual + raw_components.employer_annual
    cap_used = min(eligible, cap)
    cap_excess = max(eligible - cap, ZERO)
    deduction = min(raw_components.employee_annual, max(cap - raw_components.employer_annual, ZERO))
    employer_excess = max(raw_components.employer_annual - cap, ZERO)
    return PensionPayrollEffects(
        components=raw_components,
        deductibility_cap=cap,
        cap_used=cap_used,
        cap_excess=cap_excess,
        payroll_deduction=deduction,
        employer_taxable_excess=employer_excess,
        tax_config_id=tax_config.id,
        tax_config_valid_from=tax_config.valid_from,
    )


def _month_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current = date(current.year + (current.month == 12), 1 if current.month == 12 else current.month + 1, 1)


def _account_transfer_month(transfer: Transfer) -> date:
    """Transfers are dated by their occurrence date; report cutoff is inclusive."""
    try:
        transfer_date = date.fromisoformat(transfer.date)
    except (TypeError, ValueError):
        raise ValueError(f"Transfer {transfer.id} has an invalid date") from None
    return date(transfer_date.year, transfer_date.month, 1)


def pension_balances(db: Session, user_id: str, as_of_month: str) -> list[PensionAccountBalance]:
    """Evaluate active owned pension accounts through inclusive month cutoff.

    Accounts without an opening month are omitted unless an eligible snapshot
    supplies a dated baseline. Owned transfers are included using occurrence
    date month (not legacy ``billing_month``); a snapshot includes its own month.
    Histories are bulk-loaded once, then evaluated in memory by month.
    """
    cutoff = _month(as_of_month, name="as_of_month")
    owned_accounts: list[Account] = (
        db.query(Account)
        .filter(Account.user_id == user_id)
        .order_by(Account.id)
        .all()
    )
    owned_account_by_id = {account.id: account for account in owned_accounts}
    accounts = [
        account for account in owned_accounts
        if account.type == "pension" and account.is_active
    ]
    if not accounts:
        return []
    account_by_id = {account.id: account for account in accounts}
    ids = tuple(account_by_id)

    configs: list[PensionConfig] = (
        db.query(PensionConfig)
        .filter(
            PensionConfig.user_id == user_id,
            PensionConfig.valid_from <= cutoff.isoformat(),
        )
        .order_by(PensionConfig.valid_from, PensionConfig.id)
        .all()
    )
    for config in configs:
        _month(config.valid_from, name="configuration valid_from")
        referenced = owned_account_by_id.get(config.account_id)
        if referenced is None or referenced.type != "pension":
            raise ValueError("Pension configuration destination must be an owned pension account")
        annualized_components(config)
        _calendar(config)

    snapshots: list[PensionBalanceSnapshot] = (
        db.query(PensionBalanceSnapshot)
        .filter(
            PensionBalanceSnapshot.user_id == user_id,
            PensionBalanceSnapshot.account_id.in_(ids),
            PensionBalanceSnapshot.as_of_month <= cutoff.isoformat(),
        )
        .order_by(PensionBalanceSnapshot.account_id, PensionBalanceSnapshot.as_of_month)
        .all()
    )
    snapshots_by_account: dict[str, list[PensionBalanceSnapshot]] = {account_id: [] for account_id in ids}
    for snapshot in snapshots:
        _month(snapshot.as_of_month, name="snapshot as_of_month")
        _finite_nonnegative(snapshot.balance, "snapshot balance")
        if snapshot.source not in {"statement", "manual", "legacy_override"}:
            raise ValueError("Snapshot source is invalid")
        snapshots_by_account[snapshot.account_id].append(snapshot)

    next_month = date(cutoff.year + (cutoff.month == 12), 1 if cutoff.month == 12 else cutoff.month + 1, 1)
    transfers: list[Transfer] = (
        db.query(Transfer)
        .filter(Transfer.user_id == user_id)
        .order_by(Transfer.date, Transfer.id)
        .all()
    )
    transfer_flows: dict[str, dict[date, Decimal]] = {account_id: {} for account_id in ids}
    for transfer in transfers:
        pension_endpoints = (
            (transfer.from_account_id, -1),
            (transfer.to_account_id, 1),
        )
        endpoint_types = (transfer.from_account_type, transfer.to_account_type)
        relevant = [
            (endpoint_id, sign)
            for (endpoint_id, sign), endpoint_type in zip(pension_endpoints, endpoint_types)
            if endpoint_type == "pension" and endpoint_id in transfer_flows
        ]
        if not relevant:
            continue
        amount = _finite_nonnegative(transfer.amount, "transfer amount")
        transfer_month = _account_transfer_month(transfer)
        if transfer_month >= next_month:
            continue
        for endpoint_id, sign in relevant:
            flows = transfer_flows[endpoint_id]
            flows[transfer_month] = flows.get(transfer_month, ZERO) + amount * sign

    result: list[PensionAccountBalance] = []
    for account_id, account in account_by_id.items():
        eligible_snapshots = snapshots_by_account[account_id]
        selected_snapshot = eligible_snapshots[-1] if eligible_snapshots else None
        if selected_snapshot is not None:
            baseline_month = _month(selected_snapshot.as_of_month)
            baseline = _finite_nonnegative(selected_snapshot.balance, "snapshot balance")
            if account.opening_balance_month is not None and baseline_month < _month(
                account.opening_balance_month, name="opening_balance_month"
            ):
                raise ValueError("Pension snapshot cannot precede the account opening month")
        elif account.opening_balance_month is not None:
            baseline_month = _month(account.opening_balance_month, name="opening_balance_month")
            baseline = _finite_nonnegative(account.opening_balance, "opening balance")
        else:
            continue
        if baseline_month > cutoff:
            continue

        employees = employers = tfrs = net_transfers = Fraction(0)
        balance = Fraction(baseline)
        if selected_snapshot is None:
            first_flow_month = baseline_month
        else:
            first_flow_month = date(
                baseline_month.year + (baseline_month.month == 12),
                1 if baseline_month.month == 12 else baseline_month.month + 1,
                1,
            )

        for current in _month_range(first_flow_month, cutoff):
            # If a config changes destination, credits belong only to the
            # destination selected by that effective period.
            effective = resolve_config_from_loaded(configs, current)
            if effective is not None and effective.account_id == account_id:
                employee, employer, tfr = _monthly_credit_fractions(effective, current)
            else:
                employee = employer = tfr = Fraction(0)
            employees += employee
            employers += employer
            tfrs += tfr
            balance += employee + employer + tfr
            signed_amount = transfer_flows[account_id].get(current, ZERO)
            net_transfers += Fraction(signed_amount)
            balance += Fraction(signed_amount)

        source = selected_snapshot.source if selected_snapshot else None
        status = {
            "statement": "statement_reconciled",
            "manual": "manual_reconciled",
            "legacy_override": "legacy_reconciled",
        }.get(source, "estimated")
        result.append(
            PensionAccountBalance(
                account_id=account_id,
                account_name=account.name,
                balance=_round_fraction_money(balance),
                employee_contributions=_round_fraction_money(employees),
                employer_contributions=_round_fraction_money(employers),
                tfr_contributions=_round_fraction_money(tfrs),
                net_transfers=_round_fraction_money(net_transfers),
                valuation_status=status,
                reconciled_as_of_month=selected_snapshot.as_of_month if selected_snapshot else None,
                reconciled_balance=_round_money(baseline) if selected_snapshot else None,
                reconciliation_source=source,
                projected_through=cutoff.isoformat(),
            )
        )
    return result


def resolve_config_from_loaded(configs: list[PensionConfig], month: date) -> PensionConfig | None:
    """Pure effective-period selection for an already bulk-loaded history."""
    eligible = [config for config in configs if config.valid_from <= month.isoformat()]
    if not eligible:
        return None
    # Config dates are unique per owner by schema; ID stabilizes malformed test data.
    return max(eligible, key=lambda config: (config.valid_from, config.id))
