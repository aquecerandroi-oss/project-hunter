---
tags: ["estrategia", "catalogo", "momentum"]
strategy: momentum
version: v8
purpose: research_only
status: active
code_ref: "hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c"
params_hash: 69152dbc9173
activated_at: "2026-09-08T22:29:33.049734+00:00"
deprecated_at: ""
derived_from: "[[Estrategias/momentum-v6|momentum-v6]]"
cohorts: ["replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd", "prospective"]
exp: ["[[EXP-0018-stop-largo]]"]
updated: 2026-09-08
---
# momentum v8 (active)

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
| `stop_atr` | `3` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | stop distance from the reference, in ATR |
| `target2_atr` | `12` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | informational target 2, in ATR |
| `target3_atr` | `18` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | informational target 3, in ATR |
| `target_atr` | `6` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | target1 distance from the reference, in ATR |

## Origem

**Changelog congelado:** `variante de v6 | derived_from=v6 | overrides=stop_atr=3,target2_atr=12,target3_atr=18,target_atr=6 | params_hash=69152dbc9173` (T3.47).

## Coortes e sinais

| Coorte | Sinais (`agent_signals`) |
|---|---|
| `replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd` | 181 (`EXP-0018`, retrospectiva C2) |
| `prospective` | aberta em 2026-09-08T22:29:33Z; contagem exata não relida nesta sessão |

## Avaliações

As avaliações datadas ficam nas páginas de experimento, nunca duplicadas aqui:

- [[EXP-0018-stop-largo]]

**Veredito mais recente:** **manter em pesquisa** — única com população julgável em 30 dias entre os seis braços do [[EXP-0018-stop-largo]]; Δ pareado **+0,0161 R** contra o pai `v6` (IC contém zero), ainda perde (líquida −0,0299 R, PF 0,906); reavaliação prospectiva em ~2026-10-08.

## Replicação

não iniciada — ver `docs/plans/REPLICATION.md` quando existir (T3.19).

## Ligações

- Família: [[momentum]]
- Versão anterior: [[Estrategias/momentum-v6|momentum-v6]]
- Experimento: [[EXP-0018-stop-largo]]
<!-- generated:end -->


## Notas

Página reconciliada à mão pela Sexta-feira em 2026-09-08 a partir de
`.claude/state/exp-drafts/EXP-0018-stop-largo.md`, `obsidian/05-EXPERIMENTS/EXP-0013-momentum-alvo-3-atr.md`
e `.claude/state/notes-T3.47b.md` — o host local não tem acesso ao Postgres da VPS
(`infra/scripts/export_strategies_to_obsidian.py --dry-run` falhou com
`ConnectionRefusedError`), então o `params_hash` acima é a forma **curta** (12 caracteres) publicada
no EXP, não o hash de 64 caracteres que o exportador leria do banco. Rodar o exportador confirma (ou
corrige) este campo assim que o banco estiver acessível a partir desta máquina.
