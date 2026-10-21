import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.pension import (
    PensionBalanceSnapshotCreate,
    PensionBalanceSnapshotResponse,
    PensionConfigCreate,
    PensionConfigResponse,
)


def _config(**overrides):
    values = {
        "account_id": "account-1",
        "valid_from": "2026-01-01",
        "employee_contrib_rate": "0.0100",
        "employee_contrib_annual_base": "30000.00",
        "employer_contrib_rate": "0.0200",
        "employer_contrib_annual_base": "25000.00",
        "tfr_contrib_annual": "0.00",
        "contribution_periods_by_month": [1] * 12,
    }
    values.update(overrides)
    return values


def test_pension_config_accepts_independent_decimal_bases_and_calendar():
    config = PensionConfigCreate(**_config())

    assert config.employee_contrib_annual_base == Decimal("30000.00")
    assert config.employer_contrib_annual_base == Decimal("25000.00")
    assert config.contribution_periods_by_month == [1] * 12


@pytest.mark.parametrize("month", ["2026-1-01", "2026-01-02", "2026-13-01", "2026-01"])
def test_pension_config_requires_canonical_first_of_month(month):
    with pytest.raises(ValidationError, match="canonical YYYY-MM-01"):
        PensionConfigCreate(**_config(valid_from=month))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("employee_contrib_rate", "NaN"),
        ("employer_contrib_rate", "Infinity"),
        ("employee_contrib_rate", "1.0001"),
        ("employee_contrib_annual_base", "-0.01"),
        ("employer_contrib_annual_base", "10000000000.00"),
        ("tfr_contrib_annual", "1.001"),
    ],
)
def test_pension_config_rejects_invalid_decimal_values(field, value):
    with pytest.raises(ValidationError):
        PensionConfigCreate(**_config(**{field: value}))


@pytest.mark.parametrize(
    "calendar",
    [
        [0] * 12,
        [1] * 11,
        [1] * 11 + [-1],
        [1] * 11 + [1.5],
        [True] + [1] * 11,
    ],
)
def test_pension_config_rejects_invalid_credit_calendars(calendar):
    with pytest.raises(ValidationError):
        PensionConfigCreate(**_config(contribution_periods_by_month=calendar))


def test_snapshot_schema_limits_client_sources_and_requires_finite_nonnegative_balance():
    payload = {
        "account_id": "account-1",
        "as_of_month": "2026-03-01",
        "balance": "123.45",
        "source": "statement",
        "notes": "Quarterly statement",
    }
    assert PensionBalanceSnapshotCreate(**payload).balance == Decimal("123.45")

    for invalid in (
        {**payload, "as_of_month": "2026-03-15"},
        {**payload, "balance": "-0.01"},
        {**payload, "balance": "NaN"},
        {**payload, "source": "legacy_override"},
    ):
        with pytest.raises(ValidationError):
            PensionBalanceSnapshotCreate(**invalid)

    legacy_response = PensionBalanceSnapshotResponse(
        id="snapshot-1", user_id="user-1", **{**payload, "source": "legacy_override"}
    )
    assert legacy_response.source == "legacy_override"


def test_pension_response_json_encodes_money_and_rates_as_numbers():
    config = PensionConfigResponse(
        id="config-1", user_id="user-1", **_config()
    )
    config_json = json.loads(config.model_dump_json())
    for field in (
        "employee_contrib_rate",
        "employee_contrib_annual_base",
        "employer_contrib_rate",
        "employer_contrib_annual_base",
        "tfr_contrib_annual",
    ):
        assert type(config_json[field]) in {int, float}
    assert isinstance(config.employee_contrib_annual_base, Decimal)

    snapshot = PensionBalanceSnapshotResponse(
        id="snapshot-1",
        user_id="user-1",
        account_id="account-1",
        as_of_month="2026-12-01",
        balance=Decimal("123.45"),
        source="legacy_override",
    )
    snapshot_json = json.loads(snapshot.model_dump_json())
    assert type(snapshot_json["balance"]) in {int, float}
    assert snapshot_json["source"] == "legacy_override"
    assert snapshot.balance == Decimal("123.45")
