"""JSON structured logging with mandatory redaction."""

import logging
import sys
from typing import TextIO, cast

import structlog
from structlog.typing import EventDict, WrappedLogger

from quantforge.security import redact


def redact_event(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> EventDict:
    """Structlog processor that removes sensitive values before rendering."""

    redacted = redact(dict(event_dict))
    if not isinstance(redacted, dict):
        raise TypeError("redaction processor expected a mapping")
    return cast(EventDict, redacted)


def configure_logging(log_level: str = "INFO", stream: TextIO | None = None) -> None:
    """Configure process logging as one-JSON-object-per-line."""

    level = logging.getLevelNamesMapping().get(log_level.upper())
    if not isinstance(level, int):
        raise ValueError(f"unsupported log level: {log_level}")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_event,
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=stream or sys.stdout),
        cache_logger_on_first_use=False,
    )
