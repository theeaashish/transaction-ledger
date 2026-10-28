from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.models import Account, Transaction


def test_transactions_immutability_trigger(pg_session: Session) -> None:
    """Verify that PostgreSQL trigger rejects UPDATE and DELETE on transactions."""
    account = Account(name="Immutability Test Account")
    pg_session.add(account)
    pg_session.flush()

    tx = Transaction(
        account_id=account.id,
        type="credit",
        amount=Decimal("100.00"),
        description="Immutable entry",
        reference_id="IMMUTABLE-01",
    )
    pg_session.add(tx)
    pg_session.flush()

    # Attempt direct UPDATE on transaction
    with pytest.raises(DBAPIError) as exc_update:
        pg_session.execute(
            text("UPDATE transactions SET amount = 999.00 WHERE id = :id"),
            {"id": tx.id},
        )
        pg_session.flush()
    assert "Transactions are immutable: UPDATE not allowed" in str(exc_update.value)
    pg_session.rollback()

    # Create fresh transaction in rolled back session
    account2 = Account(name="Immutability Test Account 2")
    pg_session.add(account2)
    pg_session.flush()
    tx2 = Transaction(
        account_id=account2.id,
        type="debit",
        amount=Decimal("50.00"),
        description="Immutable entry 2",
        reference_id="IMMUTABLE-02",
    )
    pg_session.add(tx2)
    pg_session.flush()

    # Attempt direct DELETE on transaction
    with pytest.raises(DBAPIError) as exc_delete:
        pg_session.execute(
            text("DELETE FROM transactions WHERE id = :id"),
            {"id": tx2.id},
        )
        pg_session.flush()
    assert "Transactions are immutable: DELETE not allowed" in str(exc_delete.value)
    pg_session.rollback()
