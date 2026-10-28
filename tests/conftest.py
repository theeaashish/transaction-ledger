import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.core.config import settings
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


@pytest.fixture
def pg_session() -> Iterator[Session]:
    """Provide an isolated session against PostgreSQL that always rolls back."""
    engine = create_engine(settings.database_url)
    with Session(engine, autoflush=False, expire_on_commit=False) as session:
        try:
            yield session
        finally:
            session.rollback()


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
