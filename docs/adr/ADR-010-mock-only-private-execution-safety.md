# ADR-010: Mock-only private execution and identifier-first recovery

- Status: Accepted
- Date: 2026-08-23

## Context

Phase 6 needs authenticated order and private-stream contracts without using a credential or making
an authenticated network request. An order-create timeout is ambiguous: retrying may create a second
order. Client identifiers are therefore part of the safety boundary, not optional metadata.

The reviewed official sources were the Upbit [AI document index](https://docs.upbit.com/kr/llms.txt),
[authentication](https://docs.upbit.com/kr/reference/auth.md),
[create order](https://docs.upbit.com/kr/reference/new-order.md),
[test order](https://docs.upbit.com/kr/reference/order-test.md),
[get order](https://docs.upbit.com/kr/reference/get-order.md),
[cancel order](https://docs.upbit.com/kr/reference/cancel-order.md),
[MyOrder](https://docs.upbit.com/kr/reference/websocket-myorder.md),
[MyAsset](https://docs.upbit.com/kr/reference/websocket-myasset.md), and
[rate limits](https://docs.upbit.com/kr/reference/rate-limits.md) pages retrieved on 2026-08-23.

## Decision

Authentication is an interface over an opaque authorization header. QuantForge implements ordered
query-string construction and SHA-512 hashing but no credential provider, Secret reader, JWT signer,
or authenticated network client. The default provider and private port always raise a disabled
error; the only working private port is an in-memory fake.

Every order requires a deterministic identifier no longer than 64 characters. The append-only,
fsynced journal burns that identifier at intent creation and verifies identity, chronological state
transitions, sequence, and SHA-256 chain on reload. An identifier cannot be attached to another
intent even after rejection, cancellation, fill, or prevention.

Order preflight binds the request to its risk decision and a fresh dynamic order-chance snapshot.
It validates documented order shapes, tick size, supported types, exact risk amount, fees, balances,
minimum/maximum notional, expiry, and market. No value is hard-coded as a claim about current Upbit
fees, ticks, or minimums.

On create timeout or recovery from `SUBMISSION_PENDING`, the coordinator records `UNKNOWN`, enters
`RECONCILING`, and looks up the exact identifier. A missing, failed, or mismatched lookup returns to
`UNKNOWN`; it never calls create again. Balance or remote-order mismatch blocks resume.

The order-test adapter accepts only the in-memory fake and all results are marked dry-run. The live
adapter has no network capability and raises even when all six configuration gates pass.

## Consequences

- No private endpoint, test-order endpoint, real order, API Key, or production Secret is used.
- Timeout and crash recovery favor an unresolved stop over duplicate execution.
- File-journal durability is suitable for deterministic tests and a single writer; transactional
  database storage, locking, private-stream supervision, and authenticated operator controls remain
  later work.
- Any future network implementation requires a new reviewed ADR, current capability refresh,
  Secret-store boundary, full reconciliation, and explicit human approval.
