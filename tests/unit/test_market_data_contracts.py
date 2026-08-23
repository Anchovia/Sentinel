from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from quantforge.domain import CoverageWindow, DataGap, DataGapReason

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def test_gap_has_stable_fingerprint_and_availability() -> None:
    gap = DataGap(
        market="KRW-BTC",
        start_utc=BASE,
        end_utc=BASE + timedelta(seconds=1),
        known_at_utc=BASE + timedelta(seconds=2),
        reason=DataGapReason.CONNECTION_LOST,
        details="fixture disconnect",
    )
    assert gap.availability_time == BASE + timedelta(seconds=2)
    assert gap.fingerprint() == gap.model_copy().fingerprint()
    assert len(gap.fingerprint()) == 64


@pytest.mark.parametrize(
    "updates",
    [
        {"end_utc": BASE},
        {"known_at_utc": BASE},
        {"start_utc": datetime(2026, 1, 1)},
        {"start_utc": BASE.astimezone(timezone(timedelta(hours=9)))},
    ],
)
def test_invalid_gap_is_rejected(updates: dict[str, datetime]) -> None:
    payload = {
        "market": "KRW-BTC",
        "start_utc": BASE,
        "end_utc": BASE + timedelta(seconds=1),
        "known_at_utc": BASE + timedelta(seconds=1),
        "reason": "connection_lost",
        "details": "test",
        **updates,
    }
    with pytest.raises(ValidationError):
        DataGap.model_validate(payload)


def test_coverage_requires_positive_completed_interval() -> None:
    coverage = CoverageWindow(
        market="KRW-BTC",
        start_utc=BASE,
        end_utc=BASE + timedelta(seconds=1),
        asserted_at_utc=BASE + timedelta(seconds=1),
    )
    assert coverage.source == "collector_health"
    for updates in (
        {"end_utc": BASE},
        {"asserted_at_utc": BASE},
        {"start_utc": datetime(2026, 1, 1)},
    ):
        with pytest.raises(ValidationError):
            CoverageWindow.model_validate({**coverage.model_dump(), **updates})
