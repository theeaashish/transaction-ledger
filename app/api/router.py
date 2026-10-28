from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.modules.accounts.router import router as account_router
from app.modules.transactions.router import router as transaction_router
from app.modules.transfers.router import router as transfer_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(account_router)
api_router.include_router(transaction_router)
api_router.include_router(transfer_router)
