from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Account
from app.main import app
from app.modules.accounts.controller import AccountController
from app.modules.accounts.schemas import (
    AccountBalanceResponse,
    AccountCreate,
    AccountResponse,
)
from app.repositories.account import AccountRepository

ACCOUNTS_URL = "/api/v1/accounts"


@pytest.mark.parametrize("name", ["Aashish", "  Aashish\t\n", "अ" * 255])
def test_create_account(pg_client: TestClient, pg_session: Session, name: str) -> None:
    """Creation persists normalized names, zero money, UUIDv7, and aware time."""
    response = pg_client.post(ACCOUNTS_URL, json={"name": name})

    assert response.status_code == 201
    data = response.json()
    assert set(data) == {"id", "name", "balance", "created_at"}
    account_id = UUID(data["id"])
    assert account_id.version == 7
    assert data["name"] == name.strip()
    assert data["balance"] == "0.00"
    created_at = datetime.fromisoformat(data["created_at"])
    assert created_at.tzinfo is not None
    assert created_at.utcoffset() is not None

    persisted = pg_session.get(Account, account_id)
    assert persisted is not None
    assert persisted.name == name.strip()
    assert persisted.balance == Decimal("0.00")
    assert persisted.created_at == created_at


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({}, "name"),
        ({"name": ""}, "name"),
        ({"name": "   "}, "name"),
        ({"name": "\t\r\n"}, "name"),
        ({"name": "A" * 256}, "name"),
        ({"name": None}, "name"),
        ({"name": 123}, "name"),
        ({"name": "Aashish", "balance": "500.00"}, "balance"),
        ({"name": "Aashish", "id": str(uuid7())}, "id"),
        (
            {"name": "Aashish", "created_at": "2026-10-28T09:00:00Z"},
            "created_at",
        ),
        ({"name": "Aashish", "nickname": "Ash"}, "nickname"),
    ],
    ids=[
        "missing-name",
        "empty-name",
        "blank-name",
        "whitespace-name",
        "name-too-long",
        "null-name",
        "non-string-name",
        "client-balance",
        "client-id",
        "client-timestamp",
        "unknown-field",
    ],
)
def test_invalid_account_creation(
    client: TestClient,
    db_session: Session,
    payload: dict[str, object],
    field: str,
) -> None:
    """Invalid input uses the existing validation envelope and writes nothing."""
    response = client.post(ACCOUNTS_URL, json=payload)

    assert response.status_code == 422
    data = response.json()
    assert set(data) == {"error"}
    error = data["error"]
    assert set(error) == {"code", "message", "details"}
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "Request validation failed"
    assert any(detail["loc"] == ["body", field] for detail in error["details"])
    assert db_session.scalar(select(func.count()).select_from(Account)) == 0


def test_accounts_can_share_a_name(pg_client: TestClient) -> None:
    first = pg_client.post(ACCOUNTS_URL, json={"name": "Aashish"})
    second = pg_client.post(ACCOUNTS_URL, json={"name": "Aashish"})

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["balance"] == second.json()["balance"] == "0.00"


def test_get_created_account_balance(pg_client: TestClient) -> None:
    created = pg_client.post(ACCOUNTS_URL, json={"name": "Aashish"})
    assert created.status_code == 201
    account_id = created.json()["id"]

    response = pg_client.get(f"{ACCOUNTS_URL}/{account_id}/balance")

    assert response.status_code == 200
    assert response.json() == {"account_id": account_id, "balance": "0.00"}


@pytest.mark.parametrize(
    "balance",
    ["0.00", "125.50", "10.10", "9999999999999999.99"],
)
def test_get_balance_preserves_decimal_precision(
    pg_client: TestClient, pg_session: Session, balance: str
) -> None:
    """Existing NUMERIC balances retain all digits and expose no account details."""
    account = Account(name="Existing account", balance=Decimal(balance))
    pg_session.add(account)
    pg_session.flush()

    response = pg_client.get(f"{ACCOUNTS_URL}/{account.id}/balance")

    assert response.status_code == 200
    assert response.json() == {"account_id": str(account.id), "balance": balance}


def test_account_not_found(client: TestClient) -> None:
    response = client.get(f"{ACCOUNTS_URL}/{uuid7()}/balance")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "ACCOUNT_NOT_FOUND",
            "message": "Account not found",
            "details": None,
        }
    }


@pytest.mark.parametrize("account_id", ["not-a-uuid", "1234"])
def test_malformed_account_id(client: TestClient, account_id: str) -> None:
    response = client.get(f"{ACCOUNTS_URL}/{account_id}/balance")

    assert response.status_code == 422
    error = response.json()["error"]
    assert set(error) == {"code", "message", "details"}
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "Request validation failed"
    assert error["details"][0]["loc"] == ["path", "account_id"]


def test_response_schemas_keep_decimal_internally() -> None:
    account = Account(
        id=uuid7(),
        name="Aashish",
        balance=Decimal("125.5"),
        created_at=datetime.now(UTC),
    )
    response = AccountResponse.model_validate(account)
    balance_response = AccountBalanceResponse(
        account_id=account.id, balance=account.balance
    )

    for schema in (response, balance_response):
        assert schema.balance == Decimal("125.5")
        assert isinstance(schema.model_dump()["balance"], Decimal)
        assert schema.model_dump(mode="json")["balance"] == "125.50"
    assert response.created_at.tzinfo is not None


