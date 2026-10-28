from uuid import UUID

from sqlalchemy import String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base, Mixin, TimestampMixin, UUIDMixin
from app.repositories.base import BaseRepository


class SampleLedgerAccount(Mixin, Base):
    """Test model for verifying Mixin (UUIDv7 + CreatedAt) behavior."""

    __tablename__ = "sample_ledger_accounts"

    name: Mapped[str] = mapped_column(String(100), nullable=False)


class SampleMutableEntity(UUIDMixin, TimestampMixin, Base):
    """Test model for verifying TimestampMixin (CreatedAt + UpdatedAt) behavior."""

    __tablename__ = "sample_mutable_entities"

    title: Mapped[str] = mapped_column(String(100), nullable=False)


def test_uuid_and_created_at_mixin(db_session: Session) -> None:
    """Verify that Mixin automatically generates UUIDv7 and created_at."""
    Base.metadata.create_all(db_session.connection())

    account = SampleLedgerAccount(name="Treasury")
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    # Validate UUIDv7
    assert isinstance(account.id, UUID)
    assert account.id.version == 7

    # Validate created_at
    assert account.created_at is not None
    assert account.name == "Treasury"
    # Ensure updated_at is NOT present on immutable ledger model
    assert not hasattr(account, "updated_at")


def test_timestamp_mixin_has_both_timestamps(db_session: Session) -> None:
    """Verify that TimestampMixin provides both created_at and updated_at."""
    Base.metadata.create_all(db_session.connection())

    entity = SampleMutableEntity(title="Mutable Config")
    db_session.add(entity)
    db_session.commit()
    db_session.refresh(entity)

    assert entity.created_at is not None
    assert entity.updated_at is not None


def test_base_repository_operations(db_session: Session) -> None:
    """Verify BaseRepository CRUD operations without generic deletion."""
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

    # Ensure delete method is deliberately not present on BaseRepository
    assert not hasattr(repo, "delete")
