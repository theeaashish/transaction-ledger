from typing import Annotated

from fastapi import Depends

from app.dependencies.db import DBSession
from app.dependencies.repositories import (
    AccountRepositoryDep,
    TransactionRepositoryDep,
)
from app.modules.accounts.service import AccountService
from app.modules.transactions.service import TransactionService


def get_account_service(
    account_repository: AccountRepositoryDep, db: DBSession
) -> AccountService:
    """Provide an account service sharing its repository's database session."""
    return AccountService(account_repository, db)


AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]


def get_transaction_service(
    account_repository: AccountRepositoryDep,
    transaction_repository: TransactionRepositoryDep,
    db: DBSession,
) -> TransactionService:
    """Provide a transaction service sharing its repositories' database session."""
    return TransactionService(account_repository, transaction_repository, db)


TransactionServiceDep = Annotated[TransactionService, Depends(get_transaction_service)]
