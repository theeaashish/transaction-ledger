# Transaction Ledger API

A modular, high-reliability FastAPI backend for transaction ledgers with atomic operations, UUIDv7 identifiers, deterministic timestamps, and consistent error handling.

---

## 1. Project Structure

```text
ledger-api/
├── alembic/                      # Database migration scripts and environment
│   ├── env.py                    # Alembic environment configured with Base metadata
│   ├── script.py.mako            # Migration template
│   └── versions/                 # Individual migration revisions
├── app/
│   ├── api/
│   │   ├── router.py             # Root API router (mounts /api/v1)
│   │   └── v1/
│   │       └── health.py         # Service liveness check (/api/v1/health)
│   ├── core/
│   │   ├── config.py             # Pydantic Settings & environment variables
│   │   ├── exceptions.py         # Standardized exception classes and handlers
│   │   └── logging.py            # Centralized logging configuration
│   ├── db/
│   │   ├── base.py               # Base DeclarativeBase, UUIDMixin, TimestampMixin, Mixin
│   │   ├── database.py           # Engine, SessionLocal, get_db, managed_session
│   │   └── models/               # SQLAlchemy model definitions (for Alembic discovery)
│   ├── dependencies/
│   │   └── db.py                 # FastAPI dependency injection helpers (DBSession)
│   ├── repositories/
│   │   └── base.py               # Generic BaseRepository[ModelT]
│   └── main.py                   # FastAPI application entrypoint and lifespan manager
├── tests/
│   ├── conftest.py               # In-memory SQLite engine and TestClient fixtures
│   ├── test_db_base.py           # Tests for UUIDv7 and Timestamp mixins & BaseRepository
│   ├── test_exceptions.py        # Tests for error envelopes and exception handlers
│   └── test_health.py            # Tests for health and root endpoints
├── .env.example                  # Environment variable template
├── Makefile                      # Standard CLI automation tasks
├── pyproject.toml                # Project metadata, dependencies, Ruff & BasedPyright config
└── README.md                     # Project documentation
```

---

## 2. Key Architectural Components

### 2.1 Database Mixins & Base (`app/db/base.py`)
- **`Base`**: Uses standard naming conventions for primary keys, foreign keys, unique constraints, check constraints, and indexes.
- **`UUIDMixin`**: Automatically assigns primary keys using Python 3.14's native `uuid.uuid7()` (time-ordered, index-friendly UUIDv7).
- **`TimestampMixin`**: Provides timezone-aware `created_at` and `updated_at` timestamps using database-level `func.now()`.
- **`Mixin`**: Composite mixin combining `UUIDMixin` and `TimestampMixin`.

### 2.2 Database Engine & Session Management (`app/db/database.py`)
- **`engine`**: SQLAlchemy synchronous engine with connection pre-ping.
- **`SessionLocal`**: Session factory with `expire_on_commit=False` and `autoflush=False`.
- **`managed_session()`**: Context manager with deterministic rollback on exceptions.
- **`get_db()`**: FastAPI generator dependency providing request-scoped sessions.

### 2.3 Exception Handling & Standard Error Envelope (`app/core/exceptions.py`)
Standardized JSON error envelope:
```json
{
  "error": {
    "code": "INSUFFICIENT_BALANCE",
    "message": "The account has insufficient funds for this debit.",
    "details": null
  }
}
```
Pre-configured exceptions:
- `AppException` (base)
- `ValidationException` (422)
- `AuthenticationException` / `UnauthorizedException` (401)
- `ForbiddenException` (403)
- `NotFoundException` / `AccountNotFoundException` (404)
- `ConflictException` / `DuplicateTransactionException` / `InsufficientBalanceException` (409)
- `DatabaseException` / `unhandled_exception_handler` (500)
- `RequestValidationError` and `StarletteHTTPException` handlers for consistent status code mapping.

### 2.4 Configuration & Logging (`app/core/config.py` & `app/core/logging.py`)
- Environment-driven configuration via `pydantic-settings` (`Settings`, `get_settings()`).
- Unified structured log formatting across application, Uvicorn, and SQLAlchemy.

---

## 3. Development Commands

Use `make` for common development workflows:

```bash
# Start development server with hot reload
make dev

# Run full code-quality verification (formatting, linting, typechecking)
make check

# Format code with Ruff
make format

# Run linter checks and fixes
make lint
make lintfix

# Run static type checks with BasedPyright
make typecheck

# Run test suite
make test

# Database migrations
make makemigrations m="migration description"
make migrate
make downgrade
```
