from typing import Annotated

from fastapi import Depends

from app.dependencies.db import DBSession
from app.dependencies.repositories import AccountRepositoryDep
from app.modules.accounts.service import AccountService


def get_account_service(
    account_repository: AccountRepositoryDep, db: DBSession
) -> AccountService:
    """Provide an account service sharing its repository's database session."""
    return AccountService(account_repository, db)


AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]