def test_dependency_chain_shares_the_existing_db_session(
    pg_client: TestClient, pg_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FastAPI caches get_db across both the repository and service factories."""
    requested_sessions: list[Session] = []
    observed_sessions: list[tuple[Session, Session]] = []
    original_create = AccountController.create_account

    def override_db() -> Iterator[Session]:
        requested_sessions.append(pg_session)
        yield pg_session

    def capture_sessions(
        controller: AccountController, payload: AccountCreate
    ) -> AccountResponse:
        service = controller.account_service
        observed_sessions.append((service.db, service.account_repository.db))
        return original_create(controller, payload)

    monkeypatch.setitem(app.dependency_overrides, get_db, override_db)
    monkeypatch.setattr(AccountController, "create_account", capture_sessions)

    response = pg_client.post(ACCOUNTS_URL, json={"name": "Shared session"})

    assert response.status_code == 201
    assert requested_sessions == [pg_session]
    assert observed_sessions == [(pg_session, pg_session)]


def test_creation_commits_the_service_transaction(
    pg_client: TestClient, pg_session: Session
) -> None:
    response = pg_client.post(ACCOUNTS_URL, json={"name": "Committed account"})

    assert response.status_code == 201
    assert not pg_session.in_transaction()
    # A rollback after the service commit cannot undo the completed operation.
    # The fixture's outer transaction still contains it for safe test cleanup.
    pg_session.rollback()
    persisted = pg_session.get(Account, UUID(response.json()["id"]))
    assert persisted is not None
    assert persisted.name == "Committed account"


def test_creation_uses_an_already_active_transaction(
    pg_client: TestClient, pg_session: Session
) -> None:
    pg_session.execute(select(Account.id).limit(1))
    assert pg_session.in_transaction()

    response = pg_client.post(ACCOUNTS_URL, json={"name": "Active transaction"})

    assert response.status_code == 201
    assert not pg_session.in_transaction()
    assert pg_session.get(Account, UUID(response.json()["id"])) is not None


def test_repository_flushes_without_committing(pg_session: Session) -> None:
    repository = AccountRepository(pg_session)
    account = repository.add(Account(name="Repository-only account"))
    account_id = account.id

    assert account_id.version == 7
    assert account.created_at.utcoffset() is not None
    assert repository.get_by_id(account_id) is account
    assert pg_session.in_transaction()

    pg_session.rollback()

    assert repository.get_by_id(account_id) is None


def test_flush_failure_rolls_back_and_returns_safe_error(
    pg_client: TestClient, pg_session: Session
) -> None:
    """A real database constraint failure rolls back all pending account writes."""
    pg_session.add(Account(name="Pending valid account"))
    pg_session.add(Account(name=""))

    response = pg_client.post(ACCOUNTS_URL, json={"name": "Failed account"})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "Internal server error",
            "details": None,
        }
    }
    assert pg_session.is_active
    assert not pg_session.in_transaction()
    assert (
        pg_session.scalar(
            select(func.count())
            .select_from(Account)
            .where(Account.name.in_(["Pending valid account", "", "Failed account"]))
        )
        == 0
    )

    recovered = pg_client.post(ACCOUNTS_URL, json={"name": "Recovered account"})
    assert recovered.status_code == 201


def test_commit_failure_rolls_back_flushed_account(
    pg_client: TestClient, pg_session: Session
) -> None:
    """A failure after INSERT but before commit leaves no persisted account."""

    def fail_commit(session: Session) -> None:
        session.execute(text("SELECT 1 / 0"))

    event.listen(pg_session, "before_commit", fail_commit, once=True)

    response = pg_client.post(ACCOUNTS_URL, json={"name": "Failed commit account"})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "Internal server error",
            "details": None,
        }
    }
    assert pg_session.is_active
    assert not pg_session.in_transaction()
    assert (
        pg_session.scalar(
            select(func.count())
            .select_from(Account)
            .where(Account.name == "Failed commit account")
        )
        == 0
    )


def test_account_openapi_contract(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    document = response.json()
    paths = document["paths"]
    assert {
        path for path in paths if "/accounts" in path and "transactions" not in path
    } == {
        ACCOUNTS_URL,
        f"{ACCOUNTS_URL}/{{account_id}}/balance",
    }
    assert set(paths[ACCOUNTS_URL]) == {"post"}
    balance_path = paths[f"{ACCOUNTS_URL}/{{account_id}}/balance"]
    assert set(balance_path) == {"get"}
    create = paths[ACCOUNTS_URL]["post"]
    get_balance = balance_path["get"]
    assert create["tags"] == get_balance["tags"] == ["Accounts"]
    assert create["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccountCreate"
    }
    assert create["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccountResponse"
    }
    assert get_balance["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccountBalanceResponse"
    }
    assert {"201", "422", "500"} <= set(create["responses"])
    assert {"200", "404", "422", "500"} <= set(get_balance["responses"])
    assert get_balance["parameters"][0]["schema"]["format"] == "uuid"
    assert get_balance["parameters"][0]["required"] is True

    schemas = document["components"]["schemas"]
    request = schemas["AccountCreate"]
    assert set(request["properties"]) == {"name"}
    assert request["required"] == ["name"]
    assert request["additionalProperties"] is False
    assert request["properties"]["name"]["minLength"] == 1
    assert request["properties"]["name"]["maxLength"] == 255
    for schema_name in ("AccountResponse", "AccountBalanceResponse"):
        money = schemas[schema_name]["properties"]["balance"]
        assert money["type"] == "string"
        assert money["pattern"] == r"^\d+\.\d{2}$"
        assert money["examples"] == ["0.00", "125.50"]
    assert set(schemas["AccountBalanceResponse"]["properties"]) == {
        "account_id",
        "balance",
    }
    assert schemas["AccountResponse"]["properties"]["created_at"]["format"] == (
        "date-time"
    )
