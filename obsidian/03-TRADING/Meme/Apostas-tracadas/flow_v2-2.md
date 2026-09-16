---
tags: [operacoes, meme, pumpfun, graficos, m4]
status: em-andamento
owner: quant-engineer
updated: 2026-09-16
rule_set: flow_v2/2
kind: research_only
exp: EXP-M5
code_ref: hunter_indicators.meme.rules:evaluate_entry+evaluate_exit
---

# flow_v2/2 — apostas traçadas

Uma imagem por aposta **fechada** do conjunto `flow_v2/2` (research_only), desenhada por `infra/scripts/meme_render_bets.py` a partir de `meme_paper_bets`, `meme_features_15s`, `meme_features_1m` e `meme_curve_snapshots` — nenhum número desta página foi digitado à mão.

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

21 aposta(s) fechada(s) — 21 medida(s), 0 indeterminada(s). Soma de R das medidas: **-3.8006**.

**Melhor** — POGOCOIN · 05:57:38 BRT · +0.4031 R · saída por `line_broken`.

![POGOCOIN flow_v2/2 14/09 05:57](../../../attachments/meme/2026-09-14/flow_v2-2/0557-POGOCOIN-%2B0.40.png)

**Pior** — RABBITSON · 02:18:22 BRT · -0.7881 R · saída por `creator_dump`.

![RABBITSON flow_v2/2 14/09 02:18](../../../attachments/meme/2026-09-14/flow_v2-2/0218-RABBITSON--0.79.png)

**Mais recente** — QUANTHROP · 13:12:31 BRT · -0.1674 R · saída por `line_broken`.

![QUANTHROP flow_v2/2 14/09 13:12](../../../attachments/meme/2026-09-14/flow_v2-2/1312-QUANTHROP--0.17.png)

| hora (BRT) | símbolo | mint | R | saída | gráfico |
|---|---|---|---|---|---|
| 02:02:35 | SHROOMS | `5zEJv98Gen…` | -0.0403 | line_broken | [0202-SHROOMS--0.04.png](../../../attachments/meme/2026-09-14/flow_v2-2/0202-SHROOMS--0.04.png) |
| 02:18:22 | RABBITSON | `GJ1UcM2YSr…` | -0.7881 | creator_dump | [0218-RABBITSON--0.79.png](../../../attachments/meme/2026-09-14/flow_v2-2/0218-RABBITSON--0.79.png) |
| 02:38:35 | WOODS | `3mg9SaHmnU…` | -0.441 | creator_dump | [0238-WOODS--0.44.png](../../../attachments/meme/2026-09-14/flow_v2-2/0238-WOODS--0.44.png) |
| 03:25:49 | ETCAMAH | `5TncKg7ddH…` | -0.0134 | creator_dump | [0325-ETCAMAH--0.01.png](../../../attachments/meme/2026-09-14/flow_v2-2/0325-ETCAMAH--0.01.png) |
| 05:29:01 | TOPBLAST | `EhpeXu97rY…` | +0.0186 | line_broken | [0529-TOPBLAST-+0.02.png](../../../attachments/meme/2026-09-14/flow_v2-2/0529-TOPBLAST-%2B0.02.png) |
| 05:56:50 | THALEAAI | `7VxFoVMgsM…` | -0.306 | time_stop | [0556-THALEAAI--0.31.png](../../../attachments/meme/2026-09-14/flow_v2-2/0556-THALEAAI--0.31.png) |
| 05:57:38 | POGOCOIN | `GHhmR5PGcC…` | +0.4031 | line_broken | [0557-POGOCOIN-+0.40.png](../../../attachments/meme/2026-09-14/flow_v2-2/0557-POGOCOIN-%2B0.40.png) |
| 06:23:47 | BALLS | `EytoSxwBFD…` | -0.1043 | creator_dump | [0623-BALLS--0.10.png](../../../attachments/meme/2026-09-14/flow_v2-2/0623-BALLS--0.10.png) |
| 06:44:15 | BABITA | `8W83qMuygm…` | +0.3775 | line_broken | [0644-BABITA-+0.38.png](../../../attachments/meme/2026-09-14/flow_v2-2/0644-BABITA-%2B0.38.png) |
| 08:02:50 | JABALI | `HPrPCcVyhj…` | -0.2464 | creator_dump | [0802-JABALI--0.25.png](../../../attachments/meme/2026-09-14/flow_v2-2/0802-JABALI--0.25.png) |
| 09:32:27 | HEDGEHOG | `EbmHC1LCcE…` | -0.0597 | line_broken | [0932-HEDGEHOG--0.06.png](../../../attachments/meme/2026-09-14/flow_v2-2/0932-HEDGEHOG--0.06.png) |
| 09:34:39 | FIHDIH | `G37hddA7Dv…` | -0.0181 | line_broken | [0934-FIHDIH--0.02.png](../../../attachments/meme/2026-09-14/flow_v2-2/0934-FIHDIH--0.02.png) |
| 09:59:54 | SEPE | `DuK4UHAYpQ…` | +0.0584 | creator_dump | [0959-SEPE-+0.06.png](../../../attachments/meme/2026-09-14/flow_v2-2/0959-SEPE-%2B0.06.png) |
| 10:05:10 | MALKIN | `FNvkVXVvpE…` | -0.0477 | line_broken | [1005-MALKIN--0.05.png](../../../attachments/meme/2026-09-14/flow_v2-2/1005-MALKIN--0.05.png) |
| 10:09:36 | ROO | `7PjBxJhPSD…` | -0.1306 | creator_dump | [1009-ROO--0.13.png](../../../attachments/meme/2026-09-14/flow_v2-2/1009-ROO--0.13.png) |
| 10:18:21 | PUMPDOG | `5kJ9jKaPNm…` | -0.581 | max_loss | [1018-PUMPDOG--0.58.png](../../../attachments/meme/2026-09-14/flow_v2-2/1018-PUMPDOG--0.58.png) |
| 10:29:29 | ALTO | `PH84sm35uJ…` | -0.7426 | max_loss | [1029-ALTO--0.74.png](../../../attachments/meme/2026-09-14/flow_v2-2/1029-ALTO--0.74.png) |
| 10:55:27 | 胆子肥 | `A7TN4eqhJ6…` | -0.6793 | creator_dump | [1055-胆子肥--0.68.png](../../../attachments/meme/2026-09-14/flow_v2-2/1055-%E8%83%86%E5%AD%90%E8%82%A5--0.68.png) |
| 10:55:43 | BIKINIHOUSE | `HewpaqSnF5…` | +0.2844 | creator_dump | [1055-BIKINIHOUSE-+0.28.png](../../../attachments/meme/2026-09-14/flow_v2-2/1055-BIKINIHOUSE-%2B0.28.png) |
| 11:38:41 | ORB | `9qdvsftkST…` | -0.5769 | creator_dump | [1138-ORB--0.58.png](../../../attachments/meme/2026-09-14/flow_v2-2/1138-ORB--0.58.png) |
| 13:12:31 | QUANTHROP | `G2bJr5gYqn…` | -0.1674 | line_broken | [1312-QUANTHROP--0.17.png](../../../attachments/meme/2026-09-14/flow_v2-2/1312-QUANTHROP--0.17.png) |

