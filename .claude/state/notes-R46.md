# R46 — leitura da noite (22h30 BRT, 16/09/2026): top 10 do radar, mesa, T4.45, graduações

Medido em **22:21–22:31 BRT** (`date -u` = 01:21–01:31 UTC de 17/09). Janela **congelada em
[19:25, 22:25) BRT**. Só `SELECT` na VPS (`hunter-postgres-1`, `psql -U hunter -d hunter`) + `HGETALL`
em `hb:meme:radar` / `hb:meme:executor`. Nada escrito na VPS. Nota Obsidian:
`obsidian/03-TRADING/Meme/Candidatas/2026-09-16-22h30-brt.md`. SQL:
`infra/scripts/sql/research/2026-09-16-r46-q0{1,2,4,5,6,7}-*.sql` (cópia integral no fim deste arquivo).

Unidades: `meme_features_15s/1m.curve_progress_pct` é fração 0–1 (aqui em %); `meme_proposals.quote`
e `meme_rule_sets.params` já em %. Desfecho pela cadeia (`real_sol_reserves`; invariante
`virtual − real = 30,000` em todas as linhas lidas). Porta replicada = `operator/5`
(`01994d00-…-0011`): idade 30–300 s, prog 5–50 %, fita presente e fluxo > 0, holders ≥ 20,
compradores ≥ 10, vendas/compras ≤ 0,6, snipers 21–1000, dev ≤ 10 %, `max_hold_s` 1800.

## 1. Top 10 (q01)

Funil de moedas distintas: idade 2 874 → prog 5–50 % 885 → fita+fluxo 368 → holders ≥ 20 81 →
compradores ≥ 10 66 → razão ≤ 0,6 44 → snipers 21–1000 **29** → dev ≤ 10 % 29. 29 moedas / 57 leituras
passam; **10 com proposta**. Ordem: máx. compradores únicos numa leitura que passou.

| # | símbolo | mint | criada | melhor (idade) | prog | hold | compr | c×v | snip | fluxo | última 15 s (idade): prog/hold/compr | rsol pico → última | Δ | cr 7 d | propostas → ordens |
|---|---|---|---|---|---:|---:|---:|---|---:|---:|---|---|---:|---:|---|
| 1 | Lilly | `3tmKhPmo9NixC8nNZYztNR41GsyxzLifRUzUdeubpump` | 19:26:46 | 19:28:18 (91) | 47,5 | 160 | 142 | 151×59 | 86 | 3,84 | 19:31:02 (255): 0,2/160/0 | 20,32 → 0,034 | −99,8 % | 0 | 0 (12 clones) |
| 2 | ARCH | `ChgZ7GkiYkyyfp1qBuNu2qgprPYC17DnvUqbyVrQpump` | 19:25:28 | 19:26:07 (38) | 32,4 | 104 | 141 | 142×46 | 58 | 9,33 | 19:29:56 (267): 0,0/104/0 | 10,98 → 0,000 | −100 % | 0 | 0 (16 clones) |
| 3 | CELINE | `7fWspNngkwZ4rN2XSJpvsXE14RRjcrRV6DKqaN4ppump` | 19:47:52 | 19:49:16 (84) | 48,9 | 163 | 128 | 131×50 | 34 | 3,00 | 19:52:48 (295): 0,6/19/0 | 27,99 → 0,085 | −99,7 % | 0 | 4 → cfu ×2, progress_above_window |
| 4 | QAUNTITY | `GFakEBdgdKDJhsCKauSkKVjHYPqHDBEY7SgJZEJDpump` | 21:19:59 | 21:21:17 (77) | 34,0 | 55 | 115 | 150×90 | 49 | 9,84 | 21:24:48 (289): 31,6/43/0 · 1 m 21:25: 41 h, top10 20,9 | 19,36 → 9,148 (21:24:36) | −52,7 % | 31 | 6 → cfu ×6 |
| 5 | INTRA | `9PyqygumGwmbaJn7sVZVyUzHzBH4ZMj5R5eNDceupump` | 19:26:39 | 19:27:28 (49) | 45,8 | 131 | 98 | 98×23 | 62 | 10,65 | 19:31:02 (262): 2,5/131/0 | 15,34 → 0,566 | −96,3 % | 0 | 2 → cfu ×2 |
| 6 | bill | `6XcZ6ds95n9XnHvfbCqDmvowcQtLNNofnYyjMjkAjse9` | 19:43:13 | 19:44:06 (53) | 42,7 | 69 | 60 | 64×34 | 85 | 7,67 | 19:48:11 (298): 58,6/87/39 · 1 m 19:49: 51 h, creator_sold t | 39,78 → 3,83 | −90,4 % | 40 | 0 (creator_net_seller = true) |
| 7 | PUMPBALL | `97CXCc6bg7rcWo14L2UktwyxEpBRPUJ9eeeDw1ERpump` | 19:30:35 | 19:31:18 (43) | 34,2 | 87 | 58 | 62×14 | 41 | 12,34 | 19:34:18 (222): 1,2/8/– | 11,54 → 0,261 | −97,7 % | 0 | 0 (11 clones) |
| 8 | RETARDINU | `7x8cE5AoELM3gnFDq8KL7qxArp5cmi4nCZeqB2DWpump` | 20:28:26 | 20:29:23 (57) | 14,9 | 24 | 58 | 68×32 | 41 | 17,39 | 20:33:12 (286): 0,2/10/0 | 59,89 → 0,045 | −99,9 % | 4 (4 em 1 h) | 0 |
| 9 | LINK | `4TcftzQvXTwSEfsuWL75LLNQvdennvRsjmCh3VS5pump` | 21:44:54 | 21:48:40 (226) | 48,7 | 84 | 57 | 69×29 | 39 | 11,95 | 21:49:45 (290): 56,0/85/25 · 1 m 21:59 (12 min): 167 h, top10 22,3, creator_sold f | 45,25 → 33,44 (21:58:59) | −26,1 % | 0 | 0 (4 clones "LINK" 24 h) |
| 10 | Molly | `4hFxr7x8ive2NiYvrNoBiKrrimVgVP9KV4YgTEHApump` | 21:34:39 | 21:35:17 (37) | 45,2 | 20 | 53 | 60×23 | 35 | 13,29 | 21:39:31 (291): 0,7/13/0 | 15,05 → 0,157 | −99,0 % | 2 (2 em 1 h) | 0 |

`cfu` = `creator_flow_unknown`. Trajetória de 10 min só existe para LINK (1 m 21:49 → 21:59: prog
59,7 % → sem denominador; holders 80 → 167; compradores 41 → 0; cadeia 21:52–21:59 entre 27,3 e
38,6 SOL). Série da LINK parou às 21:59 (fora do top-K). **Placar: 8 abaixo de −90 %, QAUNTITY −53 %,
LINK −26 %; zero graduou.** Pedigree (q07): Lilly 12, ARCH 16, PUMPBALL 11, LINK 4 clones de símbolo em
24 h; RETARDINU 4 e Molly 2 moedas do criador em 1 h; bill `creator_net_seller = true` (2 vendas na fita).

## 2. Propostas e ordens (q02)

| rule set | modo | status | n | moedas |
|---|---|---|---:|---:|
| operator/5 | live | rejected | 25 | 9 |
| operator/5 | live | filled | 1 | 1 (TAXCOIN) |
| operator/5 | paper | expired | 1 | 1 |
| flow_v2/2, /3, /5 | paper | filled | 3 + 3 + 2 | 8 (sem ordem) |

Ordens reais: **27** — `refused: creator_flow_unknown` 23 (9 moedas) · `refused:
progress_above_window` 2 (CELINE, DOWNIE) · `confirmed: trade_event` 2 (TAXCOIN buy `SwjKQmyw…` e
sell `k6nBHehm…`). Heartbeat executor 22:30: `orders_by_state {confirmed: 2, refused: 80}`,
`positions_open 0`, `kill_switch_latched false`, `auto_refused_1h {creator_flow_unknown: 5,
progress_above_window: 1}`, `auto_skipped {too_old: 235, recently_refused: 110, tick_cap: 13}`.

