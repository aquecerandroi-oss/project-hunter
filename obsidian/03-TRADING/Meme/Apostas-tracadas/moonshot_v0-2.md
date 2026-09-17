---
tags: [operacoes, meme, pumpfun, graficos, m4]
status: em-andamento
owner: quant-engineer
updated: 2026-09-17
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

## Dia 2026-09-16

6 aposta(s) fechada(s) — 6 medida(s), 0 indeterminada(s). Soma de R das medidas: **+3.5996**.

**Melhor** — KITE · 05:09:09 BRT · +4.4087 R · saída por `trailing`.

![KITE moonshot_v0/2 16/09 05:09](../../../attachments/meme/2026-09-16/moonshot_v0-2/0509-KITE-%2B4.41.png)

**Pior** — RASMR · 16:36:08 BRT · -0.7662 R · saída por `creator_dump`.

![RASMR moonshot_v0/2 16/09 16:36](../../../attachments/meme/2026-09-16/moonshot_v0-2/1636-RASMR--0.77.png)

**Mais recente** — CART · 18:43:22 BRT · -0.4248 R · saída por `creator_dump`.

![CART moonshot_v0/2 16/09 18:43](../../../attachments/meme/2026-09-16/moonshot_v0-2/1843-CART--0.42.png)

| hora (BRT) | símbolo | mint | R | saída | gráfico |
|---|---|---|---|---|---|
| 03:25:25 | DATBOI | `6jcGTKroM1…` | +1.2676 | trailing | [0325-DATBOI-+1.27.png](../../../attachments/meme/2026-09-16/moonshot_v0-2/0325-DATBOI-%2B1.27.png) |
| 05:09:09 | KITE | `56KcQzfmDW…` | +4.4087 | trailing | [0509-KITE-+4.41.png](../../../attachments/meme/2026-09-16/moonshot_v0-2/0509-KITE-%2B4.41.png) |
| 11:49:32 | INCEPT | `FHcHh1ELbW…` | -0.6507 | creator_dump | [1149-INCEPT--0.65.png](../../../attachments/meme/2026-09-16/moonshot_v0-2/1149-INCEPT--0.65.png) |
| 15:14:19 | LPAD | `D4fi1cAWTZ…` | -0.2351 | creator_dump | [1514-LPAD--0.24.png](../../../attachments/meme/2026-09-16/moonshot_v0-2/1514-LPAD--0.24.png) |
| 16:36:08 | RASMR | `4W6Mf2DkcK…` | -0.7662 | creator_dump | [1636-RASMR--0.77.png](../../../attachments/meme/2026-09-16/moonshot_v0-2/1636-RASMR--0.77.png) |
| 18:43:22 | CART | `365D4GYWGw…` | -0.4248 | creator_dump | [1843-CART--0.42.png](../../../attachments/meme/2026-09-16/moonshot_v0-2/1843-CART--0.42.png) |

## Dia 2026-09-17

7 aposta(s) fechada(s) — 7 medida(s), 0 indeterminada(s). Soma de R das medidas: **+0.6147**.

**Melhor** — VIRUS · 07:40:24 BRT · +1.6097 R · saída por `time_stop`.

![VIRUS moonshot_v0/2 17/09 07:40](../../../attachments/meme/2026-09-17/moonshot_v0-2/0740-VIRUS-%2B1.61.png)

**Pior** — CASHOUT · 05:09:27 BRT · -0.8141 R · saída por `time_stop`.

![CASHOUT moonshot_v0/2 17/09 05:09](../../../attachments/meme/2026-09-17/moonshot_v0-2/0509-CASHOUT--0.81.png)

**Mais recente** — MAYOR · 08:07:12 BRT · -0.2957 R · saída por `time_stop`.

![MAYOR moonshot_v0/2 17/09 08:07](../../../attachments/meme/2026-09-17/moonshot_v0-2/0807-MAYOR--0.30.png)

| hora (BRT) | símbolo | mint | R | saída | gráfico |
|---|---|---|---|---|---|
| 00:47:24 | PÉPITO | `HK1fqfGv9s…` | -0.7066 | time_stop | [0047-PÉPITO--0.71.png](../../../attachments/meme/2026-09-17/moonshot_v0-2/0047-P%C3%89PITO--0.71.png) |
| 04:56:30 | ANATROC | `2EvLSYHZhc…` | -0.0766 | creator_dump | [0456-ANATROC--0.08.png](../../../attachments/meme/2026-09-17/moonshot_v0-2/0456-ANATROC--0.08.png) |
| 05:09:27 | CASHOUT | `aN3JAry31T…` | -0.8141 | time_stop | [0509-CASHOUT--0.81.png](../../../attachments/meme/2026-09-17/moonshot_v0-2/0509-CASHOUT--0.81.png) |
| 07:34:45 | GATO | `717VW8LR4m…` | +0.9367 | trailing | [0734-GATO-+0.94.png](../../../attachments/meme/2026-09-17/moonshot_v0-2/0734-GATO-%2B0.94.png) |
| 07:40:24 | VIRUS | `1m8HuLPhyw…` | +1.6097 | time_stop | [0740-VIRUS-+1.61.png](../../../attachments/meme/2026-09-17/moonshot_v0-2/0740-VIRUS-%2B1.61.png) |
| 07:57:15 | ALLIN | `FaszL4xMRE…` | -0.0388 | time_stop | [0757-ALLIN--0.04.png](../../../attachments/meme/2026-09-17/moonshot_v0-2/0757-ALLIN--0.04.png) |
| 08:07:12 | MAYOR | `9XaVY3ugtS…` | -0.2957 | time_stop | [0807-MAYOR--0.30.png](../../../attachments/meme/2026-09-17/moonshot_v0-2/0807-MAYOR--0.30.png) |
