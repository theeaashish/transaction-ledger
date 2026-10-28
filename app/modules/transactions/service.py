import math
from collections.abc import Sequence
from dataclasses import dataclass
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
from app.db.models.transaction import Transaction
from app.modules.transactions.schemas import TransactionCreate, TransactionType
from app.repositories.account import AccountRepository
from app.repositories.transaction import TransactionRepository


@dataclass(frozen=True, slots=True)
class TransactionCreateResult:
    """Created transaction and resulting account balance."""

    transaction: Transaction
    balance_after: Decimal


@dataclass(frozen=True, slots=True)
class TransactionHistoryResult:
    """Paginated transaction history."""

    account_id: UUID
    current_page: int
    page_size: int
    total_records: int
    total_pages: int
    transactions: Sequence[Transaction]


class TransactionService:
    """Coordinate transaction operations and their database boundaries."""

    def __init__(
        self,
        account_repository: AccountRepository,
        transaction_repository: TransactionRepository,
        db: Session,
    ) -> None:
        self.account_repository = account_repository
        self.transaction_repository = transaction_repository
        self.db = db

    def create_transaction(
        self,
        account_id: UUID,
        payload: TransactionCreate,
    ) -> TransactionCreateResult:
        """Atomically update an account balance and create its ledger entry."""
        try:
            account = self.account_repository.get_by_id_for_update(account_id)
            if account is None:
                raise AccountNotFoundException()

            existing = self.transaction_repository.get_by_account_and_reference(
                account_id,
                payload.reference_id,
            )
            if existing is not None:
                raise DuplicateTransactionException()

            new_balance = self._calculate_new_balance(
                current_balance=account.balance,
                transaction_type=payload.type,
                amount=payload.amount,
            )

            account.balance = new_balance

            transaction = Transaction(
                account_id=account.id,
                type=payload.type,
                amount=payload.amount,
                description=payload.description,
                reference_id=payload.reference_id,
            )
            self.transaction_repository.add(transaction)

            self.db.commit()

        except IntegrityError as exc:
            self.db.rollback()

            if is_duplicate_reference_error(exc):
                raise DuplicateTransactionException() from exc

            raise

        except Exception:
            self.db.rollback()
            raise

        return TransactionCreateResult(
            transaction=transaction,
            balance_after=new_balance,
        )

    @staticmethod
    def _calculate_new_balance(
        *,
        current_balance: Decimal,
        transaction_type: TransactionType,
        amount: Decimal,
    ) -> Decimal:
        """Calculate the next balance or reject an invalid operation."""
        if transaction_type == "credit":
            return current_balance + amount

        if transaction_type == "debit":
            if current_balance < amount:
                raise InsufficientBalanceException()
            return current_balance - amount

        # Defensive guard if this method is called outside validated API input.
        raise ValidationException("Unsupported transaction type.")

    def get_history(
        self,
        account_id: UUID,
        *,
        transaction_type: TransactionType | None = None,
        page: int = 1,
        limit: int = 10,
    ) -> TransactionHistoryResult:
        """Retrieve filtered, paginated transaction history."""
        account = self.account_repository.get_by_id(account_id)
        if account is None:
            raise AccountNotFoundException()

        total_records = self.transaction_repository.count_by_account(
            account_id,
            transaction_type=transaction_type,
        )

        total_pages = math.ceil(total_records / limit) if total_records else 0

        transactions = self.transaction_repository.get_history(
            account_id,
            transaction_type=transaction_type,
            limit=limit,
            offset=(page - 1) * limit,
        )

        return TransactionHistoryResult(
            account_id=account.id,
            current_page=page,
            page_size=limit,
            total_records=total_records,
            total_pages=total_pages,
            transactions=transactions,
        )
