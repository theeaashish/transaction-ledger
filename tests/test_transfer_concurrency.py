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
from app.modules.transfers.schemas import TransferCreate
from app.modules.transfers.service import TransferService
from app.repositories.account import AccountRepository
from app.repositories.transaction import TransactionRepository


def _cleanup_test_data(engine: Engine, account_ids: list[UUID]) -> None:
    """Safely remove test records by temporarily disabling the immutability trigger."""
    with engine.connect() as conn:
        conn.execute(
            text(
                "ALTER TABLE transactions "
                "DISABLE TRIGGER trg_prevent_transaction_modification"
            )
        )
        for account_id in account_ids:
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
        for account_id in account_ids:
            conn.execute(
                text("DELETE FROM accounts WHERE id = :account_id"),
                {"account_id": account_id},
            )
        conn.commit()


def test_concurrent_opposite_transfers_no_deadlock(pg_engine: Engine) -> None:
    """Simultaneous transfers in opposite directions (A->B and B->A) avoid deadlock.

    Without deterministic lock ordering, Thread 1 (A->B) locks A then requests B,
    while Thread 2 (B->A) locks B then requests A, creating a classical AB-BA deadlock.
    With deterministic sorted UUID row locking, both threads lock the lower UUID first,
    eliminating deadlocks. Both transfers succeed and conserve money.
    """
    with Session(pg_engine) as session:
        acc_a = Account(name="Opposite Transfer A", balance=Decimal("100.00"))
        acc_b = Account(name="Opposite Transfer B", balance=Decimal("100.00"))
        session.add_all([acc_a, acc_b])
        session.commit()
        id_a, id_b = acc_a.id, acc_b.id

    barrier = threading.Barrier(2)
    results: list[dict[str, object]] = []

    def perform_transfer(
        src_id: UUID, dst_id: UUID, amount_str: str, ref_id: str, label: str
    ) -> None:
        with Session(pg_engine) as session:
            acc_repo = AccountRepository(session)
            tx_repo = TransactionRepository(session)
            service = TransferService(acc_repo, tx_repo, session)

            payload = TransferCreate(
                source_account_id=src_id,
                destination_account_id=dst_id,
                amount=Decimal(amount_str),
                description=f"Transfer {label}",
                reference_id=ref_id,
            )

            barrier.wait()
            try:
                res = service.transfer(payload)
                results.append({"status": "success", "label": label, "res": res})
            except Exception as exc:
                results.append({"status": "error", "label": label, "exc": exc})

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(
                perform_transfer, id_a, id_b, "40.00", "CONCUR-OPP-A-TO-B", "A->B"
            )
            f2 = executor.submit(
                perform_transfer, id_b, id_a, "30.00", "CONCUR-OPP-B-TO-A", "B->A"
            )
            f1.result()
            f2.result()

        successes = [r for r in results if r["status"] == "success"]
        errors = [r for r in results if r["status"] == "error"]

        assert len(errors) == 0, f"Deadlock or error occurred: {errors}"
        assert len(successes) == 2, f"Expected 2 successful transfers, got: {results}"

        with Session(pg_engine) as session:
            persisted_a = session.get(Account, id_a)
            persisted_b = session.get(Account, id_b)
            assert persisted_a is not None and persisted_b is not None

            # A started with 100.00: -40.00 + 30.00 = 90.00
            # B started with 100.00: +40.00 - 30.00 = 110.00
            assert persisted_a.balance == Decimal("90.00")
            assert persisted_b.balance == Decimal("110.00")
            assert persisted_a.balance + persisted_b.balance == Decimal("200.00")

            # Exactly 4 transaction entries (2 debits + 2 credits)
            tx_count_a = session.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(Transaction.account_id == id_a)
            )
            tx_count_b = session.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(Transaction.account_id == id_b)
            )
            assert tx_count_a == 2
            assert tx_count_b == 2
    finally:
        _cleanup_test_data(pg_engine, [id_a, id_b])


