from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.transaction import Transaction
from app.repositories.base import BaseRepository


class TransactionRepository(BaseRepository[Transaction]):
    """Persist and query ledger transactions using the caller's session."""

    def __init__(self, db: Session) -> None:
        super().__init__(Transaction, db)

    def get_by_account_and_reference(
        self, account_id: UUID, reference_id: str
    ) -> Transaction | None:
        """Find an existing transaction by its account ID and unique reference ID."""
        statement = select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.reference_id == reference_id,
        )
        return self.db.scalar(statement)

    def get_history(
        self,
        account_id: UUID,
        *,
        transaction_type: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Sequence[Transaction]:
        """Fetch account transactions ordered by created_at DESC, id DESC."""
        statement = select(Transaction).where(Transaction.account_id == account_id)
        if transaction_type is not None:
            statement = statement.where(Transaction.type == transaction_type)
        statement = (
            statement.order_by(Transaction.created_at.desc(), Transaction.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return self.db.scalars(statement).all()

    def count_by_account(
        self,
        account_id: UUID,
        *,
        transaction_type: str | None = None,
    ) -> int:
        """Count transactions matching the account and optional transaction type."""
        statement = (
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.account_id == account_id)
        )
        if transaction_type is not None:
            statement = statement.where(Transaction.type == transaction_type)
        return self.db.scalar(statement) or 0
