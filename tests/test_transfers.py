from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Account, Transaction
from app.main import app
from app.modules.transfers.schemas import TransferCreate
from app.modules.transfers.service import TransferService
from app.repositories.account import AccountRepository
from app.repositories.transaction import TransactionRepository

ACCOUNTS_URL = "/api/v1/accounts"
TRANSFERS_URL = "/api/v1/transfers"


def _create_account(
    client: TestClient, name: str = "Transfer User", initial_credit: str | None = None
) -> str:
    """Helper to create an account and optionally fund it."""
    res = client.post(ACCOUNTS_URL, json={"name": name})
    assert res.status_code == 201
    account_id = res.json()["id"]

    if initial_credit is not None:
        credit_res = client.post(
            f"{ACCOUNTS_URL}/{account_id}/transactions",
            json={
                "type": "credit",
                "amount": initial_credit,
                "description": "Initial funding",
                "reference_id": f"INIT-{account_id}",
            },
        )
        assert credit_res.status_code == 201

    return account_id


# ==============================================================================
# 1. SUCCESSFUL TRANSFERS
# ==============================================================================


def test_transfer_success(pg_client: TestClient, pg_session: Session) -> None:
    """Execute a valid transfer between two funded accounts and verify persistence."""
    source_id = _create_account(pg_client, "Source Alice", initial_credit="100.00")
    dest_id = _create_account(pg_client, "Dest Bob", initial_credit="50.00")

    transfer_payload = {
        "source_account_id": source_id,
        "destination_account_id": dest_id,
        "amount": "30.00",
        "description": "Dinner split",
        "reference_id": "TRF-SUCCESS-001",
    }

    res = pg_client.post(TRANSFERS_URL, json=transfer_payload)
    assert res.status_code == 201
    data = res.json()

    # Response payload assertions
    assert data["reference_id"] == "TRF-SUCCESS-001"
    assert data["amount"] == "30.00"
    assert data["source_account"]["account_id"] == source_id
    assert data["source_account"]["balance"] == "70.00"
    assert data["destination_account"]["account_id"] == dest_id
    assert data["destination_account"]["balance"] == "80.00"

    debit_tx_id = UUID(data["debit_transaction_id"])
    credit_tx_id = UUID(data["credit_transaction_id"])
    assert debit_tx_id != credit_tx_id
    assert debit_tx_id.version == 7
    assert credit_tx_id.version == 7

    created_at = datetime.fromisoformat(data["created_at"])
    assert created_at.tzinfo is not None

    # Database state assertions
    persisted_source = pg_session.get(Account, UUID(source_id))
    assert persisted_source is not None
    assert persisted_source.balance == Decimal("70.00")

    persisted_dest = pg_session.get(Account, UUID(dest_id))
    assert persisted_dest is not None
    assert persisted_dest.balance == Decimal("80.00")

    # Debit transaction entry
    debit_tx = pg_session.get(Transaction, debit_tx_id)
    assert debit_tx is not None
    assert debit_tx.account_id == UUID(source_id)
    assert debit_tx.type == "debit"
    assert debit_tx.amount == Decimal("30.00")
    assert debit_tx.reference_id == "TRF-SUCCESS-001"
    assert debit_tx.description == "Dinner split"

    # Credit transaction entry
    credit_tx = pg_session.get(Transaction, credit_tx_id)
    assert credit_tx is not None
    assert credit_tx.account_id == UUID(dest_id)
    assert credit_tx.type == "credit"
    assert credit_tx.amount == Decimal("30.00")
    assert credit_tx.reference_id == "TRF-SUCCESS-001"
    assert credit_tx.description == "Dinner split"


