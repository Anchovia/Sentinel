from decimal import Decimal

import pytest

from quantforge.domain.money import MonetaryValueError, as_decimal, quantize_down


@pytest.mark.parametrize("value", [0.1, True, False])
def test_binary_float_and_bool_are_rejected(value: object) -> None:
    with pytest.raises(MonetaryValueError):
        as_decimal(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_values_are_rejected(value: str) -> None:
    with pytest.raises(MonetaryValueError):
        as_decimal(value)


def test_exact_values_are_preserved() -> None:
    assert as_decimal("0.10000001") == Decimal("0.10000001")
    assert as_decimal(10000) == Decimal("10000")


def test_quantize_down_uses_exchange_increment() -> None:
    assert quantize_down("1234.567", "0.01") == Decimal("1234.56")


def test_quantize_requires_positive_increment() -> None:
    with pytest.raises(MonetaryValueError, match="positive"):
        quantize_down("100", "0")


def test_invalid_decimal_text_is_rejected() -> None:
    with pytest.raises(MonetaryValueError, match="invalid"):
        as_decimal("not-a-number")
