---
tags: ["estrategia", "catalogo", "mean_reversion"]
strategy: mean_reversion
version: v3
purpose: research_only
status: active
code_ref: "hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f"
params_hash: a71311773886
activated_at: "2026-09-08T21:34:01.491564+00:00"
deprecated_at: ""
derived_from: "[[mean_reversion-v1]]"
cohorts: ["replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4", "prospective"]
exp: ["EXP-0015 (ainda não arquivado no vault)"]
updated: 2026-09-08
---
# mean_reversion v3 (active)

<!-- generated:start -->
## Parâmetros

| Parâmetro | Valor |
|---|---|
| `assumed_spread_bps` | `2` |
| `atr_bars` | `97` |
| `atr_pct_max` | `0.05` |
| `atr_pct_min` | `0.01` |
| `atr_period` | `14` |
| `atr_timeframe` | `15m` |
| `base_confidence` | `0.5` |
| `fee_bps` | `4` |
| `horizon_s` | `14400` |
| `max_entry_delay_s` | `120` |
| `slippage_bps` | `5` |
| `stop_atr` | `1` |
| `target2_atr` | `2.5` |
| `target_atr` | `1.5` |
| `trend_sma_bars` | `20` |
| `trend_timeframe` | `1h` |
| `zscore_bars` | `20` |
| `zscore_depth_min` | `1` |

> **Nota de proveniência:** só nome e valor são conhecidos nesta sessão (lidos do `Parameters:` JSON
> publicado em `.claude/state/exp-drafts/EXP-0018-stop-largo.md` / `EXP-0019-piso-atr.md`). As colunas
> Tipo/Vínculo/Descrição do `parameters_schema` exigem o banco (`export_strategies_to_obsidian.py`),
> inacessível deste host nesta sessão — ver Notas.

## Origem

**Changelog congelado:** `variante de v1 | derived_from=v1 | overrides=atr_pct_min=0.01 | params_hash=a71311773886 | T3.42 V2: coorte de pesquisa do teto de pedagio 0,20 R (atr_pct_min 0,010) aberta` (`.claude/state/exp-drafts/EXP-0015-mean-reversion-teto-020.md`).

## Coortes e sinais

| Coorte | Sinais (`agent_signals`) |
|---|---|
| `replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4` | 11 (`EXP-0015`, retrospectiva) |
| `prospective` | aberta em 21:34:01Z; contagem exata não relida nesta sessão |

## Avaliações

As avaliações datadas ficam nas páginas de experimento, nunca duplicadas aqui:

- EXP-0015 (ainda não arquivado no vault)
**`EXP-0015` ainda não foi arquivado no vault** (permanece em `.claude/state/exp-drafts/EXP-0015-mean-reversion-teto-020.md`); sem link até a arquivagem.

**Veredito mais recente:** **inconclusivo, `REVISE` no portão** — 11 avaliáveis (< 100), 4 dias; bruta +0,6587 R, líquida **+0,5131 R**, PF 2,69. A régua do `EXP-0006`/[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] (corte > 70 % é outra estratégia) dispara por 0,3 ponto percentual (corte de 70,3 %); as 11 decisões vivem em 4 dias consecutivos de agosto — C3/C4 `REJECT` declarados.

## Replicação

não iniciada — ver `docs/plans/REPLICATION.md` quando existir (T3.19).

## Ligações

- Família: [[mean_reversion]]
- Versão anterior: [[mean_reversion-v1]]
- Experimento: EXP-0015 (ainda não arquivado no vault)
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
