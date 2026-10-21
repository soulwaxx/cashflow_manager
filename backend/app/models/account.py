from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.user import gen_uuid


class Account(Base):
    """A user-owned non-bank account with a stable identity."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "type", "name", name="uq_account_user_type_name"),
    )
    __table_args__ = __table_args__ + (
        Index("uq_accounts_user_id_id", "user_id", "id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(255))
    opening_balance: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    opening_balance_month: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
