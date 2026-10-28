"""Database error classification and diagnostic helpers."""

from sqlalchemy.exc import IntegrityError


def is_duplicate_reference_error(exc: IntegrityError) -> bool:
    """Identify a duplicate account-scoped transaction reference."""
    diag = getattr(exc.orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name is not None:
        return constraint_name == "uq_account_reference_id"

    # Fallback for SQLite-based tests.
    message = str(exc.orig or exc)
    return (
        "uq_account_reference_id" in message
        or "transactions.account_id, transactions.reference_id" in message
    )
