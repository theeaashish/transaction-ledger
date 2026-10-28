from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Account, Transaction


def test_create_account(db_session: Session) -> None:
    """Verify account creation with UUIDv7 ID, zero balance, and created_at."""
    account = Account(name="Treasury Main")
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    assert isinstance(account.id, UUID)
    assert account.id.version == 7
    assert account.balance == Decimal("0.00")
    assert account.created_at is not None
    assert account.name == "Treasury Main"


def test_create_transaction_and_relationships(db_session: Session) -> None:
    """Verify transaction creation and bidirectional relationship navigation."""
    account = Account(name="Operating Account")
    db_session.add(account)
    db_session.commit()

    tx = Transaction(
        account_id=account.id,
        type="credit",
        amount=Decimal("1500.50"),
        description="Initial deposit",
        reference_id="DEP-2026-001",
    )
    db_session.add(tx)
    db_session.commit()
    db_session.refresh(tx)
    db_session.refresh(account)

    assert isinstance(tx.id, UUID)
    assert tx.id.version == 7
    assert tx.account_id == account.id
    assert tx.amount == Decimal("1500.50")
    assert tx.type == "credit"
    assert tx.created_at is not None

    # Relationship tests
    assert tx.account.id == account.id
    assert len(account.transactions) == 1
    assert account.transactions[0].id == tx.id


def test_same_reference_id_different_accounts(db_session: Session) -> None:
    """Verify that the same reference_id is permitted across different accounts."""
    account1 = Account(name="Account Alpha")
    account2 = Account(name="Account Beta")
    db_session.add_all([account1, account2])
    db_session.commit()

    tx1 = Transaction(
        account_id=account1.id,
        type="credit",
        amount=Decimal("100.00"),
        description="Invoice payment",
        reference_id="INV-999",
    )
    tx2 = Transaction(
        account_id=account2.id,
        type="credit",
        amount=Decimal("200.00"),
        description="Invoice payment",
        reference_id="INV-999",
    )
    db_session.add_all([tx1, tx2])
    db_session.commit()

    assert tx1.id is not None
    assert tx2.id is not None


def test_negative_balance_rejected(db_session: Session) -> None:
    """Verify that negative balance is rejected by check constraint."""
    account = Account(name="Overdrawn Account", balance=Decimal("-50.00"))
    db_session.add(account)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_blank_account_name_rejected(db_session: Session) -> None:
    """Verify that blank/whitespace name is rejected by check constraint."""
    account = Account(name="   ")
    db_session.add(account)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_non_positive_transaction_amount_rejected(db_session: Session) -> None:
    """Verify that amount <= 0 is rejected by check constraint."""
    account = Account(name="Test Account")
    db_session.add(account)
    db_session.commit()

    # Zero amount
    tx_zero = Transaction(
        account_id=account.id,
        type="credit",
        amount=Decimal("0.00"),
        description="Zero deposit",
        reference_id="ZERO-1",
    )
    db_session.add(tx_zero)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    # Negative amount
    tx_negative = Transaction(
        account_id=account.id,
        type="credit",
        amount=Decimal("-10.00"),
        description="Negative deposit",
        reference_id="NEG-1",
    )
    db_session.add(tx_negative)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_invalid_transaction_type_rejected(db_session: Session) -> None:
    """Verify that types other than 'credit' and 'debit' are rejected."""
    account = Account(name="Test Account")
    db_session.add(account)
    db_session.commit()

    tx = Transaction(
        account_id=account.id,
        type="transfer",
        amount=Decimal("10.00"),
        description="Invalid type",
        reference_id="TYP-1",
    )
    db_session.add(tx)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_blank_transaction_fields_rejected(db_session: Session) -> None:
    """Verify that blank description or reference_id are rejected."""
    account = Account(name="Test Account")
    db_session.add(account)
    db_session.commit()

    # Blank description
    tx1 = Transaction(
        account_id=account.id,
        type="credit",
        amount=Decimal("10.00"),
        description="   ",
        reference_id="REF-OK",
    )
    db_session.add(tx1)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    # Blank reference_id
    tx2 = Transaction(
        account_id=account.id,
        type="credit",
        amount=Decimal("10.00"),
        description="Valid description",
        reference_id="   ",
    )
    db_session.add(tx2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_duplicate_reference_id_same_account_rejected(db_session: Session) -> None:
    """Verify that duplicate (account_id, reference_id) is rejected."""
    account = Account(name="Test Account")
    db_session.add(account)
    db_session.commit()

    tx1 = Transaction(
        account_id=account.id,
        type="credit",
        amount=Decimal("10.00"),
        description="First transaction",
        reference_id="DUP-REF",
    )
    db_session.add(tx1)
    db_session.commit()

    tx2 = Transaction(
        account_id=account.id,
        type="credit",
        amount=Decimal("20.00"),
        description="Second transaction",
        reference_id="DUP-REF",
    )
    db_session.add(tx2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_delete_account_with_transactions_restricted(db_session: Session) -> None:
    """Verify that deleting an account with transactions is restricted."""
    account = Account(name="Account to Delete")
    db_session.add(account)
    db_session.commit()

    tx = Transaction(
        account_id=account.id,
        type="credit",
        amount=Decimal("10.00"),
        description="Transaction before delete",
        reference_id="DEL-REF",
    )
    db_session.add(tx)
    db_session.commit()

    db_session.delete(account)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
