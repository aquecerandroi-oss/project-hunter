---
tags: ["estrategia", "catalogo", "mean_reversion"]
strategy: mean_reversion
version: v8
purpose: research_only
status: active
code_ref: "hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f"
params_hash: b64c4d0e4d4c
activated_at: "2026-09-08T23:37:33.252307+00:00"
deprecated_at: ""
derived_from: "[[Estrategias/mean_reversion-v2|mean_reversion-v2]]"
cohorts: ["replay:8ac79cca-916b-4f7f-bd83-01b068b9f811", "prospective"]
exp: ["[[EXP-0019-piso-atr]]"]
updated: 2026-09-08
---
# mean_reversion v8 (active)

<!-- generated:start -->
## Parâmetros

| Parâmetro | Valor |
|---|---|
| `assumed_spread_bps` | `2` |
| `atr_bars` | `97` |
| `atr_pct_max` | `0.05` |
| `atr_pct_min` | `0.006` |
| `atr_period` | `14` |
| `atr_timeframe` | `15m` |
| `base_confidence` | `0.5` |
| `fee_bps` | `4` |
| `horizon_s` | `14400` |
| `max_entry_delay_s` | `120` |
| `slippage_bps` | `5` |
| `stop_atr` | `1.5` |
| `target2_atr` | `3.75` |
| `target_atr` | `2.25` |
| `trend_sma_bars` | `20` |
| `trend_timeframe` | `1h` |
| `zscore_bars` | `20` |
| `zscore_depth_min` | `1` |

> **Nota de proveniência:** só nome e valor são conhecidos nesta sessão (lidos do `Parameters:` JSON
> publicado em `.claude/state/exp-drafts/EXP-0018-stop-largo.md` / `EXP-0019-piso-atr.md`). As colunas
> Tipo/Vínculo/Descrição do `parameters_schema` exigem o banco (`export_strategies_to_obsidian.py`),
> inacessível deste host nesta sessão — ver Notas.

## Origem

**Changelog congelado:** `variante de v2 | derived_from=v2 | overrides=atr_pct_min=0.006,stop_atr=1.5,target2_atr=3.75,target_atr=2.25 | params_hash=b64c4d0e4d4c | T3.47b D1: coorte de pesquisa do piso de ATR% 0,006 com stop 1,5 ATR aberta (research_only, sem carteira)` (`.claude/state/notes-T3.47b.md`).

## Coortes e sinais

| Coorte | Sinais (`agent_signals`) |
|---|---|
| `replay:8ac79cca-916b-4f7f-bd83-01b068b9f811` | 33 (`EXP-0019`, retrospectiva D1) |
| `prospective` | aberta em 2026-09-08T23:37:33Z; contagem exata não relida nesta sessão |

## Avaliações

As avaliações datadas ficam nas páginas de experimento, nunca duplicadas aqui:

- [[EXP-0019-piso-atr]]


**Veredito mais recente:** **inconclusivo pelo limiar editorial (o corpo do `EXP-0019` registra o sinal como `negativo`, ver a nota de vocabulário controlado naquela página)** — 33 avaliáveis (< 100), 11 dias (< 30); líquida +0,0855 R contra +0,2861 R da irmã `v6` (Δ **−0,2006 R**, IC contém zero); estresse `frágil a custos` (`custos_x2` vira **−0,0628 R**). Mantida em pesquisa **pela mensurabilidade** (é a única versão da família com população julgável em 30 dias), não pelo mérito — os quatro dias que só existem com o piso baixo são os quatro negativos: o piso escondia dias ruins, não decisões boas.

## Replicação

não iniciada — ver `docs/plans/REPLICATION.md` quando existir (T3.19).

## Ligações

- Família: [[mean_reversion]]
- Versão anterior: [[Estrategias/mean_reversion-v2|mean_reversion-v2]]
- Experimento: [[EXP-0019-piso-atr]]
<!-- generated:end -->


## Notas

Página reconciliada à mão pela Sexta-feira em 2026-09-08 a partir de
`.claude/state/exp-drafts/EXP-0014-mean-reversion-teto-025.md`,
`.claude/state/exp-drafts/EXP-0015-mean-reversion-teto-020.md`,
`obsidian/05-EXPERIMENTS/EXP-0018-stop-largo.md`, `obsidian/05-EXPERIMENTS/EXP-0019-piso-atr.md` e
`.claude/state/notes-T3.47b.md` — o host local não tem acesso ao Postgres da VPS
(`infra/scripts/export_strategies_to_obsidian.py --dry-run` falhou com `ConnectionRefusedError`),
então `params_hash` é a forma **curta** (12 caracteres) publicada no EXP, não o hash de 64 caracteres
que o exportador leria do banco, e a tabela de parâmetros não tem tipo/vínculo/descrição. Rodar o
exportador completa estes campos assim que o banco estiver acessível a partir desta máquina.
