# ADR-032: Availability-Only Reversal Universe Replacement

- Status: accepted
- Date: 2026-09-02
- Scope: offline public-data research and paper simulation only

## Context

The first prospective reversal plan fixed fifteen markets inherited from the earlier historical
readiness window. Its immutable post-v4 scan passed every checksum, schema, row-count, duplicate-ID,
and ordering check but returned `BLOCKED`: only eight markets met the already declared 24-hour,
20,000-trade, and 20,000-orderbook minima. It executed zero trials and accessed no final holdout.

The readiness scan projected only identity, event type, market, timestamps, lineage hash, duplicate
marker, and quality flags. It did not load raw payload prices, construct features, apply a strategy,
or calculate returns or PnL. The eight passing markets are therefore selected solely by the
pre-existing data-availability rule, not observed strategy performance.

## Decision

Retain v5 and its two-record `BLOCKED` ledger unchanged. Create a separate v6 plan using exactly all
and only the eight markets that passed v5's unchanged readiness thresholds: `KRW-BTC`, `KRW-ETH`,
`KRW-ONG`, `KRW-PROM`, `KRW-SOL`, `KRW-TRUMP`, `KRW-USDT`, and `KRW-XRP`.

V6 preserves the same H-SCALP-004 through H-SCALP-006 definitions, entry thresholds, exits, base and
stress costs, three folds, 20-percent sealed final holdout, source revision, snapshot manifest set,
and receive-time interval. It changes only the fixed availability-qualified market partition and
the mechanically implied trial count from 270 to 144. The v6 plan is committed before its separate
eight-market row fingerprint is computed.

## Consequences

- No failing market threshold is weakened, and no market is selected or discarded by return, PnL,
  signal count, or strategy behavior.
- V5 remains a valid negative operational/readiness result and cannot be retried or edited.
- V6's 144 cells remain one hypothesis/cost/fold/market each and preserve identical-input neutral
  baselines and the sealed holdout.
- Any v6 insufficiency, integrity error, or source/snapshot drift blocks again; it does not authorize
  another automatic relaxation.
- Authentication, private/order networking, real orders, paper-order activation, model promotion,
  risk changes, deployment, and live activation remain unavailable.

## Registration evidence

The committed eight-market inventory contains 8,373,685 clean events from 345 selected files and
has dataset hash `dd3d3215342bd0567b8650a59e394f628cb3d612d4237d09152d9600da770b7c`. All eight markets
meet the unchanged requirements. The registration-only ledger contains one record with chain hash
`ab62c71d4c929fa3198d096f729ea368d50d87c57efcbad5df834bdd6d0f95cc`.

Execution-plan digest `d2a9a82abae518274f537b62eac841e47b5f52c348ec610c0c0f89762de31120`
seals 96 validation and 48 test units, a 500,000-event per-unit limit, and a 900-second wall limit.
It contains no final-holdout access or order capability. No v6 trial was executed while producing
this evidence.
