---
tags: ["estrategia", "catalogo", "momentum"]
strategy: momentum
version: v1
purpose: research_only
status: deprecated
code_ref: "hunter_core.strategies.momentum_v1@sha256:6ccbe8b6c8ac18f32e93a6d44e71e0045155646479907b2b1944f39c3cdf4c95"
params_hash: 40e1688e6b5f6385674cb47a81e542b215b320eb5643a1375f6401f5c41ac2f3
activated_at: "2026-09-06T03:36:36.988581+00:00"
deprecated_at: "2026-09-08T04:33:56.865371+00:00"
derived_from: ""
cohorts: ["prospective"]
exp: ["[[EXP-0001-momentum-v1]]"]
updated: 2026-09-08
---
# momentum v1 (research_only, deprecated)

<!-- generated:start -->
## Parâmetros

| Parâmetro | Valor | Tipo | Vínculo | Descrição |
|---|---|---|---|---|
| `assumed_spread_bps` | `2` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | assumed total spread, bps |
| `atr_bars` | `97` | string \| integer | regex `^-?[0-9]+$` | bars the ATR is recomputed from (rolling_window_v1) |
| `atr_pct_max` | `0.05` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | maximum ATR/close as a fraction (inclusive) |
| `atr_pct_min` | `0.003` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | minimum ATR/close as a fraction (inclusive) |
| `atr_period` | `14` | string \| integer | regex `^-?[0-9]+$` | Wilder ATR period |
| `atr_timeframe` | `15m` | string | um de: 1m, 5m, 15m, 1h | timeframe the ATR is computed on |
| `base_confidence` | `0.5` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | uncalibrated constant confidence |
| `fee_bps` | `4` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | assumed fee per side, bps |
| `horizon_s` | `14400` | string \| integer | regex `^-?[0-9]+$` | expected holding, seconds |
| `lookback_closes` | `20` | string \| integer | regex `^-?[0-9]+$` | closes the breakout must clear, current excluded |
| `max_entry_delay_s` | `120` | string \| integer | regex `^-?[0-9]+$` | max seconds from reference close to entry open |
| `return_min` | `0` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | 15m return floor, exclusive: return > return_min |
| `rvol_min` | `1.5` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | minimum relative volume (inclusive) |
| `rvol_window` | `96` | string \| integer | regex `^-?[0-9]+$` | bars in the relative-volume median, current excluded |
| `slippage_bps` | `5` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | assumed slippage per side, bps |
| `stop_atr` | `1.5` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | stop distance from the reference, in ATR |
| `target2_atr` | `3` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | informational target 2, in ATR |
| `target3_atr` | `4.5` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | informational target 3, in ATR |
| `target_atr` | `1.5` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | target1 distance from the reference, in ATR |

## Origem

**Changelog congelado:** superseded by v2 (code_ref hunter_core.strategies.momentum_v1@sha256:6ccbe8b6c8ac18f32e93a6d44e71e0045155646479907b2b1944f39c3cdf4c95 -> hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c); frozen fields cannot be corrected in place (DATABASE.md §16.1): code_moved_by_funding_slot_fix_d878fd6_lab_refused_v1_on_vps_since_2026-09-07_frozen_parameters_carried_over

- **2026-09-06T03:30:09.078298+00:00** — `strategy_version_activation_refused` (warning): no strategy_version for momentum v1 (run infra/scripts/seed.py first)
- **2026-09-06T03:36:36.988581+00:00** — `strategy_version_activated` (info): momentum v1 activated with code_ref=hunter_core.strategies.momentum_v1@sha256:6ccbe8b6c8ac18f32e93a6d44e71e0045155646479907b2b1944f39c3cdf4c95 params_format=1: S4: primeira ativacao do Shadow Lab na VPS (2026-09-06)
- **2026-09-06T12:28:11.592273+00:00** — `strategy_version_activation_refused` (warning): momentum v1 is already frozen against this code (hunter_core.strategies.momentum_v1@sha256:6ccbe8b6c8ac18f32e93a6d44e71e0045155646479907b2b1944f39c3cdf4c95)
- **2026-09-08T04:26:04.515543+00:00** — `strategy_version_activation_refused` (warning): momentum v1 is frozen at code_ref hunter_core.strategies.momentum_v1@sha256:6ccbe8b6c8ac18f32e93a6d44e71e0045155646479907b2b1944f39c3cdf4c95 but this build is hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c: a paper line runs the very code the research coorte ran; supersede first or deploy the matching build
- **2026-09-08T04:33:56.865371+00:00** — `strategy_version_superseded` (info): momentum v1 -> v2 with code_ref=hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c: code_moved_by_funding_slot_fix_d878fd6_lab_refused_v1_on_vps_since_2026-09-07_frozen_parameters_carried_over

## Coortes e sinais

| Coorte | Sinais (`agent_signals`) |
|---|---|
| `prospective` | 963 |
| **total** | **963** |

## Avaliações

As avaliações datadas ficam nas páginas de experimento, nunca duplicadas aqui:

- [[EXP-0001-momentum-v1]]

## Replicação

não iniciada — ver `docs/plans/REPLICATION.md` quando existir (T3.19).

## Ligações

- Família: [[momentum]]
- Experimento: [[EXP-0001-momentum-v1]]
<!-- generated:end -->


## Notas

