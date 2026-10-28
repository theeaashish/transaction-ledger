from typing import Any

TRANSFER_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {
        "description": (
            "Source or destination account does not exist (ACCOUNT_NOT_FOUND)."
        )
    },
    409: {
        "description": (
            "Duplicate transaction reference or insufficient funds "
            "(DUPLICATE_TRANSACTION / INSUFFICIENT_BALANCE)."
        )
    },
    422: {
        "description": "Invalid transfer request or self-transfer (VALIDATION_ERROR)."
    },
    500: {"description": "Unexpected failure (INTERNAL_SERVER_ERROR)."},
}
