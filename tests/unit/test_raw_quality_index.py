from datetime import timedelta
from pathlib import Path

import pytest

from factories import BASE_TIME, make_orderbook_event, make_ticker_event, make_trade_event
from quantforge.domain import EventEnvelope
from quantforge.storage import (
    ParquetRawEventWriter,
    RawDataIntegrityError,
    RawResearchReadinessPolicy,
    RawStoragePolicy,
    maintain_raw_storage,
    read_raw_data_quality_index,
    update_raw_data_quality_index,
)


def _write(root: Path, *events: EventEnvelope) -> None:
    writer = ParquetRawEventWriter(root, max_rows=1)
    for event in events:
        writer.append(event)
    writer.close()


def test_quality_index_scans_once_then_reuses_verified_files(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    index_path = tmp_path / "index" / "raw-data-quality-index.json"
    _write(
        root,
        make_ticker_event(sequence=1, received_offset_ms=100),
        make_trade_event(sequence=2, exchange_offset_ms=200, received_offset_ms=210),
        make_orderbook_event(sequence=3, received_offset_ms=300),
    )

    first = update_raw_data_quality_index(
        root,
        index_path,
        storage_label="test-paper-data",
        now_utc=BASE_TIME + timedelta(hours=1),
    )

    assert first.measurement_status == "VERIFIED_STORAGE"
    assert first.active_file_count == 3
    assert first.active_row_count == 3
    assert first.scanned_file_count == 3
    assert first.reused_file_count == 0
    assert first.checksum_failures == 0
    assert first.duplicate_event_identity_count == 0
    assert dict(first.event_counts) == {"orderbook": 1, "ticker": 1, "trade": 1}
    assert first.authentication_used is False
    assert first.order_submission_available is False

    second = update_raw_data_quality_index(
        root,
        index_path,
        storage_label="test-paper-data",
        now_utc=BASE_TIME + timedelta(hours=2),
    )

    assert second.scanned_file_count == 0
    assert second.reused_file_count == 3
    assert second.manifest_set_sha256 == first.manifest_set_sha256

    _write(
        root,
        make_trade_event(sequence=4, exchange_offset_ms=400, received_offset_ms=410),
    )
    third = update_raw_data_quality_index(
        root,
        index_path,
        storage_label="test-paper-data",
        now_utc=BASE_TIME + timedelta(hours=3),
    )

    assert third.active_file_count == 4
    assert third.active_row_count == 4
    assert third.scanned_file_count == 1
    assert third.reused_file_count == 3
    assert read_raw_data_quality_index(index_path) == third


def test_quality_index_fails_closed_and_keeps_previous_index(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    index_path = tmp_path / "index.json"
    _write(
        root,
        make_trade_event(sequence=1, exchange_offset_ms=100, received_offset_ms=110),
    )
    update_raw_data_quality_index(
        root,
        index_path,
        now_utc=BASE_TIME + timedelta(hours=1),
    )
    previous = index_path.read_bytes()
    indexed = read_raw_data_quality_index(index_path)
    data_path = root / indexed.files[0].data_file
    with data_path.open("ab") as stream:
        stream.write(b"damage")

    with pytest.raises(RawDataIntegrityError, match=r"size mismatch|checksum mismatch"):
        update_raw_data_quality_index(
            root,
            index_path,
            now_utc=BASE_TIME + timedelta(days=2),
            reverify_after_seconds=0,
        )

    assert index_path.read_bytes() == previous


def test_research_readiness_never_authorizes_current_experiment(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    index_path = tmp_path / "index.json"
    _write(
        root,
        make_trade_event(sequence=1, exchange_offset_ms=0, received_offset_ms=0),
        make_orderbook_event(sequence=2, received_offset_ms=7_200_000),
    )

    result = update_raw_data_quality_index(
        root,
        index_path,
        now_utc=BASE_TIME + timedelta(hours=3),
        research_policy=RawResearchReadinessPolicy(
            minimum_observed_span_hours=1,
            minimum_trade_events_per_market=1,
            minimum_orderbook_events_per_market=1,
            minimum_eligible_markets=1,
        ),
    )

    assert result.research_readiness.eligible_markets == ("KRW-BTC",)
    assert result.research_readiness.ready_for_new_preregistration is True
    assert result.research_readiness.current_experiment_authorized is False
    assert result.research_readiness.paper_order_gate_changed is False


def test_quality_index_drops_retired_manifest_cache_entries(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    index_path = tmp_path / "index.json"
    _write(
        root,
        make_trade_event(sequence=1, exchange_offset_ms=100, received_offset_ms=110),
    )
    first = update_raw_data_quality_index(root, index_path)
    assert first.active_file_count == 1

    maintenance = maintain_raw_storage(
        root,
        policy=RawStoragePolicy(
            retention_days=3650,
            max_bytes=1,
            min_free_bytes=1,
        ),
        compact=False,
    )
    assert maintenance.capacity_deleted_files == 1

    refreshed = update_raw_data_quality_index(root, index_path)

    assert refreshed.active_file_count == 0
    assert refreshed.active_row_count == 0
    assert refreshed.retired_cache_entry_count == 1
    assert refreshed.files == ()
