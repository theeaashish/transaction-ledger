from uuid import UUID

from sqlalchemy import String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base, Mixin
from app.repositories.base import BaseRepository


class SampleLedgerAccount(Mixin, Base):
    """Test model for verifying Mixin and Base behavior."""

    __tablename__ = "sample_ledger_accounts"

    name: Mapped[str] = mapped_column(String(100), nullable=False)


def test_uuid_and_timestamp_mixin(db_session: Session) -> None:
    """Verify that Mixin automatically generates UUIDv7 and timestamp fields."""
    # Ensure test table exists
    Base.metadata.create_all(db_session.connection())

    account = SampleLedgerAccount(name="Treasury")
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    # Validate UUID
    assert isinstance(account.id, UUID)
    assert account.id.version == 7

    # Validate timestamps
    assert account.created_at is not None
    assert account.updated_at is not None
    assert account.name == "Treasury"


def test_base_repository_operations(db_session: Session) -> None:
    """Verify BaseRepository CRUD operations."""
    Base.metadata.create_all(db_session.connection())
    repo = BaseRepository(SampleLedgerAccount, db_session)

    # Test count initially
    initial_count = repo.count()

    # Test add
    account = SampleLedgerAccount(name="Operations Account")
    created = repo.add(account)
    db_session.commit()

    assert created.id is not None
    assert repo.count() == initial_count + 1

    # Test get_by_id
    found = repo.get_by_id(created.id)
    assert found is not None
    assert found.name == "Operations Account"

    # Test get_all
    all_accounts = repo.get_all()
    assert len(all_accounts) >= 1

    # Test delete
    repo.delete(created)
    db_session.commit()
    assert repo.get_by_id(created.id) is None
