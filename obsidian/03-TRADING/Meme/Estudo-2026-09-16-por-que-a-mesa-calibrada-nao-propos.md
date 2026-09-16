---
tags: [estudo, meme, pumpfun, porta, operator, snipers, funil, r21]
tema: por que a mesa calibrada (operator v5) "não propôs" depois de 16:17 BRT — funil critério a critério
fonte: banco da VPS (meme_features_15s, meme_tokens, meme_proposals, meme_rule_sets) e heartbeat hb:meme:radar
lido_em: 2026-09-16
evidencia: medição própria (SQL em infra/scripts/sql/research/2026-09-16-r21-q0{1,2,3}-*.sql)
hipotese_testavel: sim
astra: não consultada nesta nota (medição quant, 16/09 17:0x BRT)
confianca: medição direta, janela curta (28 min para o funil; 3,8 h para o contrafactual)
owner: astra
updated: 2026-09-16
status: vivo
---

# Estudo 16/09 — por que a mesa calibrada não propôs desde 16:17 BRT

**Resposta curta: ela propôs.** Entre 16:36:24 e 16:50:26 BRT o `operator` gerou **7 propostas sobre 4 moedas**
(`BVf9r1…pump` ×4, `4Yz9VQ…pump`, `Cdgczy…pump`, `66LUgD…pump`). Todas morreram **depois** da porta, no
`executor:auto_stage1`: 4 × `creator_flow_unknown`, 2 × `progress_above_window`, 1 × `progress_below_window`.
O único intervalo em que a **porta** realmente zerou foi **16:17–16:28**, com o teto `max_snipers = 25` ainda em pé.

Parâmetros lidos de `meme_rule_sets` (kind `operator`, status `active`, v5, clock `15s`): `min_age_s 30`,
`max_age_s 300`, progresso 5–50 % (a coluna `curve_progress_pct` é **fração** 0–1), `max_participation_pct 1`
com `size_sol 0,05` (⇒ `curve_volume_60s_sol ≥ 5`), `max_dev_share 0,10` com `dev_share_unknown_allowed false`,
**`min_snipers 21` / `max_snipers 1000`**, `require_positive_flow true`, `min_unique_buyers 10`,
`max_sells_to_buys 0,6`, `min_holders 20`, `exclude_mayhem` (default `true`), `pedigree_exclusions` e
`pedigree_repeat_dumper` ligados. A ordem replicada é a de `hunter_indicators.meme.rules:evaluate_entry`
(pedigree aplicado antes, em `proposals.evaluate_gate`).

## 1. Funil desde 16:17 BRT (até 16:47, 28 min) — `meme_features_15s`, série da via rápida

Cumulativo (cada passo é o AND de todos os anteriores). SQL: `…-r21-q01-funil-por-criterio.sql`.

| # | critério (na ordem da porta) | linhas 15 s | moedas |
|---|---|---|---|
| 00 | janela | 14 468 | 991 |
| 01 | viva (não completa/migrada) | 14 298 | 977 |
| 02 | pedigree (serial 1 h / clone 24 h / repeat dumper 7 d) | 3 548 | **263** |
| 03 | não-Mayhem (`mayhem_enabled = false`) | 3 254 | 244 |
| 04 | idade 30–300 s | 2 876 | 222 |
| 05 | progresso 5–50 % | 547 | **71** |
| 06 | criador não vendedor (ou desconhecido com `dev_share ≤ 0,10`) | 528 | 71 |
| 07 | participação ≤ 1 % (`vol60s ≥ 5 SOL`) | 82 | **25** |
| 08 | `dev_share ≤ 0,10` (desconhecido recusa) | 82 | 25 |
| 09 | snipers 21–1000 | 32 | **10** |
| 10 | fluxo positivo | 20 | 8 |
| 11 | compradores únicos ≥ 10 | 20 | 8 |
| 12 | `sells/buys ≤ 0,6` | 11 | 5 |
| 13 | holders ≥ 20 — **sobreviventes** | **10** | **4** |

**Nenhum critério zera.** Os três cortes grandes são pedigree (977 → 263 moedas), progresso (222 → 71) e
participação/liquidez (71 → 25). O piso de snipers custa 25 → 10 moedas; o resto da porta leva a 4.

