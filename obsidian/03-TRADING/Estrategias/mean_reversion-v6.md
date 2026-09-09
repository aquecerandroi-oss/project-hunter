---
tags: ["estrategia", "catalogo", "mean_reversion"]
strategy: mean_reversion
version: v6
purpose: research_only
status: active
code_ref: "hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f"
params_hash: 11ce73ed48b5
activated_at: "2026-09-08T22:38:46.022557+00:00"
deprecated_at: ""
derived_from: "[[Estrategias/mean_reversion-v2|mean_reversion-v2]]"
cohorts: ["replay:9d99748b-21b9-44a7-8980-32c37b931e6e"]
exp: ["[[EXP-0018-stop-largo]]"]
updated: 2026-09-08
---
# mean_reversion v6 (active)

<!-- generated:start -->
## Parâmetros

| Parâmetro | Valor |
|---|---|
| `assumed_spread_bps` | `2` |
| `atr_bars` | `97` |
| `atr_pct_max` | `0.05` |
| `atr_pct_min` | `0.008` |
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

**Changelog congelado:** `variante de v2 | derived_from=v2 | overrides=stop_atr=1.5,target2_atr=3.75,target_atr=2.25 | params_hash=11ce73ed48b5` (T3.47).

## Coortes e sinais

| Coorte | Sinais (`agent_signals`) |
|---|---|
| `replay:9d99748b-21b9-44a7-8980-32c37b931e6e` | 15 (`EXP-0018`, retrospectiva B1; também controle do `EXP-0019` D1) |

## Avaliações

As avaliações datadas ficam nas páginas de experimento, nunca duplicadas aqui:

- [[EXP-0018-stop-largo]]


**Veredito mais recente:** **manter em pesquisa — melhor candidata do eixo `stop largo`** — guarda **95 %** da economia de pedágio (líquida +0,2861 R, PF 2,282); K1 (15 decisões) impede conclusão. O [[EXP-0019-piso-atr]] mediu depois que baixar o piso de ATR% para resolver o K1 **destrói** a expectância (faixa nova a −0,08 R): a leitura correta do K1 é esperar mais meses de coleta, não mexer no piso.

## Replicação

não iniciada — ver `docs/plans/REPLICATION.md` quando existir (T3.19).

## Ligações

- Família: [[mean_reversion]]
- Versão anterior: [[Estrategias/mean_reversion-v2|mean_reversion-v2]]
- Experimento: [[EXP-0018-stop-largo]]
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
