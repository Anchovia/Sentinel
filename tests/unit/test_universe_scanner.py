from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from factories import BASE_TIME, make_ticker_event
from quantforge.runtime.universe_scanner import (
    RealtimeUniversePolicy,
    RealtimeUniverseScanner,
    read_realtime_universe_snapshot,
    write_realtime_universe_snapshot,
)


def _scanner() -> RealtimeUniverseScanner:
    return RealtimeUniverseScanner(
        ("KRW-BTC", "KRW-ETH", "KRW-RISK"),
        eligible_markets=("KRW-BTC", "KRW-ETH"),
        initial_focus_markets=("KRW-BTC",),
        warning_markets=("KRW-RISK",),
        caution_markets=("KRW-ETH",),
        market_set_hash="1" * 64,
        policy=RealtimeUniversePolicy(
            focus_limit=1,
            activity_window_seconds=60,
            max_ticker_age_seconds=5,
            minimum_turnover_24h_krw=Decimal(0),
        ),
    )


def test_scanner_rotates_focus_to_the_most_active_eligible_market() -> None:
    scanner = _scanner()
    scanner.ingest(make_ticker_event(sequence=1, received_offset_ms=100, market="KRW-BTC"))
    scanner.ingest(make_ticker_event(sequence=2, received_offset_ms=200, market="KRW-ETH"))
    scanner.ingest(
        make_ticker_event(
            sequence=3,
            received_offset_ms=300,
            price=105,
            market="KRW-ETH",
        )
    )
    scanner.ingest(make_ticker_event(sequence=4, received_offset_ms=400, market="KRW-RISK"))

    selected = scanner.select(now_utc=BASE_TIME + timedelta(seconds=1))

    assert selected == ("KRW-ETH",)
    snapshot = scanner.snapshot(generated_at_utc=BASE_TIME + timedelta(seconds=1))
    assert snapshot.monitored_market_count == 3
    assert snapshot.eligible_market_count == 2
    assert snapshot.ticker_coverage_count == 3
    assert snapshot.focus_rotation_count == 1
    assert snapshot.ranked_focus[0].activity_events == 2
    assert snapshot.order_submission_available is False


def test_scanner_keeps_previous_focus_when_every_ticker_is_stale() -> None:
    scanner = _scanner()
    scanner.ingest(make_ticker_event(sequence=1, received_offset_ms=100, market="KRW-BTC"))

    selected = scanner.select(now_utc=BASE_TIME + timedelta(seconds=30))

    assert selected == ("KRW-BTC",)


def test_scanner_enforces_minimum_focus_dwell_time() -> None:
    scanner = _scanner()
    scanner.ingest(make_ticker_event(sequence=1, received_offset_ms=100, market="KRW-BTC"))
    scanner.ingest(make_ticker_event(sequence=2, received_offset_ms=200, market="KRW-ETH"))
    scanner.ingest(make_ticker_event(sequence=3, received_offset_ms=300, market="KRW-ETH"))
    assert scanner.select(now_utc=BASE_TIME + timedelta(seconds=1)) == ("KRW-ETH",)

    scanner.ingest(make_ticker_event(sequence=4, received_offset_ms=1100, market="KRW-BTC"))
    scanner.ingest(make_ticker_event(sequence=5, received_offset_ms=1200, market="KRW-BTC"))
    scanner.ingest(make_ticker_event(sequence=6, received_offset_ms=1300, market="KRW-BTC"))

    assert scanner.select(now_utc=BASE_TIME + timedelta(seconds=2)) == ("KRW-ETH",)
    assert (
        scanner.snapshot(generated_at_utc=BASE_TIME + timedelta(seconds=2)).focus_rotation_count
        == 1
    )


def test_universe_snapshot_round_trip_is_secret_free(tmp_path: Path) -> None:
    scanner = _scanner()
    scanner.ingest(make_ticker_event(sequence=1, received_offset_ms=100, market="KRW-BTC"))
    scanner.select(now_utc=BASE_TIME + timedelta(seconds=1))
    snapshot = scanner.snapshot(generated_at_utc=BASE_TIME + timedelta(seconds=1))

    path = write_realtime_universe_snapshot(snapshot, tmp_path)

    assert read_realtime_universe_snapshot(path) == snapshot
    assert "authorization" not in path.read_text(encoding="utf-8").lower()
