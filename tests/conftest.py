import os
import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.database import get_db
from app.main import app


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    """Provide an in-memory SQLite database engine for testing."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_custom_functions(
        dbapi_connection: sqlite3.Connection, connection_record: object
    ) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.close()
        dbapi_connection.create_function(
            "btrim", 1, lambda s: s.strip() if s is not None else None
        )

    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """Provide a database session bound to the test engine."""
    with Session(db_engine, autoflush=False, expire_on_commit=False) as session:
        yield session


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    """Use an explicitly configured, migrated PostgreSQL test database."""
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated PostgreSQL test database")

    engine = create_engine(database_url, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL")
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def pg_session(pg_engine: Engine) -> Iterator[Session]:
    """Contain service commits in savepoints and always roll back test data."""
    with pg_engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(
                bind=connection,
                autoflush=False,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as session:
                yield session
        finally:
            transaction.rollback()


@pytest.fixture
def pg_client(
    pg_session: Session, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Exercise the real dependency chain against isolated PostgreSQL data."""

    def override_db() -> Iterator[Session]:
        yield pg_session

    monkeypatch.setattr(app, "debug", False)
    monkeypatch.setitem(app.dependency_overrides, get_db, override_db)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def client(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Provide a FastAPI TestClient with the database dependency overridden."""

    def override_db() -> Iterator[Session]:
        yield db_session

    monkeypatch.setattr(app, "debug", False)
    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()
