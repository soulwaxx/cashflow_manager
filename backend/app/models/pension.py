from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.user import gen_uuid


class PensionConfig(Base):
    __tablename__ = "pension_configs"
    __table_args__ = (
        UniqueConstraint("user_id", "valid_from", name="uq_pension_config_user_valid_from"),
        ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["accounts.user_id", "accounts.id"],
            name="fk_pension_config_owned_account",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "employee_contrib_rate >= 0 AND employee_contrib_rate <= 1",
            name="ck_pension_config_employee_rate",
        ),
        CheckConstraint(
            "employer_contrib_rate >= 0 AND employer_contrib_rate <= 1",
            name="ck_pension_config_employer_rate",
        ),
        CheckConstraint("employee_contrib_annual_base >= 0", name="ck_pension_config_employee_base"),
        CheckConstraint("employer_contrib_annual_base >= 0", name="ck_pension_config_employer_base"),
        CheckConstraint("tfr_contrib_annual >= 0", name="ck_pension_config_tfr"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(String(36), nullable=False)
    valid_from: Mapped[str] = mapped_column(String(10), nullable=False)
    employee_contrib_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    employee_contrib_annual_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    employer_contrib_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    employer_contrib_annual_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tfr_contrib_annual: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    contribution_periods_by_month: Mapped[list[int]] = mapped_column(JSON, nullable=False)


class PensionBalanceSnapshot(Base):
    __tablename__ = "pension_balance_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "account_id", "as_of_month", name="uq_pension_snapshot_user_account_month"
        ),
        ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["accounts.user_id", "accounts.id"],
            name="fk_pension_snapshot_owned_account",
            ondelete="CASCADE",
        ),
        CheckConstraint("balance >= 0", name="ck_pension_snapshot_balance"),
        CheckConstraint(
            "source IN ('statement', 'manual', 'legacy_override')",
            name="ck_pension_snapshot_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(String(36), nullable=False)
    as_of_month: Mapped[str] = mapped_column(String(10), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
