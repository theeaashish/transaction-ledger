from uuid import UUID

from fastapi import APIRouter, status

from app.dependencies.controllers import AccountControllerDep
from app.modules.accounts.schemas import (
    AccountBalanceResponse,
    AccountCreate,
    AccountResponse,
)

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        422: {"description": "Invalid request (VALIDATION_ERROR)."},
        500: {"description": "Unexpected failure (INTERNAL_SERVER_ERROR)."},
    },
)
def create_account(
    payload: AccountCreate, account_controller: AccountControllerDep
) -> AccountResponse:
    """Create an account with a zero balance and database-generated created_at."""
    return account_controller.create_account(payload)


@router.get(
    "/{account_id}/balance",
    response_model=AccountBalanceResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"description": "Account does not exist (ACCOUNT_NOT_FOUND)."},
        422: {"description": "Invalid UUID (VALIDATION_ERROR)."},
        500: {"description": "Unexpected failure (INTERNAL_SERVER_ERROR)."},
    },
)
def get_account_balance(
    account_id: UUID, account_controller: AccountControllerDep
) -> AccountBalanceResponse:
    """Return an account's balance as an exact string with two fractional digits."""
    return account_controller.get_account_balance(account_id)