| 1ª ordem | símbolo | mint8 | ordens | motivo | prog quote | hold/compr/snip (15 s ≤ ordem) | cns na ordem → depois (Δ s) | bundle antes / depois (Δ s) | rsol0 → máx/mín 30 min | desfecho |
|---|---|---|---:|---|---:|---|---|---|---|---|
| 19:27:26 | INTRA | 9Pyqygum | 2 | cfu | 39,1 | 123/98/62 | no_trade_feed → nunca | – / – | 15,34 → 0,57/0,57 | boa |
| 19:28:44 | INUFLATION | 2DTthPWW | 1 | cfu | 28,3 | 3/39/48 | no_trade_feed → nunca | – / – | 0,43 → 0,47/0,001 | boa (vazia) |
| 19:48:43 | CELINE | 7fWspNng | 3 | cfu ×2, progress_above_window | 42,0 | 85/19/34 | → false (+114) | – / 12,3 (+63) | 14,00 → 27,99/0,085 | ruim |
| 20:45:48 | funemployed | H91rJ7Dc | 2 | cfu | 39,5 | 53/19/97 | → false (+109) | – / – (retrato +56 s sem bundle) | 14,28 → 26,43/5,59 | ruim |
| 21:14:13 | PPC | Fyko94e1 | 4 | cfu | 21,4 | 29/17/44 | → nunca | – / – | 5,65 → 10,08/6,32 | ruim |
| 21:21:26 | QAUNTITY | GFakEBdg | 6 | cfu | 34,0 | 55/115/49 | → nunca | – / – | 10,86 → 15,84/7,65 | neutra |
| 21:29:49 | SPLITPAD | FMMCvUEN | 1 | cfu | 30,3 | 20/43/68 | false → false (+8) | 38,5 (−30) / – | 3,44 → 0,74/0,024 | boa |
| 21:31:28 | TAXCOIN | 7s4dKmpv | 1+1 | trade_event | 23,2 | 19/3/37 | false → false | 15,0 (−67) / – | 5,25 → 23,14/1,26 | −0,009764 SOL |
| 21:42:47 | BUFFETT | C8ykWko6 | 4 | cfu | 20,8 | 26/22/23 | → nunca | – / 0,0 (+42) | 13,22 → 14,27/0,127 | boa |
| 22:08:14 | DOWNIE | ENBTWXHt | 2 | cfu, progress_above_window | 38,8 | 28/40/24 | → false (+82) | – / 33,2 (+89) | 16,57 → 35,94/0,119 | boa |

Placar: 6 boas, 3 ruins (CELINE, funemployed, PPC — as da R41), 1 neutra, 1 compra perdedora.
DOWNIE (q05 traj): 22:08 15–22 SOL → 22:09 24,6–35,9 → 22:10 0,19 → 22:11 0,12; criador vendeu 22:10:21.

## 3. Contrafactual T4.45 (q06) — commit `7d3a96b3`, não implantado, não retroativo

Parte B aproximada pela fita (`meme_trades.trader = meme_tokens.creator`, vendas antes da 1ª ordem);
Parte A pelo retrato mais próximo em ±600 s. Tetos em vigor: bundle ≤ 20 %, top-10 ≤ 25 %, prog ≤ 50 %.

| símbolo | vendas do criador antes | retrato Δ | bundle / top10 | veredito T4.45 | desfecho |
|---|---|---|---|---|---|
| INTRA | 0 | nenhum | – | lê sob demanda (?) | −96 % |
| INUFLATION | 0 | nenhum | – | lê sob demanda (?) | vazia |
| CELINE | 0 | +63 s | 12,3 / 18,1 | **ADMITIRIA** | +100 % em 70 s, −50 % aos 3:20 |
| funemployed | 0 (1 compra 0,099) | +56 s sem bundle | – | lê sob demanda (?) | +85 % → −61 % |
| PPC | 0 | nenhum | – | lê sob demanda (?) | +78 % |
| QAUNTITY | 0 | nenhum | – | lê sob demanda (?) | −53 % |
| SPLITPAD | 0 (1 compra 0,988) | −30 s | 38,5 / 24,9 | recusa: bundle | −99 % |
| **TAXCOIN** | **6 vendas, 10,624 SOL, 1ª às 21:30:35 (53 s antes da compra)** | −67 s | 15,0 / 19,7 | **recusa: creator_net_seller** | única compra, −0,0098 SOL |
| BUFFETT | 0 | +42 s | 0,0 / 4,5 | **ADMITIRIA** | −99 % (max_loss 50 %) |
| DOWNIE | 0 antes (vendeu +127 s) | +89 s | 33,2 / 23,0 | recusa: bundle | dobrou e zerou |

Piso de snipers ≥ 21 (q05a): nenhuma das 27 ordens tinha snipers < 21. No radar cortou 15 das 44:
11/15 perderam ≥ 50 % (Zynex, CHANCE, SPI, CLODDS, GORG, JEV, BRAVO, GARY, BPAD, Bear, BUILDERS), 4
"planas até a série acabar" (LIQUI, Memfun, MPGA, Flylock, −7 a −15 %), 0 graduaram.

## 4. Graduações (q04, q05d/e)

148 em [19:25, 22:25) (≈ 49/h); 39 Mayhem; `created_at` < 60 s antes da graduação **77** (só vistas no
board), 1–5 min 33, 5–30 min 27, > 30 min 8, sem `created_at` 3. Com série de 15 s: 74; com leitura na
janela do radar (30–300 s, 5–50 %): **39**; passaram `operator/5`: **0**; passariam sem snipers: **0**;
com proposta: 1 (SUPER CHIP `kxLJv99H`, flow_v2/2 e /3 paper). Veredito da melhor leitura das 39:
fluxo ≤ 0 21 · holders < 20 10 · sem fita 5 · razão > 0,6 2 (SPIDERBRAIN, TAG) · compradores < 10 1.

Graduadas com demanda real (série de 15 s):

| grad BRT | símbolo | mint8 | criada | idade | máx hold / compr | snipers | melhor leitura na janela | veredito | cr 7 d |
|---|---|---|---|---:|---|---|---|---|---:|
| 19:32:41 | SPIDERBRAIN | 3pKYaqro | 19:23:33 | 9,1 min | 403 / 59 | 9–50 | 19:24:12 49,6 %, 48 h, 47 c, 53×47 | razão | 350 |
| 19:36:42 | Solana | 7T59NtCT | 19:32:52 | 3,8 | 239 / 55 | 2–4 | 19:33:44 37,7 %, 37 h, 6 c | compradores | 0 |
| 20:16:24 | XENOMOUSE | 8t2Rxuhc | 19:54:45 | 21,6 | 52 / 35 | 52 | 19:58:47 46,3 %, 44 h, 40×41 | fluxo | 72 |
| 20:19:24 | ZEREBLAST | 4hMvdY7K | 20:03:40 | 15,7 | 224 / 59 | 34–48 | 20:05:52 47,7 %, 40 h | sem fita | 0 |
| 21:16:34 | SUPER CHIP | kxLJv99H | 20:54:08 | 22,4 | 28 / 25 | 10 | 20:56:00 49,0 %, 24 h, 0 c | fluxo | 2 |
| **21:37:07** | **TAG** | 3U3Y793Z | 21:12:08 | 25,0 | 168 / 45 | 91 | 21:14:33 39,8 %, 77 h, 33 c, **35×63** | razão | 0 |
| 22:01:07 | Memefun | 94b9LaJo | 21:49:20 | 11,8 | 62 / 41 | 29 | 21:51:38 39,3 %, 24 h, 0 c | fluxo | 53 |

TAG (q05b): última foto 21:36:39 rsol 77,141; 1 m 21:37: 308 holders, top-10 22,1 %, creator_sold f.
As outras ~30 graduadas com leitura: 2–12 holders com 40–170 compras/60 s (bots).
`hb:meme:radar.lab_gate_refusals.operator` (acumulado): holders_below_min 115, snipers_below_min 115,
buyers_below_min 105, flow_not_positive 104, no_buys 101, curve_volume_1m_zero 97, progress_below_min 90,
symbol_clone 68, creator_serial 59, creator_repeat_dumper 39, mayhem_curve 32.

## 5. Candidatas registradas (Obsidian)

