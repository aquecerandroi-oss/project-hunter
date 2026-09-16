---
tags: [operacoes, meme, pumpfun, graficos, m4]
status: em-andamento
owner: quant-engineer
updated: 2026-09-15
rule_set: flow_v2/3
kind: research_only
exp: EXP-M5
code_ref: hunter_indicators.meme.rules:evaluate_entry+evaluate_exit
---

# flow_v2/3 — apostas traçadas

Uma imagem por aposta **fechada** do conjunto `flow_v2/3` (research_only), desenhada por `infra/scripts/meme_render_bets.py` a partir de `meme_paper_bets`, `meme_features_15s`, `meme_features_1m` e `meme_curve_snapshots` — nenhum número desta página foi digitado à mão.

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

## Dia 2026-09-15

6 aposta(s) fechada(s) — 6 medida(s), 0 indeterminada(s). Soma de R das medidas: **-0.4012**.

**Melhor** — MITCHELLE · 17:55:34 BRT · +0.5495 R · saída por `line_broken`.

![MITCHELLE flow_v2/3 15/09 17:55](../../../attachments/meme/2026-09-15/flow_v2-3/1755-MITCHELLE-%2B0.55.png)

**Pior** — FRUK · 17:34:09 BRT · -0.911 R · saída por `creator_dump`.

![FRUK flow_v2/3 15/09 17:34](../../../attachments/meme/2026-09-15/flow_v2-3/1734-FRUK--0.91.png)

**Mais recente** — KITH · 19:00:59 BRT · +0.3282 R · saída por `line_broken`.

![KITH flow_v2/3 15/09 19:00](../../../attachments/meme/2026-09-15/flow_v2-3/1900-KITH-%2B0.33.png)

| hora (BRT) | símbolo | mint | R | saída | gráfico |
|---|---|---|---|---|---|
| 17:28:40 | NOIRA | `CLK5SyTFhn…` | -0.169 | line_broken | [1728-NOIRA--0.17.png](../../../attachments/meme/2026-09-15/flow_v2-3/1728-NOIRA--0.17.png) |
| 17:34:09 | FRUK | `6FQ8MCvigJ…` | -0.911 | creator_dump | [1734-FRUK--0.91.png](../../../attachments/meme/2026-09-15/flow_v2-3/1734-FRUK--0.91.png) |
| 17:55:34 | MITCHELLE | `BdGyZJL81E…` | +0.5495 | line_broken | [1755-MITCHELLE-+0.55.png](../../../attachments/meme/2026-09-15/flow_v2-3/1755-MITCHELLE-%2B0.55.png) |
| 18:11:45 | DPUMP | `5aBAkzHnxo…` | -0.0172 | creator_dump | [1811-DPUMP--0.02.png](../../../attachments/meme/2026-09-15/flow_v2-3/1811-DPUMP--0.02.png) |
| 18:33:00 | NYAN | `CVe9RECt4p…` | -0.1817 | line_broken | [1833-NYAN--0.18.png](../../../attachments/meme/2026-09-15/flow_v2-3/1833-NYAN--0.18.png) |
| 19:00:59 | KITH | `Rvwhhtjw1p…` | +0.3282 | line_broken | [1900-KITH-+0.33.png](../../../attachments/meme/2026-09-15/flow_v2-3/1900-KITH-%2B0.33.png) |