def test_concurrent_duplicate_transfers_idempotency(pg_engine: Engine) -> None:
    """Simultaneous identical transfers: exactly one succeeds, one gets duplicate error.

    Both threads attempt to transfer the same amount with the exact same reference_id
    concurrently. Row locking and composite uniqueness guarantee idempotency.
    """
    with Session(pg_engine) as session:
        acc_a = Account(name="Dup Transfer Source", balance=Decimal("100.00"))
        acc_b = Account(name="Dup Transfer Dest", balance=Decimal("50.00"))
        session.add_all([acc_a, acc_b])
        session.commit()
        id_a, id_b = acc_a.id, acc_b.id

    barrier = threading.Barrier(2)
    results: list[dict[str, object]] = []

    def perform_transfer(worker_id: int) -> None:
        with Session(pg_engine) as session:
            acc_repo = AccountRepository(session)
            tx_repo = TransactionRepository(session)
            service = TransferService(acc_repo, tx_repo, session)

            payload = TransferCreate(
                source_account_id=id_a,
                destination_account_id=id_b,
                amount=Decimal("30.00"),
                description=f"Duplicate test from worker {worker_id}",
                reference_id="CONCUR-TRF-DUP-REF-001",
            )

            barrier.wait()
            try:
                res = service.transfer(payload)
                results.append({"status": "success", "worker": worker_id, "res": res})
            except DuplicateTransactionException as exc:
                results.append({"status": "duplicate", "worker": worker_id, "exc": exc})
            except Exception as exc:
                results.append({"status": "error", "worker": worker_id, "exc": exc})

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(perform_transfer, 1)
            f2 = executor.submit(perform_transfer, 2)
            f1.result()
            f2.result()

        successes = [r for r in results if r["status"] == "success"]
        duplicates = [r for r in results if r["status"] == "duplicate"]

        assert len(successes) == 1, f"Expected 1 success, got: {results}"
        assert len(duplicates) == 1, f"Expected 1 duplicate, got: {results}"

        with Session(pg_engine) as session:
            persisted_a = session.get(Account, id_a)
            persisted_b = session.get(Account, id_b)
            assert persisted_a is not None and persisted_b is not None

            # Balances updated only once
            assert persisted_a.balance == Decimal("70.00")
            assert persisted_b.balance == Decimal("80.00")

            # Exactly 2 transactions in database (1 debit on A, 1 credit on B)
            total_txs = session.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(Transaction.reference_id == "CONCUR-TRF-DUP-REF-001")
            )
            assert total_txs == 2
    finally:
        _cleanup_test_data(pg_engine, [id_a, id_b])


def test_concurrent_transfers_prevent_overdraft(pg_engine: Engine) -> None:
    """Two concurrent transfers competing for insufficient source balance.

    Account A has 100.00.
    Transfer 1: A -> B for 80.00.
    Transfer 2: A -> C for 70.00.
    Total requested: 150.00 > 100.00.
    Row-level locking guarantees exactly one transfer succeeds and the other
    fails with InsufficientBalanceException. Balance never goes negative.
    """
    with Session(pg_engine) as session:
        acc_a = Account(name="Overdraft Source A", balance=Decimal("100.00"))
        acc_b = Account(name="Dest B", balance=Decimal("0.00"))
        acc_c = Account(name="Dest C", balance=Decimal("0.00"))
        session.add_all([acc_a, acc_b, acc_c])
        session.commit()
        id_a, id_b, id_c = acc_a.id, acc_b.id, acc_c.id

    barrier = threading.Barrier(2)
    results: list[dict[str, object]] = []

    def perform_transfer(
        src_id: UUID, dst_id: UUID, amount_str: str, ref_id: str
    ) -> None:
        with Session(pg_engine) as session:
            acc_repo = AccountRepository(session)
            tx_repo = TransactionRepository(session)
            service = TransferService(acc_repo, tx_repo, session)

            payload = TransferCreate(
                source_account_id=src_id,
                destination_account_id=dst_id,
                amount=Decimal(amount_str),
                description=f"Transfer {amount_str}",
                reference_id=ref_id,
            )

            barrier.wait()
            try:
                res = service.transfer(payload)
                results.append({"status": "success", "amount": amount_str, "res": res})
            except InsufficientBalanceException as exc:
                results.append(
                    {"status": "insufficient_balance", "amount": amount_str, "exc": exc}
                )
            except Exception as exc:
                results.append({"status": "error", "amount": amount_str, "exc": exc})

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(
                perform_transfer, id_a, id_b, "80.00", "CONCUR-OVERDRAFT-80"
            )
            f2 = executor.submit(
                perform_transfer, id_a, id_c, "70.00", "CONCUR-OVERDRAFT-70"
            )
            f1.result()
            f2.result()

        successes = [r for r in results if r["status"] == "success"]
        insufficient = [r for r in results if r["status"] == "insufficient_balance"]

        assert len(successes) == 1, f"Expected 1 success, got: {results}"
        assert len(insufficient) == 1, (
            f"Expected 1 insufficient balance, got: {results}"
        )

        with Session(pg_engine) as session:
            persisted_a = session.get(Account, id_a)
            persisted_b = session.get(Account, id_b)
            persisted_c = session.get(Account, id_c)
            assert (
                persisted_a is not None
                and persisted_b is not None
                and persisted_c is not None
            )

            assert persisted_a.balance in [Decimal("20.00"), Decimal("30.00")]
            assert persisted_a.balance >= Decimal("0.00")

            if persisted_a.balance == Decimal("20.00"):
                assert persisted_b.balance == Decimal("80.00")
                assert persisted_c.balance == Decimal("0.00")
            else:
                assert persisted_b.balance == Decimal("0.00")
                assert persisted_c.balance == Decimal("70.00")

            total_money = (
                persisted_a.balance + persisted_b.balance + persisted_c.balance
            )
            assert total_money == Decimal("100.00")

            # Exactly 2 transactions created
            total_txs = session.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(Transaction.account_id.in_([id_a, id_b, id_c]))
            )
            assert total_txs == 2
    finally:
        _cleanup_test_data(pg_engine, [id_a, id_b, id_c])
