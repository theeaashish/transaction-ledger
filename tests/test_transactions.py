from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Account, Transaction
from app.main import app
from app.modules.transactions.controller import TransactionController
from app.modules.transactions.schemas import (
    TransactionCreate,
    TransactionCreateResponse,
)

ACCOUNTS_URL = "/api/v1/accounts"


def _create_account(client: TestClient, name: str = "Test User") -> str:
    """Helper to create an account and return its ID."""
    response = client.post(ACCOUNTS_URL, json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


# ==============================================================================
# 1. CREDIT TESTS
# ==============================================================================


def test_credit_increases_balance_and_creates_transaction(
    pg_client: TestClient, pg_session: Session
) -> None:
    """Credit 100.00 to a zero-balance account and verify resulting state."""
    account_id = _create_account(pg_client, "Credit User")

    # Step 1: Credit 100.00
    res1 = pg_client.post(
        f"{ACCOUNTS_URL}/{account_id}/transactions",
        json={
            "type": "credit",
            "amount": "100.00",
            "description": "Initial deposit",
            "reference_id": "REF-CREDIT-001",
        },
    )
    assert res1.status_code == 201
    data1 = res1.json()
    assert data1["account_id"] == account_id
    assert data1["type"] == "credit"
    assert data1["amount"] == "100.00"
    assert data1["description"] == "Initial deposit"
    assert data1["reference_id"] == "REF-CREDIT-001"
    assert data1["balance_after"] == "100.00"
    tx1_id = UUID(data1["id"])
    assert tx1_id.version == 7
    created_at = datetime.fromisoformat(data1["created_at"])
    assert created_at.tzinfo is not None

    # Verify database state
    persisted_acc = pg_session.get(Account, UUID(account_id))
    assert persisted_acc is not None
    assert persisted_acc.balance == Decimal("100.00")

    persisted_tx = pg_session.get(Transaction, tx1_id)
    assert persisted_tx is not None
    assert persisted_tx.account_id == UUID(account_id)
    assert persisted_tx.type == "credit"
    assert persisted_tx.amount == Decimal("100.00")
    assert persisted_tx.reference_id == "REF-CREDIT-001"

    # Step 2: Credit 50.00
    res2 = pg_client.post(
        f"{ACCOUNTS_URL}/{account_id}/transactions",
        json={
            "type": "credit",
            "amount": "50.00",
            "description": "Second deposit",
            "reference_id": "REF-CREDIT-002",
        },
    )
    assert res2.status_code == 201
    data2 = res2.json()
    assert data2["balance_after"] == "150.00"
    assert data2["amount"] == "50.00"

    # Verify balance endpoint
    balance_res = pg_client.get(f"{ACCOUNTS_URL}/{account_id}/balance")
    assert balance_res.status_code == 200
    assert balance_res.json()["balance"] == "150.00"


# ==============================================================================
# 2. DEBIT TESTS
# ==============================================================================


def test_debit_decreases_balance(pg_client: TestClient, pg_session: Session) -> None:
    """Debit 30.00 from a 100.00 account; balance becomes 70.00."""
    account_id = _create_account(pg_client, "Debit User")

    # Credit 100.00 first
    pg_client.post(
        f"{ACCOUNTS_URL}/{account_id}/transactions",
        json={
            "type": "credit",
            "amount": "100.00",
            "description": "Seed",
            "reference_id": "REF-DEBIT-SEED",
        },
    )

    # Debit 30.00
    res = pg_client.post(
        f"{ACCOUNTS_URL}/{account_id}/transactions",
        json={
            "type": "debit",
            "amount": "30.00",
            "description": "Grocery withdrawal",
            "reference_id": "REF-DEBIT-001",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["type"] == "debit"
    assert data["amount"] == "30.00"
    assert data["balance_after"] == "70.00"

    persisted_acc = pg_session.get(Account, UUID(account_id))
    assert persisted_acc is not None
    assert persisted_acc.balance == Decimal("70.00")


def test_debit_exceeding_balance_is_rejected(
    pg_client: TestClient, pg_session: Session
) -> None:
    """Debiting 150.00 from an account with 100.00 returns 409 INSUFFICIENT_BALANCE."""
    account_id = _create_account(pg_client, "Insufficient User")

    # Credit 100.00
    pg_client.post(
        f"{ACCOUNTS_URL}/{account_id}/transactions",
        json={
            "type": "credit",
            "amount": "100.00",
            "description": "Initial 100",
            "reference_id": "REF-INITIAL-100",
        },
    )

    # Attempt debit of 150.00
    res = pg_client.post(
        f"{ACCOUNTS_URL}/{account_id}/transactions",
        json={
            "type": "debit",
            "amount": "150.00",
            "description": "Overdraft attempt",
            "reference_id": "REF-OVERDRAFT",
        },
    )
    assert res.status_code == 409
    error = res.json()["error"]
    assert error["code"] == "INSUFFICIENT_BALANCE"
    assert error["message"] == "The account has insufficient funds for this debit."

    # Balance remains 100.00
    balance_res = pg_client.get(f"{ACCOUNTS_URL}/{account_id}/balance")
    assert balance_res.json()["balance"] == "100.00"

    # Verify no transaction record was added for the rejected debit
    rejected_tx = pg_session.scalar(
        select(Transaction).where(Transaction.reference_id == "REF-OVERDRAFT")
    )
    assert rejected_tx is None


# ==============================================================================
# 3. IDEMPOTENCY TESTS
# ==============================================================================


def test_duplicate_reference_same_account_rejected(
    pg_client: TestClient, pg_session: Session
) -> None:
    """Duplicate reference submission on the same account returns 409 conflict."""
    account_id = _create_account(pg_client, "Idempotent User")

    # First submission succeeds
    res1 = pg_client.post(
        f"{ACCOUNTS_URL}/{account_id}/transactions",
        json={
            "type": "credit",
            "amount": "100.00",
            "description": "First try",
            "reference_id": "DUP-REF-001",
        },
    )
    assert res1.status_code == 201
    assert res1.json()["balance_after"] == "100.00"

    # Second submission with same reference fails
    res2 = pg_client.post(
        f"{ACCOUNTS_URL}/{account_id}/transactions",
        json={
            "type": "credit",
            "amount": "100.00",
            "description": "Duplicate try",
            "reference_id": "DUP-REF-001",
        },
    )
    assert res2.status_code == 409
    error = res2.json()["error"]
    assert error["code"] == "DUPLICATE_TRANSACTION"
    assert error["message"] == "Duplicate transaction reference."

    # Balance changed only once
    balance_res = pg_client.get(f"{ACCOUNTS_URL}/{account_id}/balance")
    assert balance_res.json()["balance"] == "100.00"

    # Exactly one transaction record exists
    count = pg_session.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.account_id == UUID(account_id),
            Transaction.reference_id == "DUP-REF-001",
        )
    )
    assert count == 1


def test_same_reference_allowed_across_different_accounts(
    pg_client: TestClient,
) -> None:
    """The same reference ID can be used on two separate accounts."""
    account1 = _create_account(pg_client, "User One")
    account2 = _create_account(pg_client, "User Two")

    res1 = pg_client.post(
        f"{ACCOUNTS_URL}/{account1}/transactions",
        json={
            "type": "credit",
            "amount": "50.00",
            "description": "Deposit",
            "reference_id": "SHARED-REF-001",
        },
    )
    assert res1.status_code == 201

    res2 = pg_client.post(
        f"{ACCOUNTS_URL}/{account2}/transactions",
        json={
            "type": "credit",
            "amount": "75.00",
            "description": "Deposit on second account",
            "reference_id": "SHARED-REF-001",
        },
    )
    assert res2.status_code == 201
    assert res2.json()["balance_after"] == "75.00"


# ==============================================================================
# 4. ATOMICITY TESTS
# ==============================================================================


def test_atomicity_commit_failure_rolls_back_balance_and_transaction(
    pg_client: TestClient, pg_session: Session
) -> None:
    """A commit failure rolls back both the balance update and transaction."""
    account_id = _create_account(pg_client, "Atomic User")

    # Initial balance is 0.00
    assert pg_session.get(Account, UUID(account_id)).balance == Decimal("0.00")  # pyright: ignore

    def fail_commit(session: Session) -> None:
        session.execute(text("SELECT 1 / 0"))

    event.listen(pg_session, "before_commit", fail_commit, once=True)

    res = pg_client.post(
        f"{ACCOUNTS_URL}/{account_id}/transactions",
        json={
            "type": "credit",
            "amount": "500.00",
            "description": "Doomed deposit",
            "reference_id": "ATOMIC-FAIL-01",
        },
    )

    assert res.status_code == 500
    assert res.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"

    # Session is active and clean
    assert pg_session.is_active
    assert not pg_session.in_transaction()

    # Balance remains 0.00
    persisted_acc = pg_session.get(Account, UUID(account_id))
    assert persisted_acc is not None
    assert persisted_acc.balance == Decimal("0.00")

    # Transaction record does not exist
    persisted_tx = pg_session.scalar(
        select(Transaction).where(Transaction.reference_id == "ATOMIC-FAIL-01")
    )
    assert persisted_tx is None

    # Session is usable for subsequent operations
    recovered = pg_client.post(
        f"{ACCOUNTS_URL}/{account_id}/transactions",
        json={
            "type": "credit",
            "amount": "200.00",
            "description": "Recovered deposit",
            "reference_id": "ATOMIC-OK-01",
        },
    )
    assert recovered.status_code == 201
    assert recovered.json()["balance_after"] == "200.00"


# ==============================================================================
# 5. VALIDATION TESTS
# ==============================================================================


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        # Missing fields
        (
            {
                "amount": "100.00",
                "description": "desc",
                "reference_id": "ref",
            },
            "type",
        ),
        (
            {
                "type": "credit",
                "description": "desc",
                "reference_id": "ref",
            },
            "amount",
        ),
        (
            {
                "type": "credit",
                "amount": "100.00",
                "reference_id": "ref",
            },
            "description",
        ),
        (
            {
                "type": "credit",
                "amount": "100.00",
                "description": "desc",
            },
            "reference_id",
        ),
        # Invalid type
        (
            {
                "type": "transfer",
                "amount": "100.00",
                "description": "d",
                "reference_id": "r",
            },
            "type",
        ),
        (
            {
                "type": "deposit",
                "amount": "100.00",
                "description": "d",
                "reference_id": "r",
            },
            "type",
        ),
        (
            {
                "type": "",
                "amount": "100.00",
                "description": "d",
                "reference_id": "r",
            },
            "type",
        ),
        # Zero / negative amount
        (
            {
                "type": "credit",
                "amount": "0.00",
                "description": "d",
                "reference_id": "r",
            },
            "amount",
        ),
        (
            {
                "type": "credit",
                "amount": "-50.00",
                "description": "d",
                "reference_id": "r",
            },
            "amount",
        ),
        # Excess precision
        (
            {
                "type": "credit",
                "amount": "100.001",
                "description": "d",
                "reference_id": "r",
            },
            "amount",
        ),
        (
            {
                "type": "credit",
                "amount": "100.000",
                "description": "d",
                "reference_id": "r",
            },
            "amount",
        ),
        (
            {
                "type": "credit",
                "amount": "100.555",
                "description": "d",
                "reference_id": "r",
            },
            "amount",
        ),
        # Over NUMERIC(18, 2) max digits
        (
            {
                "type": "credit",
                "amount": "99999999999999999.99",
                "description": "d",
                "reference_id": "r",
            },
            "amount",
        ),
        # Whitespace-only description / reference
        (
            {
                "type": "credit",
                "amount": "100.00",
                "description": "   ",
                "reference_id": "r",
            },
            "description",
        ),
        (
            {
                "type": "credit",
                "amount": "100.00",
                "description": "\t\n",
                "reference_id": "r",
            },
            "description",
        ),
        (
            {
                "type": "credit",
                "amount": "100.00",
                "description": "d",
                "reference_id": "   ",
            },
            "reference_id",
        ),
        # Overlong strings
        (
            {
                "type": "credit",
                "amount": "100.00",
                "description": "x" * 501,
                "reference_id": "r",
            },
            "description",
        ),
        (
            {
                "type": "credit",
                "amount": "100.00",
                "description": "d",
                "reference_id": "r" * 256,
            },
            "reference_id",
        ),
        # Unknown client fields
        (
            {
                "type": "credit",
                "amount": "100.00",
                "description": "d",
                "reference_id": "r",
                "account_id": str(uuid7()),
            },
            "account_id",
        ),
        (
            {
                "type": "credit",
                "amount": "100.00",
                "description": "d",
                "reference_id": "r",
                "id": str(uuid7()),
            },
            "id",
        ),
        (
            {
                "type": "credit",
                "amount": "100.00",
                "description": "d",
                "reference_id": "r",
                "balance_after": "100.00",
            },
            "balance_after",
        ),
        (
            {
                "type": "credit",
                "amount": "100.00",
                "description": "d",
                "reference_id": "r",
                "created_at": "2026-10-28T09:00:00Z",
            },
            "created_at",
        ),
        (
            {
                "type": "credit",
                "amount": "100.00",
                "description": "d",
                "reference_id": "r",
                "extra_field": "disallowed",
            },
            "extra_field",
        ),
    ],
    ids=[
        "missing-type",
        "missing-amount",
        "missing-description",
        "missing-reference_id",
        "invalid-type-transfer",
        "invalid-type-deposit",
        "empty-type",
        "zero-amount",
        "negative-amount",
        "excess-fractional-digits-3",
        "excess-fractional-zeros-3",
        "excess-fractional-digits-555",
        "over-max-digits",
        "whitespace-description",
        "tab-newline-description",
        "whitespace-reference_id",
        "description-too-long",
        "reference_id-too-long",
        "client-account-id",
        "client-id",
        "client-balance-after",
        "client-created-at",
        "unknown-field",
    ],
)
def test_invalid_transaction_payload(
    client: TestClient,
    payload: dict[str, object],
    field: str,
) -> None:
    """Invalid transaction input fails with 422 VALIDATION_ERROR envelope."""
    random_account_id = str(uuid7())
    res = client.post(
        f"{ACCOUNTS_URL}/{random_account_id}/transactions",
        json=payload,
    )
    assert res.status_code == 422
    data = res.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["message"] == "Request validation failed"
    assert any(detail["loc"] == ["body", field] for detail in data["error"]["details"])


