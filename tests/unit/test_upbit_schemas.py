from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from quantforge.exchange.upbit.errors import MalformedUpbitPayload, UpbitPayloadError
from quantforge.exchange.upbit.schemas import (
    UpbitOrderbook,
    UpbitTicker,
    UpbitTrade,
    decode_json_object,
    parse_public_message,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "upbit"


@pytest.mark.parametrize(
    ("name", "expected_type"),
    [
        ("ticker.default.json", UpbitTicker),
        ("trade.default.json", UpbitTrade),
        ("orderbook.synthetic.json", UpbitOrderbook),
    ],
)
def test_official_and_synthetic_fixtures_parse(name: str, expected_type: type[object]) -> None:
    message, raw = parse_public_message((FIXTURES / name).read_bytes())
    assert isinstance(message, expected_type)
    assert message.code == "KRW-BTC"
    assert raw["code"] == "KRW-BTC"


def test_json_decoder_preserves_decimal_tokens() -> None:
    payload = decode_json_object('{"price": 0.10000000, "size": 1}')
    assert payload == {"price": Decimal("0.10000000"), "size": 1}


def test_ticker_additive_field_is_retained() -> None:
    raw = (FIXTURES / "ticker.default.json").read_text(encoding="utf-8")
    extended = raw[:-2] + ', "future_additive_field": "kept"\n}'
    message, payload = parse_public_message(extended)
    assert isinstance(message, UpbitTicker)
    assert message.model_extra == {"future_additive_field": "kept"}
    assert payload["future_additive_field"] == "kept"


@pytest.mark.parametrize("raw", ["not-json", "[]", "{}", '{"type":"unknown"}'])
def test_malformed_messages_are_rejected(raw: str) -> None:
    with pytest.raises(MalformedUpbitPayload):
        parse_public_message(raw)


def test_documented_error_is_typed() -> None:
    with pytest.raises(UpbitPayloadError, match="NO_TICKET") as raised:
        parse_public_message('{"error":{"name":"NO_TICKET","message":"ticket required"}}')
    assert raised.value.name == "NO_TICKET"


def test_malformed_error_shape_is_rejected() -> None:
    with pytest.raises(MalformedUpbitPayload, match="error payload"):
        parse_public_message('{"error":{"name":1}}')


def test_schema_rejects_binary_float_at_direct_boundary() -> None:
    payload = decode_json_object((FIXTURES / "trade.default.json").read_bytes())
    payload["trade_price"] = 0.1
    with pytest.raises(ValidationError):
        UpbitTrade.model_validate(payload)
