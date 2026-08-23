from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pyarrow.parquet as pq

from quantforge.exchange.upbit.mapper import map_public_message
from quantforge.storage import (
    ParquetRawEventWriter,
    RawDataIntegrityError,
    RawFileManifest,
    cleanup_orphan_temp_files,
    read_raw_events,
    summarize_raw_storage,
    verify_manifest_checksum,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "upbit"


def _event(name: str, sequence: int):  # type: ignore[no-untyped-def]
    raw = (FIXTURES / name).read_bytes()
    timestamp_ms = __import__("json").loads(raw)["timestamp"]
    timestamp = datetime.fromtimestamp(timestamp_ms // 1000, tz=UTC).replace(
        microsecond=(timestamp_ms % 1000) * 1000
    )
    return map_public_message(
        raw,
        received_at_utc=timestamp + timedelta(milliseconds=10),
        received_monotonic_ns=sequence,
        connection_id=uuid4(),
        subscription_id="storage-test",
        local_sequence=sequence,
    )


def test_zstd_partition_manifest_and_checksum(tmp_path: Path) -> None:
    writer = ParquetRawEventWriter(tmp_path, max_rows=2)
    assert writer.append(_event("trade.default.json", 1)) == []
    manifests = writer.append(_event("trade.default.json", 2))
    assert len(manifests) == 1
    manifest = manifests[0]
    assert manifest.row_count == 2
    assert manifest.compression == "zstd"
    assert "source=upbit/event_type=trade/date=2024-10-31/hour=01" in manifest.data_file
    assert verify_manifest_checksum(tmp_path, manifest) is True

    data_path = tmp_path / manifest.data_file
    table = pq.ParquetFile(data_path).read()
    assert table.num_rows == 2
    assert table.schema.metadata[b"quantforge_schema_version"] == b"1"
    assert table.column("raw_payload")[0].as_py().startswith("{")
    assert pq.ParquetFile(data_path).metadata.row_group(0).column(0).compression == "ZSTD"

    manifest_path = data_path.with_suffix(".manifest.json")
    restored = RawFileManifest.model_validate_json(manifest_path.read_bytes())
    assert restored == manifest
    restored_events = read_raw_events(tmp_path)
    assert len(restored_events) == 2
    assert all(
        event.raw_payload_hash == restored_events[0].raw_payload_hash for event in restored_events
    )
    summary = summarize_raw_storage(tmp_path)
    assert summary.file_count == 1
    assert summary.row_count == 2
    assert summary.byte_size == manifest.byte_size
    assert writer.close() == []


def test_flush_groups_different_event_types(tmp_path: Path) -> None:
    writer = ParquetRawEventWriter(tmp_path)
    writer.append(_event("ticker.default.json", 1))
    writer.append(_event("orderbook.synthetic.json", 2))
    manifests = writer.flush()
    assert {manifest.event_type for manifest in manifests} == {"ticker", "orderbook"}


def test_checksum_detects_corruption(tmp_path: Path) -> None:
    writer = ParquetRawEventWriter(tmp_path, max_rows=1)
    manifest = writer.append(_event("trade.default.json", 1))[0]
    path = tmp_path / manifest.data_file
    with path.open("ab") as stream:
        stream.write(b"corruption")
    assert verify_manifest_checksum(tmp_path, manifest) is False
    try:
        read_raw_events(tmp_path)
    except RawDataIntegrityError as exc:
        assert "checksum" in str(exc)
    else:
        raise AssertionError("expected corrupted raw data to fail replay loading")


def test_manifest_cannot_escape_root(tmp_path: Path) -> None:
    manifest = RawFileManifest(
        source="upbit",
        event_type="trade",
        data_file="../escape.parquet",
        sha256="a" * 64,
        row_count=1,
        byte_size=1,
        min_exchange_timestamp=datetime.now(UTC),
        max_exchange_timestamp=datetime.now(UTC),
        created_at_utc=datetime.now(UTC),
    )
    try:
        verify_manifest_checksum(tmp_path, manifest)
    except ValueError as exc:
        assert "escapes" in str(exc)
    else:
        raise AssertionError("expected path traversal protection")


def test_orphan_cleanup_is_narrowly_scoped(tmp_path: Path) -> None:
    orphan = tmp_path / ".part.parquet.dead.tmp"
    keep = tmp_path / "ordinary.tmp"
    orphan.write_text("orphan", encoding="utf-8")
    keep.write_text("keep", encoding="utf-8")
    assert cleanup_orphan_temp_files(tmp_path) == 1
    assert not orphan.exists()
    assert keep.exists()
    assert cleanup_orphan_temp_files(tmp_path / "missing") == 0


def test_invalid_writer_buffer_is_rejected(tmp_path: Path) -> None:
    try:
        ParquetRawEventWriter(tmp_path, max_rows=0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected invalid buffer size to fail")


def test_reader_handles_empty_root_and_rejects_bad_manifest(tmp_path: Path) -> None:
    assert read_raw_events(tmp_path) == []
    assert summarize_raw_storage(tmp_path).row_count == 0
    manifest_path = tmp_path / "bad.manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    try:
        read_raw_events(tmp_path)
    except RawDataIntegrityError as exc:
        assert "invalid raw manifest" in str(exc)
    else:
        raise AssertionError("expected malformed manifest to fail")


def test_storage_summary_rejects_file_size_damage(tmp_path: Path) -> None:
    writer = ParquetRawEventWriter(tmp_path, max_rows=1)
    manifest = writer.append(_event("trade.default.json", 1))[0]
    with (tmp_path / manifest.data_file).open("ab") as stream:
        stream.write(b"damage")

    try:
        summarize_raw_storage(tmp_path)
    except RawDataIntegrityError as exc:
        assert "size mismatch" in str(exc)
    else:
        raise AssertionError("expected damaged raw storage summary to fail")
