import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from datetime import timedelta
from pathlib import Path

import pytest

from factories import make_orderbook_event, make_trade_event
from quantforge.config import Environment, QuantForgeSettings
from quantforge.domain import EventEnvelope
from quantforge.exchange.upbit.errors import MalformedUpbitPayload, UpbitAdapterError
from quantforge.operations import read_dashboard_snapshot
from quantforge.runtime.audit_exports import (
    WorkAuditExportWriter,
    WorkIncidentSnapshot,
    WorkModelSnapshot,
    WorkOperationsSnapshot,
    WorkPerformanceSnapshot,
    read_work_audit_baseline,
)
from quantforge.runtime.paper_recovery import (
    PaperRecoveryStatus,
    read_realtime_paper_recovery_checkpoint,
)
from quantforge.runtime.paper_supervisor import (
    PaperRuntimeBlocked,
    PaperRuntimePolicy,
    PaperRuntimeSnapshot,
    PaperRuntimeState,
    PaperRuntimeSupervisor,
    PublicStreamClient,
    read_paper_runtime_snapshot,
    validate_paper_runtime_settings,
)
from quantforge.runtime.realtime_decision import read_realtime_paper_decision_snapshot
from quantforge.runtime.realtime_pipeline import read_realtime_pipeline_snapshot
from quantforge.runtime.snapshots import DataQualitySnapshot
from quantforge.storage import RawStoragePolicy, read_raw_events


class FakePublicClient:
    def __init__(
        self,
        on_event: Callable[[EventEnvelope], Awaitable[None]],
        on_error: Callable[[UpbitAdapterError], Awaitable[None]],
        *,
        events: Sequence[EventEnvelope] = (),
        errors: Sequence[UpbitAdapterError] = (),
        failure: BaseException | None = None,
        block: bool = False,
    ) -> None:
        self._on_event = on_event
        self._on_error = on_error
        self._events = tuple(events)
        self._errors = tuple(errors)
        self._failure = failure
        self._block = block
        self._connected = False
        self._stop = asyncio.Event()
        self._reconnect_count = 0

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    async def run(self, *, max_messages: int | None = None) -> int:
        self._connected = True
        accepted = 0
        try:
            for error in self._errors:
                await self._on_error(error)
            for event in self._events:
                await self._on_event(event)
                accepted += 1
                if max_messages is not None and accepted >= max_messages:
                    break
            if self._failure is not None:
                raise self._failure
            if self._block:
                await self._stop.wait()
            return accepted
        finally:
            self._connected = False

    async def stop(self) -> None:
        self._stop.set()


def _factory(
    *,
    events: Sequence[EventEnvelope] = (),
    errors: Sequence[UpbitAdapterError] = (),
    failure: BaseException | None = None,
    block: bool = False,
) -> Callable[
    [Callable[[EventEnvelope], Awaitable[None]], Callable[[UpbitAdapterError], Awaitable[None]]],
    PublicStreamClient,
]:
    def build(
        on_event: Callable[[EventEnvelope], Awaitable[None]],
        on_error: Callable[[UpbitAdapterError], Awaitable[None]],
    ) -> PublicStreamClient:
        return FakePublicClient(
            on_event,
            on_error,
            events=events,
            errors=errors,
            failure=failure,
            block=block,
        )

    return build


def _supervisor(
    tmp_path: Path,
    factory: Callable[
        [
            Callable[[EventEnvelope], Awaitable[None]],
            Callable[[UpbitAdapterError], Awaitable[None]],
        ],
        PublicStreamClient,
    ],
    *,
    policy: PaperRuntimePolicy | None = None,
) -> PaperRuntimeSupervisor:
    return PaperRuntimeSupervisor(
        settings=QuantForgeSettings(),
        markets=("KRW-BTC",),
        streams=("ticker", "trade", "orderbook"),
        raw_output=tmp_path / "raw",
        output_root=tmp_path / "runtime",
        policy=policy or PaperRuntimePolicy(max_messages=2),
        client_factory=factory,
    )


