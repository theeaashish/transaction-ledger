from uuid import UUID

from app.modules.accounts.schemas import (
    AccountBalanceResponse,
    AccountCreate,
    AccountResponse,
)
from app.modules.accounts.service import AccountService


class AccountController:
    """Translate account service results into API response schemas."""

    def __init__(self, account_service: AccountService) -> None:
        self.account_service = account_service

    def create_account(self, payload: AccountCreate) -> AccountResponse:
        """Create an account from validated client input."""
        account = self.account_service.create_account(payload.name)
        return AccountResponse.model_validate(account)

    def get_account_balance(self, account_id: UUID) -> AccountBalanceResponse:
        """Retrieve an account and expose only its identifier and balance."""
        account = self.account_service.get_account_by_id(account_id)
        return AccountBalanceResponse(account_id=account.id, balance=account.balance)
