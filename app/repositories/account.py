from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.account import Account
from app.repositories.base import BaseRepository


class AccountRepository(BaseRepository[Account]):
    """Persist accounts using the caller's database session and transaction."""

    def __init__(self, db: Session) -> None:
        super().__init__(Account, db)

    def get_by_id_for_update(self, account_id: UUID) -> Account | None:
        """Fetch and lock an account by primary key using SELECT ... FOR UPDATE."""
        statement = select(Account).where(Account.id == account_id).with_for_update()
        return self.db.scalar(statement)
