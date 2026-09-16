---
tags: [operacoes, meme, pumpfun, graficos, m4]
status: em-andamento
owner: quant-engineer
updated: 2026-09-15
rule_set: moonshot_v0/2
kind: research_only
exp: EXP-M4
code_ref: hunter_indicators.meme.rules:evaluate_entry+evaluate_exit
---

# moonshot_v0/2 — apostas traçadas

Uma imagem por aposta **fechada** do conjunto `moonshot_v0/2` (research_only), desenhada por `infra/scripts/meme_render_bets.py` a partir de `meme_paper_bets`, `meme_features_15s`, `meme_features_1m` e `meme_curve_snapshots` — nenhum número desta página foi digitado à mão.

**Pré-registro congelado:** [[EXP-M4-moonshot]]. As linhas desenhadas são as **features** do fold (`support_line_sol`, `high_15m_sol`, `breakout_15m`, `higher_lows`, T4.10), lidas no minuto fechado da entrada — a mesma geometria da tela `/meme/{mint}` (`apps/web/components/meme/meme-lines.ts`). Para um conjunto que não lê linha para decidir elas são **contexto**, nunca entrada da decisão.

**Faixas com `≈`:** alvo, piso, arme e trailing medem a **marca em SOL** (o que uma venda cheia renderia, taxas incluídas — `docs/RISK_ENGINE_MEME.md` §6), não a capitalização; no gráfico os múltiplos aparecem aplicados ao mcap da entrada. O R do título é o da linha da aposta.

| régua congelada | valor |
|---|---|
| tamanho (SOL) | `0.02` |
| alvo (×) | `25` |
| trailing (%) | `50` |
| arma o trailing (×) | `3` |
| tempo máximo (s) | `7200` |
| piso de perda (%) | `100` |
| sai na linha rompida | — |
| sai na migração | não |
| relógio | — |

Reproduzir: `docs/PIPELINE.md` §9c. Diário do dia: [[09-OPERATIONS/Diario-Meme/README|Diário Meme]]. Índice: [[03-TRADING/Meme/Apostas-tracadas/README|Operações traçadas (meme)]].
## Dia 2026-09-14

6 aposta(s) fechada(s) — 6 medida(s), 0 indeterminada(s). Soma de R das medidas: **-0.9617**.

**Melhor** — BENDRILLR · 16:49:16 BRT · +0.5703 R · saída por `time_stop`.

![BENDRILLR moonshot_v0/2 14/09 16:49](../../../attachments/meme/2026-09-14/moonshot_v0-2/1649-BENDRILLR-%2B0.57.png)

**Pior** — CTB · 07:15:11 BRT · -0.842 R · saída por `time_stop`.

![CTB moonshot_v0/2 14/09 07:15](../../../attachments/meme/2026-09-14/moonshot_v0-2/0715-CTB--0.84.png)

**Mais recente** — LBN · 22:23:26 BRT · -0.4649 R · saída por `creator_dump`.

![LBN moonshot_v0/2 14/09 22:23](../../../attachments/meme/2026-09-14/moonshot_v0-2/2223-LBN--0.46.png)

