from typing import Annotated

from fastapi import Depends

from app.dependencies.db import DBSession
from app.repositories.account import AccountRepository


def get_account_repository(db: DBSession) -> AccountRepository:
    """Provide an account repository using the request-scoped database session."""
    return AccountRepository(db)


AccountRepositoryDep = Annotated[AccountRepository, Depends(get_account_repository)]