def test_malformed_account_uuid_in_transactions(client: TestClient) -> None:
    """A non-UUID account ID path parameter returns 422 VALIDATION_ERROR."""
    res_post = client.post(
        f"{ACCOUNTS_URL}/not-a-uuid/transactions",
        json={
            "type": "credit",
            "amount": "100.00",
            "description": "d",
            "reference_id": "r",
        },
    )
    assert res_post.status_code == 422
    assert res_post.json()["error"]["code"] == "VALIDATION_ERROR"
    assert res_post.json()["error"]["details"][0]["loc"] == ["path", "account_id"]

    res_get = client.get(f"{ACCOUNTS_URL}/not-a-uuid/transactions")
    assert res_get.status_code == 422
    assert res_get.json()["error"]["code"] == "VALIDATION_ERROR"
    assert res_get.json()["error"]["details"][0]["loc"] == ["path", "account_id"]


def test_nonexistent_account_returns_404(client: TestClient) -> None:
    """Operations on a nonexistent account return 404 ACCOUNT_NOT_FOUND."""
    missing_id = str(uuid7())

    res_post = client.post(
        f"{ACCOUNTS_URL}/{missing_id}/transactions",
        json={
            "type": "credit",
            "amount": "100.00",
            "description": "deposit",
            "reference_id": "REF-MISSING-01",
        },
    )
    assert res_post.status_code == 404
    assert res_post.json()["error"] == {
        "code": "ACCOUNT_NOT_FOUND",
        "message": "Account not found",
        "details": None,
    }

    res_get = client.get(f"{ACCOUNTS_URL}/{missing_id}/transactions")
    assert res_get.status_code == 404
    assert res_get.json()["error"] == {
        "code": "ACCOUNT_NOT_FOUND",
        "message": "Account not found",
        "details": None,
    }


