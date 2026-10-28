from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, WithJsonSchema


def _serialize_money(value: Decimal) -> str:
    """Preserve decimal precision and always include two fractional digits."""
    return format(value, ".2f")


Money = Annotated[
    Decimal,
    PlainSerializer(_serialize_money, return_type=str, when_used="json"),
    WithJsonSchema(
        {
            "type": "string",
            "pattern": r"^\d+\.\d{2}$",
            "description": "Exact monetary amount with two fractional digits.",
            "examples": ["0.00", "125.50"],
        },
        mode="serialization",
    ),
]


class AccountCreate(BaseModel):
    """Client-controlled fields for creating an account."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255, examples=["Aashish"])


class AccountResponse(BaseModel):
    """Persisted account with a UUIDv7 ID and database-generated timestamp."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    balance: Money
    created_at: datetime


class AccountBalanceResponse(BaseModel):
    """Account identifier and exact current balance."""

    account_id: UUID
    balance: Money
