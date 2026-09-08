---
tags: ["estrategia", "catalogo", "volume_anomaly"]
strategy: volume_anomaly
version: v2
purpose: research_only
status: active
code_ref: "hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22"
params_hash: fa5dce78173b2b9688578f7c96a5f37544eb504aa7b2227262ad296c32f63bb9
activated_at: "2026-09-08T04:32:42.178866+00:00"
deprecated_at: ""
derived_from: "[[volume_anomaly-v1]]"
cohorts: ["prospective", "replay:bac27c12-7e50-4dfa-9eee-35fccc4012d7", "replay:cd0d5584-b53b-4bb0-bdb0-ec39d960d549"]
exp: ["[[EXP-0002-volume-anomaly-v1]]"]
updated: 2026-09-08
---
# volume_anomaly v2 (research_only, active)

<!-- generated:start -->
## Parâmetros

| Parâmetro | Valor | Tipo | Vínculo | Descrição |
|---|---|---|---|---|
| `assumed_spread_bps` | `2` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | assumed total spread, bps |
| `atr_bars` | `97` | string \| integer | regex `^-?[0-9]+$` | bars the ATR is recomputed from (rolling_window_v1) |
| `atr_period` | `14` | string \| integer | regex `^-?[0-9]+$` | Wilder ATR period |
| `atr_timeframe` | `15m` | string | um de: 1m, 5m, 15m, 1h | timeframe the ATR is computed on |
| `base_confidence` | `0.5` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | uncalibrated constant confidence |
| `fee_bps` | `4` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | assumed fee per side, bps |
| `horizon_s` | `7200` | string \| integer | regex `^-?[0-9]+$` | expected holding, seconds |
| `max_entry_delay_s` | `120` | string \| integer | regex `^-?[0-9]+$` | max seconds from reference close to entry open |
| `return_max_atr` | `2` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | 5m return ceiling in ATR%, inclusive |
| `return_min` | `0` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | 5m return floor, inclusive |
| `slippage_bps` | `5` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | assumed slippage per side, bps |
| `target_atr` | `1.5` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | target1 distance from the reference, in ATR |
| `volume_mult` | `4` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | volume / median floor (inclusive) |
| `volume_window` | `288` | string \| integer | regex `^-?[0-9]+$` | bars in the volume median, current excluded |

## Origem

**Changelog congelado:** succeeds v1: code_moved_by_funding_slot_fix_d878fd6_lab_refused_v1_on_vps_since_2026-09-07_frozen_parameters_carried_over

Nenhum evento de ativação registrado ainda (versão nunca ativada).

## Coortes e sinais

| Coorte | Sinais (`agent_signals`) |
|---|---|
| `prospective` | 336 |
| `replay:bac27c12-7e50-4dfa-9eee-35fccc4012d7` | 341 |
| `replay:cd0d5584-b53b-4bb0-bdb0-ec39d960d549` | 341 |
| **total** | **1018** |

## Avaliações

As avaliações datadas ficam nas páginas de experimento, nunca duplicadas aqui:

- [[EXP-0002-volume-anomaly-v1]]

## Replicação

não iniciada — ver `docs/plans/REPLICATION.md` quando existir (T3.19).

## Ligações

- Família: [[volume_anomaly]]
- Versão anterior: [[volume_anomaly-v1]]
- Experimento: [[EXP-0002-volume-anomaly-v1]]
<!-- generated:end -->


## Notas

