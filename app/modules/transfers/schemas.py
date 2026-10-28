from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.types import Money, PositiveMoney


class TransferCreate(BaseModel):
    """Client-controlled payload for transferring funds between accounts."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_account_id: UUID = Field(
        description="UUID of the account to be debited.",
    )
    destination_account_id: UUID = Field(
        description="UUID of the account to be credited (must differ from source).",
    )
    amount: PositiveMoney
    reference_id: str = Field(
        min_length=1,
        max_length=255,
        description=(
            "Unique transfer reference identifier (1 to 255 characters, non-blank)."
        ),
        examples=["TRANSFER-001"],
    )
    description: str = Field(
        min_length=1,
        max_length=500,
        description="Transfer description (1 to 500 characters, non-blank).",
        examples=["Payment to another account"],
    )

    @model_validator(mode="after")
    def validate_different_accounts(self) -> Self:
        """Disallow self-transfers."""
        if self.source_account_id == self.destination_account_id:
            raise ValueError("Source and destination accounts must be different.")
        return self


class TransferAccountResponse(BaseModel):
    """Account identifier and balance resulting from a transfer."""

    account_id: UUID
    balance: Money


class TransferResponse(BaseModel):
    """Resulting record of an atomic transfer between two accounts."""

    reference_id: str
    amount: Money
    source_account: TransferAccountResponse
    destination_account: TransferAccountResponse
    debit_transaction_id: UUID
    credit_transaction_id: UUID
    created_at: datetime