# ==============================================================================
# 6. TRANSACTION HISTORY & PAGINATION TESTS
# ==============================================================================


def test_history_empty_results(pg_client: TestClient) -> None:
    """An account with no transactions returns 0 total records and an empty list."""
    account_id = _create_account(pg_client, "Empty History User")
    res = pg_client.get(f"{ACCOUNTS_URL}/{account_id}/transactions")
    assert res.status_code == 200
    data = res.json()
    assert data["account_id"] == account_id
    assert data["current_page"] == 1
    assert data["page_size"] == 10
    assert data["total_records"] == 0
    assert data["total_pages"] == 0
    assert data["transactions"] == []


def test_history_filtering_and_deterministic_ordering(
    pg_client: TestClient, pg_session: Session
) -> None:
    """History supports type filtering and deterministic newest-first ordering."""
    account_id = _create_account(pg_client, "History Filter User")
    acc_uuid = UUID(account_id)

    # Insert transactions with deterministic created_at timestamps
    base_time = datetime(2026, 10, 28, 9, 0, 0, tzinfo=UTC)
    tx1 = Transaction(
        id=uuid7(),
        account_id=acc_uuid,
        type="credit",
        amount=Decimal("100.00"),
        description="First credit",
        reference_id="H-REF-01",
        created_at=base_time,
    )
    tx2 = Transaction(
        id=uuid7(),
        account_id=acc_uuid,
        type="debit",
        amount=Decimal("20.00"),
        description="First debit",
        reference_id="H-REF-02",
        created_at=base_time + timedelta(seconds=10),
    )
    tx3 = Transaction(
        id=uuid7(),
        account_id=acc_uuid,
        type="credit",
        amount=Decimal("50.00"),
        description="Second credit",
        reference_id="H-REF-03",
        created_at=base_time + timedelta(seconds=20),
    )
    tx4 = Transaction(
        id=uuid7(),
        account_id=acc_uuid,
        type="debit",
        amount=Decimal("10.00"),
        description="Second debit",
        reference_id="H-REF-04",
        created_at=base_time + timedelta(seconds=30),
    )
    # tx5 has identical timestamp to tx4 but different UUID to test tie-breaking
    tx5 = Transaction(
        id=uuid7(),
        account_id=acc_uuid,
        type="credit",
        amount=Decimal("200.00"),
        description="Third credit same time",
        reference_id="H-REF-05",
        created_at=base_time + timedelta(seconds=30),
    )
    pg_session.add_all([tx1, tx2, tx3, tx4, tx5])
    pg_session.flush()

    # Query 1: All transactions (no filter) -> newest first
    res_all = pg_client.get(f"{ACCOUNTS_URL}/{account_id}/transactions")
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert data_all["total_records"] == 5
    assert data_all["total_pages"] == 1
    assert len(data_all["transactions"]) == 5

    # Check newest first ordering
    returned_refs = [tx["reference_id"] for tx in data_all["transactions"]]
    # Tx4 and Tx5 share timestamp base_time + 30s; tie-breaker is id DESC
    expected_top = sorted([tx4, tx5], key=lambda t: t.id, reverse=True)
    assert returned_refs[0] == expected_top[0].reference_id
    assert returned_refs[1] == expected_top[1].reference_id
    assert returned_refs[2] == "H-REF-03"
    assert returned_refs[3] == "H-REF-02"
    assert returned_refs[4] == "H-REF-01"

    # Query 2: Filter type=credit
    res_credits = pg_client.get(f"{ACCOUNTS_URL}/{account_id}/transactions?type=credit")
    assert res_credits.status_code == 200
    data_credits = res_credits.json()
    assert data_credits["total_records"] == 3
    assert data_credits["total_pages"] == 1
    assert all(tx["type"] == "credit" for tx in data_credits["transactions"])
    assert [tx["reference_id"] for tx in data_credits["transactions"]] == [
        "H-REF-05",
        "H-REF-03",
        "H-REF-01",
    ]

    # Query 3: Filter type=debit
    res_debits = pg_client.get(f"{ACCOUNTS_URL}/{account_id}/transactions?type=debit")
    assert res_debits.status_code == 200
    data_debits = res_debits.json()
    assert data_debits["total_records"] == 2
    assert data_debits["total_pages"] == 1
    assert all(tx["type"] == "debit" for tx in data_debits["transactions"])
    assert [tx["reference_id"] for tx in data_debits["transactions"]] == [
        "H-REF-04",
        "H-REF-02",
    ]


