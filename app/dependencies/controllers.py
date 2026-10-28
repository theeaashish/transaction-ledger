from typing import Annotated

from fastapi import Depends

from app.dependencies.services import AccountServiceDep
from app.modules.accounts.controller import AccountController


def get_account_controller(account_service: AccountServiceDep) -> AccountController:
    """Provide an account controller backed by the request's account service."""
    return AccountController(account_service)


AccountControllerDep = Annotated[AccountController, Depends(get_account_controller)]
