# qf-scalp-20260828-v4 final report

- Decision: `REJECT`
- Generated: `2026-08-30T07:44:05.793957+00:00`
- Report digest: `0794f2e6bf9d68a49f506501eca774d0f0f91f3556f207fcb985096fce7c2a12`
- Input ledger chain: `25f66eb1280fccbe2c3ce67c08328ea0987df54a2783f3ae9da633fa34e3182d`
- Decision ledger chain: `009263444403a07487616db6698f5d26e9ce02e5041bc3572522e16ba3cb7c45`
- Trials: `270` planned, `253` succeeded, `17` failed
- Validated artifacts: `253`
- Final holdout used: `false`
- Actual investment performed: `false`

## Result

Every successful market trial had non-positive cost-inclusive net PnL. Base, stress, validation, and test aggregates were non-positive for all three hypotheses, so the preregistered reject rule fired before any positive-evidence multiplicity gate.

Independent trial sums overlap across markets, folds, rules, and cost scenarios and are not an account or portfolio equity curve.

## Hypotheses

| Hypothesis | Succeeded | Failed | Positive | Negative | Zero | Closed trades | Net PnL sum | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| H-SCALP-001 | 84 | 6 | 0 | 47 | 37 | 1489 | -42901.767482337213834900 | REJECT |
| H-SCALP-002 | 83 | 7 | 0 | 52 | 31 | 6175 | -156447.122105732359952700 | REJECT |
| H-SCALP-003 | 86 | 4 | 0 | 36 | 50 | 585 | -14377.367089286344260600 | REJECT |

## Predetermined market-cell aggregates

| Hypothesis | Cost | Fold | Split | Succeeded markets | Failed markets | Closed trades | Net PnL sum |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| H-SCALP-001 | base | 1 | validation | 14 | 1 | 222 | -5110.565166685436681100 |
| H-SCALP-001 | base | 2 | validation | 15 | 0 | 121 | -2960.184482901154570800 |
| H-SCALP-001 | base | 3 | test | 13 | 2 | 409 | -9722.021746749177635000 |
| H-SCALP-001 | stress | 1 | validation | 13 | 2 | 192 | -6528.780566385288564000 |
| H-SCALP-001 | stress | 2 | validation | 15 | 0 | 123 | -4223.046250319143878000 |
| H-SCALP-001 | stress | 3 | test | 14 | 1 | 422 | -14357.169269297012506000 |
| H-SCALP-002 | base | 1 | validation | 13 | 2 | 1150 | -24206.619729316297192600 |
| H-SCALP-002 | base | 2 | validation | 14 | 1 | 632 | -11969.987479973355932300 |
| H-SCALP-002 | base | 3 | test | 14 | 1 | 1187 | -23485.329408650393083800 |
| H-SCALP-002 | stress | 1 | validation | 13 | 2 | 1112 | -34722.970670501016094000 |
| H-SCALP-002 | stress | 2 | validation | 14 | 1 | 643 | -18753.452977660341128000 |
| H-SCALP-002 | stress | 3 | test | 15 | 0 | 1451 | -43308.761839630956522000 |
| H-SCALP-003 | base | 1 | validation | 14 | 1 | 136 | -2684.227375390747645600 |
| H-SCALP-003 | base | 2 | validation | 15 | 0 | 29 | -569.132155985305588600 |
| H-SCALP-003 | base | 3 | test | 15 | 0 | 180 | -3681.012110625676400400 |
| H-SCALP-003 | stress | 1 | validation | 14 | 1 | 100 | -2968.840458640269438000 |
| H-SCALP-003 | stress | 2 | validation | 14 | 1 | 29 | -854.885433377107768000 |
| H-SCALP-003 | stress | 3 | test | 14 | 1 | 111 | -3619.269555267237420000 |

Failure types: `AccountingInvariantError=5, RawDataIntegrityError=9, ScalpingTrialLimitError=3`. Failed units have no metrics and were neither retried nor imputed.

No authentication, private/order network, real order, final-holdout access, model promotion, risk-limit change, paper-order gate change, or live-mode change occurred.
