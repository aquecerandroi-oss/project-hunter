---
tags: ["estrategia", "catalogo", "momentum"]
strategy: momentum
version: v2
purpose: research_only
status: deprecated
code_ref: "hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c"
params_hash: 40e1688e6b5f6385674cb47a81e542b215b320eb5643a1375f6401f5c41ac2f3
activated_at: "2026-09-08T04:33:56.865371+00:00"
deprecated_at: "2026-09-09T14:56:27.659818+00:00"
derived_from: "[[momentum-v1]]"
cohorts: ["prospective", "replay:31bb3a12-090d-43ee-998b-630b2645bb46", "replay:7598d6c4-c8b6-430e-974e-3a5118d3a288", "replay:f8d8279c-1fba-42ae-95ef-202042f96c60"]
exp: ["[[EXP-0001-momentum-v1]]"]
updated: 2026-09-09
---
# momentum v2 (research_only, deprecated)

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

**Changelog congelado:** succeeds v1: code_moved_by_funding_slot_fix_d878fd6_lab_refused_v1_on_vps_since_2026-09-07_frozen_parameters_carried_over

Nenhum evento de ativação registrado ainda (versão nunca ativada).

## Coortes e sinais

| Coorte | Sinais (`agent_signals`) |
|---|---|
| `prospective` | 177 |
| `replay:31bb3a12-090d-43ee-998b-630b2645bb46` | 3 |
| `replay:7598d6c4-c8b6-430e-974e-3a5118d3a288` | 224 |
| `replay:f8d8279c-1fba-42ae-95ef-202042f96c60` | 224 |
| **total** | **628** |

## Avaliações

As avaliações datadas ficam nas páginas de experimento, nunca duplicadas aqui:

- [[EXP-0001-momentum-v1]]

## Replicação

não iniciada — ver `docs/plans/REPLICATION.md` quando existir (T3.19).

## Ligações

- Família: [[momentum]]
- Versão anterior: [[momentum-v1]]
- Experimento: [[EXP-0001-momentum-v1]]
<!-- generated:end -->


## Notas

**Aposentada pela via auditada em 2026-09-09T14:56:27Z (T3.56)**, autorização de Everton
2026-09-09 11:50 BRT ("as que estão dando ruim pode matar"). Veredito medido (`as_of`
2026-09-09T14:52Z): negativa nas duas coortes — prospectiva −0,2167 R (n=471), replay −0,2247 R
(n=248). Sem sucessora declarada: a única `momentum` que fica viva pelo mérito é a `v8`. Ver
`.claude/state/notes-T3.56.md` §5.2 e [[momentum]].
