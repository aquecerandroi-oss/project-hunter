---
tags: ["estrategia", "catalogo", "sweep_reclaim"]
strategy: sweep_reclaim
version: v1
purpose: research_only
status: em-andamento
code_ref: "hunter_core.strategies.sweep_reclaim_v1"
params_hash: "não atribuído (nunca ativada)"
activated_at: ""
deprecated_at: ""
derived_from: ""
cohorts: []
exp: ["[[EXP-0017-sweep-reclaim]]"]
updated: 2026-09-08
---
# sweep_reclaim v1 (research_only, em-andamento)

<!-- generated:start -->
## Parâmetros

20 chaves em `default_parameters`, mais o timeframe de decisão (`15m`, atributo de classe, não
parâmetro) — tabela verbatim do contrato ([[EXP-0017-sweep-reclaim]] §"Parâmetros congelados"):

| Parâmetro | Valor | Por quê este valor |
|---|---|---|
| `pivot_k` | `3` | o `k` da T3.34; confirmação em `index + 3`, impede que a decisão dependa do futuro |
| `min_swing_atr` | `1` | o padrão de `find_pivots`; sem ele todo tremor de uma fita quieta vira "suporte" |
| `pivot_lookback_bars` | `40` | 10 h de 15 min; cabe nos 1 560 min de `SHADOW_CONTEXT_MINUTES` |
| `sweep_atr` | `0,25` | a varredura tem de ser visível **e** pequena; convenção declarada |
| `rvol_window` | `20` | 5 h de mediana, mesmo tamanho de janela da `momentum_v1` |
| `rvol_min` | `1,5` | convenção declarada; já congelado por `momentum_v1` e `breakout_v1` |
| `atr_period` | `14` | Wilder |
| `atr_timeframe` | `15m` | a mesma barra da decisão |
| `atr_bars` | `97` | `rolling_window_v1`: 82 passos de suavização derrubam o peso da semente a ~0,23 % |
| `stop_buffer_atr` | `0,10` | stop **abaixo** da mínima varrida, não nela |
| `risk_pct_min` | `0,006` | a porta de custo: fixa o teto de pedágio em `0,0020/0,006 = 0,3333 R` |
| `risk_atr_max` | `3` | recusa a varredura de um pivô longe demais |
| `target_r` | `2` | equilíbrio 44,5 % no piso de custo |
| `target2_r` | `3` | informativo |
| `horizon_s` | `14400` | 4 h = 16 barras |
| `base_confidence` | `0,5` | constante não calibrada, como nas outras estratégias |
| `assumed_spread_bps` | `2` | `docs/plans/SHADOW-LAB.md` §3 |
| `slippage_bps` | `5` | `docs/plans/SHADOW-LAB.md` §3 |
| `fee_bps` | `4` | `docs/plans/SHADOW-LAB.md` §3 |
| `max_entry_delay_s` | `120` | `docs/plans/SHADOW-LAB.md` §3 |

**Invalidação:** nenhuma, por desenho declarado (a mínima varrida já é o stop; ver
[[EXP-0017-sweep-reclaim]] §"Por que nenhuma invalidação"). **Universo (replay planejado):**
binance ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT.

## Origem

**Contrato:** T3.45 (`.claude/state/brief-T3.45`), portão C1–C8 = 70,5 `REVISE` (C8 `fail` por
desenho — sem invalidação). **Pré-checagem** (somente leitura, `2026-09-09-sweep-reclaim-precheck.sql`):
57 eventos em 31 d × 4 mercados, 17 dias distintos, 30 % no maior mercado (XRPUSDT), cobertura
99,50 % — nenhuma regra de morte (P1–P4) disparou. **Implementação:** T3.45b, commit `a9bacc6`
("sweep_reclaim_v1 (stop estrutural, porta de custo por risco% 0,006, teto 0,3333 R, 46 testes,
digests vivos intactos)"). **Nenhuma ativação, nenhuma coorte, nenhum replay** foram executados até
2026-09-08 — `sweep_reclaim: implemented, replay pending`.

## Coortes e sinais

Nenhuma coorte aberta ainda (nem `research_only`, nem `replay:<run_id>`). O próximo passo é ativar
pela via auditada e rodar o replay de 31 dias sobre os quatro mercados do contrato.

## Avaliações

As avaliações datadas ficam na página de experimento, nunca duplicadas aqui:

- [[EXP-0017-sweep-reclaim]] — pré-checagem de 2026-09-08 (população, não edge: **inconclusivo**,
  "nada foi medido sobre a hipótese").

## Replicação

não iniciada — ver `docs/plans/REPLICATION.md` quando existir (T3.19).

## Ligações

- Família: [[sweep_reclaim]]
- Experimento: [[EXP-0017-sweep-reclaim]]
- Mecanismo aparentado: [[mean_reversion-v1]] (eixo de reversão; a divergência de desenho está
  declarada no próprio EXP)
<!-- generated:end -->


## Notas

Página criada à mão pela Sexta-feira em 2026-09-08 a partir de [[EXP-0017-sweep-reclaim]] — o host
local não alcança o Postgres da VPS (`export_strategies_to_obsidian.py --dry-run` falhou com
`ConnectionRefusedError`), então `code_ref` fica sem o digest sha256 (não citado no corpo do EXP;
seria confirmado pelo `--dry-run` do `activate_strategy_version.py` na ativação) e `params_hash` fica
vazio até a primeira ativação gravar os dois no banco.
