from fastapi import APIRouter, status

from app.dependencies.controllers import TransferControllerDep
from app.modules.transfers.constants import TRANSFER_RESPONSES
from app.modules.transfers.schemas import TransferCreate, TransferResponse

router = APIRouter(prefix="/transfers", tags=["Transfers"])


@router.post(
    "",
    response_model=TransferResponse,
    status_code=status.HTTP_201_CREATED,
    responses=TRANSFER_RESPONSES,
)
def create_transfer(
    payload: TransferCreate,
    transfer_controller: TransferControllerDep,
) -> TransferResponse:
    """Transfer funds atomically between two distinct accounts."""
    return transfer_controller.transfer(payload)
