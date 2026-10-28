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
│   │   ├── router.py             # API router aggregation (prefix applied in main.py)
│   │   └── v1/
│   │       └── health.py         # Service liveness check (/api/v1/health)
│   ├── core/
│   │   ├── config.py             # Pydantic Settings & environment variables
│   │   ├── exceptions.py         # Standardized exception classes and handlers
│   │   ├── logging.py            # Centralized logging configuration
│   │   └── types.py              # Shared Money serialization and type definitions
│   ├── db/
│   │   ├── base.py               # Base DeclarativeBase, UUIDMixin, TimestampMixin, Mixin
│   │   ├── database.py           # Engine, SessionLocal, get_db, managed_session
│   │   ├── errors.py             # Database error inspection and constraint helpers
│   │   └── models/               # SQLAlchemy model definitions (for Alembic discovery)
│   ├── dependencies/
│   │   ├── db.py                 # Request-scoped synchronous DBSession
│   │   ├── repositories.py       # Central repository dependency factories
│   │   ├── services.py           # Central service dependency factories
│   │   └── controllers.py        # Central controller dependency factories
│   ├── modules/
│   │   ├── accounts/             # Account router, controller, service, and schemas
│   │   ├── transactions/         # Transaction router, controller, service, and schemas
│   │   └── transfers/            # Money transfer router, controller, service, and schemas
│   ├── repositories/
│   │   ├── base.py               # Generic BaseRepository[ModelT]
│   │   ├── account.py            # Account persistence using BaseRepository[Account]
│   │   └── transaction.py        # Transaction persistence using BaseRepository[Transaction]
│   └── main.py                   # FastAPI application entrypoint and lifespan manager
├── tests/
│   ├── conftest.py               # SQLite and isolated PostgreSQL/TestClient fixtures
│   ├── test_accounts.py          # Account API, validation, DI, and transaction tests
│   ├── test_db_base.py           # Tests for UUIDv7 and Timestamp mixins & BaseRepository
│   ├── test_exceptions.py        # Tests for error envelopes and exception handlers
│   ├── test_health.py            # Tests for health and root endpoints
│   ├── test_models.py            # Database model constraint and relationship tests
│   ├── test_transaction_concurrency.py # Concurrent debit and duplicate reference tests
│   ├── test_transactions.py      # Transaction API, validation, atomicity, and history tests
│   ├── test_transfer_concurrency.py    # Deadlock prevention, duplicate transfer, overdraft tests
│   ├── test_transfers.py         # Money transfer API, validation, atomicity, and DI tests
│   └── test_trigger.py           # PostgreSQL immutability trigger tests
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
- **`CreatedAtMixin`**: Provides a timezone-aware `created_at` timestamp with database-level default (`func.now()`). Designed for immutable ledger records.
- **`UpdatedAtMixin`**: Provides a timezone-aware `updated_at` timestamp with `onupdate=func.now()`.
- **`TimestampMixin`**: Composite mixin combining `CreatedAtMixin` and `UpdatedAtMixin`.
- **`Mixin`**: Composite convenience mixin combining `UUIDMixin` and `CreatedAtMixin` for ledger models.

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

### 2.5 Generic Base Repository (`app/repositories/base.py`)
- **`BaseRepository[ModelT]`**: Generic persistence helper providing `get_by_id`, `get_all`, `add`, and `count`. Generic deletion is deliberately omitted to safeguard against accidental financial record deletion.

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

---

## 4. Account API

Account dependencies are constructed centrally in `app/dependencies/`:
`get_db` / `DBSession` → `AccountRepository` → `AccountService` → `AccountController` → route.
The repository and service share the same request-scoped synchronous session. The repository flushes pending writes; the service commits account creation and rolls back on failure.

### Create an account

`POST /api/v1/accounts` accepts only the account holder's name:

```json
{
  "name": "Aashish"
}
```

Successful response: **201 Created**.

```json
{
  "id": "019aa695-6280-7000-8000-000000000001",
  "name": "Aashish",
  "balance": "0.00",
  "created_at": "2026-10-28T09:00:00Z"
}
```

