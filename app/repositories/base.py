from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base


class BaseRepository[ModelT: Base]:
    """Generic base repository for SQLAlchemy models."""

    def __init__(self, model: type[ModelT], db: Session) -> None:
        self.model = model
        self.db = db

    def get_by_id(self, id: UUID) -> ModelT | None:
        """Fetch a model instance by primary key."""
        return self.db.get(self.model, id)

    def get_all(self, *, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        """Fetch all model instances with pagination."""
        statement = select(self.model).offset(offset).limit(limit)
        return self.db.scalars(statement).all()

    def add(self, instance: ModelT) -> ModelT:
        """Add an instance to the session and flush."""
        self.db.add(instance)
        self.db.flush()
        return instance

    def delete(self, instance: ModelT) -> None:
        """Delete an instance from the session and flush."""
        self.db.delete(instance)
        self.db.flush()

    def count(self) -> int:
        """Count total instances of the model."""
        statement = select(func.count()).select_from(self.model)
        return self.db.scalar(statement) or 0
