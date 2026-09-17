---
tags: [operacoes, meme, pumpfun, graficos, m4]
status: em-andamento
owner: quant-engineer
updated: 2026-09-17
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

## Dia 2026-09-16

26 aposta(s) fechada(s) — 26 medida(s), 0 indeterminada(s). Soma de R das medidas: **-1.1583**.

**Melhor** — LAUNCH · 00:18:37 BRT · +2.8961 R · saída por `target`.

![LAUNCH flow_v2/3 16/09 00:18](../../../attachments/meme/2026-09-16/flow_v2-3/0018-LAUNCH-%2B2.90.png)

**Pior** — CHILLIN · 10:49:26 BRT · -0.8818 R · saída por `max_loss`.

![CHILLIN flow_v2/3 16/09 10:49](../../../attachments/meme/2026-09-16/flow_v2-3/1049-CHILLIN--0.88.png)

**Mais recente** — ERMDOG · 22:54:33 BRT · -0.3012 R · saída por `line_broken`.

![ERMDOG flow_v2/3 16/09 22:54](../../../attachments/meme/2026-09-16/flow_v2-3/2254-ERMDOG--0.30.png)

| hora (BRT) | símbolo | mint | R | saída | gráfico |
|---|---|---|---|---|---|
| 00:16:31 | LAUNCH | `JBFeVRrjtu…` | -0.0769 | line_broken | [0016-LAUNCH--0.08.png](../../../attachments/meme/2026-09-16/flow_v2-3/0016-LAUNCH--0.08.png) |
| 00:18:37 | LAUNCH | `JBFeVRrjtu…` | +2.8961 | target | [0018-LAUNCH-+2.90.png](../../../attachments/meme/2026-09-16/flow_v2-3/0018-LAUNCH-%2B2.90.png) |
| 02:54:04 | INDIEREACH | `kDToGHjuti…` | +0.8917 | line_broken | [0254-INDIEREACH-+0.89.png](../../../attachments/meme/2026-09-16/flow_v2-3/0254-INDIEREACH-%2B0.89.png) |
| 02:56:10 | INDIEREACH | `kDToGHjuti…` | -0.8661 | max_loss | [0256-INDIEREACH--0.87.png](../../../attachments/meme/2026-09-16/flow_v2-3/0256-INDIEREACH--0.87.png) |
| 03:48:25 | NAMEROT | `3ySWBtEico…` | -0.2507 | line_broken | [0348-NAMEROT--0.25.png](../../../attachments/meme/2026-09-16/flow_v2-3/0348-NAMEROT--0.25.png) |
| 06:01:17 | JSC | `FS8Vrc5zyT…` | -0.2748 | max_loss | [0601-JSC--0.27.png](../../../attachments/meme/2026-09-16/flow_v2-3/0601-JSC--0.27.png) |
| 06:10:27 | ZKPASS | `FMh5opbs4e…` | -0.8109 | max_loss | [0610-ZKPASS--0.81.png](../../../attachments/meme/2026-09-16/flow_v2-3/0610-ZKPASS--0.81.png) |
| 06:19:06 | BITMAKER | `SogCcFn78Y…` | +0.0951 | line_broken | [0619-BITMAKER-+0.10.png](../../../attachments/meme/2026-09-16/flow_v2-3/0619-BITMAKER-%2B0.10.png) |
| 06:20:09 | BITMAKER | `SogCcFn78Y…` | +0.245 | line_broken | [0620-BITMAKER-+0.24.png](../../../attachments/meme/2026-09-16/flow_v2-3/0620-BITMAKER-%2B0.24.png) |
| 06:53:17 | TASKON | `j3YSKrAJrT…` | -0.7703 | max_loss | [0653-TASKON--0.77.png](../../../attachments/meme/2026-09-16/flow_v2-3/0653-TASKON--0.77.png) |
| 08:49:54 | KORI | `CGYSnnTTqF…` | -0.0687 | line_broken | [0849-KORI--0.07.png](../../../attachments/meme/2026-09-16/flow_v2-3/0849-KORI--0.07.png) |
| 10:07:48 | COINU | `EnPx4oBFL1…` | +0.1466 | line_broken | [1007-COINU-+0.15.png](../../../attachments/meme/2026-09-16/flow_v2-3/1007-COINU-%2B0.15.png) |
| 10:49:26 | CHILLIN | `6DUhuuQVaQ…` | -0.8818 | max_loss | [1049-CHILLIN--0.88.png](../../../attachments/meme/2026-09-16/flow_v2-3/1049-CHILLIN--0.88.png) |
| 12:07:55 | CGRAM | `3tAFaZsjAv…` | -0.1441 | line_broken | [1207-CGRAM--0.14.png](../../../attachments/meme/2026-09-16/flow_v2-3/1207-CGRAM--0.14.png) |
| 13:45:01 | GPT6SOL | `9NPxe7cB8B…` | -0.1426 | line_broken | [1345-GPT6SOL--0.14.png](../../../attachments/meme/2026-09-16/flow_v2-3/1345-GPT6SOL--0.14.png) |
| 14:08:24 | STEVE | `FLHSaTeXxo…` | +0.0885 | line_broken | [1408-STEVE-+0.09.png](../../../attachments/meme/2026-09-16/flow_v2-3/1408-STEVE-%2B0.09.png) |
| 14:13:48 | RIZZLERS | `3T4AueQkix…` | -0.8503 | line_broken | [1413-RIZZLERS--0.85.png](../../../attachments/meme/2026-09-16/flow_v2-3/1413-RIZZLERS--0.85.png) |
| 16:08:33 | MOONEY | `E2y5iF7aKn…` | -0.1489 | line_broken | [1608-MOONEY--0.15.png](../../../attachments/meme/2026-09-16/flow_v2-3/1608-MOONEY--0.15.png) |
| 17:00:32 | MAXBIDDING | `6qHrLunMNU…` | -0.0451 | line_broken | [1700-MAXBIDDING--0.05.png](../../../attachments/meme/2026-09-16/flow_v2-3/1700-MAXBIDDING--0.05.png) |
| 18:19:34 | FLYDRONES | `41tvJNWrNm…` | -0.3857 | line_broken | [1819-FLYDRONES--0.39.png](../../../attachments/meme/2026-09-16/flow_v2-3/1819-FLYDRONES--0.39.png) |
| 19:19:07 | AAS | `DvKH9THR4R…` | -0.1031 | line_broken | [1919-AAS--0.10.png](../../../attachments/meme/2026-09-16/flow_v2-3/1919-AAS--0.10.png) |
| 19:27:17 | LIQUI | `5gg7L1ifsj…` | -0.1543 | creator_dump | [1927-LIQUI--0.15.png](../../../attachments/meme/2026-09-16/flow_v2-3/1927-LIQUI--0.15.png) |
| 20:22:54 | BPAD | `2M49EhYQeR…` | +0.2814 | trailing | [2022-BPAD-+0.28.png](../../../attachments/meme/2026-09-16/flow_v2-3/2022-BPAD-%2B0.28.png) |
| 20:56:05 | SUPERCHIP | `kxLJv99HeP…` | +0.5316 | line_broken | [2056-SUPERCHIP-+0.53.png](../../../attachments/meme/2026-09-16/flow_v2-3/2056-SUPERCHIP-%2B0.53.png) |
| 22:52:55 | ERMDOG | `6DuyEnK3wf…` | -0.0588 | line_broken | [2252-ERMDOG--0.06.png](../../../attachments/meme/2026-09-16/flow_v2-3/2252-ERMDOG--0.06.png) |
| 22:54:33 | ERMDOG | `6DuyEnK3wf…` | -0.3012 | line_broken | [2254-ERMDOG--0.30.png](../../../attachments/meme/2026-09-16/flow_v2-3/2254-ERMDOG--0.30.png) |