def test_history_pagination(pg_client: TestClient, pg_session: Session) -> None:
    """Pagination metadata, limit, offset, and pages beyond total_pages."""
    account_id = _create_account(pg_client, "Pagination User")
    acc_uuid = UUID(account_id)

    # Insert 5 transactions
    base_time = datetime(2026, 10, 28, 10, 0, 0, tzinfo=UTC)
    for i in range(1, 6):
        tx = Transaction(
            account_id=acc_uuid,
            type="credit",
            amount=Decimal(f"{i * 10}.00"),
            description=f"Tx {i}",
            reference_id=f"PAG-REF-{i:02d}",
            created_at=base_time + timedelta(seconds=i),
        )
        pg_session.add(tx)
    pg_session.flush()

    # Page 1, limit 2
    res_p1 = pg_client.get(f"{ACCOUNTS_URL}/{account_id}/transactions?page=1&limit=2")
    assert res_p1.status_code == 200
    d1 = res_p1.json()
    assert d1["current_page"] == 1
    assert d1["page_size"] == 2
    assert d1["total_records"] == 5
    assert d1["total_pages"] == 3
    assert [tx["reference_id"] for tx in d1["transactions"]] == [
        "PAG-REF-05",
        "PAG-REF-04",
    ]

    # Page 2, limit 2
    res_p2 = pg_client.get(f"{ACCOUNTS_URL}/{account_id}/transactions?page=2&limit=2")
    assert res_p2.status_code == 200
    d2 = res_p2.json()
    assert d2["current_page"] == 2
    assert d2["page_size"] == 2
    assert [tx["reference_id"] for tx in d2["transactions"]] == [
        "PAG-REF-03",
        "PAG-REF-02",
    ]

    # Page 3, limit 2 (last page, only 1 item)
    res_p3 = pg_client.get(f"{ACCOUNTS_URL}/{account_id}/transactions?page=3&limit=2")
    assert res_p3.status_code == 200
    d3 = res_p3.json()
    assert d3["current_page"] == 3
    assert len(d3["transactions"]) == 1
    assert d3["transactions"][0]["reference_id"] == "PAG-REF-01"

    # Page 4, limit 2 (page beyond final page -> empty list, correct metadata)
    res_p4 = pg_client.get(f"{ACCOUNTS_URL}/{account_id}/transactions?page=4&limit=2")
    assert res_p4.status_code == 200
    d4 = res_p4.json()
    assert d4["current_page"] == 4
    assert d4["page_size"] == 2
    assert d4["total_records"] == 5
    assert d4["total_pages"] == 3
    assert d4["transactions"] == []

    # Combined filter + pagination: add 2 debits
    for i in range(1, 3):
        deb = Transaction(
            account_id=acc_uuid,
            type="debit",
            amount=Decimal(f"{i * 5}.00"),
            description=f"Deb {i}",
            reference_id=f"PAG-DEB-{i:02d}",
            created_at=base_time + timedelta(seconds=10 + i),
        )
        pg_session.add(deb)
    pg_session.flush()

    res_comb = pg_client.get(
        f"{ACCOUNTS_URL}/{account_id}/transactions?type=debit&page=1&limit=1"
    )
    assert res_comb.status_code == 200
    dc = res_comb.json()
    assert dc["current_page"] == 1
    assert dc["page_size"] == 1
    assert dc["total_records"] == 2
    assert dc["total_pages"] == 2
    assert len(dc["transactions"]) == 1
    assert dc["transactions"][0]["reference_id"] == "PAG-DEB-02"