The ID and timestamp are illustrative. The existing model mixin generates UUIDv7 identifiers, PostgreSQL generates the timezone-aware `created_at`, and every new account starts with a zero balance. Names are trimmed, required, non-blank, and limited to 255 characters. Duplicate account names are allowed. Unknown request fields, including `balance`, `id`, and `created_at`, are rejected.

### Retrieve an account balance

`GET /api/v1/accounts/{account_id}/balance` accepts a UUID path parameter.

Successful response: **200 OK**.

```json
{
  "account_id": "019aa695-6280-7000-8000-000000000001",
  "balance": "0.00"
}
```

Balances use Python `Decimal` and PostgreSQL `NUMERIC(18, 2)`. JSON always represents money as a **string with exactly two fractional digits**, such as `"0.00"` or `"125.50"`; no conversion to floating point is performed.

Invalid creation requests and malformed UUIDs return **422** with code `VALIDATION_ERROR`. An absent account returns **404** with code `ACCOUNT_NOT_FOUND`. Unexpected failures return **500** with code `INTERNAL_SERVER_ERROR` and omit database details. All errors use the existing envelope:

```json
{
  "error": {
    "code": "ACCOUNT_NOT_FOUND",
    "message": "Account not found",
    "details": null
  }
}
```

Validation errors include field details in `error.details`. Both endpoints, request validation, response schemas, monetary string formats, and status codes are documented in FastAPI's `/docs` and `/openapi.json`.

Authentication and authorization are outside the scope of this assessment.

---

## 5. Transaction API

Transaction dependencies are injected centrally via `app/dependencies/`:
`get_db` / `DBSession` → `AccountRepository` + `TransactionRepository` → `TransactionService` → `TransactionController` → router.
All layers share the identical request-scoped synchronous SQLAlchemy `Session`.

### 5.1 Create a transaction

`POST /api/v1/accounts/{account_id}/transactions` creates an immutable transaction record and updates the account balance within a single atomic database transaction.

Example request body:

```json
{
  "type": "credit",
  "amount": "100.00",
  "description": "Initial deposit",
  "reference_id": "REF-2026-001"
}
```

Successful response: **201 Created**.

```json
{
  "id": "019aa695-6280-7000-8000-000000000010",
  "account_id": "019aa695-6280-7000-8000-000000000001",
  "type": "credit",
  "amount": "100.00",
  "description": "Initial deposit",
  "reference_id": "REF-2026-001",
  "balance_after": "100.00",
  "created_at": "2026-10-28T09:15:00Z"
}
```

#### Business Rules & Invariants
- **Credit**: Computes `new_balance = current_balance + amount`, updates the account balance, and inserts the transaction record.
- **Debit**: Verifies that `current_balance >= amount`. If funds are insufficient, rejects the operation with **409 Conflict** and error code `INSUFFICIENT_BALANCE`. If sufficient, computes `new_balance = current_balance - amount`.
- **Atomicity & Row Locking**: The account row is locked exclusively using `SELECT ... FOR UPDATE` before balance evaluation and modification. The balance update and transaction insert occur in the same database transaction. If any failure occurs, all writes roll back.
- **Resulting Balance**: The response field `balance_after` is computed and returned while holding the lock; it is never persisted as a column on the `transactions` table.
- **Idempotency**: Submitting a duplicate `reference_id` on the same account returns **409 Conflict** with error code `DUPLICATE_TRANSACTION`. Duplicate detection is enforced both application-side and via PostgreSQL's `UNIQUE (account_id, reference_id)` constraint (`uq_account_reference_id`). The same reference ID is permitted across different accounts.
- **Monetary Format**: Monetary amounts (`amount`, `balance_after`) are exact `Decimal` values serialized in JSON as **strings with exactly two fractional digits** (e.g. `"100.00"`, `"0.00"`). Amounts exceeding two decimal places (e.g. `"100.001"`) are rejected with **422 Unprocessable Entity**.

### 5.2 Retrieve transaction history

`GET /api/v1/accounts/{account_id}/transactions` retrieves paginated transactions for an existing account, sorted newest first.

Query parameters:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `type` | string | `None` | Optional filter: `credit` or `debit` |
| `page` | integer | `1` | 1-based page number (minimum 1) |
| `limit` | integer | `10` | Maximum items per page (1 to 100) |

