---
tags: ["estrategia", "catalogo", "momentum"]
strategy: momentum
version: v6
purpose: research_only
status: deprecated
code_ref: "hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c"
params_hash: 8cb1aa497956
activated_at: "2026-09-08T19:04:56.213531+00:00"
deprecated_at: "2026-09-09T14:58:00.789121+00:00"
derived_from: "[[momentum-v2]]"
cohorts: ["replay:9a08835a-ae13-4c23-b521-734b2f60a3a2", "prospective"]
exp: ["[[EXP-0013-momentum-alvo-3-atr]]"]
updated: 2026-09-09
---
# momentum v6 (deprecated)

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
| `target2_atr` | `6` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | informational target 2, in ATR |
| `target3_atr` | `9` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | informational target 3, in ATR |
| `target_atr` | `3` | string \| number | regex `^-?[0-9]+(\.[0-9]+)?$` | target1 distance from the reference, in ATR |

## Origem

**Changelog congelado:** `variante de v2 | derived_from=v2 | overrides=target2_atr=6,target3_atr=9,target_atr=3 | params_hash=8cb1aa497956` (T3.40/T3.41; a mudança literal `--set target_atr=3.0` foi recusada pelo `derive_variant.py` porque `target_atr` precisa ser menor que `target2_atr`, resolvida deslocando a escada inteira para 3/6/9).

## Coortes e sinais

| Coorte | Sinais (`agent_signals`) |
|---|---|
| `replay:9a08835a-ae13-4c23-b521-734b2f60a3a2` | 196 (`EXP-0013`, retrospectiva pareada com o pai `v2`) |
| `prospective` | aberta em 2026-09-08T19:04:56Z; contagem exata não relida nesta sessão (ver EXP-0013 e exportador) |

## Avaliações

As avaliações datadas ficam nas páginas de experimento, nunca duplicadas aqui:

- [[EXP-0013-momentum-alvo-3-atr]]

**Veredito mais recente:** **inconclusivo, mantida em pesquisa** — replay pareado com o pai (191 pares): Δ líquido **+0,1341 R** por decisão, mas o IC 95 % por bloco de dia **[−0,0939; +0,1866] contém zero**; a variante reduz a perda em 70 % (líquida −0,0513 R, PF 0,9064) sem inverter o sinal ([[EXP-0013-momentum-alvo-3-atr]]).

## Replicação

não iniciada — ver `docs/plans/REPLICATION.md` quando existir (T3.19).

## Ligações

- Família: [[momentum]]
- Versão anterior: [[momentum-v2]]
- Experimento: [[EXP-0013-momentum-alvo-3-atr]]
<!-- generated:end -->


## Notas

**Aposentada pela via auditada em 2026-09-09T14:58:00Z (T3.56)**, sucessora `momentum v8` (mesma
linhagem, stop 3 ATR). Veredito medido (`as_of` 2026-09-09T14:52Z): negativa nas duas coortes —
prospectiva −0,2856 R (n=156), replay −0,0513 R (n=195). Ver `.claude/state/notes-T3.56.md` §5.4.

Página reconciliada à mão pela Sexta-feira em 2026-09-08 a partir de
`.claude/state/exp-drafts/EXP-0018-stop-largo.md`, `obsidian/05-EXPERIMENTS/EXP-0013-momentum-alvo-3-atr.md`
e `.claude/state/notes-T3.47b.md` — o host local não tem acesso ao Postgres da VPS
(`infra/scripts/export_strategies_to_obsidian.py --dry-run` falhou com
`ConnectionRefusedError`), então o `params_hash` acima é a forma **curta** (12 caracteres) publicada
no EXP, não o hash de 64 caracteres que o exportador leria do banco. Rodar o exportador confirma (ou
corrige) este campo assim que o banco estiver acessível a partir desta máquina.