@pytest.mark.parametrize(
    "query_params",
    [
        "?page=0",
        "?page=-1",
        "?page=invalid",
        "?limit=0",
        "?limit=101",
        "?limit=-1",
        "?limit=invalid",
        "?type=transfer",
        "?type=invalid",
    ],
)
def test_invalid_history_query_parameters(
    client: TestClient, query_params: str
) -> None:
    """Invalid pagination or filter parameters return 422 VALIDATION_ERROR."""
    res = client.get(f"{ACCOUNTS_URL}/{uuid7()}/transactions{query_params}")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


# ==============================================================================
# 7. DEPENDENCY INJECTION & SESSION SHARING
# ==============================================================================


def test_transaction_dependency_chain_shares_session(
    pg_client: TestClient, pg_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FastAPI caches get_db across both repositories and service factories."""
    account_id = _create_account(pg_client, "DI User")
    requested_sessions: list[Session] = []
    observed_sessions: list[tuple[Session, Session, Session]] = []
    original_create = TransactionController.create_transaction

    def override_db() -> Iterator[Session]:
        requested_sessions.append(pg_session)
        yield pg_session

    def capture_sessions(
        controller: TransactionController,
        acc_id: UUID,
        payload: TransactionCreate,
    ) -> TransactionCreateResponse:
        service = controller.transaction_service
        observed_sessions.append(
            (
                service.db,
                service.account_repository.db,
                service.transaction_repository.db,
            )
        )
        return original_create(controller, acc_id, payload)

    monkeypatch.setitem(app.dependency_overrides, get_db, override_db)
    monkeypatch.setattr(TransactionController, "create_transaction", capture_sessions)

    res = pg_client.post(
        f"{ACCOUNTS_URL}/{account_id}/transactions",
        json={
            "type": "credit",
            "amount": "100.00",
            "description": "DI check",
            "reference_id": "DI-REF-01",
        },
    )

    assert res.status_code == 201
    assert requested_sessions == [pg_session]
    assert observed_sessions == [(pg_session, pg_session, pg_session)]


# ==============================================================================
# 8. OPENAPI CONTRACT TESTS
# ==============================================================================


def test_transactions_openapi_contract(client: TestClient) -> None:
    """Verify OpenAPI documentation accurately reflects the transaction routes."""
    res = client.get("/openapi.json")
    assert res.status_code == 200
    doc = res.json()
    paths = doc["paths"]
    tx_path = f"{ACCOUNTS_URL}/{{account_id}}/transactions"

    assert tx_path in paths
    assert set(paths[tx_path]) == {"post", "get"}

    # POST route
    post_op = paths[tx_path]["post"]
    assert post_op["tags"] == ["Transactions"]
    assert post_op["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/TransactionCreate"
    }
    assert post_op["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/TransactionCreateResponse"
    }
    assert {"201", "404", "409", "422", "500"} <= set(post_op["responses"])

    # GET route
    get_op = paths[tx_path]["get"]
    assert get_op["tags"] == ["Transactions"]
    assert get_op["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/TransactionHistoryResponse"
    }
    assert {"200", "404", "422", "500"} <= set(get_op["responses"])

    param_names = [p["name"] for p in get_op["parameters"]]
    assert "account_id" in param_names
    assert "type" in param_names
    assert "page" in param_names
    assert "limit" in param_names

    schemas = doc["components"]["schemas"]
    # TransactionCreate schema
    tx_create = schemas["TransactionCreate"]
    assert tx_create["additionalProperties"] is False
    assert set(tx_create["required"]) == {
        "type",
        "amount",
        "description",
        "reference_id",
    }
    assert tx_create["properties"]["type"]["enum"] == ["credit", "debit"]

    # TransactionCreateResponse schema
    tx_create_res = schemas["TransactionCreateResponse"]
    assert set(tx_create_res["properties"]) == {
        "id",
        "account_id",
        "type",
        "amount",
        "description",
        "reference_id",
        "balance_after",
        "created_at",
    }
    for field in ("amount", "balance_after"):
        prop = tx_create_res["properties"][field]
        assert prop["type"] == "string"
        assert prop["pattern"] == r"^\d+\.\d{2}$"
        assert prop["examples"] == ["0.00", "125.50"]

    # TransactionResponse schema (no balance_after)
    tx_res = schemas["TransactionResponse"]
    assert "balance_after" not in tx_res["properties"]
    assert set(tx_res["properties"]) == {
        "id",
        "account_id",
        "type",
        "amount",
        "description",
        "reference_id",
        "created_at",
    }