1. LINK `4TcftzQv…` — viva na última foto (33,4 SOL, 167 holders), barrada por `symbol_clone`, sem dado
   desde 21:59, prog > 50 % desde 21:46.
2. TAG `3U3Y793Z…` — graduou 21:37:07 (a "que doeu" da R41); razão 1,8 na melhor leitura.
3. QAUNTITY `GFakEBdg…` — única recusada viva em 30 min; criador com 31 moedas; sem dado desde 21:25.

## Comandos

```
timeout 300 ssh -o ConnectTimeout=20 hunter-vps 'docker exec -i hunter-postgres-1 psql -U hunter -d hunter -At' < <arquivo>.sql
timeout 60 ssh hunter-vps 'docker exec hunter-redis-1 redis-cli --no-auth-warning HGETALL hb:meme:radar'
timeout 60 ssh hunter-vps 'docker exec hunter-redis-1 redis-cli --no-auth-warning HGETALL hb:meme:executor'
```

(SQL por stdin: `$$` dentro da string do ssh é expandido pelo shell remoto; o arquivo evita isso.)

## SQL (cópia integral)

### 2026-09-16-r46-q01-top10-porta-operator5.sql

```sql
-- R46 q01: top 10 da janela congelada [19:25, 22:25) BRT pela porta operator/5 sobre meme_features_15s
SET statement_timeout = 200000;
\pset format unaligned
\pset fieldsep '|'
CREATE TEMP TABLE r46_pass AS
  SELECT f.mint, f.as_of, f.age_s, f.curve_progress_pct, f.holders, f.holders_prev, f.unique_buyers_60s,
         f.buys_60s, f.sells_60s, f.snipers, f.dev_share, f.net_sol_flow_60s, f.curve_volume_60s_sol,
         f.creator_net_seller, f.creator_net_seller_reason
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint
  WHERE f.as_of >= timestamptz '2026-09-16 19:25-03' AND f.as_of < timestamptz '2026-09-16 22:25-03'
    AND f.age_s BETWEEN 30 AND 300
    AND t.mayhem_mode IS NULL
    AND (t.completed_at IS NULL OR t.completed_at > f.as_of)
    AND f.curve_progress_pct BETWEEN 0.05 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
    AND f.holders >= 20 AND f.unique_buyers_60s >= 10
    AND f.snipers BETWEEN 21 AND 1000
    AND f.dev_share IS NOT NULL AND f.dev_share <= 0.10
    AND f.buys_60s > 0 AND f.sells_60s::numeric/f.buys_60s <= 0.6
    AND coalesce(f.curve_volume_60s_sol,0) > 0;
-- (a) funil de moedas distintas na janela
WITH u AS (
  SELECT f.mint, bool_or(f.age_s BETWEEN 30 AND 300) AS idade,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50) AS prog,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s>0) AS fluxo,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s>0 AND f.holders>=20) AS h20,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s>0 AND f.holders>=20 AND f.unique_buyers_60s>=10) AS b10,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s>0 AND f.holders>=20 AND f.unique_buyers_60s>=10 AND f.buys_60s>0 AND f.sells_60s::numeric/f.buys_60s<=0.6) AS r06,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s>0 AND f.holders>=20 AND f.unique_buyers_60s>=10 AND f.buys_60s>0 AND f.sells_60s::numeric/f.buys_60s<=0.6 AND f.snipers BETWEEN 21 AND 1000) AS s21,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s>0 AND f.holders>=20 AND f.unique_buyers_60s>=10 AND f.buys_60s>0 AND f.sells_60s::numeric/f.buys_60s<=0.6 AND f.snipers BETWEEN 21 AND 1000 AND f.dev_share<=0.10) AS dev
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= timestamptz '2026-09-16 19:25-03' AND f.as_of < timestamptz '2026-09-16 22:25-03'
  GROUP BY 1)
SELECT 'funil' AS q, count(*) FILTER (WHERE idade) AS idade, count(*) FILTER (WHERE prog) AS prog_5_50,
  count(*) FILTER (WHERE fluxo) AS fluxo_pos, count(*) FILTER (WHERE h20) AS holders20,
  count(*) FILTER (WHERE b10) AS compr10, count(*) FILTER (WHERE r06) AS razao06,
  count(*) FILTER (WHERE s21) AS snipers21, count(*) FILTER (WHERE dev) AS dev10 FROM u;
-- (b) top 10 por demanda (max compradores unicos numa leitura que passou), com trajetoria
WITH agg AS (
  SELECT mint, count(*) AS n_pass, min(as_of) AS first_pass, max(as_of) AS last_pass,
    max(unique_buyers_60s) AS max_compr, max(holders) AS max_holders
  FROM r46_pass GROUP BY 1
), best AS (
  SELECT DISTINCT ON (p.mint) p.* FROM r46_pass p ORDER BY p.mint, p.unique_buyers_60s DESC, p.holders DESC
), top AS (
  SELECT a.*, b.as_of AS best_at, b.age_s, b.curve_progress_pct AS prog_best, b.holders AS holders_best,
    b.unique_buyers_60s AS compr_best, b.buys_60s, b.sells_60s, b.snipers, b.dev_share, b.net_sol_flow_60s,
    b.curve_volume_60s_sol, b.creator_net_seller, b.creator_net_seller_reason
  FROM agg a JOIN best b ON b.mint=a.mint ORDER BY a.max_compr DESC, a.max_holders DESC LIMIT 10
), l1 AS (
  SELECT DISTINCT ON (t.mint) t.mint, f.end_time, f.curve_progress_pct, f.holders, f.unique_buyers, f.buy_sell_ratio, f.top10_share, f.creator_sold, f.age_minutes
  FROM top t JOIN meme_features_1m f ON f.mint=t.mint AND f.end_time < timestamptz '2026-09-16 22:25-03'
  ORDER BY t.mint, f.end_time DESC
), l10 AS (
  SELECT DISTINCT ON (t.mint) t.mint, f.end_time, f.curve_progress_pct, f.holders, f.unique_buyers
  FROM top t JOIN l1 ON l1.mint=t.mint JOIN meme_features_1m f ON f.mint=t.mint AND f.end_time <= l1.end_time - interval '10 minutes'
  ORDER BY t.mint, f.end_time DESC
), l15 AS (
  SELECT DISTINCT ON (t.mint) t.mint, f.as_of, f.curve_progress_pct, f.holders, f.unique_buyers_60s, f.age_s
  FROM top t JOIN meme_features_15s f ON f.mint=t.mint AND f.as_of < timestamptz '2026-09-16 22:25-03'
  ORDER BY t.mint, f.as_of DESC
), pk AS (SELECT c.mint, max(c.real_sol_reserves) AS rsol_pico FROM meme_curve_snapshots c JOIN top t ON t.mint=c.mint
          WHERE c.observed_at >= timestamptz '2026-09-16 19:00-03' GROUP BY 1),
ag AS (SELECT DISTINCT ON (c.mint) c.mint, c.observed_at, c.real_sol_reserves AS rsol_agora, c.complete
       FROM meme_curve_snapshots c JOIN top t ON t.mint=c.mint WHERE c.observed_at >= timestamptz '2026-09-16 19:00-03'
       ORDER BY c.mint, c.observed_at DESC),
cr AS (SELECT t.mint, (SELECT count(*) FROM meme_tokens o WHERE o.creator=k.creator AND o.mint<>t.mint AND o.created_at > k.created_at - interval '7 days' AND o.created_at <= k.created_at) AS criador_7d
       FROM top t JOIN meme_tokens k ON k.mint=t.mint),
pr AS (SELECT t.mint, count(p.id) AS propostas, string_agg(DISTINCT rs.name||'/'||rs.version, ',') AS rule_sets,
              string_agg(DISTINCT coalesce(o.status||':'||coalesce(o.reason,'-'),'sem_ordem'), ',') AS ordens
       FROM top t LEFT JOIN meme_proposals p ON p.mint=t.mint AND p.proposed_at >= timestamptz '2026-09-16 19:25-03'
       LEFT JOIN meme_rule_sets rs ON rs.id=p.rule_set_id LEFT JOIN meme_live_orders o ON o.proposal_id=p.id GROUP BY 1)
SELECT 'top10' AS q, k.symbol, k.name, left(t.mint,8) AS mint8, t.mint,
  to_char(k.created_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS criada_brt,
  coalesce(to_char(k.completed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS'),'-') AS completou_brt,
  t.n_pass, to_char(t.first_pass AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS primeira_pass,
  to_char(t.last_pass AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS ultima_pass,
  to_char(t.best_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS melhor_brt, t.age_s,
  round(t.prog_best*100,1) AS prog_melhor, t.holders_best, t.compr_best, t.buys_60s, t.sells_60s, t.snipers,
  round(t.dev_share*100,2) AS dev_pct, round(t.net_sol_flow_60s,2) AS fluxo, round(t.curve_volume_60s_sol,1) AS vol60,
  coalesce(t.creator_net_seller::text, coalesce(t.creator_net_seller_reason,'null')) AS cns,
  to_char(l15.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS ult15_brt, l15.age_s AS ult15_age,
  round(l15.curve_progress_pct*100,1) AS ult15_prog, l15.holders AS ult15_holders, l15.unique_buyers_60s AS ult15_compr,
  to_char(l1.end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS ult1m_brt, l1.age_minutes,
  round(l1.curve_progress_pct*100,1) AS ult1m_prog, l1.holders AS ult1m_holders, l1.unique_buyers AS ult1m_compr,
  round(l1.top10_share*100,1) AS top10, l1.creator_sold,
  to_char(l10.end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS m10_brt, round(l10.curve_progress_pct*100,1) AS m10_prog,
  l10.holders AS m10_holders, l10.unique_buyers AS m10_compr,
  round(pk.rsol_pico,3) AS rsol_pico, round(ag.rsol_agora,3) AS rsol_agora,
  to_char(ag.observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS rsol_brt, ag.complete,
  cr.criador_7d, pr.propostas, coalesce(pr.rule_sets,'-') AS rule_sets, coalesce(pr.ordens,'-') AS ordens
FROM top t JOIN meme_tokens k ON k.mint=t.mint LEFT JOIN l1 ON l1.mint=t.mint LEFT JOIN l10 ON l10.mint=t.mint
  LEFT JOIN l15 ON l15.mint=t.mint LEFT JOIN pk ON pk.mint=t.mint LEFT JOIN ag ON ag.mint=t.mint
  LEFT JOIN cr ON cr.mint=t.mint LEFT JOIN pr ON pr.mint=t.mint
ORDER BY t.max_compr DESC, t.max_holders DESC;
-- (c) quantas passaram ao todo e quantas tiveram proposta
SELECT 'pass_total' AS q, count(DISTINCT p.mint) AS moedas_passaram, count(*) AS leituras,
  count(DISTINCT p.mint) FILTER (WHERE EXISTS (SELECT 1 FROM meme_proposals x WHERE x.mint=p.mint AND x.proposed_at >= timestamptz '2026-09-16 19:25-03')) AS com_proposta
FROM r46_pass p;
```

