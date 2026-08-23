"""Isolatable errors raised by untrusted Upbit messages."""


class UpbitAdapterError(Exception):
    """Base adapter error."""


class MalformedUpbitPayload(UpbitAdapterError):
    """Payload was not valid JSON or did not satisfy the reviewed schema."""


class UpbitPayloadError(UpbitAdapterError):
    """Upbit returned a documented WebSocket error object."""

    def __init__(self, name: str, message: str) -> None:
        super().__init__(f"{name}: {message}")
        self.name = name
        self.message = message
