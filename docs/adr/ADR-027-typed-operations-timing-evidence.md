# ADR-027: Typed Operations Timing Evidence

- Status: accepted
- Date: 2026-08-26

## Context

The first unattended six-hour operations report classified the paper runtime `WARNING` because the
dashboard exposed the session's maximum positive ingress latency as `clock_skew_ms`. One duplicate
ticker from an inactive market retained a 94-minute-old exchange timestamp, so a legitimate stale
payload was reported as if the Windows clock were wrong. Independent host sampling showed an NTP
offset near 0.13 seconds, while Docker and continuity evidence remained healthy.

The same scheduled sandbox could not query the Docker named pipe or a presumed `D:` host mount and
treated those capability limits as operational warnings. Its hand-written JSON summary also failed
the closed `automation-report-1` contract. Repeating that behavior would make routine reports noisy
and unauditable.

## Decision

Version the paper lifecycle export as `paper-runtime-7`, the Work operations view as `work-ops-3`,
and the dashboard as `operations-dashboard-2`.

- Keep `max_ingress_latency_ms` as the nonnegative session high-water mark for
  receive-minus-exchange latency. It measures staleness and may be dominated by a duplicate ticker.
- Add `latest_ingress_latency_ms` as the newest event's signed latency.
- Add `latest_exchange_clock_ahead_ms` as `max(0, -latest_ingress_latency_ms)`. The dashboard's
  backward-compatible `clock_skew_ms` field carries this same fresh exchange-ahead proxy instead of
  the positive-latency high-water mark.
- Do not present any public-event field as independent host NTP evidence. Host time remains an
  optional operator check.

Scheduled operations audits must use fresh redacted exports for supported claims, leave inaccessible
host/Docker evidence unknown, and never assume a drive letter. They must construct the same-stem JSON
manifest from the complete version-1 fixture shape and pass `validate-automation-report` before the
run is considered complete.

## Consequences

- Old or duplicate ticker timestamps remain visible as ingress-staleness evidence without producing
  a false host-clock alert.
- A current exchange-ahead event still produces a nonnegative clock proxy consistent with the
  fail-closed real-time risk calculation.
- Existing paper-runtime, Work-ops, and dashboard snapshots remain readable through version unions
  and defaulted new fields.
- A scheduled sandbox cannot claim Docker restart/OOM or host NTP health when access is denied, but
  denial alone no longer downgrades otherwise fresh verified runtime evidence.
- The paper data host path remains machine-specific; storage integrity, capacity, and free-space
  evidence come from the mounted runtime rather than a guessed `D:` path.
- No model, risk, paper-order, authentication, private-network, or live-trading gate changes.
