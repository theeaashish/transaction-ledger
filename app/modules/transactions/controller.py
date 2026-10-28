from typing import cast
from uuid import UUID

from app.modules.transactions.schemas import (
    TransactionCreate,
    TransactionCreateResponse,
    TransactionHistoryResponse,
    TransactionResponse,
    TransactionType,
)
from app.modules.transactions.service import TransactionService


class TransactionController:
    """Translate transaction service results into API response schemas."""

    def __init__(self, transaction_service: TransactionService) -> None:
        self.transaction_service = transaction_service

    def create_transaction(
        self, account_id: UUID, payload: TransactionCreate
    ) -> TransactionCreateResponse:
        """Create a transaction and return it alongside the resulting balance."""
        result = self.transaction_service.create_transaction(account_id, payload)
        return TransactionCreateResponse(
            id=result.transaction.id,
            account_id=result.transaction.account_id,
            type=cast(TransactionType, result.transaction.type),
            amount=result.transaction.amount,
            description=result.transaction.description,
            reference_id=result.transaction.reference_id,
            balance_after=result.balance_after,
            created_at=result.transaction.created_at,
        )

    def get_history(
        self,
        account_id: UUID,
        *,
        transaction_type: TransactionType | None = None,
        page: int = 1,
        limit: int = 10,
    ) -> TransactionHistoryResponse:
        """Retrieve paginated transaction history."""
        result = self.transaction_service.get_history(
            account_id=account_id,
            transaction_type=transaction_type,
            page=page,
            limit=limit,
        )
        return TransactionHistoryResponse(
            account_id=result.account_id,
            current_page=result.current_page,
            page_size=result.page_size,
            total_records=result.total_records,
            total_pages=result.total_pages,
            transactions=[
                TransactionResponse.model_validate(tx) for tx in result.transactions
            ],
        )
