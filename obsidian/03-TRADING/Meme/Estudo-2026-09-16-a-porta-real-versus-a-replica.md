---
tags: [meme, pumpfun, porta, lab, estudo, r27, m4]
data: 2026-09-16
janela_medida: 16:17–17:02 BRT (mesa) · últimas 3 h em §3 (17:19–20:19 BRT do relógio da VPS em UTC−3)
medido_em: 2026-09-16 17:1x–17:2x BRT (20:1x UTC, `date -u` conferido na VPS)
fonte: banco da VPS (meme_features_15s, meme_curve_snapshots, meme_tokens, meme_lab_ticks, meme_proposals, meme_rule_sets, meme_features_1m) + código (`rules.py`, `rules_criteria.py`, `proposals.py`, `lab_fast.py`, `lab_repo_fast.py`, `pedigree.py`)
sql: infra/scripts/sql/research/2026-09-16-r27-q01..q08
owner: astra/quant
status: vivo
confianca: alta em (1) e (2) — comparação nome a nome entre a réplica e o contador gravado por tique; média em (3) (3 h, n pequeno)
updated: 2026-09-16
---

# R27 — a porta real versus a réplica: por que Kintsugi não virou proposta

> **Achado central.** Não foi corrida nem bug de gravação: **a porta que rodava às 16:20 não era a
> porta que o R23 replicou às 16:50**. Até **16:25:0x BRT** o `operator/5` em vigor tinha **teto**
> de snipers e **nenhum piso**; a partir daí passou a ter **piso 21 / teto 1000**. Kintsugi tinha
> **64 snipers**: a porta de 16:20 a recusou por `snipers_above_max` — exatamente o critério que
> cinco minutos depois passou a **exigir** o que ela tinha.

## 0. Como eu sei (o método, não a narrativa)

O worker **não loga nada por mint** (só linhas HTTP; `grep BiCp7N` nos logs de 3 h dá 4 linhas, todas
`HTTP Request`). A única trilha por decisão é o **contador por tique** em `meme_lab_ticks.refusals`
(o mesmo dicionário do `hb:meme:radar` / `lab_gate_refusals`), agregado por nome de recusa e por
conjunto. Então reconstruí a porta REAL em SQL, foto a foto da série de 15 s, na **ordem do código**
(`evaluate_gate` → `already_open` → pedigree/identidade/evento → `evaluate_entry`: `size_not_positive`
→ `curve_complete` → `already_migrated` → `mayhem_*` → `age_*` → `progress_*` → `creator_*` →
`participation` / `curve_volume_1m_*` → `line_*` → `hype` / `dev_share` / `snipers` / `top10` →
`flow` / `buyers` / `sells_ratio` / `holders` → `no_snapshot_for_quote`) e **comparei o vetor de nomes**
com o contador gravado (q06). O alinhamento foto↔tique (q05) é 1:1 e sem buraco: cada instante de 15 s
é julgado **um tique depois** (atraso de commit de ~3 s); em 3 h foram **524 tiques, 0 buracos > 45 s**
(`lab_fast_backlog_s`), gap médio **20,6 s**, máximo **42,2 s**. Heartbeat no fim da medição:
`lab_fast_rows_evaluated = 780` (último tique), `lab_fast_proposals_total = 18`, `lab_bets_open = 0`.

## 1. As três moedas, foto a foto, na porta REAL

### 1a. Kintsugi `BiCp7Nhz…` (criada 16:19:25, criador `ArHqwc…`)

| foto (BRT) | idade | prog | holders | compr | c/v | fluxo | vol 60 s | snipers | dev | recusas da porta real (ordem do código) |
|---|---|---|---|---|---|---|---|---|---|---|
| 16:19:27 | 2 s | — | 0 | — | — | — | — | 4 | 0 | `age_below_min`, `progress_unknown`, `curve_volume_1m_unknown`, `snipers_below_min`, `flow_no_trade_feed`, `buyers_unknown`, `sells_ratio_unknown`, `holders_below_min`, `no_snapshot_for_quote` |
| 16:19:44 | 18 s | 37,98 % | 51 | — | — | — | — | 64 | 0 | `age_below_min`, `curve_volume_1m_unknown`, `flow_not_polled`, `buyers_unknown`, `sells_ratio_unknown` |
| **16:20:00** | 34 s | 36,17 % | 79 | 108 | 117/47 | 11,12 | 36,33 | **64** | 0 | **nenhuma** pelos params de hoje → **`snipers_above_max`** pelos params de 16:20 |
| **16:20:16** | 51 s | 36,70 % | 108 | 108 | 117/47 | 11,12 | 36,33 | 64 | 0 | idem (essa foto veio do `pumpfun_rest`, sem o bit de Mayhem) |
| **16:20:33** | 67 s | 41,72 % | 123 | 108 | 117/47 | 11,12 | 36,33 | 64 | 0 | idem |
| **16:20:49** | 83 s | 42,22 % | 162 | 108 | 117/47 | 11,12 | 36,33 | 64 | 0 | idem |
| 16:21:05–16:23:32 | 100–247 s | 48,9 → 61,3 % | 170 → 340 | — | — | — | — | 64 | 0 | `curve_volume_1m_unknown`, `buyers_unknown`, `sells_ratio_unknown` (fita `not_polled`) e, de 16:21:38 em diante, `progress_above_max` |

