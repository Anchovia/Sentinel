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
