"""A wall-clock-free, monotonic virtual clock for replay."""

from datetime import UTC, datetime, timedelta


class VirtualClock:
    def __init__(self, start_utc: datetime) -> None:
        self._now = self._validate_utc(start_utc)

    @property
    def now(self) -> datetime:
        return self._now

    def advance_to(self, timestamp_utc: datetime) -> datetime:
        selected = self._validate_utc(timestamp_utc)
        if selected < self._now:
            raise ValueError("virtual clock cannot move backwards")
        self._now = selected
        return self._now

    def advance_by(self, duration: timedelta) -> datetime:
        if duration < timedelta(0):
            raise ValueError("virtual clock duration cannot be negative")
        return self.advance_to(self._now + duration)

    @staticmethod
    def _validate_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("virtual clock timestamps must be UTC-aware")
        return value
