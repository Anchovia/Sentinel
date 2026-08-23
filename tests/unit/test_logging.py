import json
from io import StringIO

import pytest
import structlog

from quantforge.monitoring.logging import configure_logging
from quantforge.security import REDACTED


def test_structured_logging_redacts_before_json_render() -> None:
    stream = StringIO()
    configure_logging(stream=stream)

    structlog.get_logger("test").info(
        "request complete",
        market="KRW-BTC",
        authorization="Bearer this-token-must-never-appear",
    )
    payload = json.loads(stream.getvalue())

    assert payload["event"] == "request complete"
    assert payload["market"] == "KRW-BTC"
    assert payload["authorization"] == REDACTED
    assert "this-token" not in stream.getvalue()


def test_structured_logging_rejects_unknown_level() -> None:
    with pytest.raises(ValueError, match="unsupported log level"):
        configure_logging("verbose")
