from typing import Any

CREATE_TRANSACTION_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "Account does not exist (ACCOUNT_NOT_FOUND)."},
    409: {
        "description": (
            "Duplicate transaction reference or insufficient balance "
            "(DUPLICATE_TRANSACTION / INSUFFICIENT_BALANCE)."
        )
    },
    422: {"description": "Invalid request (VALIDATION_ERROR)."},
    500: {"description": "Unexpected failure (INTERNAL_SERVER_ERROR)."},
}

GET_HISTORY_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "Account does not exist (ACCOUNT_NOT_FOUND)."},
    422: {"description": "Invalid query parameters (VALIDATION_ERROR)."},
    500: {"description": "Unexpected failure (INTERNAL_SERVER_ERROR)."},
}