**A janela útil da Kintsugi durou 4 fotos = 64 s** (16:20:00–16:20:49). Pedigree limpo em tudo:
criador 1 h = **0**, símbolo 24 h = **0**, `creator_prior_dump_count` 7 d = **0** (o criador não tem
nenhuma outra moeda em 7 d). Não-Mayhem **conhecido** (`meme_tokens.mayhem_enabled = false`, e a foto
de curva de `solana_rpc` das 16:19:48 já trazia o bit). Fita presente e coberta nas 4 fotos
(108 compradores únicos). Retrato para cotação existia (`meme_curve_snapshots` com reservas > 0) —
`no_snapshot_for_quote` **não apareceu uma única vez** em toda a mesa.

**O que o contador gravado diz do tique que julgou 16:20:00 (tique 16:20:03)** — comparação nome a
nome com a réplica do código (q06): **os 24 nomes batem exatamente**, menos dois:

| nome | réplica do código (params de hoje) | gravado no tique 16:20:03 |
|---|---|---|
| `snipers_below_min` (piso 21) | **80** | **0** |
| `snipers_above_max` | **0** | **5** |

As 5 recusas `snipers_above_max` são exatamente as 5 fotos daquele instante com **snipers ≥ 28**
(64, 56, 45, 29, 28; o valor seguinte para baixo é 20) — **a Kintsugi é uma delas**. Ou seja: às 16:20
o `operator/5` em vigor tinha **teto de snipers entre 20 e 27, e nenhum piso**.

**Quando virou:** q07 mostra o sinal trocando entre dois tiques consecutivos — **16:24:54**
(`snipers_above_max` 15, `snipers_below_min` 0) → **16:25:13** (`snipers_above_max` **0**,
`snipers_below_min` **95**). `load_active_rule_sets` roda **a cada tique** e o worker não reiniciou
(contêiner de pé desde 16:17:42 BRT, imagem `hunter-api:7a5bacc`): a linha de params do `operator/5`
foi **reescrita no banco por volta das 16:25**, não às 16:17. A mesa passou 8 minutos com a porta antiga.

### 1b. Grammuh `FLz2Hv…` (16:32:27) e HANNAH `DgFP1A…` (16:35:25)

| moeda | fotos limpas no `EntryGate` | por que não virou proposta |
|---|---|---|
| **Grammuh** | 16:33:04 (37 s, 26,0 %, 23 holders, 37 compr, 38/15, 33,51 SOL, 84 snipers) e 16:33:21 (54 s, 48,7 %) | **`creator_repeat_dumper`** — criador `6tyjMa…` com **96 moedas em 7 d** e **2 delas com `creator_sold = true`** antes desta. De 16:33:37 em diante a fita zera (`no_buys`, `flow_not_positive`, `buyers_below_min`) e às 16:36 o progresso cai para 1,6 % (`progress_below_min`). |
| **HANNAH** | 16:38:51 (206 s, 39,1 %, 52 holders, 13 compr, 13/4, 4,70 SOL, 46 snipers) — **uma só foto** | **`creator_repeat_dumper`** — criador `JDQKDr…` com **92 moedas em 7 d** e **7 dumps**. Nas fotos vizinhas: `progress_above_max` (76–89 %), `sells_ratio_above_max` (60/38), `flow_not_positive` (−16 SOL) e `curve_volume_1m_zero`. |

As duas já estavam **depois** da virada de 16:25 (piso 21 valendo, e as duas tinham snipers acima dele)
— e caem numa exclusão de pedigree que a réplica do R23 **não aplica**.

## 2. A réplica do R23 (`2026-09-16-r23-q04-*.sql`) versus o código, critério a critério