## Dia 2026-09-15

23 aposta(s) fechada(s) — 23 medida(s), 0 indeterminada(s). Soma de R das medidas: **-4.8949**.

**Melhor** — ASSCOIN · 02:12:09 BRT · +0.5979 R · saída por `creator_dump`.

![ASSCOIN flow_v2/2 15/09 02:12](../../../attachments/meme/2026-09-15/flow_v2-2/0212-ASSCOIN-%2B0.60.png)

**Pior** — SOLSOUNDS · 06:56:53 BRT · -0.7911 R · saída por `time_stop`.

![SOLSOUNDS flow_v2/2 15/09 06:56](../../../attachments/meme/2026-09-15/flow_v2-2/0656-SOLSOUNDS--0.79.png)

**Mais recente** — ALON · 07:27:12 BRT · -0.4154 R · saída por `creator_dump`.

![ALON flow_v2/2 15/09 07:27](../../../attachments/meme/2026-09-15/flow_v2-2/0727-ALON--0.42.png)

| hora (BRT) | símbolo | mint | R | saída | gráfico |
|---|---|---|---|---|---|
| 00:03:17 | KIRKYAHU | `BgJGJNyu6m…` | +0.0809 | line_broken | [0003-KIRKYAHU-+0.08.png](../../../attachments/meme/2026-09-15/flow_v2-2/0003-KIRKYAHU-%2B0.08.png) |
| 00:05:23 | KIRKYAHU | `BgJGJNyu6m…` | -0.2278 | line_broken | [0005-KIRKYAHU--0.23.png](../../../attachments/meme/2026-09-15/flow_v2-2/0005-KIRKYAHU--0.23.png) |
| 00:15:42 | HOT | `6NPa4ww1Gq…` | -0.4113 | creator_dump | [0015-HOT--0.41.png](../../../attachments/meme/2026-09-15/flow_v2-2/0015-HOT--0.41.png) |
| 01:20:48 | 21CABBAGE | `Gx5rXExD2p…` | +0.1303 | line_broken | [0120-21CABBAGE-+0.13.png](../../../attachments/meme/2026-09-15/flow_v2-2/0120-21CABBAGE-%2B0.13.png) |
| 01:33:23 | PLASMA | `FFFomNPUNv…` | -0.7068 | max_loss | [0133-PLASMA--0.71.png](../../../attachments/meme/2026-09-15/flow_v2-2/0133-PLASMA--0.71.png) |
| 01:58:31 | ASIANDOG | `BgP6Hwn5XC…` | -0.3526 | creator_dump | [0158-ASIANDOG--0.35.png](../../../attachments/meme/2026-09-15/flow_v2-2/0158-ASIANDOG--0.35.png) |
| 02:12:09 | ASSCOIN | `GNjHEoZK5R…` | +0.5979 | creator_dump | [0212-ASSCOIN-+0.60.png](../../../attachments/meme/2026-09-15/flow_v2-2/0212-ASSCOIN-%2B0.60.png) |
| 02:53:38 | YENNII56 | `CxMf8sTCij…` | -0.0665 | creator_dump | [0253-YENNII56--0.07.png](../../../attachments/meme/2026-09-15/flow_v2-2/0253-YENNII56--0.07.png) |
| 02:54:25 | BLAST | `BwcWz1LdGe…` | -0.5863 | max_loss | [0254-BLAST--0.59.png](../../../attachments/meme/2026-09-15/flow_v2-2/0254-BLAST--0.59.png) |
| 03:10:51 | CUBA | `HEH8n3YfYq…` | -0.299 | creator_dump | [0310-CUBA--0.30.png](../../../attachments/meme/2026-09-15/flow_v2-2/0310-CUBA--0.30.png) |
| 03:12:45 | RUSELL | `5y35sVHmBH…` | -0.1101 | creator_dump | [0312-RUSELL--0.11.png](../../../attachments/meme/2026-09-15/flow_v2-2/0312-RUSELL--0.11.png) |
| 03:15:33 | OG | `JB3Rrt2HT3…` | -0.0434 | line_broken | [0315-OG--0.04.png](../../../attachments/meme/2026-09-15/flow_v2-2/0315-OG--0.04.png) |
| 04:03:30 | ANSIM | `9aZFnxKCAv…` | -0.5117 | max_loss | [0403-ANSIM--0.51.png](../../../attachments/meme/2026-09-15/flow_v2-2/0403-ANSIM--0.51.png) |
| 04:24:10 | LEBROOM | `82KAQ8mvhR…` | -0.0418 | line_broken | [0424-LEBROOM--0.04.png](../../../attachments/meme/2026-09-15/flow_v2-2/0424-LEBROOM--0.04.png) |
| 04:35:29 | TBUZZ | `FmfB54HiRF…` | +0.02 | creator_dump | [0435-TBUZZ-+0.02.png](../../../attachments/meme/2026-09-15/flow_v2-2/0435-TBUZZ-%2B0.02.png) |
| 06:12:13 | SOLFLY | `99B9ZJWagN…` | -0.0984 | line_broken | [0612-SOLFLY--0.10.png](../../../attachments/meme/2026-09-15/flow_v2-2/0612-SOLFLY--0.10.png) |
| 06:46:00 | STOCKPILLS | `73PrUsqpcx…` | -0.3918 | max_loss | [0646-STOCKPILLS--0.39.png](../../../attachments/meme/2026-09-15/flow_v2-2/0646-STOCKPILLS--0.39.png) |
| 06:47:36 | HYPNOTIZE | `AdKH1t84SA…` | -0.2402 | line_broken | [0647-HYPNOTIZE--0.24.png](../../../attachments/meme/2026-09-15/flow_v2-2/0647-HYPNOTIZE--0.24.png) |
| 06:49:42 | HYPNOTIZE | `AdKH1t84SA…` | +0.271 | line_broken | [0649-HYPNOTIZE-+0.27.png](../../../attachments/meme/2026-09-15/flow_v2-2/0649-HYPNOTIZE-%2B0.27.png) |
| 06:56:53 | SOLSOUNDS | `EU7cRDihom…` | -0.7911 | time_stop | [0656-SOLSOUNDS--0.79.png](../../../attachments/meme/2026-09-15/flow_v2-2/0656-SOLSOUNDS--0.79.png) |
| 07:05:49 | TUDUM | `FDchkT7ycr…` | +0.0469 | creator_dump | [0705-TUDUM-+0.05.png](../../../attachments/meme/2026-09-15/flow_v2-2/0705-TUDUM-%2B0.05.png) |
| 07:17:50 | RIZZ | `7LLE17W7XL…` | -0.7476 | time_stop | [0717-RIZZ--0.75.png](../../../attachments/meme/2026-09-15/flow_v2-2/0717-RIZZ--0.75.png) |
| 07:27:12 | ALON | `95xcQiPd8u…` | -0.4154 | creator_dump | [0727-ALON--0.42.png](../../../attachments/meme/2026-09-15/flow_v2-2/0727-ALON--0.42.png) |

