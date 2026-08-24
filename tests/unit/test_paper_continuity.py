from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from factories import BASE_TIME
from quantforge.runtime.paper_continuity import (
    PaperContinuityIntegrity,
    PaperRuntimeContinuityTracker,
    PaperRuntimeGapKind,
    PaperSessionEventType,
    PaperSessionOutcome,
    PaperSessionState,
    read_paper_runtime_session_ledger,
)


def test_clean_sessions_form_a_verified_chain_and_reach_horizons(tmp_path: Path) -> None:
    first = PaperRuntimeContinuityTracker(
        tmp_path,
        run_id=uuid4(),
        started_at_utc=BASE_TIME,
        stale_after_seconds=90,
    )
    started = first.start()
    assert started.integrity is PaperContinuityIntegrity.NEW
    first.observe(
        observed_at_utc=BASE_TIME + timedelta(seconds=1),
        websocket_connected=True,
        last_event_at_utc=BASE_TIME + timedelta(seconds=1),
        reconnect_count=0,
    )
    stopped = first.stop(
        stopped_at_utc=BASE_TIME + timedelta(seconds=2),
        failed=False,
        shutdown_reason="signal_sigterm",
        failure_type=None,
        last_event_at_utc=BASE_TIME + timedelta(seconds=1),
        reconnect_count=0,
    )
    assert stopped.current_session_state is PaperSessionState.STOPPED

    second_start = BASE_TIME + timedelta(seconds=3)
    second = PaperRuntimeContinuityTracker(
        tmp_path,
        run_id=uuid4(),
        started_at_utc=second_start,
        stale_after_seconds=90,
    )
    second.start()
    horizon_time = second_start + timedelta(hours=13)
    horizon = second.observe(
        observed_at_utc=horizon_time,
        websocket_connected=True,
        last_event_at_utc=horizon_time,
        reconnect_count=0,
    )

    assert horizon.integrity is PaperContinuityIntegrity.VERIFIED
    assert horizon.previous_session_outcome is PaperSessionOutcome.CLEAN_STOP
    assert horizon.session_count == 2
    assert horizon.clean_stop_count == 1
    assert horizon.unexpected_interruption_count == 0
    assert horizon.six_hour_baseline_ready is True
    assert horizon.twelve_hour_baseline_ready is True
    assert horizon.exchange_gap_completeness_claimed is False
    ledger = read_paper_runtime_session_ledger(first.ledger_path)
    assert [event.event_type for event in ledger] == [
        PaperSessionEventType.SESSION_STARTED,
        PaperSessionEventType.SESSION_STOPPED,
        PaperSessionEventType.SESSION_STARTED,
    ]


def test_missing_terminal_record_is_classified_on_next_start(tmp_path: Path) -> None:
    interrupted_id = uuid4()
    interrupted = PaperRuntimeContinuityTracker(
        tmp_path,
        run_id=interrupted_id,
        started_at_utc=BASE_TIME,
        stale_after_seconds=90,
    )
    interrupted.start()
    interrupted.observe(
        observed_at_utc=BASE_TIME + timedelta(seconds=15),
        websocket_connected=True,
        last_event_at_utc=BASE_TIME + timedelta(seconds=15),
        reconnect_count=0,
    )

    restarted = PaperRuntimeContinuityTracker(
        tmp_path,
        run_id=uuid4(),
        started_at_utc=BASE_TIME + timedelta(seconds=45),
        stale_after_seconds=90,
    )
    snapshot = restarted.start()

    assert snapshot.previous_session_outcome is PaperSessionOutcome.UNEXPECTED_INTERRUPTION
    assert snapshot.unexpected_interruption_count == 1
    assert snapshot.last_shutdown_reason == "terminal_record_missing"
    ledger = read_paper_runtime_session_ledger(restarted.ledger_path)
    interruption = next(
        event
        for event in ledger
        if event.event_type is PaperSessionEventType.UNEXPECTED_INTERRUPTION
    )
    assert interruption.related_run_id == interrupted_id
    assert interruption.duration_seconds == 30


