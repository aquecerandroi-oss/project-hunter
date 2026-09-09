---
tags: ["estrategia", "catalogo", "momentum"]
strategy: momentum
version: v7
purpose: research_only
status: deprecated
code_ref: "hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c"
params_hash: 5e456ae9eb5b
activated_at: "2026-09-08T22:29:28.783999+00:00"
deprecated_at: "2026-09-08T23:34:42.370162+00:00"
derived_from: "[[Estrategias/momentum-v6|momentum-v6]]"
cohorts: ["replay:293d98b7-90e1-4dfe-a604-60556f3b175e", "prospective"]
exp: ["[[EXP-0018-stop-largo]]"]
updated: 2026-09-08
---
# momentum v7 (deprecated)

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
| `stop_atr` | `2.25` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | stop distance from the reference, in ATR |
| `target2_atr` | `9` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | informational target 2, in ATR |
| `target3_atr` | `13.5` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | informational target 3, in ATR |
| `target_atr` | `4.5` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | target1 distance from the reference, in ATR |

## Origem

**Changelog congelado:** `variante de v6 | derived_from=v6 | overrides=stop_atr=2.25,target2_atr=9,target3_atr=13.5,target_atr=4.5 | params_hash=5e456ae9eb5b` (T3.47).

**Aposentadoria (T3.47b, `--deprecate --successor v8`):** `deprecated momentum v7 (purpose research_only) at 2026-09-08T23:34:42.370162+00:00, successor=momentum v8` — o script preserva o prefixo de linhagem no `changelog` e acrescenta o veredito: *"descartar - delta pareado -0,0040 R em 181 pares (pior que o pai momentum v6), 105% da economia de pedagio devolvida no bruto, estresse sem_vantagem_na_base (-0,0568 R, PF 0,859 contra -0,0513 e PF 0,906 do pai); dominada pela irma v8 em toda metrica"* (`.claude/state/notes-T3.47b.md`).

## Coortes e sinais

| Coorte | Sinais (`agent_signals`) |
|---|---|
| `replay:293d98b7-90e1-4dfe-a604-60556f3b175e` | 184 (`EXP-0018`, retrospectiva C1) |
| `prospective` | aberta em 22:29:28Z e encerrada pela aposentadoria às 23:34:42Z no mesmo dia; contagem de sinais prospectivos não relida nesta sessão |

## Avaliações

As avaliações datadas ficam nas páginas de experimento, nunca duplicadas aqui:

- [[EXP-0018-stop-largo]]

**Veredito mais recente:** **descartar** — Δ pareado **−0,0040 R** (181 pares) contra o pai `v6`, dominada pela irmã `v8` em toda métrica; aposentada pela via auditada em 2026-09-08T23:34:42Z, sucessora `momentum v8` ([[EXP-0018-stop-largo]]).

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
