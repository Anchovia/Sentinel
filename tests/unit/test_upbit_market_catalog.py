import json

import pytest

from quantforge.exchange.upbit.market_catalog import (
    MARKET_CATALOG_PATH,
    QUOTE_TICKERS_PATH,
    UPBIT_PUBLIC_HOST,
    UpbitMarketCatalogError,
    UpbitPublicMarketCatalog,
)


def _payloads() -> dict[str, bytes]:
    markets = [
        {
            "market": "KRW-BTC",
            "korean_name": "비트코인",
            "english_name": "Bitcoin",
            "market_event": {"warning": False, "caution": {"PRICE_FLUCTUATIONS": False}},
        },
        {
            "market": "KRW-ETH",
            "korean_name": "이더리움",
            "english_name": "Ethereum",
            "market_event": {"warning": False, "caution": {"PRICE_FLUCTUATIONS": True}},
        },
        {
            "market": "KRW-RISK",
            "korean_name": "위험",
            "english_name": "Risk",
            "market_event": {"warning": True, "caution": {"PRICE_FLUCTUATIONS": False}},
        },
        {
            "market": "BTC-ETH",
            "korean_name": "이더리움",
            "english_name": "Ethereum",
            "market_event": {"warning": False, "caution": {}},
        },
    ]
    tickers = [
        {"market": "KRW-BTC", "acc_trade_price_24h": 1000.1},
        {"market": "KRW-ETH", "acc_trade_price_24h": 2000.2},
        {"market": "KRW-RISK", "acc_trade_price_24h": 9999.9},
    ]
    return {
        MARKET_CATALOG_PATH: json.dumps(markets).encode(),
        QUOTE_TICKERS_PATH: json.dumps(tickers).encode(),
    }


def test_catalog_monitors_all_krw_but_excludes_warning_from_focus() -> None:
    payloads = _payloads()
    calls: list[tuple[str, str, float]] = []

    def fetch(host: str, path: str, timeout: float) -> bytes:
        calls.append((host, path, timeout))
        return payloads[path]

    universe = UpbitPublicMarketCatalog(fetcher=fetch).fetch_krw_universe(focus_limit=2)

    assert universe.monitored_markets == ("KRW-BTC", "KRW-ETH", "KRW-RISK")
    assert universe.eligible_markets == ("KRW-BTC", "KRW-ETH")
    assert universe.warning_markets == ("KRW-RISK",)
    assert universe.caution_markets == ("KRW-ETH",)
    assert universe.initial_focus_markets == ("KRW-ETH", "KRW-BTC")
    assert calls == [
        (UPBIT_PUBLIC_HOST, MARKET_CATALOG_PATH, 10.0),
        (UPBIT_PUBLIC_HOST, QUOTE_TICKERS_PATH, 10.0),
    ]


def test_catalog_fails_closed_on_invalid_public_schema() -> None:
    def fetch(_host: str, path: str, _timeout: float) -> bytes:
        if path == MARKET_CATALOG_PATH:
            return b'[{"market":"BTC-ETH"}]'
        return b"[]"

    with pytest.raises(UpbitMarketCatalogError, match="schema validation"):
        UpbitPublicMarketCatalog(fetcher=fetch).fetch_krw_universe(focus_limit=1)


@pytest.mark.parametrize("focus_limit", [0, -1])
def test_catalog_rejects_nonpositive_focus_limit(focus_limit: int) -> None:
    with pytest.raises(ValueError, match="focus limit"):
        UpbitPublicMarketCatalog(fetcher=lambda *_: b"[]").fetch_krw_universe(
            focus_limit=focus_limit
        )