| hora (BRT) | símbolo | mint | R | saída | gráfico |
|---|---|---|---|---|---|
| 03:23:14 | UNCLE | `J5iARiAWbd…` | -0.0367 | creator_dump | [0323-UNCLE--0.04.png](../../../attachments/meme/2026-09-14/moonshot_v0-2/0323-UNCLE--0.04.png) |
| 07:15:11 | CTB | `4afLRsZLb4…` | -0.842 | time_stop | [0715-CTB--0.84.png](../../../attachments/meme/2026-09-14/moonshot_v0-2/0715-CTB--0.84.png) |
| 10:24:08 | DICARPIO | `25zWDWqsvv…` | -0.0524 | creator_dump | [1024-DICARPIO--0.05.png](../../../attachments/meme/2026-09-14/moonshot_v0-2/1024-DICARPIO--0.05.png) |
| 16:49:16 | BENDRILLR | `DmccGwRcUU…` | +0.5703 | time_stop | [1649-BENDRILLR-+0.57.png](../../../attachments/meme/2026-09-14/moonshot_v0-2/1649-BENDRILLR-%2B0.57.png) |
| 16:53:17 | STUART | `8fJjPjFc9P…` | -0.1359 | time_stop | [1653-STUART--0.14.png](../../../attachments/meme/2026-09-14/moonshot_v0-2/1653-STUART--0.14.png) |
| 22:23:26 | LBN | `Hp9aqfw8xj…` | -0.4649 | creator_dump | [2223-LBN--0.46.png](../../../attachments/meme/2026-09-14/moonshot_v0-2/2223-LBN--0.46.png) |

## Dia 2026-09-15

7 aposta(s) fechada(s) — 7 medida(s), 0 indeterminada(s). Soma de R das medidas: **+2.8365**.

**Melhor** — HYPNOTIZE · 06:46:16 BRT · +3.3555 R · saída por `trailing`.

![HYPNOTIZE moonshot_v0/2 15/09 06:46](../../../attachments/meme/2026-09-15/moonshot_v0-2/0646-HYPNOTIZE-%2B3.36.png)

**Pior** — FLYHIGH · 17:40:27 BRT · -0.824 R · saída por `creator_dump`.

![FLYHIGH moonshot_v0/2 15/09 17:40](../../../attachments/meme/2026-09-15/moonshot_v0-2/1740-FLYHIGH--0.82.png)

**Mais recente** — BOLDCOIN · 18:55:29 BRT · +0.7689 R · saída por `creator_dump`.

![BOLDCOIN moonshot_v0/2 15/09 18:55](../../../attachments/meme/2026-09-15/moonshot_v0-2/1855-BOLDCOIN-%2B0.77.png)

| hora (BRT) | símbolo | mint | R | saída | gráfico |
|---|---|---|---|---|---|
| 06:46:16 | HYPNOTIZE | `AdKH1t84SA…` | +3.3555 | trailing | [0646-HYPNOTIZE-+3.36.png](../../../attachments/meme/2026-09-15/moonshot_v0-2/0646-HYPNOTIZE-%2B3.36.png) |
| 09:20:20 | BDOGC | `261sDw1fQ1…` | -0.0484 | time_stop | [0920-BDOGC--0.05.png](../../../attachments/meme/2026-09-15/moonshot_v0-2/0920-BDOGC--0.05.png) |
| 11:34:22 | ETCH | `3zw996PTFi…` | +0.3804 | creator_dump | [1134-ETCH-+0.38.png](../../../attachments/meme/2026-09-15/moonshot_v0-2/1134-ETCH-%2B0.38.png) |
| 14:28:22 | PHANTOM | `7TBsLxMbhD…` | -0.0746 | time_stop | [1428-PHANTOM--0.07.png](../../../attachments/meme/2026-09-15/moonshot_v0-2/1428-PHANTOM--0.07.png) |
| 14:42:17 | CAPS | `B795sDDSw9…` | -0.7211 | time_stop | [1442-CAPS--0.72.png](../../../attachments/meme/2026-09-15/moonshot_v0-2/1442-CAPS--0.72.png) |
| 17:40:27 | FLYHIGH | `9w3XgArZLR…` | -0.824 | creator_dump | [1740-FLYHIGH--0.82.png](../../../attachments/meme/2026-09-15/moonshot_v0-2/1740-FLYHIGH--0.82.png) |
| 18:55:29 | BOLDCOIN | `EZdoYwMPiS…` | +0.7689 | creator_dump | [1855-BOLDCOIN-+0.77.png](../../../attachments/meme/2026-09-15/moonshot_v0-2/1855-BOLDCOIN-%2B0.77.png) |