Example:

`GET /api/v1/accounts/{account_id}/transactions?type=credit&page=1&limit=10`

Successful response: **200 OK**.

```json
{
  "account_id": "019aa695-6280-7000-8000-000000000001",
  "current_page": 1,
  "page_size": 10,
  "total_records": 1,
  "total_pages": 1,
  "transactions": [
    {
      "id": "019aa695-6280-7000-8000-000000000010",
      "account_id": "019aa695-6280-7000-8000-000000000001",
      "type": "credit",
      "amount": "100.00",
      "description": "Initial deposit",
      "reference_id": "REF-2026-001",
      "created_at": "2026-10-28T09:15:00Z"
    }
  ]
}
```

#### History Characteristics
- **Account Verification**: Verifies the account exists before querying history; returns **404** with `ACCOUNT_NOT_FOUND` if absent. History queries are read-only and do not acquire row locks.
- **Deterministic Ordering**: Ordered deterministically by `created_at DESC, id DESC`, utilizing the existing `ix_transactions_account_history` index.
- **Pagination**: `total_pages` is computed as `ceil(total_records / limit)` (or `0` when `total_records == 0`). Valid pages requested beyond `total_pages` return `transactions: []` with accurate pagination metadata.
- **Filter Consistency**: Identical filters are applied to both count and records queries.

### 5.3 Error Envelopes & Status Codes

All errors use the standardized JSON envelope:

```json
{
  "error": {
    "code": "DUPLICATE_TRANSACTION",
    "message": "Duplicate transaction reference.",
    "details": null
  }
}
```

| HTTP Status | Error Code | Trigger Condition |
|---|---|---|
| `201 Created` | — | Transaction created and committed |
| `200 OK` | — | Transaction history successfully retrieved |
| `404 Not Found` | `ACCOUNT_NOT_FOUND` | Account does not exist |
| `409 Conflict` | `DUPLICATE_TRANSACTION` | `reference_id` already exists for this account |
| `409 Conflict` | `INSUFFICIENT_BALANCE` | Debit amount exceeds account balance |
| `422 Unprocessable Entity` | `VALIDATION_ERROR` | Invalid type, zero/negative amount, >2 decimal places, missing/blank fields, unknown fields, invalid UUID, or invalid page/limit |
| `500 Internal Server Error` | `INTERNAL_SERVER_ERROR` | Unexpected database or runtime failure (safe envelope, details suppressed) |

---

## 6. Money Transfer API

Transfer dependencies are wired centrally in `app/dependencies/`:
`get_db` / `DBSession` → `AccountRepository` + `TransactionRepository` → `TransferService` → `TransferController` → router.
All layers share the identical request-scoped synchronous SQLAlchemy `Session`.

### 6.1 Create a transfer

`POST /api/v1/transfers` atomically transfers funds between two distinct accounts using double-entry bookkeeping (a debit record on the source account and a credit record on the destination account).

Example request body:

```json
{
  "source_account_id": "019aa695-6280-7000-8000-000000000001",
  "destination_account_id": "019aa695-6280-7000-8000-000000000002",
  "amount": "50.00",
  "description": "Invoice payment",
  "reference_id": "TRF-2026-001"
}
```

Successful response: **201 Created**.

```json
{
  "reference_id": "TRF-2026-001",
  "amount": "50.00",
  "source_account": {
    "account_id": "019aa695-6280-7000-8000-000000000001",
    "balance": "50.00"
  },
  "destination_account": {
    "account_id": "019aa695-6280-7000-8000-000000000002",
    "balance": "100.00"
  },
  "debit_transaction_id": "019aa695-6280-7000-8000-000000000021",
  "credit_transaction_id": "019aa695-6280-7000-8000-000000000022",
  "created_at": "2026-10-28T09:30:00Z"
}
```

#### Transfer Business Rules & Invariants
- **Double-Entry Ledger Creation**: Creates exactly two entries in the existing `transactions` table:
  1. A `debit` entry on the source account with the specified `amount`, `reference_id`, and `description`.
  2. A `credit` entry on the destination account with the identical `amount`, `reference_id`, and `description`.
