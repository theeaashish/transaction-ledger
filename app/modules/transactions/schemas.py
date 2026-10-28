from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.types import Money, PositiveMoney

TransactionType = Literal["credit", "debit"]


class TransactionCreate(BaseModel):
    """Client-controlled payload for creating a transaction."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: TransactionType = Field(
        description="Transaction type ('credit' to deposit, 'debit' to withdraw).",
        examples=["credit"],
    )
    amount: PositiveMoney
    description: str = Field(
        min_length=1,
        max_length=500,
        description="Transaction description (1 to 500 characters, non-blank).",
        examples=["Initial deposit"],
    )
    reference_id: str = Field(
        min_length=1,
        max_length=255,
        description=(
            "Unique reference identifier for the account "
            "(1 to 255 characters, non-blank)."
        ),
        examples=["REF-2026-001"],
    )


class TransactionCreateResponse(BaseModel):
    """Response returned upon successful transaction creation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    type: TransactionType
    amount: Money
    description: str
    reference_id: str
    balance_after: Money
    created_at: datetime


class TransactionResponse(BaseModel):
    """Transaction item in account history."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    type: TransactionType
    amount: Money
    description: str
    reference_id: str
    created_at: datetime


class TransactionHistoryResponse(BaseModel):
    """Paginated list of account transactions with metadata."""

    account_id: UUID
    current_page: int
    page_size: int
    total_records: int
    total_pages: int
    transactions: list[TransactionResponse]
