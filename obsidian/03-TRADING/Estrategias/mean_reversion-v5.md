---
tags: ["estrategia", "catalogo", "mean_reversion"]
strategy: mean_reversion
version: v5
purpose: research_only
status: deprecated
code_ref: "hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f"
params_hash: dd8b22cd30a0
activated_at: "2026-09-08T22:38:41.887854+00:00"
deprecated_at: "2026-09-08T23:34:59.064478+00:00"
derived_from: "[[Estrategias/mean_reversion-v3|mean_reversion-v3]]"
cohorts: ["replay:66fa85cb-1d51-4330-a00b-00964b430ab4"]
exp: ["[[EXP-0018-stop-largo]]"]
updated: 2026-09-08
---
# mean_reversion v5 (deprecated)

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
| `stop_atr` | `2` |
| `target2_atr` | `5` |
| `target_atr` | `3` |
| `trend_sma_bars` | `20` |
| `trend_timeframe` | `1h` |
| `zscore_bars` | `20` |
| `zscore_depth_min` | `1` |

> **Nota de proveniência:** só nome e valor são conhecidos nesta sessão (lidos do `Parameters:` JSON
> publicado em `.claude/state/exp-drafts/EXP-0018-stop-largo.md` / `EXP-0019-piso-atr.md`). As colunas
> Tipo/Vínculo/Descrição do `parameters_schema` exigem o banco (`export_strategies_to_obsidian.py`),
> inacessível deste host nesta sessão — ver Notas.

## Origem

**Changelog congelado:** `variante de v3 | derived_from=v3 | overrides=stop_atr=2,target2_atr=5,target_atr=3 | params_hash=dd8b22cd30a0` (T3.47).

**Aposentadoria (T3.47b, `--deprecate`, sem sucessora):** `deprecated mean_reversion v5 (purpose research_only) at 2026-09-08T23:34:59.064478+00:00, successor=none` — veredito preservado no `changelog`: *"descartar como candidata - K1 (9 decisoes em 31 d), PF 21 sobre 8 saidas por horizonte em 4 dias consecutivos de agosto (episodio reprecificado, nao estrategia), 44% das decisoes acima do teto de stop do paper_v1, delta pareado +0,0572 R com IC95 [-0,318; +0,192]. Sem sucessora: nada a substitui"* (`.claude/state/notes-T3.47b.md`).

## Coortes e sinais

| Coorte | Sinais (`agent_signals`) |
|---|---|
| `replay:66fa85cb-1d51-4330-a00b-00964b430ab4` | 9 (`EXP-0018`, retrospectiva A2) |

## Avaliações

As avaliações datadas ficam nas páginas de experimento, nunca duplicadas aqui:

- [[EXP-0018-stop-largo]]


**Veredito mais recente:** **descartar** — K1 dispara (9 decisões em 31 d), PF alto sobre uma amostra reprecificada de 4 dias consecutivos, 44 % das decisões fora da banda de stop do `paper_v1`; aposentada pela via auditada em 2026-09-08T23:34:59Z, sem sucessora.

## Replicação

não iniciada — ver `docs/plans/REPLICATION.md` quando existir (T3.19).

## Ligações

- Família: [[mean_reversion]]
- Versão anterior: [[Estrategias/mean_reversion-v3|mean_reversion-v3]]
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