| # | o que o código faz | o que a réplica faz | efeito medido (3 h) |
|---|---|---|---|
| 1 | `pedigree_repeat_dumper` (ligado em `operator/5`): **`creator_prior_dump_count` ≥ 1 em 7 dias** → `creator_repeat_dumper` | **não existe na réplica** | **18 das 33** moedas que só a réplica passa |
| 2 | pedigree 1 h/24 h com `PEDIGREE_V1` (`max_creator_prior_mints_1h = 1`, `max_symbol_dup_24h = 2`) e **desconhecido recusa por nome** (`creator_unknown`/`symbol_unknown`) | mesmas janelas, mas exige `creator IS NOT NULL` em vez de recusar por nome | **10 das 33** |
| 3 | `require_creator_not_net_seller` **ligado**, com a exceção declarada `creator_unknown_allowed_if_dev_measured` (um `dev_share` medido ≤ 0,10 avaliza o desconhecido) → `creator_is_net_seller` / `creator_net_seller_unknown` | **ignora `creator_net_seller`** | **7 das 33** |
| 4 | Mayhem: `meme_tokens.mayhem_enabled`, senão o bit da **foto de curva**; **desconhecido recusa** (`mayhem_unknown`) | `t.mayhem_mode IS NULL` — **outra coluna**, e lê nulo como "não-Mayhem" | 0 nesta janela, mas é falha-aberta |
| 5 | fluxo: `net_sol_flow_1m > 0` **ou**, sem fita, `mcap_delta_60s > 0` | exige `tape_reason IS NULL` **e** `net_sol_flow_60s > 0` — mais **apertada** que o código | a réplica **perde** moedas sem fita que o código aceitaria |
| 6 | `snipers` **21–1000** a partir de 16:25; **antes disso, teto ~20 sem piso** | piso 21 na hora inteira | **a inversão de §1** |
| 7 | cotação: exige `meme_curve_snapshots` com reservas > 0, senão `no_snapshot_for_quote` | não olha | 0 casos |
| 8 | dedupe: `already_open` (proposta `proposed`/`approved` **ou** aposta aberta do mesmo conjunto) + índice único `(rule_set_id, mint, features_end_time)`; o TTL de 180 s do `operator/5` expira a proposta e devolve o mint | não olha | 10 recusas `already_open` em 8 tiques na mesa |
| 9 | julga **toda** foto de 15 s da janela | `DISTINCT ON (mint)` — só a **primeira** foto que passa | conta moeda, não oportunidade |
| 10 | idade = `as_of − created_at`; progresso = fração × 100 contra 5–50; participação = `100 × 0,05 / vol ≤ 1` | `age_s`, `curve_progress_pct BETWEEN 0.05 AND 0.50`, `vol ≥ 5` | equivalentes |

Fora da réplica e **sem efeito aqui** porque `operator/5` não os pede: `max_top10_share`,
`min_hype_score`, `require_twitter`, `require_event`, `pedigree_e2b`, critérios de linha.
E `max_open_positions = 2` **não é critério de proposta**: mora no fill (`paper_fill`), depois.

## 3. Vazão: porta real × réplica (últimas 3 h, q08)

| porta | moedas distintas | por hora |
|---|---|---|
| réplica do R23 (q04) | **43** | **14,3** |
| porta real, só o `EntryGate` | 35 | 11,7 |
| + pedigree 1 h/24 h | 14 | 4,7 |
| + `creator_repeat_dumper` (7 d) | **10** | **3,3** |
| *propostas reais do conjunto `operator` no mesmo período* | *8 moedas* | *2,7* |

**A réplica exagera a vazão em 4,3×.** A causa principal é o **repeat dumper de 7 dias** (18 das 33
moedas que só ela passa), seguido do pedigree de 1 h/24 h (10) e do `creator_net_seller` (7);
`mayhem_unknown` e `no_snapshot_for_quote` não custaram nada nesta janela. A porta real entrega
**3,3 moedas/h** e o banco mostra **2,7 moedas/h** virando proposta — o resto é `already_open` e a
virada de params das 16:25.

## 4. Conclusão (4 linhas)

1. **Não foi bug nem corrida.** A via rápida cobriu todas as fotos (524 tiques, 0 buracos > 45 s) e o
   contador por tique bate nome a nome com o código: cada foto foi julgada uma vez, e só uma vez.
2. **Kintsugi foi recusada por `snipers_above_max`**: às 16:20 o `operator/5` em vigor tinha teto de
   snipers (~20) e nenhum piso; a calibragem "piso 21" só entrou em vigor às **16:25:0x** — o R23
   replicou a porta **de depois** sobre a hora **de antes**.
3. **Grammuh e HANNAH foram recusadas por `creator_repeat_dumper`** (2 e 7 dumps do criador em 7 d):
   critério real que a réplica SQL nunca aplicou — aqui a porta real está certa e a réplica, errada.
4. **O que vale rever (pré-registrado, nunca ligado à mão):** a janela útil da Kintsugi durou **64 s /
   4 fotos**, e uma troca de params no meio dela custou a única moeda boa da hora. Duas emendas para
   o próximo EXP-M*: (a) `meme_rule_sets` **imutável** — nova versão em vez de `UPDATE` in place (hoje
   não dá para recuperar o teto antigo: a linha foi sobrescrita e a tabela não tem histórico); e
   (b) **registrar a recusa por mint** (uma linha por foto que chega ao último critério), porque hoje
   só existe o agregado por tique.

## Ligações

[[03-TRADING/Meme/Candidatas/2026-09-16-17h02-brt|Candidatas R23 (a discrepância)]] ·
[[11-KNOWLEDGE/KB-0109-top10-e-bundle-onde-o-teto-deveria-estar|KB-0109]] ·
[[03-TRADING/Meme/README|Meme (catálogo)]] ·
`infra/scripts/sql/research/2026-09-16-r27-q01..q08`
