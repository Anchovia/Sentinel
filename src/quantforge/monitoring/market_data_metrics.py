"""Prometheus metrics for public market-data health and quality."""

from dataclasses import dataclass
from time import time

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from quantforge.domain import EventEnvelope


@dataclass(frozen=True, slots=True)
class MarketDataMetrics:
    registry: CollectorRegistry
    connected: Gauge
    received: Counter
    accepted: Counter
    rejected: Counter
    reconnects: Counter
    duplicates: Counter
    last_event_timestamp: Gauge
    ingress_latency_seconds: Histogram

    def record_event(self, event: EventEnvelope) -> None:
        labels = {"event_type": event.event_type}
        self.accepted.labels(**labels).inc()
        self.last_event_timestamp.labels(**labels).set(time())
        self.ingress_latency_seconds.labels(**labels).observe(event.ingress_latency_us / 1_000_000)
        if event.is_duplicate:
            self.duplicates.labels(**labels).inc()


def create_market_data_metrics(registry: CollectorRegistry | None = None) -> MarketDataMetrics:
    selected_registry = registry or CollectorRegistry(auto_describe=True)
    connected = Gauge(
        "quantforge_market_data_connected",
        "Whether the public market-data WebSocket is connected",
        registry=selected_registry,
    )
    received = Counter(
        "quantforge_market_data_messages_received_total",
        "Raw messages received before validation",
        registry=selected_registry,
    )
    accepted = Counter(
        "quantforge_market_data_messages_accepted_total",
        "Schema-valid normalized public events",
        ("event_type",),
        registry=selected_registry,
    )
    rejected = Counter(
        "quantforge_market_data_messages_rejected_total",
        "Messages isolated at the exchange trust boundary",
        ("reason",),
        registry=selected_registry,
    )
    reconnects = Counter(
        "quantforge_market_data_reconnects_total",
        "Reconnect sleeps entered after transport failure",
        registry=selected_registry,
    )
    duplicates = Counter(
        "quantforge_market_data_duplicates_total",
        "Exact raw-payload duplicates detected",
        ("event_type",),
        registry=selected_registry,
    )
    last_event_timestamp = Gauge(
        "quantforge_market_data_last_event_timestamp_seconds",
        "Local wall-clock time of the last accepted event",
        ("event_type",),
        registry=selected_registry,
    )
    ingress_latency_seconds = Histogram(
        "quantforge_market_data_ingress_latency_seconds",
        "Receive wall clock minus exchange timestamp",
        ("event_type",),
        buckets=(-1.0, -0.25, 0.0, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0, 30.0),
        registry=selected_registry,
    )
    return MarketDataMetrics(
        registry=selected_registry,
        connected=connected,
        received=received,
        accepted=accepted,
        rejected=rejected,
        reconnects=reconnects,
        duplicates=duplicates,
        last_event_timestamp=last_event_timestamp,
        ingress_latency_seconds=ingress_latency_seconds,
    )
