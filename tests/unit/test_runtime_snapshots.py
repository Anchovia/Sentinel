from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from factories import BASE_TIME, make_trade_bar, make_trade_event
from quantforge.features import FeatureSnapshot
from quantforge.replay import ReplayEngine
from quantforge.runtime import DataQualitySnapshot, write_data_quality_snapshot


def _phase2_inputs():  # type: ignore[no-untyped-def]
    event = make_trade_event(sequence=1, exchange_offset_ms=100, received_offset_ms=150)
    replay = ReplayEngine().run(
        [event],
        lambda item, clock: f"{clock.now}|{item.kind if hasattr(item, 'kind') else 'event'}",
    )
    bars = [make_trade_bar(index=index, close=100 + index) for index in range(3)]
    feature = FeatureSnapshot(
        feature_set="test",
        feature_version="1",
        market="KRW-BTC",
        event_time_utc=BASE_TIME + timedelta(seconds=3),
        available_at_utc=BASE_TIME + timedelta(seconds=3),
        computed_at_utc=BASE_TIME + timedelta(seconds=3),
        values={"value": 1.0},
        input_hash="a" * 64,
    )
    return replay, bars, [feature]


def test_data_quality_snapshot_is_atomic_and_secret_free(tmp_path: Path) -> None:
    replay, bars, features = _phase2_inputs()
    snapshot = DataQualitySnapshot.from_phase2(
        replay,
        bars,
        features,
        parse_errors=2,
        checksum_failures=1,
        generated_at_utc=BASE_TIME + timedelta(seconds=4),
    )
    assert snapshot.delivered_events == 1
    assert snapshot.complete_bar_count == 3
    assert snapshot.coverage_ratio == 1.0
    assert snapshot.feature_snapshot_hashes == (features[0].snapshot_hash,)

    path = write_data_quality_snapshot(snapshot, tmp_path / "data_quality")
    restored = DataQualitySnapshot.model_validate_json(path.read_bytes())
    assert restored == snapshot
    assert list(path.parent.glob("*.tmp")) == []
    assert "authorization" not in path.read_text(encoding="utf-8").lower()


def test_empty_bar_snapshot_has_zero_coverage() -> None:
    replay, _, _ = _phase2_inputs()
    snapshot = DataQualitySnapshot.from_phase2(replay, [], [], generated_at_utc=BASE_TIME)
    assert snapshot.coverage_ratio == 0.0
    assert snapshot.complete_bar_count == 0


def test_snapshot_rejects_naive_time_and_nonfinite_ratio() -> None:
    replay, bars, features = _phase2_inputs()
    snapshot = DataQualitySnapshot.from_phase2(replay, bars, features, generated_at_utc=BASE_TIME)
    with pytest.raises(ValidationError, match="UTC-aware"):
        DataQualitySnapshot.model_validate(
            {**snapshot.model_dump(), "generated_at_utc": BASE_TIME.replace(tzinfo=None)}
        )
    with pytest.raises(ValidationError):
        DataQualitySnapshot.model_validate(
            {**snapshot.model_dump(), "coverage_ratio": float("nan")}
        )


def test_live_data_quality_snapshot_is_partial_and_versioned() -> None:
    snapshot = DataQualitySnapshot.from_live_runtime(
        generated_at_utc=BASE_TIME,
        run_id="paper-run",
        policy_hash="a" * 64,
        accepted_messages=20,
        processed_events=18,
        event_counts=(("orderbook", 10), ("trade", 10)),
        duplicate_count=2,
        reconnects=0,
        parse_errors=0,
        feature_frames=18,
        inference_ready_frames=9,
        monitored_market_count=3,
        observed_market_count=2,
        last_event_at_utc=BASE_TIME,
        storage_queue_depth=0,
        storage_queue_overflows=0,
        processing_budget_breaches=0,
    )

    assert snapshot.schema_version == 2
    assert snapshot.source_kind == "public_paper_runtime"
    assert snapshot.measurement_status == "PARTIAL"
    assert snapshot.dataset_hash_scope == "live_counter_snapshot"
    assert snapshot.coverage_ratio == 0.5
    assert snapshot.gap_measurement_supported is False
    assert snapshot.checksum_measurement_supported is False
    assert len(snapshot.dataset_hash) == 64


def test_version_one_data_quality_snapshot_remains_readable() -> None:
    replay, _, _ = _phase2_inputs()
    current = DataQualitySnapshot.from_phase2(replay, [], [], generated_at_utc=BASE_TIME)
    legacy = current.model_dump()
    legacy["schema_version"] = 1
    for field in (
        "source_kind",
        "measurement_status",
        "dataset_hash_scope",
        "monitored_market_count",
        "observed_market_count",
        "last_event_at_utc",
        "event_counts",
        "storage_queue_depth",
        "storage_queue_overflows",
        "processing_budget_breaches",
        "gap_measurement_supported",
        "checksum_measurement_supported",
        "limitation",
    ):
        legacy.pop(field)

    restored = DataQualitySnapshot.model_validate(legacy)

    assert restored.schema_version == 1
    assert restored.source_kind == "deterministic_replay"
