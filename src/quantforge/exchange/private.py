"""Private exchange ports with disabled and deterministic fake implementations only."""

from typing import Protocol

from quantforge.domain import (
    ExchangeOrderRequest,
    OrderChance,
    OrderTestResult,
    RemoteOrderSnapshot,
)


class PrivateExchangeDisabled(RuntimeError):
    """Raised by every authenticated capability unless a test fake is injected."""


class PrivateTransportTimeout(TimeoutError):
    """A response was not observed; the submission outcome is uncertain."""


class PrivateTransportError(RuntimeError):
    """A definite fake transport failure that did not create an order."""


class PrivateOrderPort(Protocol):
    async def create_order(self, request: ExchangeOrderRequest) -> RemoteOrderSnapshot: ...

    async def find_order(self, identifier: str) -> RemoteOrderSnapshot | None: ...

    async def cancel_order(self, identifier: str) -> RemoteOrderSnapshot: ...

    async def test_order(self, request: ExchangeOrderRequest) -> OrderTestResult: ...

    async def order_chance(self, market: str) -> OrderChance: ...


class DisabledPrivateOrderPort:
    """Default Phase 6 port. It has no URL, credential, or network implementation."""

    @staticmethod
    def _blocked() -> PrivateExchangeDisabled:
        return PrivateExchangeDisabled("authenticated exchange transport is disabled")

    async def create_order(self, request: ExchangeOrderRequest) -> RemoteOrderSnapshot:
        del request
        raise self._blocked()

    async def find_order(self, identifier: str) -> RemoteOrderSnapshot | None:
        del identifier
        raise self._blocked()

    async def cancel_order(self, identifier: str) -> RemoteOrderSnapshot:
        del identifier
        raise self._blocked()

    async def test_order(self, request: ExchangeOrderRequest) -> OrderTestResult:
        del request
        raise self._blocked()

    async def order_chance(self, market: str) -> OrderChance:
        del market
        raise self._blocked()


class FakePrivateOrderPort:
    """In-memory deterministic fake; it cannot issue network requests."""

    def __init__(self) -> None:
        self.create_outcomes: dict[str, RemoteOrderSnapshot | Exception] = {}
        self.lookup_outcomes: dict[str, RemoteOrderSnapshot | Exception | None] = {}
        self.cancel_outcomes: dict[str, RemoteOrderSnapshot | Exception] = {}
        self.test_outcomes: dict[str, OrderTestResult | Exception] = {}
        self.chances: dict[str, OrderChance] = {}
        self.create_calls: list[str] = []
        self.lookup_calls: list[str] = []
        self.cancel_calls: list[str] = []
        self.test_calls: list[str] = []

    async def create_order(self, request: ExchangeOrderRequest) -> RemoteOrderSnapshot:
        self.create_calls.append(request.identifier)
        outcome = self.create_outcomes.get(request.identifier)
        if outcome is None:
            raise PrivateTransportError("fake create outcome was not registered")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def find_order(self, identifier: str) -> RemoteOrderSnapshot | None:
        self.lookup_calls.append(identifier)
        outcome = self.lookup_outcomes.get(identifier)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def cancel_order(self, identifier: str) -> RemoteOrderSnapshot:
        self.cancel_calls.append(identifier)
        outcome = self.cancel_outcomes.get(identifier)
        if outcome is None:
            raise PrivateTransportError("fake cancel outcome was not registered")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def test_order(self, request: ExchangeOrderRequest) -> OrderTestResult:
        self.test_calls.append(request.identifier)
        outcome = self.test_outcomes.get(request.identifier)
        if outcome is None:
            raise PrivateTransportError("fake order-test outcome was not registered")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def order_chance(self, market: str) -> OrderChance:
        try:
            return self.chances[market]
        except KeyError as exc:
            raise PrivateTransportError("fake order chance was not registered") from exc


class MockOnlyOrderTestAdapter:
    """Order-test adapter intentionally restricted to the no-network fake port."""

    def __init__(self, port: FakePrivateOrderPort) -> None:
        self.port = port

    async def validate(self, request: ExchangeOrderRequest) -> OrderTestResult:
        result = await self.port.test_order(request)
        if not result.dry_run or result.identifier != request.identifier:
            raise PrivateTransportError("invalid fake order-test result")
        return result
