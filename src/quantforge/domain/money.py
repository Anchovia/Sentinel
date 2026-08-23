"""Decimal-only monetary boundary helpers."""

from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Annotated

from pydantic import BeforeValidator


class MonetaryValueError(ValueError):
    """Raised when a value cannot safely cross the monetary boundary."""


def as_decimal(value: Decimal | int | str) -> Decimal:
    """Convert an exact input into a finite Decimal.

    Binary floats and booleans are deliberately rejected because their implicit
    conversion can introduce accounting or order-sizing errors.
    """

    if isinstance(value, (bool, float)):
        raise MonetaryValueError("binary floats and booleans are forbidden for monetary values")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise MonetaryValueError(f"invalid monetary value: {value!r}") from exc
    if not result.is_finite():
        raise MonetaryValueError("monetary values must be finite")
    return result


def _validate_decimal(value: object) -> Decimal:
    if not isinstance(value, (Decimal, int, str)) or isinstance(value, bool):
        raise MonetaryValueError("monetary values must be Decimal, int, or decimal strings")
    return as_decimal(value)


type MonetaryDecimal = Annotated[Decimal, BeforeValidator(_validate_decimal)]


def quantize_down(value: Decimal | int | str, increment: Decimal | int | str) -> Decimal:
    """Round a value down to an exchange-defined positive increment."""

    decimal_value = as_decimal(value)
    decimal_increment = as_decimal(increment)
    if decimal_increment <= 0:
        raise MonetaryValueError("increment must be positive")
    steps = (decimal_value / decimal_increment).to_integral_value(rounding=ROUND_DOWN)
    return steps * decimal_increment
