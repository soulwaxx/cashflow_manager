from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.user import gen_uuid


class TaxConfig(Base):
    __tablename__ = "tax_config"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    valid_from: Mapped[str] = mapped_column(String(10))
    inps_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0.0919)
    irpef_band1_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0.23)
    irpef_band1_limit: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=28000)
    irpef_band2_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0.33)
    irpef_band2_limit: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=50000)
    irpef_band3_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0.43)
    employment_deduction_band1_limit: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=15000)
    employment_deduction_band1_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=1955)
    employment_deduction_band2_limit: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=28000)
    employment_deduction_band2_base: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=1910)
    employment_deduction_band2_variable: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=1190)
    employment_deduction_band2_range: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=13000)
    employment_deduction_band3_limit: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=50000)
    employment_deduction_band3_base: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=1910)
    employment_deduction_band3_range: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=22000)
    pension_deductibility_cap: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=5300.00)
    employment_deduction_floor: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=690.00)