### 2026-09-16-r46-q02-propostas-e-ordens.sql

```sql
-- R46 q02: propostas e ordens reais na janela [19:25, 22:25) BRT
SET statement_timeout = 200000;
\pset format unaligned
\pset fieldsep '|'
SELECT 'por_rule_set' AS q, rs.name||'/'||rs.version AS rule_set, p.mode, p.status, coalesce(p.refusal,'-') AS refusal, count(*) AS n, count(DISTINCT p.mint) AS moedas
FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
WHERE p.proposed_at >= timestamptz '2026-09-16 19:25-03' AND p.proposed_at < timestamptz '2026-09-16 22:25-03'
GROUP BY 1,2,3,4,5 ORDER BY 2,3,4,5;
SELECT 'ordens_por_motivo' AS q, o.side, o.status, coalesce(o.reason,'-') AS reason, count(*) AS n, count(DISTINCT p.mint) AS moedas
FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id
WHERE o.received_at >= timestamptz '2026-09-16 19:25-03' AND o.received_at < timestamptz '2026-09-16 22:25-03'
GROUP BY 1,2,3,4 ORDER BY n DESC;
-- lista das ordens reais com a feature de 15 s mais recente antes da ordem e o desfecho pela cadeia
WITH o AS (
  SELECT o.id, o.received_at, o.side, o.status, o.reason, o.tx_signature, o.admission, p.mint, p.origin, p.mode, rs.name||'/'||rs.version AS rule_set,
    (p.quote->>'curve_progress_pct')::numeric AS prog_quote
  FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
  WHERE o.received_at >= timestamptz '2026-09-16 19:25-03' AND o.received_at < timestamptz '2026-09-16 22:25-03'
), chk AS (
  SELECT o.id,
    max(CASE WHEN c->>'name'='curve_progress' THEN (c->>'value')::numeric END) AS prog_adm,
    max(CASE WHEN c->>'name'='bundled_share' THEN (c->>'value')::numeric END) AS bundle_adm,
    max(CASE WHEN c->>'name'='top10_share' THEN (c->>'value')::numeric END) AS top10_adm,
    string_agg(CASE WHEN (c->>'ok')::boolean IS FALSE THEN c->>'name' END, ',') AS falhou
  FROM o, LATERAL jsonb_array_elements(o.admission->'checks') c GROUP BY 1
), f AS (
  SELECT DISTINCT ON (o.id) o.id, x.as_of, x.curve_progress_pct, x.holders, x.unique_buyers_60s, x.snipers, x.net_sol_flow_60s, x.buys_60s, x.sells_60s, x.dev_share, x.creator_net_seller, x.creator_net_seller_reason
  FROM o JOIN meme_features_15s x ON x.mint=o.mint AND x.as_of <= o.received_at ORDER BY o.id, x.as_of DESC
), rk AS (
  SELECT DISTINCT ON (o.id) o.id, r.observed_at, r.bundled_share, r.top10_share, extract(epoch FROM (o.received_at - r.observed_at))::int AS idade_retrato_s
  FROM o JOIN meme_risk_snapshots r ON r.mint=o.mint AND r.observed_at <= o.received_at ORDER BY o.id, r.observed_at DESC
), rk2 AS (
  SELECT DISTINCT ON (o.id) o.id, r.bundled_share, extract(epoch FROM (r.observed_at - o.received_at))::int AS atraso_s
  FROM o JOIN meme_risk_snapshots r ON r.mint=o.mint AND r.observed_at > o.received_at ORDER BY o.id, r.observed_at
), cns AS (
  SELECT DISTINCT ON (o.id) o.id, x.creator_net_seller, x.as_of
  FROM o JOIN meme_features_15s x ON x.mint=o.mint AND x.as_of > o.received_at AND x.creator_net_seller IS NOT NULL ORDER BY o.id, x.as_of
), ent AS (
  SELECT DISTINCT ON (o.id) o.id, c.real_sol_reserves AS rsol0 FROM o JOIN meme_curve_snapshots c ON c.mint=o.mint AND c.observed_at <= o.received_at AND c.observed_at > o.received_at - interval '30 minutes' ORDER BY o.id, c.observed_at DESC
), w AS (
  SELECT o.id, c.observed_at, c.real_sol_reserves AS rsol, c.complete FROM o JOIN meme_curve_snapshots c ON c.mint=o.mint AND c.observed_at > o.received_at AND c.observed_at <= o.received_at + interval '30 minutes'
), ag AS (SELECT id, count(*) AS n, min(rsol) AS rmin, max(rsol) AS rmax, bool_or(complete) AS graduou FROM w GROUP BY 1)
SELECT 'ordens' AS q, to_char(o.received_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt, coalesce(t.symbol,'?') AS symbol, left(o.mint,8) AS mint8,
  o.rule_set, o.origin, o.side, o.status, coalesce(o.reason,'-') AS motivo, coalesce(chk.falhou,'-') AS checks_falhos, coalesce(left(o.tx_signature,12),'-') AS tx,
  round(o.prog_quote,1) AS prog_quote, round(f.curve_progress_pct*100,1) AS prog15, round(chk.prog_adm*100,1) AS prog_adm,
  f.holders, f.unique_buyers_60s AS compr, f.snipers, f.buys_60s, f.sells_60s, round(f.dev_share*100,2) AS dev_pct, round(f.net_sol_flow_60s,2) AS fluxo,
  coalesce(f.creator_net_seller::text, coalesce(f.creator_net_seller_reason,'null')) AS cns_na_ordem,
  coalesce(cns.creator_net_seller::text,'nunca') AS cns_depois, extract(epoch FROM (cns.as_of - o.received_at))::int AS cns_atraso_s,
  round(rk.bundled_share*100,1) AS bundle_antes, rk.idade_retrato_s, round(rk2.bundled_share*100,1) AS bundle_depois, rk2.atraso_s AS retrato_atraso_s,
  round(ent.rsol0,3) AS rsol0, coalesce(ag.n,0) AS fotos30, round(ag.rmin,3) AS rmin30, round(ag.rmax,3) AS rmax30, coalesce(ag.graduou,false) AS graduou
FROM o LEFT JOIN meme_tokens t ON t.mint=o.mint LEFT JOIN chk ON chk.id=o.id LEFT JOIN f ON f.id=o.id LEFT JOIN rk ON rk.id=o.id LEFT JOIN rk2 ON rk2.id=o.id
  LEFT JOIN cns ON cns.id=o.id LEFT JOIN ent ON ent.id=o.id LEFT JOIN ag ON ag.id=o.id
ORDER BY o.received_at;
-- propostas sem ordem (nao-live, ou live sem executor)
SELECT 'propostas_sem_ordem' AS q, rs.name||'/'||rs.version AS rule_set, p.mode, p.status, coalesce(p.refusal,'-') AS refusal, count(*) AS n, count(DISTINCT p.mint) AS moedas
FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
WHERE p.proposed_at >= timestamptz '2026-09-16 19:25-03' AND p.proposed_at < timestamptz '2026-09-16 22:25-03'
  AND NOT EXISTS (SELECT 1 FROM meme_live_orders o WHERE o.proposal_id=p.id)
GROUP BY 1,2,3,4,5 ORDER BY n DESC;
```