@pytest.mark.asyncio
async def test_supervisor_commits_public_events_and_secret_free_status(tmp_path: Path) -> None:
    events = (
        make_orderbook_event(sequence=1, received_offset_ms=100),
        make_trade_event(sequence=2, exchange_offset_ms=200, received_offset_ms=250),
    )
    supervisor = _supervisor(
        tmp_path,
        _factory(
            events=events,
            errors=(MalformedUpbitPayload("isolated malformed payload"),),
        ),
    )

    snapshot = await supervisor.run()

    assert snapshot.state is PaperRuntimeState.STOPPED
    assert snapshot.accepted_messages == 2
    assert snapshot.committed_rows == 2
    assert snapshot.retained_rows == 2
    assert snapshot.retained_files > 0
    assert snapshot.retained_bytes > 0
    assert snapshot.schema_version == "paper-runtime-6"
    assert snapshot.storage_retention_days == 30
    assert snapshot.storage_max_bytes == 50 * 1024**3
    assert snapshot.disk_free_bytes is not None
    assert snapshot.parser_errors == 1
    assert snapshot.last_error_type == "MalformedUpbitPayload"
    assert snapshot.authentication_used is False
    assert snapshot.private_network_used is False
    assert snapshot.order_submission_available is False
    assert snapshot.live_submission_allowed is False
    assert len(read_raw_events(tmp_path / "raw")) == 2
    persisted = read_paper_runtime_snapshot(tmp_path / "runtime/ops/paper-runtime.json")
    assert persisted == snapshot
    dashboard = read_dashboard_snapshot(tmp_path / "runtime/ops/dashboard.json")
    assert dashboard.overview.trading_mode == "paper"
    assert dashboard.overview.live_submission_allowed is False
    assert dashboard.markets[0].market == "KRW-BTC"
    monitor = (tmp_path / "runtime/ops/paper-monitor.html").read_text(encoding="utf-8")
    assert "공개 데이터 모니터" in monitor
    assert "누적 저장 행" in monitor
    assert "저장 위치" in monitor
    assert "보관 한도" in monitor
    assert "자동 압축 / 정리" in monitor
    assert "2" in monitor
    assert "실제 주문" in monitor
    assert "완전 차단" in monitor
    assert 'http-equiv="refresh" content="5"' in monitor
    assert "raw_output" not in monitor
    assert "policy_hash" not in monitor
    assert "밀리초 처리" in monitor
    assert "처리 지연 p99" in monitor
    assert "현재 판단" in monitor
    assert "모의 판단" in monitor
    assert "모의 주문</span><strong>차단" in monitor
    assert "모델 검토" in monitor
    assert "재시작 복구" in monitor
    assert "재시작 복구</span><strong>신규" in monitor
    realtime = read_realtime_pipeline_snapshot(tmp_path / "runtime/ops/realtime-pipeline.json")
    assert realtime.processed_events == 2
    assert realtime.decision_state == "HOLD"
    assert realtime.order_submission_available is False
    decision = read_realtime_paper_decision_snapshot(
        tmp_path / "runtime/ops/realtime-paper-decision.json"
    )
    assert decision.processed_events == 2
    assert decision.model_approval_valid is False
    assert decision.recovery_status is PaperRecoveryStatus.NEW
    assert decision.recovery_blocked is False
    assert decision.paper_order_simulation_enabled is False
    assert decision.paper_orders == 0
    assert decision.paper_fills == 0
    assert decision.real_order_submission_available is False
    recovery = read_realtime_paper_recovery_checkpoint(
        tmp_path / "state/realtime-paper-recovery.json"
    )
    assert recovery.clean_shutdown is True
    assert recovery.recovery_blocked is False

    work_ops = WorkOperationsSnapshot.model_validate_json(
        (tmp_path / "runtime/ops/latest.json").read_bytes()
    )
    assert work_ops.runtime_state == "STOPPED"
    assert work_ops.trading_mode == "paper"
    assert work_ops.paper_orders == 0
    assert work_ops.private_websocket_state == "NOT_CONFIGURED"
    assert work_ops.safety.real_order_submission_available is False
    quality = DataQualitySnapshot.model_validate_json(
        (tmp_path / "runtime/data_quality/latest.json").read_bytes()
    )
    assert quality.schema_version == 3
    assert quality.source_kind == "public_paper_runtime_with_verified_storage"
    assert quality.measurement_status == "VERIFIED_STORAGE"
    assert quality.delivered_events == 2
    assert quality.indexed_event_count == 2
    assert quality.verified_manifest_count > 0
    assert quality.current_experiment_authorized is False
    assert quality.gap_measurement_supported is False
    incidents = WorkIncidentSnapshot.model_validate_json(
        (tmp_path / "runtime/incidents/open.json").read_bytes()
    )
    assert incidents.complete is False
    assert incidents.source_state == "NOT_CONFIGURED"
    performance = WorkPerformanceSnapshot.model_validate_json(
        (tmp_path / "runtime/performance/latest.json").read_bytes()
    )
    assert performance.representative is False
    assert performance.sample_state == "INSUFFICIENT_SAMPLE"
    assert performance.closed_trade_count is None
    models = WorkModelSnapshot.model_validate_json(
        (tmp_path / "runtime/models/latest.json").read_bytes()
    )
    assert models.active_approved_model_available is False
    assert models.drift_state == "INSUFFICIENT_SAMPLE"
    baselines = tuple((tmp_path / "runtime/baselines").glob("**/*-audit-baseline.json"))
    assert len(baselines) == 1
    audit_baseline = read_work_audit_baseline(baselines[0])
    assert audit_baseline.operations.runtime_state == "STARTING"
    assert audit_baseline.performance.representative is False
    bounded_root = tmp_path / "bounded-audit"
    bounded_writer = WorkAuditExportWriter(
        bounded_root,
        baseline_interval_seconds=60,
        baseline_retention_days=1,
    )
    bounded_writer.write(audit_baseline)
    bounded_writer.write(
        audit_baseline.model_copy(
            update={"generated_at_utc": audit_baseline.generated_at_utc + timedelta(seconds=30)}
        )
    )
    assert len(tuple((bounded_root / "baselines").glob("**/*.json"))) == 1
    bounded_writer.write(
        audit_baseline.model_copy(
            update={"generated_at_utc": audit_baseline.generated_at_utc + timedelta(seconds=61)}
        )
    )
    assert len(tuple((bounded_root / "baselines").glob("**/*.json"))) == 2
    bounded_writer.write(
        audit_baseline.model_copy(
            update={"generated_at_utc": audit_baseline.generated_at_utc + timedelta(days=2)}
        )
    )
    assert len(tuple((bounded_root / "baselines").glob("**/*.json"))) == 1

    serialized = json.loads((tmp_path / "runtime/ops/paper-runtime.json").read_text())
    forbidden = {"authorization", "access_key", "secret_key", "token", "password"}
    assert forbidden.isdisjoint(serialized)


