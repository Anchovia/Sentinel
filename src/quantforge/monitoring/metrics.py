"""Prometheus metrics with an app-local registry for deterministic tests."""

from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Gauge

from quantforge.config import QuantForgeSettings
from quantforge.runtime import LiveSubmissionGuard


@dataclass(frozen=True, slots=True)
class FoundationMetrics:
    registry: CollectorRegistry
    live_submission_allowed: Gauge
    trading_mode_info: Gauge


def create_foundation_metrics(settings: QuantForgeSettings) -> FoundationMetrics:
    registry = CollectorRegistry(auto_describe=True)
    live_submission_allowed = Gauge(
        "quantforge_live_submission_allowed",
        "Whether every mandatory live submission gate is currently satisfied",
        registry=registry,
    )
    trading_mode_info = Gauge(
        "quantforge_trading_mode_info",
        "Current configured trading mode as a one-hot labeled gauge",
        labelnames=("mode",),
        registry=registry,
    )
    live_submission_allowed.set(float(LiveSubmissionGuard.evaluate(settings).allowed))
    trading_mode_info.labels(mode=settings.trading_mode.value).set(1.0)
    return FoundationMetrics(registry, live_submission_allowed, trading_mode_info)
