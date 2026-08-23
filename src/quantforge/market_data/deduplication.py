"""Bounded duplicate detection for reconnect and replay boundaries."""

from collections import OrderedDict
from dataclasses import dataclass, field

from quantforge.domain import EventEnvelope


@dataclass(slots=True)
class EventDeduplicator:
    max_entries: int = 100_000
    _seen: OrderedDict[str, None] = field(default_factory=OrderedDict, init=False)

    def __post_init__(self) -> None:
        if self.max_entries < 1:
            raise ValueError("max_entries must be positive")

    def mark(self, event: EventEnvelope) -> EventEnvelope:
        """Return an envelope marked duplicate when its exact raw digest was seen."""

        digest = event.raw_payload_hash
        if digest in self._seen:
            self._seen.move_to_end(digest)
            flags = (*event.quality_flags, "duplicate_raw_payload")
            return event.model_copy(update={"is_duplicate": True, "quality_flags": flags})

        self._seen[digest] = None
        if len(self._seen) > self.max_entries:
            self._seen.popitem(last=False)
        return event

    def __len__(self) -> int:
        return len(self._seen)