def test_transfer_exact_full_balance(
    pg_client: TestClient, pg_session: Session
) -> None:
    """Transfer the entire balance, leaving the source account at exactly zero."""
    source_id = _create_account(pg_client, "Empty Me", initial_credit="150.00")
    dest_id = _create_account(pg_client, "Fill Me", initial_credit="25.00")

    res = pg_client.post(
        TRANSFERS_URL,
        json={
            "source_account_id": source_id,
            "destination_account_id": dest_id,
            "amount": "150.00",
            "description": "Transfer all funds",
            "reference_id": "TRF-FULL-001",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["source_account"]["balance"] == "0.00"
    assert data["destination_account"]["balance"] == "175.00"

    persisted_source = pg_session.get(Account, UUID(source_id))
    assert persisted_source is not None
    assert persisted_source.balance == Decimal("0.00")


# ==============================================================================
# 2. VALIDATION & ERROR HANDLING
# ==============================================================================


def test_transfer_self_transfer_rejected(client: TestClient) -> None:
    """Reject transfer when source and destination accounts are the same."""
    account_id = str(uuid7())
    res = client.post(
        TRANSFERS_URL,
        json={
            "source_account_id": account_id,
            "destination_account_id": account_id,
            "amount": "10.00",
            "description": "Self transfer",
            "reference_id": "TRF-SELF-001",
        },
    )
    assert res.status_code == 422
    data = res.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "different" in str(data["error"]["details"]).lower()


def test_transfer_source_not_found(client: TestClient) -> None:
    """Return 404 when source account does not exist."""
    dest_id = _create_account(client, "Bob")
    missing_id = str(uuid7())

    res = client.post(
        TRANSFERS_URL,
        json={
            "source_account_id": missing_id,
            "destination_account_id": dest_id,
            "amount": "10.00",
            "description": "Payment",
            "reference_id": "TRF-NOTFOUND-01",
        },
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"


def test_transfer_destination_not_found(client: TestClient) -> None:
    """Return 404 when destination account does not exist."""
    source_id = _create_account(client, "Alice")
    missing_id = str(uuid7())

    res = client.post(
        TRANSFERS_URL,
        json={
            "source_account_id": source_id,
            "destination_account_id": missing_id,
            "amount": "10.00",
            "description": "Payment",
            "reference_id": "TRF-NOTFOUND-02",
        },
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"


def test_transfer_insufficient_balance(
    pg_client: TestClient, pg_session: Session
) -> None:
    """Reject transfer when source account does not have enough funds."""
    source_id = _create_account(pg_client, "Low Balance Alice", initial_credit="20.00")
    dest_id = _create_account(pg_client, "Dest Bob", initial_credit="10.00")

    res = pg_client.post(
        TRANSFERS_URL,
        json={
            "source_account_id": source_id,
            "destination_account_id": dest_id,
            "amount": "30.00",
            "description": "Too expensive",
            "reference_id": "TRF-INSUFFICIENT-01",
        },
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "INSUFFICIENT_BALANCE"

    # Verify no balance change
    persisted_source = pg_session.get(Account, UUID(source_id))
    persisted_dest = pg_session.get(Account, UUID(dest_id))
    assert persisted_source is not None and persisted_source.balance == Decimal("20.00")
    assert persisted_dest is not None and persisted_dest.balance == Decimal("10.00")

    # Verify no transactions created for this reference
    tx = pg_session.scalar(
        select(Transaction).where(Transaction.reference_id == "TRF-INSUFFICIENT-01")
    )
    assert tx is None


# ==============================================================================
# 3. IDEMPOTENCY & DUPLICATE REFERENCE HANDLING
# ==============================================================================


def test_transfer_duplicate_reference_rejected(
    pg_client: TestClient, pg_session: Session
) -> None:
    """Repeated transfer with same reference is rejected with 409."""
    source_id = _create_account(pg_client, "Idempotent Alice", initial_credit="100.00")
    dest_id = _create_account(pg_client, "Idempotent Bob", initial_credit="50.00")

    payload = {
        "source_account_id": source_id,
        "destination_account_id": dest_id,
        "amount": "25.00",
        "description": "Monthly rent",
        "reference_id": "TRF-IDEMPOTENT-001",
    }

    # First attempt succeeds
    res1 = pg_client.post(TRANSFERS_URL, json=payload)
    assert res1.status_code == 201

    # Second attempt with identical reference must be rejected
    res2 = pg_client.post(TRANSFERS_URL, json=payload)
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "DUPLICATE_TRANSACTION"

    # Balances are unchanged by the failed duplicate attempt
    persisted_source = pg_session.get(Account, UUID(source_id))
    persisted_dest = pg_session.get(Account, UUID(dest_id))
    assert persisted_source is not None and persisted_source.balance == Decimal("75.00")
    assert persisted_dest is not None and persisted_dest.balance == Decimal("75.00")


def test_transfer_rejected_when_reference_already_on_source(
    pg_client: TestClient,
) -> None:
    """Transfer rejected if reference_id is already used on the source account."""
    source_id = _create_account(pg_client, "Alice Existing", initial_credit="100.00")
    dest_id = _create_account(pg_client, "Bob Existing", initial_credit="50.00")

    # Create an independent transaction on source with reference "EXISTING-REF-01"
    tx_res = pg_client.post(
        f"{ACCOUNTS_URL}/{source_id}/transactions",
        json={
            "type": "debit",
            "amount": "10.00",
            "description": "Standalone debit",
            "reference_id": "EXISTING-REF-01",
        },
    )
    assert tx_res.status_code == 201

    # Transfer with same reference must fail
    transfer_res = pg_client.post(
        TRANSFERS_URL,
        json={
            "source_account_id": source_id,
            "destination_account_id": dest_id,
            "amount": "15.00",
            "description": "Conflict transfer",
            "reference_id": "EXISTING-REF-01",
        },
    )
    assert transfer_res.status_code == 409
    assert transfer_res.json()["error"]["code"] == "DUPLICATE_TRANSACTION"


def test_transfer_rejected_when_reference_already_on_destination(
    pg_client: TestClient,
) -> None:
    """Transfer rejected if reference_id is already used on the destination account."""
    source_id = _create_account(pg_client, "Alice Normal", initial_credit="100.00")
    dest_id = _create_account(pg_client, "Bob Existing Ref", initial_credit="50.00")

    # Create an independent transaction on destination with reference "EXISTING-REF-02"
    tx_res = pg_client.post(
        f"{ACCOUNTS_URL}/{dest_id}/transactions",
        json={
            "type": "credit",
            "amount": "20.00",
            "description": "Standalone credit",
            "reference_id": "EXISTING-REF-02",
        },
    )
    assert tx_res.status_code == 201

    # Transfer with same reference must fail
    transfer_res = pg_client.post(
        TRANSFERS_URL,
        json={
            "source_account_id": source_id,
            "destination_account_id": dest_id,
            "amount": "15.00",
            "description": "Conflict transfer on destination",
            "reference_id": "EXISTING-REF-02",
        },
    )
    assert transfer_res.status_code == 409
    assert transfer_res.json()["error"]["code"] == "DUPLICATE_TRANSACTION"


def test_transfer_same_reference_allowed_across_unrelated_accounts(
    pg_client: TestClient,
) -> None:
    """Different pairs of accounts may reuse the same reference identifier."""
    acc_a = _create_account(pg_client, "Pair 1 Alice", initial_credit="100.00")
    acc_b = _create_account(pg_client, "Pair 1 Bob", initial_credit="50.00")
    acc_c = _create_account(pg_client, "Pair 2 Charlie", initial_credit="100.00")
    acc_d = _create_account(pg_client, "Pair 2 David", initial_credit="50.00")

    shared_ref = "SHARED-TRANSFER-REF-99"

    # Transfer 1: A -> B
    res1 = pg_client.post(
        TRANSFERS_URL,
        json={
            "source_account_id": acc_a,
            "destination_account_id": acc_b,
            "amount": "10.00",
            "description": "Transfer 1",
            "reference_id": shared_ref,
        },
    )
    assert res1.status_code == 201

    # Transfer 2: C -> D with the exact same reference
    res2 = pg_client.post(
        TRANSFERS_URL,
        json={
            "source_account_id": acc_c,
            "destination_account_id": acc_d,
            "amount": "20.00",
            "description": "Transfer 2",
            "reference_id": shared_ref,
        },
    )
    assert res2.status_code == 201


# ==============================================================================
# 4. PAYLOAD VALIDATION TESTS
# ==============================================================================


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", "0.00"),
        ("amount", "-10.00"),
        ("amount", "10.005"),
        ("amount", "10.000"),
        ("amount", "1000000000000000000.00"),
        ("reference_id", ""),
        ("reference_id", "   "),
        ("reference_id", "X" * 256),
        ("description", ""),
        ("description", "   "),
        ("description", "D" * 501),
        ("source_account_id", "invalid-uuid"),
        ("destination_account_id", "not-a-uuid"),
    ],
)
def test_transfer_invalid_fields(client: TestClient, field: str, value: str) -> None:
    """Validate strict schema boundary enforcement on all transfer fields."""
    payload = {
        "source_account_id": str(uuid7()),
        "destination_account_id": str(uuid7()),
        "amount": "20.00",
        "description": "Valid description",
        "reference_id": "VALID-REF-01",
    }
    payload[field] = value

    res = client.post(TRANSFERS_URL, json=payload)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_transfer_extra_fields_forbidden(client: TestClient) -> None:
    """Reject payloads containing unexpected extra properties."""
    res = client.post(
        TRANSFERS_URL,
        json={
            "source_account_id": str(uuid7()),
            "destination_account_id": str(uuid7()),
            "amount": "20.00",
            "description": "Valid description",
            "reference_id": "EXTRA-FIELD-01",
            "unexpected_property": "attack",
        },
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


# ==============================================================================
# 5. ATOMICITY & ROLLBACK TESTS
# ==============================================================================


def test_transfer_atomicity_commit_failure_rolls_back_everything(
    pg_client: TestClient, pg_session: Session
) -> None:
    """A commit failure rolls back balances on both accounts completely."""
    source_id = _create_account(pg_client, "Atomic Alice", initial_credit="100.00")
    dest_id = _create_account(pg_client, "Atomic Bob", initial_credit="50.00")

    def fail_commit(session: Session) -> None:
        session.execute(text("SELECT 1 / 0"))

    event.listen(pg_session, "before_commit", fail_commit, once=True)

    res = pg_client.post(
        TRANSFERS_URL,
        json={
            "source_account_id": source_id,
            "destination_account_id": dest_id,
            "amount": "40.00",
            "description": "Doomed transfer",
            "reference_id": "ATOMIC-FAIL-TRF-01",
        },
    )

    assert res.status_code == 500
    assert res.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"

    # Both account balances must be completely unchanged
    persisted_source = pg_session.get(Account, UUID(source_id))
    persisted_dest = pg_session.get(Account, UUID(dest_id))
    assert persisted_source is not None and persisted_source.balance == Decimal(
        "100.00"
    )
    assert persisted_dest is not None and persisted_dest.balance == Decimal("50.00")

    # Zero transactions created with this reference ID
    txs = pg_session.scalars(
        select(Transaction).where(Transaction.reference_id == "ATOMIC-FAIL-TRF-01")
    ).all()
    assert len(txs) == 0


# ==============================================================================
# 6. IMMUTABILITY TRIGGER ENFORCEMENT
# ==============================================================================


def test_transfer_transactions_are_immutable(
    pg_client: TestClient, pg_session: Session
) -> None:
    """Ledger transactions created by a transfer cannot be updated or deleted."""
    source_id = _create_account(pg_client, "Immutable Source", initial_credit="100.00")
    dest_id = _create_account(pg_client, "Immutable Dest", initial_credit="50.00")

    res = pg_client.post(
        TRANSFERS_URL,
        json={
            "source_account_id": source_id,
            "destination_account_id": dest_id,
            "amount": "20.00",
            "description": "Immutable transfer entry",
            "reference_id": "IMMUTABLE-TRF-01",
        },
    )
    assert res.status_code == 201
    debit_id = UUID(res.json()["debit_transaction_id"])
    credit_id = UUID(res.json()["credit_transaction_id"])

    # Attempt UPDATE on debit entry
    with pytest.raises(DBAPIError) as exc_update:
        pg_session.execute(
            text("UPDATE transactions SET amount = 999.00 WHERE id = :id"),
            {"id": debit_id},
        )
        pg_session.flush()
    assert "Transactions are immutable: UPDATE not allowed" in str(exc_update.value)
    pg_session.rollback()

    # Attempt DELETE on credit entry
    with pytest.raises(DBAPIError) as exc_delete:
        pg_session.execute(
            text("DELETE FROM transactions WHERE id = :id"),
            {"id": credit_id},
        )
        pg_session.flush()
    assert "Transactions are immutable: DELETE not allowed" in str(exc_delete.value)
    pg_session.rollback()


# ==============================================================================
# 7. DEPENDENCY INJECTION & ARCHITECTURE
# ==============================================================================


def test_transfer_dependency_chain_shares_session(
    pg_client: TestClient, pg_session: Session
) -> None:
    """Verify controller, service, and repositories resolve with caller session."""
    called = False

    def check_dependencies() -> Iterator[Session]:
        nonlocal called
        called = True
        yield pg_session

    app.dependency_overrides[get_db] = check_dependencies
    try:
        source_id = _create_account(pg_client, "DI Alice", initial_credit="50.00")
        dest_id = _create_account(pg_client, "DI Bob", initial_credit="20.00")
        res = pg_client.post(
            TRANSFERS_URL,
            json={
                "source_account_id": source_id,
                "destination_account_id": dest_id,
                "amount": "10.00",
                "description": "DI test",
                "reference_id": "DI-TEST-001",
            },
        )
        assert res.status_code == 201
        assert called
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 8. OPENAPI SPECIFICATION CONTRACT
# ==============================================================================


def test_transfers_openapi_contract(client: TestClient) -> None:
    """Verify OpenAPI documentation accurately reflects the transfer route."""
    res = client.get("/openapi.json")
    assert res.status_code == 200
    doc = res.json()
    paths = doc["paths"]

    assert TRANSFERS_URL in paths
    transfer_path = paths[TRANSFERS_URL]
    assert "post" in transfer_path

    post_op = transfer_path["post"]
    assert post_op["tags"] == ["Transfers"]

    # Request body ref
    req_schema = post_op["requestBody"]["content"]["application/json"]["schema"]
    assert req_schema == {"$ref": "#/components/schemas/TransferCreate"}

    # Responses
    responses = post_op["responses"]
    assert {"201", "404", "409", "422", "500"} <= set(responses)
    assert responses["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/TransferResponse"
    }

    schemas = doc["components"]["schemas"]
    assert "TransferCreate" in schemas
    assert "TransferResponse" in schemas
    assert "TransferAccountResponse" in schemas

    transfer_create = schemas["TransferCreate"]
    assert transfer_create["additionalProperties"] is False
    assert set(transfer_create["required"]) == {
        "source_account_id",
        "destination_account_id",
        "amount",
        "reference_id",
        "description",
    }


def test_transfer_service_populates_server_timestamp(
    pg_session: Session,
) -> None:
    """Verify that TransferResult.created_at is populated by server default."""
    acc_repo = AccountRepository(pg_session)
    tx_repo = TransactionRepository(pg_session)
    service = TransferService(acc_repo, tx_repo, pg_session)

    src = Account(name="Service Timestamp Src", balance=Decimal("100.00"))
    dst = Account(name="Service Timestamp Dst", balance=Decimal("50.00"))
    pg_session.add_all([src, dst])
    pg_session.flush()

    payload = TransferCreate(
        source_account_id=src.id,
        destination_account_id=dst.id,
        amount=Decimal("25.00"),
        description="Verify timestamp",
        reference_id="SRV-TIME-001",
    )

    result = service.transfer(payload)

    assert isinstance(result.created_at, datetime)
    assert result.created_at.tzinfo is not None

    # Verify matching persisted timestamp without requiring extra queries
    persisted_debit = pg_session.get(Transaction, result.debit_transaction_id)
    assert persisted_debit is not None
    assert persisted_debit.created_at == result.created_at