Minuto a minuto (`…-r21-q03-*.sql`), as linhas aprovadas foram: **16:20:00/16/33/49** (`BiCp7N…`, snipers 64),
**16:36:06** (`4Yz9VQ…` e `BVf9r1…`), 16:36:22/39/55 (`BVf9r1…`), **16:41:02** (`Cdgczy…`), **16:50:05** (`66LUgD…`).
O bloco das 16:20 **não** virou proposta porque naquele momento o teto ainda era `max_snipers 25` e a moeda tinha 64
(`snipers_above_max`); a partir do piso de 16:28 todo sobrevivente virou proposta em ≤ 20 s.

## 2. Histograma `lab_gate_refusals` (heartbeat, conjunto `operator`)

Acumulado desde o reload da porta; `snipers_above_max` não aparece, o que confirma que o contador corresponde à
era **pós-16:28** (piso 21 / teto 1000).

`holders_below_min 238` · **`snipers_below_min 215`** · `buyers_below_min 189` · `progress_below_min 174` ·
`flow_not_positive 158` · `symbol_clone 137` · `no_buys 136` · `curve_volume_1m_zero 115` · `creator_serial 112` ·
`participation_above_cap 64` · `creator_repeat_dumper 63` · `mayhem_curve 51` · `sells_ratio_above_max 49` ·
`age_below_min 43` · `buyers_unknown 43` · `curve_volume_1m_unknown 43` · `sells_ratio_unknown 43` ·
`flow_not_polled 39` · `progress_unknown 28` · `creator_net_seller_unknown 12` · `dev_share_unknown 8` ·
`snipers_unknown 8` · `holders_no_holders_reader 8` · `progress_above_max 6` · `creator_is_net_seller 4` ·
`dev_share_above_max 4` · `flow_no_trade_feed 4`.

Cegueira é minoria: `creator_unknown`/`symbol_unknown` nem aparecem, `snipers_unknown` são 8 contra 215
`snipers_below_min`. O que recusa é o mercado, não a falta de leitura.

## 3. O piso `min_snipers ≥ 21` — 13:00–16:47 BRT de hoje (3,83 h)

Sobreviventes de **toda** a porta menos o critério de snipers (`…-r21-q02-piso-de-snipers.sql`):

| faixa de snipers | linhas | moedas | moedas/h |
|---|---|---|---|
| desconhecido | 0 | 0 | 0,00 |
| 0–10 | 4 | 4 | 1,04 |
| 11–20 | 6 | 3 | 0,78 |
| 21–30 | 0 | 0 | 0,00 |
| 31–60 | 12 | 6 | 1,57 |
| > 60 | 8 | 4 | 1,04 |
| **piso 21 (atual)** | 20 | **10** | **2,61** |
| piso 11 ou 16 | 26 | 13 | 3,39 |
| sem piso | 30 | 17 | 4,44 |

**O piso não zera a mesa**: ele custa 7 moedas em 3,8 h (17 → 10), ou −41 % de candidatas, e ainda deixa
**2,6 moedas/h** — que hoje viraram 7 propostas em 22 min. Baixar para 11 compraria **+0,78 moeda/h** exatamente
na faixa que o [[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]] mede como ruído
(11–20: R médio +0,037, IC [−0,24; +0,22]) contra 21–30 (+0,116) e 31–60 (+0,522). **Não vale**: diluiria o R
para ganhar menos de uma moeda por hora. Se faltar volume de propostas, o lugar barato é o corte de
**participação** (25 → 10 moedas no funil de hoje já com snipers; `max_participation_pct` 1 % com 0,05 SOL exige
5 SOL de volume por minuto), não o piso de snipers.

## 4. Conclusão (4 linhas)

1. A porta calibrada **funcionou**: 4 moedas sobreviveram em 28 min e geraram 7 propostas entre 16:36 e 16:50 BRT.
2. O silêncio real foi de **16:17 a 16:28**, causado pelo teto `max_snipers 25` (o sobrevivente das 16:20 tinha 64).
3. O que mata hoje é **depois** da porta: `auto_stage1` recusou 4/7 por `creator_flow_unknown` e 3/7 por
   janela de progresso (o risco recalcula o progresso pelas reservas ao vivo, com limites 0,02–0,50 — divergente
   da foto de 15 s que aprovou: `Cdgczy…` passou com 35,2 % e foi recusada como `progress_below_window`).
4. **Ação: nenhum `--set-param` na porta.** Não rode `meme_rule_set.py --set-param … min_snipers=11`: compra
   +0,78 moeda/h na faixa de R nulo do KB-0102. A ação é no estágio 1 do executor (medir o fluxo do criador e
   alinhar o denominador de progresso com `meme_features_15s`), a ser aberta como tarefa própria.
