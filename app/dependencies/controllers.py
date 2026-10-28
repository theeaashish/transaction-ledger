from typing import Annotated

from fastapi import Depends

from app.dependencies.services import (
    AccountServiceDep,
    TransactionServiceDep,
    TransferServiceDep,
)
from app.modules.accounts.controller import AccountController
from app.modules.transactions.controller import TransactionController
from app.modules.transfers.controller import TransferController


def get_account_controller(account_service: AccountServiceDep) -> AccountController:
    """Provide an account controller backed by the request's account service."""
    return AccountController(account_service)


AccountControllerDep = Annotated[AccountController, Depends(get_account_controller)]


def get_transaction_controller(
    transaction_service: TransactionServiceDep,
) -> TransactionController:
    """Provide a transaction controller backed by the request's transaction service."""
    return TransactionController(transaction_service)


TransactionControllerDep = Annotated[
    TransactionController, Depends(get_transaction_controller)
]


def get_transfer_controller(
    transfer_service: TransferServiceDep,
) -> TransferController:
    """Provide a transfer controller backed by the request's transfer service."""
    return TransferController(transfer_service)


TransferControllerDep = Annotated[TransferController, Depends(get_transfer_controller)]
