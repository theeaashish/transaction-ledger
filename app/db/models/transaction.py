from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Mixin

if TYPE_CHECKING:
    from app.db.models.account import Account


class Transaction(Mixin, Base):
    """Transaction database model."""

    __tablename__ = "transactions"

    __table_args__ = (
        CheckConstraint(
            "type IN ('credit', 'debit')",
            name="type_valid",
        ),
        CheckConstraint(
            "amount > 0",
            name="amount_positive",
        ),
        CheckConstraint(
            "length(btrim(description)) > 0",
            name="description_not_blank",
        ),
        CheckConstraint(
            "length(btrim(reference_id)) > 0",
            name="reference_id_not_blank",
        ),
        UniqueConstraint(
            "account_id",
            "reference_id",
            name="uq_account_reference_id",
        ),
        Index(
            "ix_transactions_account_history",
            "account_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
    )

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )

    type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    reference_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Relationships
    account: Mapped[Account] = relationship(
        "Account",
        back_populates="transactions",
    )