## Dia 2026-09-17

34 aposta(s) fechada(s) — 34 medida(s), 0 indeterminada(s). Soma de R das medidas: **+0.5826**.

**Melhor** — FLOCK · 03:28:28 BRT · +1.3343 R · saída por `line_broken`.

![FLOCK flow_v2/3 17/09 03:28](../../../attachments/meme/2026-09-17/flow_v2-3/0328-FLOCK-%2B1.33.png)

**Pior** — AIZEMPIG · 03:20:54 BRT · -0.6755 R · saída por `max_loss`.

![AIZEMPIG flow_v2/3 17/09 03:20](../../../attachments/meme/2026-09-17/flow_v2-3/0320-AIZEMPIG--0.68.png)

**Mais recente** — CUMMIES · 09:17:47 BRT · -0.2917 R · saída por `creator_dump`.

![CUMMIES flow_v2/3 17/09 09:17](../../../attachments/meme/2026-09-17/flow_v2-3/0917-CUMMIES--0.29.png)

| hora (BRT) | símbolo | mint | R | saída | gráfico |
|---|---|---|---|---|---|
| 01:07:01 | WISH | `4qpraJNwVi…` | -0.2723 | creator_dump | [0107-WISH--0.27.png](../../../attachments/meme/2026-09-17/flow_v2-3/0107-WISH--0.27.png) |
| 01:41:11 | JACOB | `2aSiTzA3tS…` | -0.3498 | line_broken | [0141-JACOB--0.35.png](../../../attachments/meme/2026-09-17/flow_v2-3/0141-JACOB--0.35.png) |
| 01:48:43 | MO | `GLZ4KoE61G…` | -0.4008 | line_broken | [0148-MO--0.40.png](../../../attachments/meme/2026-09-17/flow_v2-3/0148-MO--0.40.png) |
| 01:56:05 | PETA | `3RMktUeuUM…` | -0.0982 | line_broken | [0156-PETA--0.10.png](../../../attachments/meme/2026-09-17/flow_v2-3/0156-PETA--0.10.png) |
| 02:21:25 | STACK | `FX4W3xMLi4…` | +0.5964 | creator_dump | [0221-STACK-+0.60.png](../../../attachments/meme/2026-09-17/flow_v2-3/0221-STACK-%2B0.60.png) |
| 02:36:17 | UNRWA | `45agCDaFCn…` | -0.103 | line_broken | [0236-UNRWA--0.10.png](../../../attachments/meme/2026-09-17/flow_v2-3/0236-UNRWA--0.10.png) |
| 02:41:37 | STAND | `4azaSvHaCy…` | +0.0189 | line_broken | [0241-STAND-+0.02.png](../../../attachments/meme/2026-09-17/flow_v2-3/0241-STAND-%2B0.02.png) |
| 02:43:29 | STAND | `4azaSvHaCy…` | -0.0374 | line_broken | [0243-STAND--0.04.png](../../../attachments/meme/2026-09-17/flow_v2-3/0243-STAND--0.04.png) |
| 03:11:22 | BOB | `3jjcJMbwM6…` | +0.0456 | line_broken | [0311-BOB-+0.05.png](../../../attachments/meme/2026-09-17/flow_v2-3/0311-BOB-%2B0.05.png) |
| 03:16:40 | GAMBLER | `C3bsd1nZXx…` | +0.1406 | line_broken | [0316-GAMBLER-+0.14.png](../../../attachments/meme/2026-09-17/flow_v2-3/0316-GAMBLER-%2B0.14.png) |
| 03:20:54 | AIZEMPIG | `Ebzu4xwziA…` | -0.6755 | max_loss | [0320-AIZEMPIG--0.68.png](../../../attachments/meme/2026-09-17/flow_v2-3/0320-AIZEMPIG--0.68.png) |
| 03:24:51 | ARCANE | `9pkehwnktJ…` | +0.024 | line_broken | [0324-ARCANE-+0.02.png](../../../attachments/meme/2026-09-17/flow_v2-3/0324-ARCANE-%2B0.02.png) |
| 03:28:28 | FLOCK | `EuS3oJQ9xx…` | +1.3343 | line_broken | [0328-FLOCK-+1.33.png](../../../attachments/meme/2026-09-17/flow_v2-3/0328-FLOCK-%2B1.33.png) |
| 04:35:12 | CORTANA | `HUbapm9ZHN…` | +0.0028 | line_broken | [0435-CORTANA-+0.00.png](../../../attachments/meme/2026-09-17/flow_v2-3/0435-CORTANA-%2B0.00.png) |
| 04:37:17 | CORTANA | `HUbapm9ZHN…` | +0.659 | creator_dump | [0437-CORTANA-+0.66.png](../../../attachments/meme/2026-09-17/flow_v2-3/0437-CORTANA-%2B0.66.png) |
| 04:44:21 | ALTLAYER | `6rziNWMPP8…` | -0.0378 | line_broken | [0444-ALTLAYER--0.04.png](../../../attachments/meme/2026-09-17/flow_v2-3/0444-ALTLAYER--0.04.png) |
| 04:45:39 | ALTLAYER | `6rziNWMPP8…` | +0.1358 | line_broken | [0445-ALTLAYER-+0.14.png](../../../attachments/meme/2026-09-17/flow_v2-3/0445-ALTLAYER-%2B0.14.png) |
| 04:57:18 | 401K | `kjcARRbT5r…` | +0.6341 | line_broken | [0457-401K-+0.63.png](../../../attachments/meme/2026-09-17/flow_v2-3/0457-401K-%2B0.63.png) |
| 04:58:23 | ASPCAT | `86ViwEDh38…` | +0.6027 | creator_dump | [0458-ASPCAT-+0.60.png](../../../attachments/meme/2026-09-17/flow_v2-3/0458-ASPCAT-%2B0.60.png) |
| 05:05:17 | INOSHISHI | `6thWBKZ9Ka…` | -0.6415 | max_loss | [0505-INOSHISHI--0.64.png](../../../attachments/meme/2026-09-17/flow_v2-3/0505-INOSHISHI--0.64.png) |
| 05:38:37 | SPIKE | `Adhkq34cPu…` | -0.0348 | creator_dump | [0538-SPIKE--0.03.png](../../../attachments/meme/2026-09-17/flow_v2-3/0538-SPIKE--0.03.png) |
| 05:45:29 | MERTCASH | `2apUMi97QM…` | -0.5945 | creator_dump | [0545-MERTCASH--0.59.png](../../../attachments/meme/2026-09-17/flow_v2-3/0545-MERTCASH--0.59.png) |
| 05:49:40 | ELONMUSEK | `6c3aYhoNf4…` | -0.2305 | line_broken | [0549-ELONMUSEK--0.23.png](../../../attachments/meme/2026-09-17/flow_v2-3/0549-ELONMUSEK--0.23.png) |
| 06:13:33 | BYZ | `8Rjh5N6fPo…` | -0.189 | line_broken | [0613-BYZ--0.19.png](../../../attachments/meme/2026-09-17/flow_v2-3/0613-BYZ--0.19.png) |
| 06:19:40 | FRANK01 | `2TCHAJbLjx…` | -0.0367 | creator_dump | [0619-FRANK01--0.04.png](../../../attachments/meme/2026-09-17/flow_v2-3/0619-FRANK01--0.04.png) |
| 06:28:41 | GIREUMEE | `mJkh4h759E…` | +0.1603 | line_broken | [0628-GIREUMEE-+0.16.png](../../../attachments/meme/2026-09-17/flow_v2-3/0628-GIREUMEE-%2B0.16.png) |
| 07:08:33 | TESTES | `6YsoQWiqmK…` | -0.211 | line_broken | [0708-TESTES--0.21.png](../../../attachments/meme/2026-09-17/flow_v2-3/0708-TESTES--0.21.png) |
| 07:20:19 | MELO | `EjamsQo99B…` | -0.0375 | creator_dump | [0720-MELO--0.04.png](../../../attachments/meme/2026-09-17/flow_v2-3/0720-MELO--0.04.png) |
| 07:55:13 | FREEBOTS | `BWAGS7sWBC…` | -0.1156 | creator_dump | [0755-FREEBOTS--0.12.png](../../../attachments/meme/2026-09-17/flow_v2-3/0755-FREEBOTS--0.12.png) |
| 08:35:17 | RINA | `CTCpMwvtFq…` | +0.0333 | creator_dump | [0835-RINA-+0.03.png](../../../attachments/meme/2026-09-17/flow_v2-3/0835-RINA-%2B0.03.png) |
| 08:50:55 | MONKES | `DM82WtB7zT…` | +0.2394 | line_broken | [0850-MONKES-+0.24.png](../../../attachments/meme/2026-09-17/flow_v2-3/0850-MONKES-%2B0.24.png) |
| 08:53:35 | 4CHAN | `27oqvy8Vmu…` | -0.0736 | line_broken | [0853-4CHAN--0.07.png](../../../attachments/meme/2026-09-17/flow_v2-3/0853-4CHAN--0.07.png) |
| 09:01:18 | PAIDSEM | `EB2f6dyTDM…` | +0.3865 | line_broken | [0901-PAIDSEM-+0.39.png](../../../attachments/meme/2026-09-17/flow_v2-3/0901-PAIDSEM-%2B0.39.png) |
| 09:17:47 | CUMMIES | `3NxcqafYo8…` | -0.2917 | creator_dump | [0917-CUMMIES--0.29.png](../../../attachments/meme/2026-09-17/flow_v2-3/0917-CUMMIES--0.29.png) |
