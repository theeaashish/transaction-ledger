from sqlalchemy.orm import Session

from app.db.models.account import Account
from app.repositories.base import BaseRepository


class AccountRepository(BaseRepository[Account]):
    """Persist accounts using the caller's database session and transaction."""

    def __init__(self, db: Session) -> None:
        super().__init__(Account, db)