- **Atomicity**: Both account balance updates and both ledger transaction inserts are committed together in a single database transaction. If any error occurs (insufficient funds, constraint violation, connection disruption), all mutations roll back completely.
- **Deadlock Prevention via Deterministic Lock Ordering**: Both participating accounts are locked using `SELECT ... FOR UPDATE` via `AccountRepository.get_by_id_for_update()`. To prevent deadlocks when concurrent transfers occur in opposite directions (e.g. Account A → Account B and Account B → Account A simultaneously), lock acquisition is strictly sorted by account UUID (`sorted([source_id, dest_id])`).
- **Idempotency**: Submitting a transfer with a `reference_id` that already exists on either the source or destination account returns **409 Conflict** with error code `DUPLICATE_TRANSACTION`. Duplicate detection checks application-level records and safely traps PostgreSQL's `uq_account_reference_id` unique constraint. The same reference ID remains valid across unrelated account pairs.
- **Overdraft Prevention**: Checks that `source_account.balance >= amount`. If insufficient, returns **409 Conflict** with error code `INSUFFICIENT_BALANCE`. Balances are guaranteed never to go negative.
- **Self-Transfer Prevention**: Self-transfers (`source_account_id == destination_account_id`) are rejected at the schema level with **422 Unprocessable Entity** (`VALIDATION_ERROR`).
- **Exact Decimal Arithmetic**: Balances and amounts use exact Python `Decimal` arithmetic and are formatted as strings with exactly 2 decimal places (`Money` type). Excessive decimal precision (e.g. `10.000` or `10.005`) is strictly rejected.
- **Immutability**: Both generated transactions are protected by PostgreSQL's immutability trigger (`trg_prevent_transaction_modification`), preventing updates and deletes.

### 6.2 Transfer Error Responses & Status Codes

| HTTP Status | Error Code | Trigger Condition |
|---|---|---|
| `201 Created` | — | Transfer executed and atomically committed |
| `404 Not Found` | `ACCOUNT_NOT_FOUND` | Source or destination account does not exist |
| `409 Conflict` | `DUPLICATE_TRANSACTION` | `reference_id` already exists for source or destination account |
| `409 Conflict` | `INSUFFICIENT_BALANCE` | Transfer amount exceeds source account balance |
| `422 Unprocessable Entity` | `VALIDATION_ERROR` | Self-transfer, zero/negative amount, >2 decimal places, missing/blank fields, or extra unknown fields |
| `500 Internal Server Error` | `INTERNAL_SERVER_ERROR` | Unexpected database or system error (database details suppressed) |

---

## 7. PostgreSQL Integration & Concurrency Tests

Use a dedicated test database with the existing Alembic migration applied. Set `TEST_DATABASE_URL` explicitly; PostgreSQL tests are skipped when it is unset, and never fall back to the application's `DATABASE_URL`.

```bash
# Create a dedicated ledger_test database before running these commands.
export TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/ledger_test"

# Apply the existing migration only to that test database.
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head

# Run SQLite tests and PostgreSQL integration tests.
make test
```

PostgreSQL fixtures open an outer transaction and use SQLAlchemy's `join_transaction_mode="create_savepoint"` so service commits and rollbacks remain contained. Teardown rolls back the outer transaction.

### Concurrency Test Scenarios
1. **Opposite-Direction Transfers (Deadlock Prevention)**: Simultaneous transfers between Account A and Account B in opposite directions (`A -> B` and `B -> A`) executed concurrently with barrier synchronization. Verified to avoid deadlocks due to deterministic UUID-ordered row locking, with complete conservation of total funds.
2. **Concurrent Duplicate Transfers (Idempotency Race)**: Identical transfer requests submitted in parallel across separate threads. Verified that exactly one transfer succeeds and the duplicate request is rejected with `409 DUPLICATE_TRANSACTION`.
3. **Concurrent Overdraft Race (Balance Exhaustion)**: Competing concurrent transfers from the same source account exceeding its total balance. Verified that exactly one debit succeeds, the competing transfer receives `409 INSUFFICIENT_BALANCE`, and the balance never becomes negative.
4. **Immutability Enforcement**: Direct `UPDATE` and `DELETE` queries on ledger transactions are verified to fail against PostgreSQL trigger `trg_prevent_transaction_modification`.
