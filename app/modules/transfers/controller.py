from app.modules.transfers.schemas import (
    TransferAccountResponse,
    TransferCreate,
    TransferResponse,
)
from app.modules.transfers.service import TransferService


class TransferController:
    """Translate transfer service results into API response schemas."""

    def __init__(self, transfer_service: TransferService) -> None:
        self.transfer_service = transfer_service

    def transfer(self, payload: TransferCreate) -> TransferResponse:
        """Execute a fund transfer and format the response with both account states."""
        result = self.transfer_service.transfer(payload)
        return TransferResponse(
            reference_id=result.reference_id,
            amount=result.amount,
            source_account=TransferAccountResponse(
                account_id=result.source_account_id,
                balance=result.source_balance,
            ),
            destination_account=TransferAccountResponse(
                account_id=result.destination_account_id,
                balance=result.destination_balance,
            ),
            debit_transaction_id=result.debit_transaction_id,
            credit_transaction_id=result.credit_transaction_id,
            created_at=result.created_at,
        )