### 2026-09-16-r46-q04-graduacoes.sql

```sql
-- R46 q04: graduacoes na janela [19:25, 22:25) BRT e o que o radar tinha delas
SET statement_timeout = 200000;
\pset format unaligned
\pset fieldsep '|'
WITH g AS (
  SELECT t.mint, t.symbol, t.name, t.creator, t.created_at, t.completed_at, t.graduated_board_seen_at, t.mayhem_mode,
    least(t.completed_at, t.graduated_board_seen_at) AS grad_at
  FROM meme_tokens t
  WHERE least(t.completed_at, t.graduated_board_seen_at) >= timestamptz '2026-09-16 19:25-03'
    AND least(t.completed_at, t.graduated_board_seen_at) < timestamptz '2026-09-16 22:25-03'
)
SELECT 'grad_total' AS q, count(*) AS graduadas, count(*) FILTER (WHERE created_at IS NOT NULL) AS com_created,
  count(*) FILTER (WHERE mayhem_mode IS NOT NULL) AS mayhem,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM meme_features_15s f WHERE f.mint=g.mint)) AS com_serie_15s,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM meme_features_1m f WHERE f.mint=g.mint AND f.end_time > timestamptz '2026-09-16 15:00-03')) AS com_serie_1m,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM meme_proposals p WHERE p.mint=g.mint)) AS com_proposta,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM (grad_at - created_at))/60)::numeric,1) AS idade_mediana_min
FROM g;
WITH g AS (
  SELECT t.mint, t.symbol, t.name, t.creator, t.created_at, t.completed_at, t.graduated_board_seen_at, t.mayhem_mode,
    least(t.completed_at, t.graduated_board_seen_at) AS grad_at
  FROM meme_tokens t
  WHERE least(t.completed_at, t.graduated_board_seen_at) >= timestamptz '2026-09-16 19:25-03'
    AND least(t.completed_at, t.graduated_board_seen_at) < timestamptz '2026-09-16 22:25-03'
), s15 AS (
  SELECT g.mint, count(*) AS n15, min(f.as_of) AS first15, max(f.as_of) AS last15, max(f.age_s) AS max_age,
    max(f.holders) AS max_holders, max(f.unique_buyers_60s) AS max_compr, max(f.snipers) AS max_snipers, min(f.snipers) AS min_snipers,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s>0 AND f.holders>=20 AND f.unique_buyers_60s>=10 AND f.buys_60s>0 AND f.sells_60s::numeric/f.buys_60s<=0.6 AND f.snipers BETWEEN 21 AND 1000 AND f.dev_share<=0.10) AS passou_porta,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s>0 AND f.holders>=20 AND f.unique_buyers_60s>=10 AND f.buys_60s>0 AND f.sells_60s::numeric/f.buys_60s<=0.6 AND f.dev_share<=0.10) AS passou_sem_snipers,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50) AS na_janela,
    count(*) FILTER (WHERE f.tape_reason IS NULL) AS n_com_fita,
    count(*) FILTER (WHERE f.snipers IS NULL) AS n_snipers_null,
    count(*) FILTER (WHERE f.dev_share IS NULL) AS n_dev_null
  FROM g JOIN meme_features_15s f ON f.mint=g.mint GROUP BY 1
), s1 AS (
  SELECT g.mint, count(*) AS n1m, max(f.holders) AS max_holders_1m, max(f.unique_buyers) AS max_compr_1m
  FROM g JOIN meme_features_1m f ON f.mint=g.mint AND f.end_time > timestamptz '2026-09-16 15:00-03' GROUP BY 1
), bestj AS (
  SELECT DISTINCT ON (g.mint) g.mint, f.as_of, f.age_s, f.curve_progress_pct, f.holders, f.unique_buyers_60s, f.buys_60s, f.sells_60s, f.snipers, f.dev_share, f.net_sol_flow_60s, f.tape_reason,
    CASE WHEN f.tape_reason IS NOT NULL THEN 'sem_fita' WHEN f.net_sol_flow_60s<=0 THEN 'fluxo' WHEN f.holders<20 THEN 'holders' WHEN f.unique_buyers_60s<10 THEN 'compradores'
         WHEN f.buys_60s=0 OR f.sells_60s::numeric/f.buys_60s>0.6 THEN 'razao' WHEN f.snipers IS NULL THEN 'snipers_null' WHEN f.snipers<21 THEN 'snipers<21' WHEN f.snipers>1000 THEN 'snipers>1000'
         WHEN f.dev_share IS NULL THEN 'dev_null' WHEN f.dev_share>0.10 THEN 'dev>10' ELSE 'passa' END AS veredito
  FROM g JOIN meme_features_15s f ON f.mint=g.mint AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50
  ORDER BY g.mint, f.unique_buyers_60s DESC NULLS LAST, f.holders DESC NULLS LAST
), pr AS (
  SELECT g.mint, count(p.id) AS propostas, string_agg(DISTINCT rs.name||'/'||rs.version||':'||p.status||':'||coalesce(p.refusal,'-'), ' ; ') AS props,
    string_agg(DISTINCT coalesce(o.status||':'||coalesce(o.reason,'-'),''), ',') AS ordens
  FROM g LEFT JOIN meme_proposals p ON p.mint=g.mint LEFT JOIN meme_rule_sets rs ON rs.id=p.rule_set_id LEFT JOIN meme_live_orders o ON o.proposal_id=p.id GROUP BY 1
), cr AS (
  SELECT g.mint, (SELECT count(*) FROM meme_tokens o WHERE o.creator=g.creator AND o.mint<>g.mint AND o.created_at > g.created_at - interval '7 days' AND o.created_at <= g.created_at) AS criador_7d FROM g
)
SELECT 'grad' AS q, to_char(g.grad_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS grad_brt, coalesce(g.symbol,'?') AS symbol, left(g.mint,8) AS mint8,
  coalesce(to_char(g.created_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS'),'-') AS criada_brt,
  round(extract(epoch FROM (g.grad_at - g.created_at))/60,1) AS idade_min,
  CASE WHEN g.completed_at IS NOT NULL AND g.graduated_board_seen_at IS NOT NULL THEN 'ambos' WHEN g.completed_at IS NOT NULL THEN 'completed' ELSE 'board' END AS sinal,
  coalesce(g.mayhem_mode,'-') AS mayhem,
  coalesce(s15.n15,0) AS n15, s15.max_age, s15.max_holders, s15.max_compr, s15.min_snipers, s15.max_snipers, s15.n_com_fita, s15.n_snipers_null,
  coalesce(s15.na_janela,false) AS na_janela, coalesce(s15.passou_porta,false) AS passou_porta, coalesce(s15.passou_sem_snipers,false) AS passou_sem_snipers,
  coalesce(s1.n1m,0) AS n1m, s1.max_holders_1m, s1.max_compr_1m,
  to_char(bj.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS melhor_brt, round(bj.curve_progress_pct*100,1) AS prog, bj.holders, bj.unique_buyers_60s AS compr, bj.buys_60s, bj.sells_60s, bj.snipers, round(bj.dev_share*100,1) AS dev, round(bj.net_sol_flow_60s,2) AS fluxo, coalesce(bj.veredito,'sem_leitura_na_janela') AS veredito,
  cr.criador_7d, coalesce(pr.propostas,0) AS propostas, coalesce(pr.props,'-') AS props, coalesce(nullif(pr.ordens,''),'-') AS ordens
FROM g LEFT JOIN s15 ON s15.mint=g.mint LEFT JOIN s1 ON s1.mint=g.mint LEFT JOIN bestj bj ON bj.mint=g.mint LEFT JOIN pr ON pr.mint=g.mint LEFT JOIN cr ON cr.mint=g.mint
ORDER BY g.grad_at;
```

