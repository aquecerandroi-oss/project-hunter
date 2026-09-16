---
tags: [operacoes, meme, pumpfun, graficos, m4]
status: em-andamento
owner: quant-engineer
updated: 2026-09-15
rule_set: flow_v2/1
kind: research_only
exp: EXP-M5
code_ref: hunter_indicators.meme.rules:evaluate_entry+evaluate_exit
---

# flow_v2/1 — apostas traçadas

Uma imagem por aposta **fechada** do conjunto `flow_v2/1` (research_only), desenhada por `infra/scripts/meme_render_bets.py` a partir de `meme_paper_bets`, `meme_features_15s`, `meme_features_1m` e `meme_curve_snapshots` — nenhum número desta página foi digitado à mão.

**Pré-registro congelado:** [[EXP-M5-fluxo-e-holders]]. As linhas desenhadas são as **features** do fold (`support_line_sol`, `high_15m_sol`, `breakout_15m`, `higher_lows`, T4.10), lidas no minuto fechado da entrada — a mesma geometria da tela `/meme/{mint}` (`apps/web/components/meme/meme-lines.ts`). Para um conjunto que não lê linha para decidir elas são **contexto**, nunca entrada da decisão.

**Faixas com `≈`:** alvo, piso, arme e trailing medem a **marca em SOL** (o que uma venda cheia renderia, taxas incluídas — `docs/RISK_ENGINE_MEME.md` §6), não a capitalização; no gráfico os múltiplos aparecem aplicados ao mcap da entrada. O R do título é o da linha da aposta.

| régua congelada | valor |
|---|---|
| tamanho (SOL) | `0.05` |
| alvo (×) | `3` |
| trailing (%) | `35` |
| arma o trailing (×) | `1.5` |
| tempo máximo (s) | `1800` |
| piso de perda (%) | `50` |
| sai na linha rompida | sim |
| sai na migração | — |
| relógio | `15s` |

Reproduzir: `docs/PIPELINE.md` §9c. Diário do dia: [[09-OPERATIONS/Diario-Meme/README|Diário Meme]]. Índice: [[03-TRADING/Meme/Apostas-tracadas/README|Operações traçadas (meme)]].
## Dia 2026-09-14

1 aposta(s) fechada(s) — 1 medida(s), 0 indeterminada(s). Soma de R das medidas: **-0.4456**.

**Melhor · Pior · Mais recente** — LBN · 22:21:56 BRT · -0.4456 R · saída por `line_broken`.

![LBN flow_v2/1 14/09 22:21](../../../attachments/meme/2026-09-14/flow_v2-1/2221-LBN--0.45.png)

| hora (BRT) | símbolo | mint | R | saída | gráfico |
|---|---|---|---|---|---|
| 22:21:56 | LBN | `Hp9aqfw8xj…` | -0.4456 | line_broken | [2221-LBN--0.45.png](../../../attachments/meme/2026-09-14/flow_v2-1/2221-LBN--0.45.png) |

## Dia 2026-09-15

2 aposta(s) fechada(s) — 2 medida(s), 0 indeterminada(s). Soma de R das medidas: **-0.3060**.

**Melhor · Mais recente** — FLYHIGH · 17:38:42 BRT · -0.0658 R · saída por `line_broken`.

![FLYHIGH flow_v2/1 15/09 17:38](../../../attachments/meme/2026-09-15/flow_v2-1/1738-FLYHIGH--0.07.png)

**Pior** — HYPNOTIZE · 06:47:36 BRT · -0.2402 R · saída por `line_broken`.

![HYPNOTIZE flow_v2/1 15/09 06:47](../../../attachments/meme/2026-09-15/flow_v2-1/0647-HYPNOTIZE--0.24.png)

| hora (BRT) | símbolo | mint | R | saída | gráfico |
|---|---|---|---|---|---|
| 06:47:36 | HYPNOTIZE | `AdKH1t84SA…` | -0.2402 | line_broken | [0647-HYPNOTIZE--0.24.png](../../../attachments/meme/2026-09-15/flow_v2-1/0647-HYPNOTIZE--0.24.png) |
| 17:38:42 | FLYHIGH | `9w3XgArZLR…` | -0.0658 | line_broken | [1738-FLYHIGH--0.07.png](../../../attachments/meme/2026-09-15/flow_v2-1/1738-FLYHIGH--0.07.png) |