def test_observed_disconnect_and_stale_feed_block_continuity_baselines(tmp_path: Path) -> None:
    tracker = PaperRuntimeContinuityTracker(
        tmp_path,
        run_id=uuid4(),
        started_at_utc=BASE_TIME,
        stale_after_seconds=5,
    )
    tracker.start()
    tracker.observe(
        observed_at_utc=BASE_TIME + timedelta(seconds=1),
        websocket_connected=True,
        last_event_at_utc=BASE_TIME + timedelta(seconds=1),
        reconnect_count=0,
    )
    disconnected = tracker.observe(
        observed_at_utc=BASE_TIME + timedelta(seconds=10),
        websocket_connected=False,
        last_event_at_utc=BASE_TIME + timedelta(seconds=1),
        reconnect_count=1,
    )
    assert disconnected.current_gap_kind is PaperRuntimeGapKind.WEBSOCKET_DISCONNECTED
    resumed = tracker.observe(
        observed_at_utc=BASE_TIME + timedelta(seconds=20),
        websocket_connected=True,
        last_event_at_utc=BASE_TIME + timedelta(seconds=20),
        reconnect_count=1,
    )
    stale = tracker.observe(
        observed_at_utc=BASE_TIME + timedelta(hours=13),
        websocket_connected=True,
        last_event_at_utc=BASE_TIME + timedelta(seconds=20),
        reconnect_count=1,
    )

    assert resumed.longest_current_session_gap_seconds == 10
    assert stale.current_gap_kind is PaperRuntimeGapKind.DATA_STALE
    assert stale.websocket_gap_count == 1
    assert stale.stale_data_gap_count == 1
    assert stale.reconnect_count == 1
    assert stale.six_hour_baseline_ready is False
    assert "WEBSOCKET_GAP_OBSERVED" in stale.six_hour_limitations
    assert "STALE_DATA_GAP_OBSERVED" in stale.six_hour_limitations
    assert "RECONNECT_OBSERVED" in stale.six_hour_limitations


def test_corrupt_continuity_evidence_degrades_without_blocking_public_observation(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "paper-runtime-session-ledger.jsonl"
    ledger.write_text("not-json\n", encoding="utf-8")
    tracker = PaperRuntimeContinuityTracker(
        tmp_path,
        run_id=uuid4(),
        started_at_utc=BASE_TIME,
        stale_after_seconds=90,
    )

    tracker.start()
    snapshot = tracker.observe(
        observed_at_utc=BASE_TIME + timedelta(seconds=1),
        websocket_connected=True,
        last_event_at_utc=BASE_TIME + timedelta(seconds=1),
        reconnect_count=0,
    )

    assert snapshot.integrity is PaperContinuityIntegrity.DEGRADED
    assert "CONTINUITY_INTEGRITY_DEGRADED" in snapshot.six_hour_limitations
    assert ledger.read_text(encoding="utf-8") == "not-json\n"


def test_newer_unclosed_ledger_run_wins_over_stale_terminal_lease(tmp_path: Path) -> None:
    first = PaperRuntimeContinuityTracker(
        tmp_path,
        run_id=uuid4(),
        started_at_utc=BASE_TIME,
        stale_after_seconds=90,
    )
    first.start()
    first.stop(
        stopped_at_utc=BASE_TIME + timedelta(seconds=1),
        failed=False,
        shutdown_reason="planned_stop",
        failure_type=None,
        last_event_at_utc=None,
        reconnect_count=0,
    )
    terminal_lease = first.lease_path.read_bytes()

    interrupted_id = uuid4()
    interrupted = PaperRuntimeContinuityTracker(
        tmp_path,
        run_id=interrupted_id,
        started_at_utc=BASE_TIME + timedelta(seconds=2),
        stale_after_seconds=90,
    )
    interrupted.start()
    interrupted.lease_path.write_bytes(terminal_lease)

    restarted = PaperRuntimeContinuityTracker(
        tmp_path,
        run_id=uuid4(),
        started_at_utc=BASE_TIME + timedelta(seconds=3),
        stale_after_seconds=90,
    )
    snapshot = restarted.start()

    assert snapshot.integrity is PaperContinuityIntegrity.VERIFIED
    assert snapshot.previous_session_outcome is PaperSessionOutcome.UNEXPECTED_INTERRUPTION
    assert snapshot.unexpected_interruption_count == 1
    ledger = read_paper_runtime_session_ledger(restarted.ledger_path)
    interruption = ledger[-2]
    assert interruption.event_type is PaperSessionEventType.UNEXPECTED_INTERRUPTION
    assert interruption.related_run_id == interrupted_id
    assert interruption.reason == "terminal_record_missing_without_matching_lease"


def test_terminal_ledger_and_active_lease_mismatch_degrades_without_rewrite(
    tmp_path: Path,
) -> None:
    first = PaperRuntimeContinuityTracker(
        tmp_path,
        run_id=uuid4(),
        started_at_utc=BASE_TIME,
        stale_after_seconds=90,
    )
    first.start()
    active_lease = first.lease_path.read_bytes()
    first.stop(
        stopped_at_utc=BASE_TIME + timedelta(seconds=1),
        failed=False,
        shutdown_reason="planned_stop",
        failure_type=None,
        last_event_at_utc=None,
        reconnect_count=0,
    )
    ledger_before_restart = first.ledger_path.read_bytes()
    first.lease_path.write_bytes(active_lease)

    restarted = PaperRuntimeContinuityTracker(
        tmp_path,
        run_id=uuid4(),
        started_at_utc=BASE_TIME + timedelta(seconds=2),
        stale_after_seconds=90,
    )
    snapshot = restarted.start()

    assert snapshot.integrity is PaperContinuityIntegrity.DEGRADED
    assert snapshot.previous_session_outcome is PaperSessionOutcome.UNKNOWN
    assert snapshot.last_shutdown_reason == "lease_ledger_state_mismatch"
    assert restarted.ledger_path.read_bytes() == ledger_before_restart
