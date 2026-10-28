from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AccountNotFoundException,
    DuplicateTransactionException,
    InsufficientBalanceException,
    ValidationException,
)
from app.db.errors import is_duplicate_reference_error
from app.db.models import Account, Transaction
from app.modules.transfers.schemas import TransferCreate
from app.repositories.account import AccountRepository
from app.repositories.transaction import TransactionRepository


@dataclass(frozen=True, slots=True)
class TransferResult:
    """Outcome of an atomic transfer operation across two accounts."""

    reference_id: str
    amount: Decimal
    source_account_id: UUID
    source_balance: Decimal
    destination_account_id: UUID
    destination_balance: Decimal
    debit_transaction_id: UUID
    credit_transaction_id: UUID
    created_at: datetime


class TransferService:
    """Coordinates atomic fund transfers between accounts."""

    def __init__(
        self,
        account_repository: AccountRepository,
        transaction_repository: TransactionRepository,
        db: Session,
    ) -> None:
        self.account_repository = account_repository
        self.transaction_repository = transaction_repository
        self.db = db

    def transfer(self, payload: TransferCreate) -> TransferResult:
        """Atomically execute a transfer between two distinct accounts."""
        # 1. Defensively validate distinct accounts
        if payload.source_account_id == payload.destination_account_id:
            raise ValidationException(
                "Source and destination accounts must be different."
            )

        try:
            # 2. Acquire row locks in deterministic order to prevent deadlocks
            lock_ids = sorted(
                [payload.source_account_id, payload.destination_account_id]
            )
            locked_accounts: dict[UUID, Account] = {}

            for account_id in lock_ids:
                account = self.account_repository.get_by_id_for_update(account_id)
                if account is None:
                    raise AccountNotFoundException()
                locked_accounts[account_id] = account

            source_account = locked_accounts[payload.source_account_id]
            destination_account = locked_accounts[payload.destination_account_id]

            # 3. Check reference uniqueness on both participating accounts
            source_existing = self.transaction_repository.get_by_account_and_reference(
                source_account.id, payload.reference_id
            )
            if source_existing is not None:
                raise DuplicateTransactionException()

            dest_existing = self.transaction_repository.get_by_account_and_reference(
                destination_account.id, payload.reference_id
            )
            if dest_existing is not None:
                raise DuplicateTransactionException()

            # 4. Verify source account has sufficient funds
            if source_account.balance < payload.amount:
                raise InsufficientBalanceException()

            # 5. Compute resulting balances using exact Decimal arithmetic
            new_source_balance = source_account.balance - payload.amount
            new_destination_balance = destination_account.balance + payload.amount

            # 6. Apply balance mutations
            source_account.balance = new_source_balance
            destination_account.balance = new_destination_balance

            # 7. Insert debit transaction for source and
            #    credit transaction for destination
            debit_tx = Transaction(
                account_id=source_account.id,
                type="debit",
                amount=payload.amount,
                description=payload.description,
                reference_id=payload.reference_id,
            )
            credit_tx = Transaction(
                account_id=destination_account.id,
                type="credit",
                amount=payload.amount,
                description=payload.description,
                reference_id=payload.reference_id,
            )

            self.transaction_repository.add(debit_tx)
            self.transaction_repository.add(credit_tx)

            # 8. Single atomic commit
            self.db.commit()

        except IntegrityError as exc:
            self.db.rollback()
            if is_duplicate_reference_error(exc):
                raise DuplicateTransactionException() from exc
            raise

        except Exception:
            self.db.rollback()
            raise

        return TransferResult(
            reference_id=payload.reference_id,
            amount=payload.amount,
            source_account_id=source_account.id,
            source_balance=new_source_balance,
            destination_account_id=destination_account.id,
            destination_balance=new_destination_balance,
            debit_transaction_id=debit_tx.id,
            credit_transaction_id=credit_tx.id,
            created_at=debit_tx.created_at,
        )
