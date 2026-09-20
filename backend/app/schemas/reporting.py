"""Shared validation contracts for bounded reporting requests."""

import datetime
import re

from pydantic import BaseModel, Field, field_validator, model_validator

# The summary and assets year controls limit reporting to this range.
MIN_REPORTING_YEAR = 2000
MAX_REPORTING_YEAR = 2100


class AsOfMonth(BaseModel):
    """A canonical first-of-month asset reporting cutoff."""

    as_of: str

    @field_validator("as_of")
    @classmethod
    def validate_as_of_month(cls, value: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Asset as_of must be YYYY-MM-DD")
        try:
            as_of = datetime.date.fromisoformat(value)
        except ValueError:
            raise ValueError("Asset as_of must be a valid date")
        if as_of.day != 1:
            raise ValueError("Asset as_of must be the first day of a month")
        if not MIN_REPORTING_YEAR <= as_of.year <= MAX_REPORTING_YEAR:
            raise ValueError(
                f"Reporting year must be between {MIN_REPORTING_YEAR} and {MAX_REPORTING_YEAR}"
            )
        return as_of.isoformat()


class YearMonthRange(BaseModel):
    """A canonical, inclusive ISO-8601 year-month reporting range."""

    from_: str = Field(alias="from")
    to: str

    @field_validator("from_", "to")
    @classmethod
    def validate_year_month(cls, value: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}", value):
            raise ValueError("Reporting month must be YYYY-MM")
        try:
            month = datetime.date.fromisoformat(f"{value}-01")
        except ValueError:
            raise ValueError("Reporting month must be a valid YYYY-MM")
        if not MIN_REPORTING_YEAR <= month.year <= MAX_REPORTING_YEAR:
            raise ValueError(
                f"Reporting year must be between {MIN_REPORTING_YEAR} and {MAX_REPORTING_YEAR}"
            )
        return value

    @model_validator(mode="after")
    def validate_ordered_range(self) -> "YearMonthRange":
        if self.from_ > self.to:
            raise ValueError("Reporting range start must not be after its end")
        return self
