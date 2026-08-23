from quantforge.security import REDACTED, redact


def test_sensitive_mapping_values_are_redacted_recursively() -> None:
    event = {
        "market": "KRW-BTC",
        "authorization": "Bearer abc.def.ghi",
        "nested": {"secret_key": "do-not-log", "status": "ok"},
    }

    assert redact(event) == {
        "market": "KRW-BTC",
        "authorization": REDACTED,
        "nested": {"secret_key": REDACTED, "status": "ok"},
    }


def test_bearer_and_jwt_are_removed_from_free_text() -> None:
    text = "request used Bearer abcDEF-123._~+/= then eyJabc.def.ghi"
    redacted = redact(text)

    assert isinstance(redacted, str)
    assert "abcDEF" not in redacted
    assert "eyJabc" not in redacted
    assert REDACTED in redacted


def test_sequences_and_plain_values_keep_shape() -> None:
    value = ("safe", [1, {"password": "hidden"}], b"bytes")

    assert redact(value) == ("safe", [1, {"password": REDACTED}], b"bytes")
