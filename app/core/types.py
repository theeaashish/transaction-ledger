from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, Field, PlainSerializer, WithJsonSchema


def serialize_money(value: Decimal) -> str:
    """Preserve decimal precision and always include two fractional digits."""
    return format(value, ".2f")


def validate_monetary_precision(value: Decimal) -> Decimal:
    """Ensure monetary values are finite and have at most two decimal places."""
    if not value.is_finite():
        raise ValueError("Monetary amount must be a finite number.")
    exp = value.as_tuple().exponent
    if isinstance(exp, int) and exp < -2:
        raise ValueError("Monetary precision must not exceed two decimal places.")
    return value


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

PositiveMoney = Annotated[
    Decimal,
    Field(
        gt=Decimal("0"),
        max_digits=18,
        decimal_places=2,
        description="Exact positive monetary amount with at most two decimal places.",
        examples=["100.00"],
    ),
    AfterValidator(validate_monetary_precision),
]
