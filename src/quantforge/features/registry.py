"""Feature definitions and stable manifest hashing."""

from hashlib import sha256
from typing import Literal

import orjson
from pydantic import BaseModel, ConfigDict, Field

type FeatureFamily = Literal["orderbook", "trade", "volatility"]


class FeatureDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: str = Field(min_length=1)
    family: FeatureFamily
    unit: str = Field(min_length=1)
    description: str = Field(min_length=1)


class FeatureRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, FeatureDefinition] = {}

    def register(self, definition: FeatureDefinition) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"feature already registered: {definition.name}")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> FeatureDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise KeyError(f"unknown feature: {name}") from exc

    @property
    def definitions(self) -> tuple[FeatureDefinition, ...]:
        return tuple(self._definitions[name] for name in sorted(self._definitions))

    @property
    def manifest_hash(self) -> str:
        payload = orjson.dumps(
            [definition.model_dump(mode="json") for definition in self.definitions],
            option=orjson.OPT_SORT_KEYS,
        )
        return sha256(payload).hexdigest()


def default_feature_registry() -> FeatureRegistry:
    registry = FeatureRegistry()
    groups: dict[FeatureFamily, dict[str, str]] = {
        "orderbook": {
            "best_bid": "quote_currency",
            "best_ask": "quote_currency",
            "mid_price": "quote_currency",
            "spread": "quote_currency",
            "relative_spread": "ratio",
            "weighted_mid": "quote_currency",
            "microprice": "quote_currency",
            "bid_depth_1": "base_currency",
            "ask_depth_1": "base_currency",
            "bid_depth_5": "base_currency",
            "ask_depth_5": "base_currency",
            "bid_depth_15": "base_currency",
            "ask_depth_15": "base_currency",
            "bid_depth_30": "base_currency",
            "ask_depth_30": "base_currency",
            "queue_imbalance_1": "ratio",
            "queue_imbalance_5": "ratio",
            "queue_imbalance_15": "ratio",
            "queue_imbalance_30": "ratio",
            "snapshot_derived_ofi_1": "base_currency",
            "snapshot_derived_ofi_5": "base_currency",
            "snapshot_derived_ofi_15": "base_currency",
            "snapshot_derived_ofi_30": "base_currency",
            "orderbook_slope_bid": "ratio_per_level",
            "orderbook_slope_ask": "ratio_per_level",
            "depth_concentration": "ratio",
            "book_pressure": "ratio",
            "price_impact_buy": "ratio",
            "price_impact_sell": "ratio",
            "estimated_market_buy_slippage": "ratio",
            "estimated_market_sell_slippage": "ratio",
            "book_resilience_proxy": "ratio",
            "spread_zscore": "zscore",
            "depth_zscore": "zscore",
        },
        "trade": {
            "signed_trade_volume": "base_currency",
            "aggressive_buy_volume": "base_currency",
            "aggressive_sell_volume": "base_currency",
            "trade_imbalance": "ratio",
            "trade_arrival_rate": "trades_per_second",
            "interarrival_mean": "seconds",
            "interarrival_variance": "seconds_squared",
            "volume_weighted_trade_imbalance": "ratio",
            "large_trade_count": "count",
            "large_trade_volume": "base_currency",
            "buy_run_length": "count",
            "sell_run_length": "count",
            "trade_price_vs_mid": "ratio",
            "short_term_vwap": "quote_currency",
            "vwap_deviation": "ratio",
            "trade_intensity_zscore": "zscore",
            "volume_shock": "ratio",
        },
        "volatility": {
            "log_return": "log_ratio",
            "multi_horizon_return_1": "log_ratio",
            "multi_horizon_return_5": "log_ratio",
            "realized_variance": "log_ratio_squared",
            "realized_volatility": "log_ratio",
            "bipower_variation": "log_ratio_squared",
            "jump_proxy": "log_ratio_squared",
            "atr_baseline": "quote_currency",
            "range_volatility": "log_ratio",
            "ewma_volatility": "log_ratio",
            "har_like_short_rv": "log_ratio_squared",
            "har_like_medium_rv": "log_ratio_squared",
            "har_like_long_rv": "log_ratio_squared",
            "volatility_of_volatility": "log_ratio_squared",
            "downside_volatility": "log_ratio",
        },
    }
    for family, definitions in groups.items():
        for name, unit in definitions.items():
            registry.register(
                FeatureDefinition(
                    name=name,
                    version="1",
                    family=family,
                    unit=unit,
                    description=f"QuantForge causal {family} feature: {name}",
                )
            )
    return registry