### 2026-09-16-r46-q05-piso-snipers-vivas-veredito.sql

```sql
-- R46 q05: piso de snipers (o que ele cortou na janela), estado atual das vivas, veredito das graduadas
SET statement_timeout = 200000;
\pset format unaligned
\pset fieldsep '|'
-- (a) moedas que passaram TUDO menos o piso de snipers (snipers < 21 ou NULL), melhor leitura, desfecho pela cadeia
WITH p AS (
  SELECT f.mint, f.as_of, f.age_s, f.curve_progress_pct, f.holders, f.unique_buyers_60s, f.buys_60s, f.sells_60s, f.snipers, f.snipers_reason, f.dev_share, f.net_sol_flow_60s
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint
  WHERE f.as_of >= timestamptz '2026-09-16 19:25-03' AND f.as_of < timestamptz '2026-09-16 22:25-03'
    AND f.age_s BETWEEN 30 AND 300 AND t.mayhem_mode IS NULL AND (t.completed_at IS NULL OR t.completed_at > f.as_of)
    AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
    AND f.holders >= 20 AND f.unique_buyers_60s >= 10 AND f.dev_share IS NOT NULL AND f.dev_share <= 0.10
    AND f.buys_60s > 0 AND f.sells_60s::numeric/f.buys_60s <= 0.6
    AND (f.snipers IS NULL OR f.snipers < 21)
    AND NOT EXISTS (SELECT 1 FROM meme_features_15s g WHERE g.mint=f.mint AND g.as_of >= timestamptz '2026-09-16 19:25-03' AND g.as_of < timestamptz '2026-09-16 22:25-03'
                    AND g.age_s BETWEEN 30 AND 300 AND g.curve_progress_pct BETWEEN 0.05 AND 0.50 AND g.tape_reason IS NULL AND g.net_sol_flow_60s > 0
                    AND g.holders >= 20 AND g.unique_buyers_60s >= 10 AND g.dev_share <= 0.10 AND g.buys_60s > 0 AND g.sells_60s::numeric/g.buys_60s <= 0.6 AND g.snipers BETWEEN 21 AND 1000)
), best AS (SELECT DISTINCT ON (mint) * FROM p ORDER BY mint, unique_buyers_60s DESC, holders DESC),
pk AS (SELECT c.mint, max(c.real_sol_reserves) AS rsol_pico FROM meme_curve_snapshots c JOIN best b ON b.mint=c.mint WHERE c.observed_at >= timestamptz '2026-09-16 19:00-03' GROUP BY 1),
ag AS (SELECT DISTINCT ON (c.mint) c.mint, c.observed_at, c.real_sol_reserves AS rsol_agora, c.complete FROM meme_curve_snapshots c JOIN best b ON b.mint=c.mint WHERE c.observed_at >= timestamptz '2026-09-16 19:00-03' ORDER BY c.mint, c.observed_at DESC),
cr AS (SELECT b.mint, (SELECT count(*) FROM meme_tokens o WHERE o.creator=k.creator AND o.mint<>b.mint AND o.created_at > k.created_at - interval '7 days' AND o.created_at <= k.created_at) AS criador_7d FROM best b JOIN meme_tokens k ON k.mint=b.mint)
SELECT 'so_snipers' AS q, to_char(b.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt, coalesce(k.symbol,'?') AS symbol, left(b.mint,8) AS mint8, b.age_s,
  round(b.curve_progress_pct*100,1) AS prog, b.holders, b.unique_buyers_60s AS compr, b.buys_60s, b.sells_60s, coalesce(b.snipers::text, coalesce(b.snipers_reason,'null')) AS snipers,
  round(b.dev_share*100,2) AS dev, round(b.net_sol_flow_60s,2) AS fluxo, round(pk.rsol_pico,3) AS rsol_pico, round(ag.rsol_agora,3) AS rsol_ult,
  to_char(ag.observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS rsol_brt, ag.complete, coalesce(to_char(k.completed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS'),'-') AS completou, cr.criador_7d
FROM best b JOIN meme_tokens k ON k.mint=b.mint LEFT JOIN pk ON pk.mint=b.mint LEFT JOIN ag ON ag.mint=b.mint LEFT JOIN cr ON cr.mint=b.mint
ORDER BY b.unique_buyers_60s DESC;
-- (b) estado atual (ultima foto da cadeia, ate agora) das que interessam
WITH m AS (SELECT unnest(ARRAY['4TcftzQvXTwSEfsuWL75LLNQvdennvRsjmCh3VS5pump','GFakEBdgdKDJhsCKauSkKVjHYPqHDBEY7SgJZEJDpump']) AS mint
           UNION SELECT mint FROM meme_tokens WHERE mint LIKE 'ENBTWXHt%' OR mint LIKE 'C8ykWko6%' OR mint LIKE '3U3Y793Z%' OR mint LIKE 'H91rJ7Dc%' OR mint LIKE 'Fyko94e1%' OR mint LIKE 'FMMCvUEN%')
SELECT 'agora' AS q, coalesce(t.symbol,'?') AS symbol, left(m.mint,8) AS mint8,
  (SELECT to_char(c.observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS')||' rsol='||round(c.real_sol_reserves,3)||' complete='||c.complete FROM meme_curve_snapshots c WHERE c.mint=m.mint AND c.observed_at >= timestamptz '2026-09-16 19:00-03' ORDER BY c.observed_at DESC LIMIT 1) AS ultima_foto,
  (SELECT count(*) FROM meme_curve_snapshots c WHERE c.mint=m.mint AND c.observed_at >= timestamptz '2026-09-16 19:00-03') AS fotos,
  (SELECT round(max(c.real_sol_reserves),3) FROM meme_curve_snapshots c WHERE c.mint=m.mint AND c.observed_at >= timestamptz '2026-09-16 19:00-03') AS rsol_pico,
  (SELECT to_char(f.end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI')||' age='||f.age_minutes||' prog='||round(coalesce(f.curve_progress_pct,0)*100,1)||' holders='||coalesce(f.holders::text,'-')||' compr='||coalesce(f.unique_buyers::text,'-')||' top10='||coalesce(round(f.top10_share*100,1)::text,'-')||' creator_sold='||coalesce(f.creator_sold::text,'-')||' cns='||coalesce(f.creator_net_seller::text,'-') FROM meme_features_1m f WHERE f.mint=m.mint ORDER BY f.end_time DESC LIMIT 1) AS ult_1m,
  coalesce(to_char(t.completed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS'),'-') AS completou
FROM m JOIN meme_tokens t ON t.mint=m.mint;
-- (c) trajetoria da LINK e da DOWNIE a cada ~2 min (cadeia)
SELECT 'traj' AS q, coalesce(t.symbol,'?') AS symbol, to_char(date_trunc('minute', c.observed_at) AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS min_brt,
  round(min(c.real_sol_reserves),2) AS rsol_min, round(max(c.real_sol_reserves),2) AS rsol_max, round(max(c.virtual_sol_reserves - c.real_sol_reserves),1) AS invariante, bool_or(c.complete) AS complete
FROM meme_curve_snapshots c JOIN meme_tokens t ON t.mint=c.mint
WHERE (c.mint LIKE '4TcftzQv%' OR c.mint LIKE 'ENBTWXHt%') AND c.observed_at >= timestamptz '2026-09-16 21:40-03'
GROUP BY 1,2,3 ORDER BY 2,3;
-- (d) veredito das graduadas que tiveram leitura na janela do radar
WITH g AS (
  SELECT t.mint FROM meme_tokens t WHERE least(t.completed_at, t.graduated_board_seen_at) >= timestamptz '2026-09-16 19:25-03' AND least(t.completed_at, t.graduated_board_seen_at) < timestamptz '2026-09-16 22:25-03'
), bj AS (
  SELECT DISTINCT ON (g.mint) g.mint,
    CASE WHEN f.tape_reason IS NOT NULL THEN 'sem_fita' WHEN f.net_sol_flow_60s<=0 THEN 'fluxo' WHEN f.holders<20 THEN 'holders' WHEN f.unique_buyers_60s<10 THEN 'compradores'
         WHEN f.buys_60s=0 OR f.sells_60s::numeric/f.buys_60s>0.6 THEN 'razao' WHEN f.snipers IS NULL THEN 'snipers_null' WHEN f.snipers<21 THEN 'snipers<21' WHEN f.snipers>1000 THEN 'snipers>1000'
         WHEN f.dev_share IS NULL THEN 'dev_null' WHEN f.dev_share>0.10 THEN 'dev>10' ELSE 'passa' END AS veredito
  FROM g JOIN meme_features_15s f ON f.mint=g.mint AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50
  ORDER BY g.mint, f.unique_buyers_60s DESC NULLS LAST, f.holders DESC NULLS LAST
)
SELECT 'grad_veredito' AS q, coalesce(bj.veredito,'sem_leitura_na_janela') AS veredito, count(*) FROM g LEFT JOIN bj ON bj.mint=g.mint GROUP BY 2 ORDER BY 3 DESC;
-- (e) graduadas: created_at real (criada > 60 s antes de graduar) x instantaneas
SELECT 'grad_idade' AS q,
  count(*) FILTER (WHERE least(t.completed_at, t.graduated_board_seen_at) - t.created_at < interval '60 seconds') AS instantaneas_lt60s,
  count(*) FILTER (WHERE least(t.completed_at, t.graduated_board_seen_at) - t.created_at >= interval '60 seconds' AND least(t.completed_at, t.graduated_board_seen_at) - t.created_at < interval '5 minutes') AS de_1_a_5min,
  count(*) FILTER (WHERE least(t.completed_at, t.graduated_board_seen_at) - t.created_at >= interval '5 minutes' AND least(t.completed_at, t.graduated_board_seen_at) - t.created_at < interval '30 minutes') AS de_5_a_30min,
  count(*) FILTER (WHERE least(t.completed_at, t.graduated_board_seen_at) - t.created_at >= interval '30 minutes') AS acima_30min,
  count(*) FILTER (WHERE t.created_at IS NULL) AS sem_created
FROM meme_tokens t WHERE least(t.completed_at, t.graduated_board_seen_at) >= timestamptz '2026-09-16 19:25-03' AND least(t.completed_at, t.graduated_board_seen_at) < timestamptz '2026-09-16 22:25-03';
-- (f) colunas de meme_trades
SELECT 'cols' AS q, string_agg(column_name||':'||data_type, ', ' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='meme_trades';
```

