from uuid import UUID

from fastapi import APIRouter, Query, status

from app.dependencies.controllers import TransactionControllerDep
from app.modules.transactions.constants import (
    CREATE_TRANSACTION_RESPONSES,
    GET_HISTORY_RESPONSES,
)
from app.modules.transactions.schemas import (
    TransactionCreate,
    TransactionCreateResponse,
    TransactionHistoryResponse,
    TransactionType,
)

router = APIRouter(
    prefix="/accounts/{account_id}/transactions",
    tags=["Transactions"],
)


@router.post(
    "",
    response_model=TransactionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses=CREATE_TRANSACTION_RESPONSES,
)
def create_transaction(
    account_id: UUID,
    payload: TransactionCreate,
    transaction_controller: TransactionControllerDep,
) -> TransactionCreateResponse:
    """Create a new transaction (credit or debit) for an account."""
    return transaction_controller.create_transaction(account_id, payload)


@router.get(
    "",
    response_model=TransactionHistoryResponse,
    status_code=status.HTTP_200_OK,
    responses=GET_HISTORY_RESPONSES,
)
def get_transaction_history(
    account_id: UUID,
    transaction_controller: TransactionControllerDep,
    transaction_type: TransactionType | None = Query(
        default=None,
        alias="type",
        description="Filter transactions by type ('credit' or 'debit').",
    ),
    page: int = Query(
        default=1,
        ge=1,
        description="Page number (1-indexed, minimum 1).",
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Number of transactions per page (1 to 100).",
    ),
) -> TransactionHistoryResponse:
    """Retrieve paginated transaction history for an account, sorted newest first."""
    return transaction_controller.get_history(
        account_id=account_id,
        transaction_type=transaction_type,
        page=page,
        limit=limit,
    )
