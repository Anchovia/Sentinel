"""Credential-free discovery of the current Upbit KRW paper universe."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from http.client import HTTPSConnection

import orjson
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from quantforge.domain import MonetaryDecimal

UPBIT_PUBLIC_HOST = "api.upbit.com"
MARKET_CATALOG_PATH = "/v1/market/all?is_details=true"
QUOTE_TICKERS_PATH = "/v1/ticker/all?quote_currencies=KRW"
MAX_PUBLIC_RESPONSE_BYTES = 8 * 1024 * 1024


class UpbitMarketCatalogError(RuntimeError):
    """Raised when the public market catalog cannot be trusted."""


class UpbitMarketEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    warning: bool
    caution: dict[str, bool]


class UpbitMarketPair(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    market: str = Field(pattern=r"^[A-Z0-9]+-[A-Z0-9]+$")
    korean_name: str = Field(min_length=1)
    english_name: str = Field(min_length=1)
    market_event: UpbitMarketEvent


class UpbitQuoteTicker(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    acc_trade_price_24h: MonetaryDecimal = Field(ge=0)


class UpbitKrwUniverse(BaseModel):
    """Versioned startup evidence for broad monitoring and focused processing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "upbit-krw-universe-1"
    discovered_at_utc: datetime
    monitored_markets: tuple[str, ...] = Field(min_length=1)
    eligible_markets: tuple[str, ...] = Field(min_length=1)
    warning_markets: tuple[str, ...]
    caution_markets: tuple[str, ...]
    initial_focus_markets: tuple[str, ...] = Field(min_length=1)
    market_set_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_membership(self) -> "UpbitKrwUniverse":
        monitored = set(self.monitored_markets)
        if not set(self.eligible_markets).issubset(monitored):
            raise ValueError("eligible markets must belong to the monitored universe")
        if not set(self.warning_markets).issubset(monitored):
            raise ValueError("warning markets must belong to the monitored universe")
        if not set(self.initial_focus_markets).issubset(set(self.eligible_markets)):
            raise ValueError("focus markets must be eligible")
        if set(self.eligible_markets) & set(self.warning_markets):
            raise ValueError("warning markets cannot enter the eligible universe")
        return self


type PublicJsonFetcher = Callable[[str, str, float], bytes]


def _fetch_public_json(host: str, path: str, timeout_seconds: float) -> bytes:
    if host != UPBIT_PUBLIC_HOST or not path.startswith("/v1/"):
        raise UpbitMarketCatalogError("public market discovery only permits the Upbit HTTPS host")
    connection = HTTPSConnection(host, timeout=timeout_seconds)
    try:
        connection.request(
            "GET",
            path,
            headers={"Accept": "application/json", "User-Agent": "QuantForge/0.1 public-paper"},
        )
        response = connection.getresponse()
        body = response.read(MAX_PUBLIC_RESPONSE_BYTES + 1)
        if response.status != 200:
            raise UpbitMarketCatalogError(f"Upbit public catalog returned HTTP {response.status}")
        if len(body) > MAX_PUBLIC_RESPONSE_BYTES:
            raise UpbitMarketCatalogError("Upbit public catalog response exceeded the size limit")
        return body
    except (OSError, TimeoutError) as exc:
        raise UpbitMarketCatalogError("Upbit public catalog request failed") from exc
    finally:
        connection.close()


class UpbitPublicMarketCatalog:
    """Resolve all KRW pairs and a liquid initial focus without credentials."""

    def __init__(
        self,
        *,
        fetcher: PublicJsonFetcher = _fetch_public_json,
        timeout_seconds: float = 10.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("catalog timeout must be positive")
        self._fetcher = fetcher
        self._timeout_seconds = timeout_seconds

    def fetch_krw_universe(self, *, focus_limit: int) -> UpbitKrwUniverse:
        if focus_limit < 1:
            raise ValueError("focus limit must be positive")
        markets_raw = self._fetcher(UPBIT_PUBLIC_HOST, MARKET_CATALOG_PATH, self._timeout_seconds)
        tickers_raw = self._fetcher(UPBIT_PUBLIC_HOST, QUOTE_TICKERS_PATH, self._timeout_seconds)
        try:
            market_payload = json.loads(markets_raw, parse_float=Decimal)
            ticker_payload = json.loads(tickers_raw, parse_float=Decimal)
            if not isinstance(market_payload, list) or not isinstance(ticker_payload, list):
                raise UpbitMarketCatalogError("Upbit public catalog roots must be lists")
            pairs = tuple(UpbitMarketPair.model_validate(item) for item in market_payload)
            tickers = tuple(UpbitQuoteTicker.model_validate(item) for item in ticker_payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise UpbitMarketCatalogError("Upbit public catalog failed schema validation") from exc

        krw_pairs = tuple(
            sorted(
                (item for item in pairs if item.market.startswith("KRW-")),
                key=lambda item: item.market,
            )
        )
        if not krw_pairs:
            raise UpbitMarketCatalogError("Upbit public catalog returned no KRW markets")
        monitored = tuple(item.market for item in krw_pairs)
        warning = tuple(item.market for item in krw_pairs if item.market_event.warning)
        caution = tuple(
            item.market for item in krw_pairs if any(item.market_event.caution.values())
        )
        warning_set = set(warning)
        eligible = tuple(market for market in monitored if market not in warning_set)
        turnover = {
            item.market: item.acc_trade_price_24h
            for item in tickers
            if item.market in set(eligible)
        }
        ranked = tuple(
            sorted(eligible, key=lambda market: (-turnover.get(market, Decimal(0)), market))
        )
        focus = ranked[: min(focus_limit, len(ranked))]
        if not focus:
            raise UpbitMarketCatalogError("Upbit public catalog produced no eligible focus market")

        market_set_bytes = orjson.dumps(monitored)
        evidence_hash = sha256(markets_raw + b"\n" + tickers_raw).hexdigest()
        return UpbitKrwUniverse(
            discovered_at_utc=datetime.now(UTC),
            monitored_markets=monitored,
            eligible_markets=eligible,
            warning_markets=warning,
            caution_markets=caution,
            initial_focus_markets=focus,
            market_set_hash=sha256(market_set_bytes).hexdigest(),
            evidence_hash=evidence_hash,
        )