@pytest.mark.asyncio
async def test_supervisor_retains_totals_across_runs(tmp_path: Path) -> None:
    first_event = make_trade_event(sequence=1, exchange_offset_ms=100, received_offset_ms=150)
    second_event = make_trade_event(sequence=2, exchange_offset_ms=200, received_offset_ms=250)
    first = _supervisor(tmp_path, _factory(events=(first_event,)))
    first_snapshot = await first.run()
    second = _supervisor(tmp_path, _factory(events=(second_event,)))

    second_snapshot = await second.run()

    assert first_snapshot.retained_rows == 1
    assert second_snapshot.committed_rows == 1
    assert second_snapshot.retained_rows == 2
    assert second_snapshot.retained_files == first_snapshot.retained_files + 1
    assert second_snapshot.retained_bytes > first_snapshot.retained_bytes
    decision = read_realtime_paper_decision_snapshot(
        tmp_path / "runtime/ops/realtime-paper-decision.json"
    )
    assert decision.recovery_status is PaperRecoveryStatus.VERIFIED_CLEAN
    assert decision.recovery_blocked is False


@pytest.mark.asyncio
async def test_duration_bound_stops_a_blocked_client_cleanly(tmp_path: Path) -> None:
    supervisor = _supervisor(
        tmp_path,
        _factory(block=True),
        policy=PaperRuntimePolicy(
            duration_seconds=0.01,
            heartbeat_seconds=0.002,
            flush_seconds=0.005,
        ),
    )

    snapshot = await supervisor.run()

    assert snapshot.state is PaperRuntimeState.STOPPED
    assert snapshot.shutdown_reason == "duration_elapsed"
    assert snapshot.websocket_connected is False


@pytest.mark.asyncio
async def test_external_stop_request_closes_recovery_checkpoint_cleanly(tmp_path: Path) -> None:
    supervisor = _supervisor(
        tmp_path,
        _factory(block=True),
        policy=PaperRuntimePolicy(heartbeat_seconds=0.01, flush_seconds=0.01),
    )
    task = asyncio.create_task(supervisor.run())
    await asyncio.sleep(0)

    await supervisor.request_stop(reason="signal_sigterm")
    snapshot = await task

    assert snapshot.state is PaperRuntimeState.STOPPED
    assert snapshot.shutdown_reason == "signal_sigterm"
    recovery = read_realtime_paper_recovery_checkpoint(
        tmp_path / "state/realtime-paper-recovery.json"
    )
    assert recovery.clean_shutdown is True
    assert recovery.recovery_blocked is False