### 2026-09-16-r46-q06-contrafactual-t445.sql

```sql
-- R46 q06: contrafactual T4.45 sobre as 9 moedas recusadas por creator_flow_unknown na janela [19:25, 22:25) BRT
-- Parte B (fluxo do criador pela cadeia): aproximado pela fita (meme_trades, trader = criador) -- o que a ATA diria.
-- Parte A (retrato sob demanda): o retrato mais proximo (antes ou depois) da 1a ordem, e o veredito bundle <= 20 % / top10 <= 25 %.
SET statement_timeout = 200000;
\pset format unaligned
\pset fieldsep '|'
WITH o AS (
  SELECT p.mint, min(o.received_at) AS primeira_ordem, count(*) AS ordens, string_agg(DISTINCT o.reason, ',') AS motivos,
    min((p.quote->>'curve_progress_pct')::numeric) AS prog_quote_min
  FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id
  WHERE o.received_at >= timestamptz '2026-09-16 19:25-03' AND o.received_at < timestamptz '2026-09-16 22:25-03' AND o.side='buy'
  GROUP BY 1
), ct AS (
  SELECT o.mint, count(*) FILTER (WHERE tr.side='buy') AS cr_buys, count(*) FILTER (WHERE tr.side='sell') AS cr_sells,
    round(sum(tr.sol_lamports) FILTER (WHERE tr.side='buy')/1e9,3) AS cr_buy_sol, round(sum(tr.sol_lamports) FILTER (WHERE tr.side='sell')/1e9,3) AS cr_sell_sol,
    min(tr.block_time) FILTER (WHERE tr.side='sell') AS cr_first_sell,
    min(tr.block_time) AS fita_inicio, count(*) AS fita_n
  FROM o JOIN meme_tokens t ON t.mint=o.mint LEFT JOIN meme_trades tr ON tr.mint=o.mint AND tr.trader=t.creator
    AND tr.block_time >= timestamptz '2026-09-16 19:00-03' AND tr.block_time < timestamptz '2026-09-16 22:30-03'
  GROUP BY 1
), fita AS (
  SELECT o.mint, min(tr.block_time) AS fita_inicio, count(*) AS fita_n, count(DISTINCT tr.trader) FILTER (WHERE tr.side='buy') AS compradores
  FROM o JOIN meme_trades tr ON tr.mint=o.mint AND tr.block_time >= timestamptz '2026-09-16 19:00-03' AND tr.block_time < timestamptz '2026-09-16 22:30-03' GROUP BY 1
), rk AS (
  SELECT DISTINCT ON (o.mint) o.mint, r.observed_at, r.bundled_share, r.top10_share, r.holders, r.snipers, r.dev_share,
    extract(epoch FROM (r.observed_at - o.primeira_ordem))::int AS delta_s
  FROM o JOIN meme_risk_snapshots r ON r.mint=o.mint AND r.observed_at BETWEEN o.primeira_ordem - interval '600 seconds' AND o.primeira_ordem + interval '600 seconds'
  ORDER BY o.mint, abs(extract(epoch FROM (r.observed_at - o.primeira_ordem)))
), ch AS (
  SELECT o.mint, max(c.real_sol_reserves) FILTER (WHERE c.observed_at <= o.primeira_ordem) AS rsol_antes_max,
    max(c.real_sol_reserves) FILTER (WHERE c.observed_at > o.primeira_ordem AND c.observed_at <= o.primeira_ordem + interval '30 minutes') AS rmax30,
    min(c.real_sol_reserves) FILTER (WHERE c.observed_at > o.primeira_ordem AND c.observed_at <= o.primeira_ordem + interval '30 minutes') AS rmin30
  FROM o JOIN meme_curve_snapshots c ON c.mint=o.mint AND c.observed_at >= timestamptz '2026-09-16 19:00-03' GROUP BY 1
), ent AS (
  SELECT DISTINCT ON (o.mint) o.mint, c.real_sol_reserves AS rsol0 FROM o JOIN meme_curve_snapshots c ON c.mint=o.mint AND c.observed_at <= o.primeira_ordem AND c.observed_at >= timestamptz '2026-09-16 19:00-03' ORDER BY o.mint, c.observed_at DESC
)
SELECT 'cf' AS q, to_char(o.primeira_ordem AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS primeira_ordem, coalesce(t.symbol,'?') AS symbol, left(o.mint,8) AS mint8,
  o.ordens, o.motivos, round(o.prog_quote_min,1) AS prog_quote_min,
  left(t.creator,6) AS criador, ct.cr_buys, ct.cr_sells, ct.cr_buy_sol, ct.cr_sell_sol,
  coalesce(to_char(ct.cr_first_sell AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS'),'-') AS cr_1a_venda,
  CASE WHEN ct.cr_first_sell IS NOT NULL AND ct.cr_first_sell <= o.primeira_ordem THEN 'vendeu_antes' WHEN ct.cr_first_sell IS NOT NULL THEN 'vendeu_depois' ELSE 'nao_vendeu_na_fita' END AS fluxo_criador,
  to_char(fita.fita_inicio AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS fita_desde, fita.fita_n, fita.compradores,
  round(rk.bundled_share*100,1) AS bundle, round(rk.top10_share*100,1) AS top10, rk.holders AS r_holders, rk.snipers AS r_snipers, round(rk.dev_share*100,1) AS r_dev, rk.delta_s AS retrato_delta_s,
  CASE WHEN rk.mint IS NULL THEN 'sem_retrato_600s'
       WHEN (ct.cr_first_sell IS NOT NULL AND ct.cr_first_sell <= o.primeira_ordem) THEN 'recusa:creator_net_seller'
       WHEN rk.bundled_share > 0.20 THEN 'recusa:bundle'
       WHEN rk.top10_share > 0.25 THEN 'recusa:top10'
       WHEN o.prog_quote_min > 50 THEN 'recusa:progress'
       ELSE 'ADMITIRIA' END AS veredito_t445,
  round(ent.rsol0,3) AS rsol0, round(ch.rmax30,3) AS rmax30, round(ch.rmin30,3) AS rmin30,
  CASE WHEN ch.rmax30 >= 1.5*ent.rsol0 THEN 'subiu>=50%' ELSE '-' END AS subiu, CASE WHEN ch.rmin30 <= 0.5*ent.rsol0 THEN 'caiu>=50%' ELSE '-' END AS caiu
FROM o JOIN meme_tokens t ON t.mint=o.mint LEFT JOIN ct ON ct.mint=o.mint LEFT JOIN fita ON fita.mint=o.mint LEFT JOIN rk ON rk.mint=o.mint LEFT JOIN ch ON ch.mint=o.mint LEFT JOIN ent ON ent.mint=o.mint
ORDER BY o.primeira_ordem;
-- heartbeat do executor (ultimo)
```

