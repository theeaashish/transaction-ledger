from typing import Annotated

from fastapi import Depends

from app.dependencies.db import DBSession
from app.repositories.account import AccountRepository
from app.repositories.transaction import TransactionRepository


def get_account_repository(db: DBSession) -> AccountRepository:
    """Provide an account repository using the request-scoped database session."""
    return AccountRepository(db)


AccountRepositoryDep = Annotated[AccountRepository, Depends(get_account_repository)]


def get_transaction_repository(db: DBSession) -> TransactionRepository:
    """Provide a transaction repository using the request-scoped database session."""
    return TransactionRepository(db)


TransactionRepositoryDep = Annotated[
    TransactionRepository, Depends(get_transaction_repository)
]
