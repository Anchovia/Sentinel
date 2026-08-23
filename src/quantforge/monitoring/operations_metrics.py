"""Prometheus instruments for operations, incidents, and emergency controls."""

from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter, Gauge


@dataclass(frozen=True, slots=True)
class OperationsMetrics:
    unauthorized_requests: Counter
    control_requests: Counter
    open_incidents: Gauge
    unknown_orders: Gauge
    balance_mismatch: Gauge
    daily_pnl_krw: Gauge
    drawdown_ratio: Gauge
    exposure_krw: Gauge
    kill_switch_active: Gauge
    disk_free_bytes: Gauge
    reconciliation_age_seconds: Gauge
    backup_verified: Gauge


def create_operations_metrics(registry: CollectorRegistry) -> OperationsMetrics:
    return OperationsMetrics(
        unauthorized_requests=Counter(
            "quantforge_dashboard_unauthorized_total",
            "Rejected dashboard authentication attempts",
            registry=registry,
        ),
        control_requests=Counter(
            "quantforge_emergency_control_requests_total",
            "Audited emergency-control requests",
            ("action", "status"),
            registry=registry,
        ),
        open_incidents=Gauge(
            "quantforge_open_incidents",
            "Current open or acknowledged incidents by severity",
            ("severity",),
            registry=registry,
        ),
        unknown_orders=Gauge(
            "quantforge_unknown_orders", "Current unresolved UNKNOWN orders", registry=registry
        ),
        balance_mismatch=Gauge(
            "quantforge_balance_mismatch",
            "Whether exact balance reconciliation currently differs",
            registry=registry,
        ),
        daily_pnl_krw=Gauge(
            "quantforge_daily_pnl_krw", "Paper daily net PnL in KRW", registry=registry
        ),
        drawdown_ratio=Gauge(
            "quantforge_drawdown_ratio", "Current paper drawdown ratio", registry=registry
        ),
        exposure_krw=Gauge(
            "quantforge_exposure_krw", "Current paper exposure in KRW", registry=registry
        ),
        kill_switch_active=Gauge(
            "quantforge_kill_switch_active",
            "Whether the local kill switch blocks new orders",
            registry=registry,
        ),
        disk_free_bytes=Gauge(
            "quantforge_disk_free_bytes",
            "Free bytes on the monitored data volume",
            registry=registry,
        ),
        reconciliation_age_seconds=Gauge(
            "quantforge_reconciliation_age_seconds",
            "Age of the latest successful reconciliation",
            registry=registry,
        ),
        backup_verified=Gauge(
            "quantforge_backup_verified",
            "Whether the latest local backup passed checksum verification",
            registry=registry,
        ),
    )