## Dia 2026-09-16

30 aposta(s) fechada(s) — 30 medida(s), 0 indeterminada(s). Soma de R das medidas: **-1.2205**.

**Melhor** — LAUNCH · 00:18:37 BRT · +2.8961 R · saída por `target`.

![LAUNCH flow_v2/2 16/09 00:18](../../../attachments/meme/2026-09-16/flow_v2-2/0018-LAUNCH-%2B2.90.png)

**Pior** — ALICE · 02:27:34 BRT · -0.903 R · saída por `line_broken`.

![ALICE flow_v2/2 16/09 02:27](../../../attachments/meme/2026-09-16/flow_v2-2/0227-ALICE--0.90.png)

**Mais recente** — CASINU · 15:33:17 BRT · -0.4408 R · saída por `creator_dump`.

![CASINU flow_v2/2 16/09 15:33](../../../attachments/meme/2026-09-16/flow_v2-2/1533-CASINU--0.44.png)

| hora (BRT) | símbolo | mint | R | saída | gráfico |
|---|---|---|---|---|---|
| 00:16:31 | LAUNCH | `JBFeVRrjtu…` | -0.0769 | line_broken | [0016-LAUNCH--0.08.png](../../../attachments/meme/2026-09-16/flow_v2-2/0016-LAUNCH--0.08.png) |
| 00:18:37 | LAUNCH | `JBFeVRrjtu…` | +2.8961 | target | [0018-LAUNCH-+2.90.png](../../../attachments/meme/2026-09-16/flow_v2-2/0018-LAUNCH-%2B2.90.png) |
| 00:33:42 | STABILITY | `xgJXYDEWaM…` | +0.2296 | line_broken | [0033-STABILITY-+0.23.png](../../../attachments/meme/2026-09-16/flow_v2-2/0033-STABILITY-%2B0.23.png) |
| 01:58:46 | RETAR | `6tfXSECzrG…` | -0.0614 | creator_dump | [0158-RETAR--0.06.png](../../../attachments/meme/2026-09-16/flow_v2-2/0158-RETAR--0.06.png) |
| 02:27:34 | ALICE | `GHNuFBxVwH…` | -0.903 | line_broken | [0227-ALICE--0.90.png](../../../attachments/meme/2026-09-16/flow_v2-2/0227-ALICE--0.90.png) |
| 02:50:10 | KANYE | `34kSYEW5sn…` | -0.3483 | creator_dump | [0250-KANYE--0.35.png](../../../attachments/meme/2026-09-16/flow_v2-2/0250-KANYE--0.35.png) |
| 02:54:04 | INDIEREACH | `kDToGHjuti…` | +0.8917 | line_broken | [0254-INDIEREACH-+0.89.png](../../../attachments/meme/2026-09-16/flow_v2-2/0254-INDIEREACH-%2B0.89.png) |
| 02:56:10 | INDIEREACH | `kDToGHjuti…` | -0.8661 | max_loss | [0256-INDIEREACH--0.87.png](../../../attachments/meme/2026-09-16/flow_v2-2/0256-INDIEREACH--0.87.png) |
| 03:48:25 | NAMEROT | `3ySWBtEico…` | -0.2507 | line_broken | [0348-NAMEROT--0.25.png](../../../attachments/meme/2026-09-16/flow_v2-2/0348-NAMEROT--0.25.png) |
| 05:07:36 | KITE | `56KcQzfmDW…` | +0.3842 | line_broken | [0507-KITE-+0.38.png](../../../attachments/meme/2026-09-16/flow_v2-2/0507-KITE-%2B0.38.png) |
| 06:01:17 | JSC | `FS8Vrc5zyT…` | -0.2748 | max_loss | [0601-JSC--0.27.png](../../../attachments/meme/2026-09-16/flow_v2-2/0601-JSC--0.27.png) |
| 06:10:27 | ZKPASS | `FMh5opbs4e…` | -0.8109 | max_loss | [0610-ZKPASS--0.81.png](../../../attachments/meme/2026-09-16/flow_v2-2/0610-ZKPASS--0.81.png) |
| 06:19:06 | BITMAKER | `SogCcFn78Y…` | +0.0951 | line_broken | [0619-BITMAKER-+0.10.png](../../../attachments/meme/2026-09-16/flow_v2-2/0619-BITMAKER-%2B0.10.png) |
| 06:20:09 | BITMAKER | `SogCcFn78Y…` | +0.245 | line_broken | [0620-BITMAKER-+0.24.png](../../../attachments/meme/2026-09-16/flow_v2-2/0620-BITMAKER-%2B0.24.png) |
| 06:53:17 | TASKON | `j3YSKrAJrT…` | -0.7703 | max_loss | [0653-TASKON--0.77.png](../../../attachments/meme/2026-09-16/flow_v2-2/0653-TASKON--0.77.png) |
| 07:00:06 | POLKADOT | `Un18N8fpCb…` | -0.0416 | line_broken | [0700-POLKADOT--0.04.png](../../../attachments/meme/2026-09-16/flow_v2-2/0700-POLKADOT--0.04.png) |
| 07:42:54 | SWISSC | `XtSLPWvMt4…` | -0.1002 | line_broken | [0742-SWISSC--0.10.png](../../../attachments/meme/2026-09-16/flow_v2-2/0742-SWISSC--0.10.png) |
| 07:58:52 | KLING | `YNsgprpQRL…` | +0.6814 | line_broken | [0758-KLING-+0.68.png](../../../attachments/meme/2026-09-16/flow_v2-2/0758-KLING-%2B0.68.png) |
| 08:49:54 | KORI | `CGYSnnTTqF…` | -0.0687 | line_broken | [0849-KORI--0.07.png](../../../attachments/meme/2026-09-16/flow_v2-2/0849-KORI--0.07.png) |
| 10:07:48 | COINU | `EnPx4oBFL1…` | +0.1466 | line_broken | [1007-COINU-+0.15.png](../../../attachments/meme/2026-09-16/flow_v2-2/1007-COINU-%2B0.15.png) |
| 10:49:26 | CHILLIN | `6DUhuuQVaQ…` | -0.8818 | max_loss | [1049-CHILLIN--0.88.png](../../../attachments/meme/2026-09-16/flow_v2-2/1049-CHILLIN--0.88.png) |
| 11:46:40 | INCEPT | `FHcHh1ELbW…` | +0.2959 | line_broken | [1146-INCEPT-+0.30.png](../../../attachments/meme/2026-09-16/flow_v2-2/1146-INCEPT-%2B0.30.png) |
| 12:07:55 | CGRAM | `3tAFaZsjAv…` | -0.1441 | line_broken | [1207-CGRAM--0.14.png](../../../attachments/meme/2026-09-16/flow_v2-2/1207-CGRAM--0.14.png) |
| 12:52:49 | GREMLIN | `Gn9U13zkBd…` | +1.3044 | migrated | [1252-GREMLIN-+1.30.png](../../../attachments/meme/2026-09-16/flow_v2-2/1252-GREMLIN-%2B1.30.png) |
| 13:45:01 | GPT6SOL | `9NPxe7cB8B…` | -0.1426 | line_broken | [1345-GPT6SOL--0.14.png](../../../attachments/meme/2026-09-16/flow_v2-2/1345-GPT6SOL--0.14.png) |
| 14:04:54 | SORT | `7uwn4TV124…` | -0.698 | max_loss | [1404-SORT--0.70.png](../../../attachments/meme/2026-09-16/flow_v2-2/1404-SORT--0.70.png) |
| 14:08:24 | STEVE | `FLHSaTeXxo…` | +0.0885 | line_broken | [1408-STEVE-+0.09.png](../../../attachments/meme/2026-09-16/flow_v2-2/1408-STEVE-%2B0.09.png) |
| 14:13:48 | RIZZLERS | `3T4AueQkix…` | -0.8503 | line_broken | [1413-RIZZLERS--0.85.png](../../../attachments/meme/2026-09-16/flow_v2-2/1413-RIZZLERS--0.85.png) |
| 15:12:10 | LPAD | `D4fi1cAWTZ…` | -0.7484 | max_loss | [1512-LPAD--0.75.png](../../../attachments/meme/2026-09-16/flow_v2-2/1512-LPAD--0.75.png) |
| 15:33:17 | CASINU | `Cfsb4vMug1…` | -0.4408 | creator_dump | [1533-CASINU--0.44.png](../../../attachments/meme/2026-09-16/flow_v2-2/1533-CASINU--0.44.png) |
