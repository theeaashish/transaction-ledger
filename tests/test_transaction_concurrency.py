import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.core.exceptions import (
    DuplicateTransactionException,
    InsufficientBalanceException,
)
from app.db.models import Account, Transaction
from app.modules.transactions.schemas import TransactionCreate
from app.modules.transactions.service import TransactionService
from app.repositories.account import AccountRepository
from app.repositories.transaction import TransactionRepository


def _cleanup_test_data(engine: Engine, account_id: UUID) -> None:
    """Safely remove test records by temporarily disabling the immutability trigger."""
    with engine.connect() as conn:
        conn.execute(
            text(
                "ALTER TABLE transactions "
                "DISABLE TRIGGER trg_prevent_transaction_modification"
            )
        )
        conn.execute(
            text("DELETE FROM transactions WHERE account_id = :account_id"),
            {"account_id": account_id},
        )
        conn.execute(
            text(
                "ALTER TABLE transactions "
                "ENABLE TRIGGER trg_prevent_transaction_modification"
            )
        )
        conn.execute(
            text("DELETE FROM accounts WHERE id = :account_id"),
            {"account_id": account_id},
        )
        conn.commit()


def test_concurrent_debits_prevent_overdraft(pg_engine: Engine) -> None:
    """Two concurrent debits totaling more than available balance cannot overspend.

    Account has 100.00. Concurrent debits of 80.00 and 50.00 are submitted.
    Row-level locking guarantees that exactly one debit succeeds and the other
    is rejected with InsufficientBalanceException. The account balance never
    becomes negative.
    """
    with Session(pg_engine) as session:
        account = Account(name="Concurrency Overdraft Test", balance=Decimal("100.00"))
        session.add(account)
        session.commit()
        account_id = account.id

    barrier = threading.Barrier(2)
    results: list[dict[str, object]] = []

    def perform_debit(amount_str: str, ref_id: str) -> None:
        with Session(pg_engine) as session:
            acc_repo = AccountRepository(session)
            tx_repo = TransactionRepository(session)
            service = TransactionService(acc_repo, tx_repo, session)

            payload = TransactionCreate(
                type="debit",
                amount=Decimal(amount_str),
                description=f"Debit {amount_str}",
                reference_id=ref_id,
            )

            # Synchronize thread start to guarantee genuinely overlapping operations
            barrier.wait()
            try:
                res = service.create_transaction(account_id, payload)
                results.append({"status": "success", "amount": amount_str, "res": res})
            except InsufficientBalanceException as exc:
                results.append(
                    {"status": "insufficient_balance", "amount": amount_str, "exc": exc}
                )
            except Exception as exc:
                results.append({"status": "error", "amount": amount_str, "exc": exc})

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(perform_debit, "80.00", "CONCUR-DEBIT-80")
            f2 = executor.submit(perform_debit, "50.00", "CONCUR-DEBIT-50")
            f1.result()
            f2.result()

        successes = [r for r in results if r["status"] == "success"]
        insufficient = [r for r in results if r["status"] == "insufficient_balance"]

        assert len(successes) == 1, f"Expected 1 success, got: {results}"
        assert len(insufficient) == 1, (
            f"Expected 1 insufficient balance, got: {results}"
        )

        with Session(pg_engine) as session:
            persisted_acc = session.get(Account, account_id)
            assert persisted_acc is not None
            assert persisted_acc.balance in [Decimal("20.00"), Decimal("50.00")]
            assert persisted_acc.balance >= Decimal("0.00")

            tx_count = session.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(Transaction.account_id == account_id)
            )
            assert tx_count == 1

            successful_tx = session.scalar(
                select(Transaction).where(Transaction.account_id == account_id)
            )
            assert successful_tx is not None
            if persisted_acc.balance == Decimal("20.00"):
                assert successful_tx.amount == Decimal("80.00")
            else:
                assert successful_tx.amount == Decimal("50.00")
    finally:
        _cleanup_test_data(pg_engine, account_id)


def test_concurrent_duplicate_reference_submission(pg_engine: Engine) -> None:
    """Two concurrent requests with the exact same reference on the same account.

    Row locking and unique constraint guarantee that at most one creates
    a transaction and the second is rejected with DuplicateTransactionException.
    """
    with Session(pg_engine) as session:
        account = Account(name="Concurrency Duplicate Test", balance=Decimal("0.00"))
        session.add(account)
        session.commit()
        account_id = account.id

    barrier = threading.Barrier(2)
    results: list[dict[str, object]] = []

    def perform_credit(worker_id: int) -> None:
        with Session(pg_engine) as session:
            acc_repo = AccountRepository(session)
            tx_repo = TransactionRepository(session)
            service = TransactionService(acc_repo, tx_repo, session)

            payload = TransactionCreate(
                type="credit",
                amount=Decimal("100.00"),
                description=f"Credit from worker {worker_id}",
                reference_id="CONCUR-DUP-REF-001",
            )

            barrier.wait()
            try:
                res = service.create_transaction(account_id, payload)
                results.append({"status": "success", "worker": worker_id, "res": res})
            except DuplicateTransactionException as exc:
                results.append({"status": "duplicate", "worker": worker_id, "exc": exc})
            except Exception as exc:
                results.append({"status": "error", "worker": worker_id, "exc": exc})

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(perform_credit, 1)
            f2 = executor.submit(perform_credit, 2)
            f1.result()
            f2.result()

        successes = [r for r in results if r["status"] == "success"]
        duplicates = [r for r in results if r["status"] == "duplicate"]

        assert len(successes) == 1, f"Expected 1 success, got: {results}"
        assert len(duplicates) == 1, f"Expected 1 duplicate, got: {results}"

        with Session(pg_engine) as session:
            persisted_acc = session.get(Account, account_id)
            assert persisted_acc is not None
            assert persisted_acc.balance == Decimal("100.00")

            tx_count = session.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(
                    Transaction.account_id == account_id,
                    Transaction.reference_id == "CONCUR-DUP-REF-001",
                )
            )
            assert tx_count == 1
    finally:
        _cleanup_test_data(pg_engine, account_id)
