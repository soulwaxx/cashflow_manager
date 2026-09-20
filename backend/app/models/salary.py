from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Numeric, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.user import gen_uuid


class SalaryConfig(Base):
    __tablename__ = "salary_config"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    valid_from: Mapped[str] = mapped_column(String(10))
    ral: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    employer_contrib_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0.04)
    voluntary_contrib_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0.0)
    regional_tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0.0173)
    municipal_tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0.001)
    meal_vouchers_annual: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    welfare_annual: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    salary_months: Mapped[int] = mapped_column(Integer, default=12)
    manual_net_override: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    computed_net_monthly: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