### 2026-09-16-r46-q07-pedigree-e-link.sql

```sql
-- R46 q07: por que 7 das 10 nao foram propostas (pedigree aproximado) + estado agora das vivas (LINK, QAUNTITY)
SET statement_timeout = 200000;
\pset format unaligned
\pset fieldsep '|'
WITH m AS (
  SELECT t.* FROM meme_tokens t WHERE t.mint IN ('3tmKhPmo9NixC8nNZYztNR41GsyxzLifRUzUdeubpump','ChgZ7GkiYkyyfp1qBuNu2qgprPYC17DnvUqbyVrQpump','6XcZ6ds95n9XnHvfbCqDmvowcQtLNNofnYyjMjkAjse9','97CXCc6bg7rcWo14L2UktwyxEpBRPUJ9eeeDw1ERpump','7x8cE5AoELM3gnFDq8KL7qxArp5cmi4nCZeqB2DWpump','4TcftzQvXTwSEfsuWL75LLNQvdennvRsjmCh3VS5pump','4hFxr7x8ive2NiYvrNoBiKrrimVgVP9KV4YgTEHApump','7fWspNngkwZ4rN2XSJpvsXE14RRjcrRV6DKqaN4ppump','GFakEBdgdKDJhsCKauSkKVjHYPqHDBEY7SgJZEJDpump','9PyqygumGwmbaJn7sVZVyUzHzBH4ZMj5R5eNDceupump')
)
SELECT 'pedigree' AS q, m.symbol, left(m.mint,8) AS mint8, coalesce(m.pool,'-') AS pool, coalesce(m.mayhem_mode,'-') AS mayhem,
  (SELECT count(*) FROM meme_tokens o WHERE o.symbol=m.symbol AND o.mint<>m.mint AND o.created_at IS NOT NULL AND o.created_at <= m.created_at AND o.created_at > m.created_at - interval '24 hours') AS clones_simbolo_24h,
  (SELECT count(*) FROM meme_tokens o WHERE o.creator=m.creator AND o.mint<>m.mint AND o.created_at IS NOT NULL AND o.created_at <= m.created_at AND o.created_at > m.created_at - interval '1 hour') AS criador_1h,
  (SELECT count(*) FROM meme_tokens o WHERE o.creator=m.creator AND o.mint<>m.mint AND o.created_at IS NOT NULL AND o.created_at <= m.created_at AND o.created_at > m.created_at - interval '7 days') AS criador_7d,
  (SELECT count(*) FROM meme_proposals p WHERE p.mint=m.mint) AS propostas,
  (SELECT count(*) FROM meme_features_1m f WHERE f.mint=m.mint AND f.end_time >= timestamptz '2026-09-16 19:00-03') AS n1m,
  (SELECT string_agg(DISTINCT coalesce(f.creator_net_seller::text, f.creator_net_seller_reason), ',') FROM meme_features_15s f WHERE f.mint=m.mint) AS cns_15s,
  (SELECT string_agg(DISTINCT coalesce(f.creator_sold::text, f.creator_sold_reason), ',') FROM meme_features_1m f WHERE f.mint=m.mint AND f.end_time >= timestamptz '2026-09-16 19:00-03') AS creator_sold_1m,
  (SELECT count(*) FROM meme_trades tr WHERE tr.mint=m.mint AND tr.trader=m.creator AND tr.side='sell' AND tr.block_time >= timestamptz '2026-09-16 19:00-03') AS cr_sells_fita
FROM m ORDER BY m.created_at;
-- LINK e QAUNTITY agora (1 m ate agora + ultima foto da cadeia)
SELECT 'link_1m' AS q, to_char(f.end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS brt, f.age_minutes, round(f.curve_progress_pct*100,1) AS prog, coalesce(f.progress_reason,'-') AS prog_reason, round(f.mcap_sol,2) AS mcap_sol, f.holders, f.unique_buyers AS compr, f.buys_1m, f.sells_1m, round(f.net_sol_flow_1m,2) AS fluxo, round(f.top10_share*100,1) AS top10, f.creator_sold, f.creator_net_seller AS cns, f.snipers, round(f.dev_share*100,2) AS dev
FROM meme_features_1m f WHERE f.mint='4TcftzQvXTwSEfsuWL75LLNQvdennvRsjmCh3VS5pump' AND f.end_time >= timestamptz '2026-09-16 21:40-03' ORDER BY f.end_time;
SELECT 'link_cadeia' AS q, to_char(c.observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS brt, round(c.real_sol_reserves,3) AS rsol, round(c.virtual_sol_reserves - c.real_sol_reserves,1) AS inv, c.complete, c.source
FROM meme_curve_snapshots c WHERE c.mint='4TcftzQvXTwSEfsuWL75LLNQvdennvRsjmCh3VS5pump' AND c.observed_at >= timestamptz '2026-09-16 21:55-03' ORDER BY c.observed_at DESC LIMIT 5;
SELECT 'qauntity_1m' AS q, to_char(f.end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS brt, f.age_minutes, round(f.curve_progress_pct*100,1) AS prog, round(f.mcap_sol,2) AS mcap_sol, f.holders, f.unique_buyers AS compr, round(f.net_sol_flow_1m,2) AS fluxo, round(f.top10_share*100,1) AS top10, f.creator_sold
FROM meme_features_1m f WHERE f.mint='GFakEBdgdKDJhsCKauSkKVjHYPqHDBEY7SgJZEJDpump' AND f.end_time >= timestamptz '2026-09-16 21:15-03' ORDER BY f.end_time DESC LIMIT 4;
SELECT 'symbol_link_24h' AS q, count(*) FROM meme_tokens WHERE symbol='LINK' AND created_at >= timestamptz '2026-09-15 21:44-03' AND created_at < timestamptz '2026-09-16 21:44:54-03';
```