@pytest.mark.asyncio
async def test_failure_is_persisted_and_propagated(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path, _factory(failure=RuntimeError("storage boundary failed")))

    with pytest.raises(RuntimeError, match="storage boundary failed"):
        await supervisor.run()

    snapshot = read_paper_runtime_snapshot(tmp_path / "runtime/ops/paper-runtime.json")
    assert snapshot.state is PaperRuntimeState.FAILED
    assert snapshot.failure_type == "RuntimeError"
    assert snapshot.order_submission_available is False


@pytest.mark.asyncio
async def test_bounded_storage_queue_overflow_fails_without_silent_loss(tmp_path: Path) -> None:
    events = tuple(
        make_trade_event(
            sequence=sequence,
            exchange_offset_ms=sequence * 10,
            received_offset_ms=sequence * 10 + 1,
        )
        for sequence in range(1, 5)
    )
    supervisor = _supervisor(
        tmp_path,
        _factory(events=events),
        policy=PaperRuntimePolicy(
            max_messages=4,
            storage_queue_capacity=1,
            storage_batch_size=512,
        ),
    )

    with pytest.raises(PaperRuntimeBlocked, match="queue overflowed"):
        await supervisor.run()

    snapshot = read_paper_runtime_snapshot(tmp_path / "runtime/ops/paper-runtime.json")
    assert snapshot.state is PaperRuntimeState.FAILED
    assert snapshot.storage_queue_overflows == 1
    assert snapshot.accepted_messages < len(events)
    assert snapshot.retained_rows == snapshot.accepted_messages


@pytest.mark.parametrize(
    "settings",
    [
        QuantForgeSettings(environment=Environment.PRODUCTION),
        QuantForgeSettings(trading_mode="replay"),
        QuantForgeSettings(upbit_access_key="access", upbit_secret_key="secret"),
        QuantForgeSettings(live_release_manifest_valid=True),
    ],
)
def test_public_runtime_refuses_non_paper_or_partially_open_settings(
    settings: QuantForgeSettings,
) -> None:
    with pytest.raises(PaperRuntimeBlocked):
        validate_paper_runtime_settings(settings)


def test_policy_rejects_unbounded_values() -> None:
    with pytest.raises(ValueError):
        PaperRuntimePolicy(heartbeat_seconds=0)
    with pytest.raises(ValueError):
        PaperRuntimePolicy(duration_seconds=0)
    with pytest.raises(ValueError):
        PaperRuntimePolicy(max_messages=0)
    with pytest.raises(ValueError):
        PaperRuntimePolicy(storage_queue_capacity=0)
    with pytest.raises(ValueError):
        PaperRuntimePolicy(storage_batch_size=0)


def test_supervisor_refuses_low_space_storage_root(tmp_path: Path) -> None:
    with pytest.raises(PaperRuntimeBlocked, match="safety floor"):
        _supervisor(
            tmp_path,
            _factory(),
            policy=PaperRuntimePolicy(storage_policy=RawStoragePolicy(min_free_bytes=10**18)),
        )


def test_version_one_runtime_snapshot_remains_read_compatible() -> None:
    payload = {
        "schema_version": "paper-runtime-1",
        "run_id": "00000000-0000-0000-0000-000000000001",
        "state": "RUNNING",
        "started_at_utc": "2026-08-23T00:00:00Z",
        "updated_at_utc": "2026-08-23T00:00:01Z",
        "markets": ["KRW-BTC"],
        "streams": ["ticker"],
        "accepted_messages": 0,
        "event_counts": [],
        "duplicate_messages": 0,
        "parser_errors": 0,
        "reconnects": 0,
        "committed_files": 0,
        "committed_rows": 0,
        "heartbeat_sequence": 1,
        "websocket_connected": True,
        "raw_output": "data/paper/raw",
        "policy_hash": "a" * 64,
    }

    parsed = PaperRuntimeSnapshot.model_validate(payload)

    assert parsed.schema_version == "paper-runtime-1"
    assert parsed.retained_files == 0
    assert parsed.retained_rows == 0
    assert parsed.retained_bytes == 0
    assert parsed.storage_queue_depth == 0
    assert parsed.storage_queue_capacity == 0
    assert parsed.storage_queue_overflows == 0
