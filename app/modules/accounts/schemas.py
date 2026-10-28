from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.types import Money


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
