from datetime import datetime
from typing import Optional
from sqlalchemy import String, Numeric, DateTime, Integer, Text, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.user import gen_uuid


class Transfer(Base):
    __tablename__ = "transfers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[str] = mapped_column(String(10))
    detail: Mapped[str] = mapped_column(String(500))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    from_account_type: Mapped[str] = mapped_column(String(20))
    from_account_name: Mapped[str] = mapped_column(String(255))
    to_account_type: Mapped[str] = mapped_column(String(20))
    to_account_name: Mapped[str] = mapped_column(String(255))
    billing_month: Mapped[str] = mapped_column(String(10))
    recurrence_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parent_transfer_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("transfers.id"), nullable=True
    )
    from_payment_method_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("payment_methods.id", ondelete="SET NULL"), nullable=True
    )
    to_payment_method_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("payment_methods.id", ondelete="SET NULL"), nullable=True
    )
    from_account_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    to_account_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_transfer_user_billing_month", "user_id", "billing_month"),
        Index("ix_transfer_parent_id", "parent_transfer_id"),
    )
