from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AccountNotFoundException
from app.db.models.account import Account
from app.repositories.account import AccountRepository


class AccountService:
    """Account business operations and transaction boundaries."""

    def __init__(self, account_repository: AccountRepository, db: Session) -> None:
        self.account_repository = account_repository
        self.db = db

    def create_account(self, name: str) -> Account:
        """Create a zero-balance account and atomically commit its persistence."""
        try:
            account = self.account_repository.add(
                Account(name=name, balance=Decimal("0.00"))
            )
            # Flush starts a transaction automatically, or uses the active one.
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return account

    def get_account_by_id(self, account_id: UUID) -> Account:
        """Retrieve an account or raise the application's not-found exception."""
        account = self.account_repository.get_by_id(account_id)
        if account is None:
            raise AccountNotFoundException()
        return account
