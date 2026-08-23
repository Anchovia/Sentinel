from pydantic import ValidationError

from quantforge.config import QuantForgeSettings, TradingMode, get_settings


def test_defaults_are_paper_and_fail_closed() -> None:
    settings = QuantForgeSettings(_env_file=None)

    assert settings.trading_mode is TradingMode.PAPER
    assert settings.allow_order_submission is False
    assert settings.live_release_manifest_valid is False
    assert settings.risk_policy_approved is False
    assert settings.model_release_approved is False
    assert settings.operator_unlock_present is False


def test_credentials_must_be_configured_as_a_pair() -> None:
    try:
        QuantForgeSettings(_env_file=None, upbit_access_key="only-one-key")
    except ValidationError as exc:
        assert "configured as a pair" in str(exc)
    else:
        raise AssertionError("partial credential configuration must be rejected")


def test_log_level_is_normalized() -> None:
    settings = QuantForgeSettings(_env_file=None, log_level="warning")

    assert settings.log_level == "WARNING"


def test_invalid_log_level_is_rejected() -> None:
    try:
        QuantForgeSettings(_env_file=None, log_level="verbose")
    except ValidationError as exc:
        assert "unsupported log level" in str(exc)
    else:
        raise AssertionError("unknown log levels must be rejected")


def test_invalid_timezone_is_rejected() -> None:
    try:
        QuantForgeSettings(_env_file=None, display_timezone="Mars/Olympus")
    except ValidationError as exc:
        assert "unknown IANA timezone" in str(exc)
    else:
        raise AssertionError("unknown timezones must be rejected")


def test_get_settings_is_process_cached() -> None:
    get_settings.cache_clear()

    first = get_settings()
    second = get_settings()

    assert first is second
    get_settings.cache_clear()
