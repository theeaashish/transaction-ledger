from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Mixin

if TYPE_CHECKING:
    from app.db.models.transaction import Transaction


class Account(Mixin, Base):
    """Account database model."""

    __tablename__ = "accounts"

    __table_args__ = (
        CheckConstraint(
            "length(btrim(name)) > 0",
            name="name_not_blank",
        ),
        CheckConstraint(
            "balance >= 0",
            name="balance_non_negative",
        ),
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0.00"),
    )

    # Relationships
    transactions: Mapped[list[Transaction]] = relationship(
        "Transaction",
        back_populates="account",
        cascade="save-update, merge",
        passive_deletes="all",
    )
