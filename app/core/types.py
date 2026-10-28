from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer, WithJsonSchema


def serialize_money(value: Decimal) -> str:
    """Preserve decimal precision and always include two fractional digits."""
    return format(value, ".2f")


Money = Annotated[
    Decimal,
    PlainSerializer(serialize_money, return_type=str, when_used="json"),
    WithJsonSchema(
        {
            "type": "string",
            "pattern": r"^\d+\.\d{2}$",
            "description": "Exact monetary amount with two fractional digits.",
            "examples": ["0.00", "125.50"],
        },
        mode="serialization",
    ),
]
