---
tags: [meme, pumpfun, knowledge, fita, dados, cobertura, porta, m4]
data: 2026-09-16
janela_medida: 15/09 00:00–23:59 BRT (dia inteiro) e 16/09 00:00–17:49 BRT (parcial — a série acaba no relógio da medição)
medido_em: 2026-09-16 18:0x–18:2x BRT
fonte: banco da VPS (meme_trades, meme_curve_snapshots, meme_features_1m, meme_features_15s, meme_board_observations, meme_tokens) — só SELECT
sql: infra/scripts/sql/research/2026-09-16-r34-q0{1,2,3,4,5,6,7}-*.sql
owner: astra/quant
status: vivo
confianca: alta para a cobertura por board e para a origem dos números da porta (contagens diretas); média para as razões cadeia/fita (a cadeia é ela própria um piso, §2)
updated: 2026-09-16
---

# KB-0116 — a fita vê quanto da negociação real? cobertura por fonte, hora e idade

> **A pergunta.** A [[11-KNOWLEDGE/KB-0115-volta-ao-piso-e-real-ou-artefato|KB-0115]] mediu que
> `meme_trades` explica **5 %** do SOL que sai da curva e que só 16 % das quedas têm qualquer
> negócio na fita, e concluiu "a fita está quebrada". Esta KB pergunta o passo seguinte: **quanto da
> negociação real a fita vê, por fonte, por hora e por idade da moeda — e o que isso invalida?**
>
> **A virada.** A resposta muda a pergunta: **a porta quase não lê `meme_trades`.** 96 % das linhas
> de 15 s com número de fita vêm do **lote** `activity_1m` (agregado da própria pump.fun), não da
> nossa fita — e o lote **bate com a cadeia** (correlação 0,835, razão mediana 1,00), enquanto as
> linhas que vêm de `meme_trades` têm **razão mediana 0,00** contra a cadeia. O problema não é "a
> fita vê pouco": é que **quando a fita fala, ela cala o lote, e o zero dela é falso**.
>
> **Unidades:** SOL; `curve_progress_pct` é fração (0–1); hora sempre **BRT**.

## 1. Conclusão em quatro linhas

1. **A fita serve para nomear carteiras, e só.** `meme_trades` é a única fonte que diz *quem*
   negociou — `creator_sold`/`creator_net_seller`, maior comprador (E2B), carteiras repetidas. Para
   *quanto* e *quantos* ela é pior que o lote que já temos: nos minutos em que o fold usou a fita, a
   mediana de `net_sol_flow_1m / Δ real_sol` é **0,00** e o sinal só concorda em **34,9 %** (contra
   1,00 e 85,7 % do `activity_1m`, n = 8 508 pares minuto-moeda).
2. **A cobertura da fita é o board, não a demanda.** No dia 15/09: **66,0 %** das moedas do board
   `graduating` têm fita, **19,5 %** de `movers`, **4,6 %** de `new` — exatamente a ordem de
   prioridade do orçamento de 16 chamadas/60 s (`trades.py`). Selecionar por `unique_buyers_60s` da
   fita é, em boa parte, selecionar por "a pump.fun já estava mostrando esta moeda".
3. **A fita não é amostra rala de tudo: é censo estreito de pouco.** Por dia ela grava ~**90 %** do
   SOL que a cadeia mostra (177,9 mil contra 197,1 mil SOL em 15/09), mas concentrado em **~6 %** das
   moedas jovens; nas moedas que ela cobre com < 5 min de vida ela registra **mais** SOL que o Δ de
   reservas (mediana 247 %), porque conta as duas pernas do vaivém que o Δ de 15 s anula.
4. **O que muda.** (a) o fold deve **preferir `activity_1m`** e usar `meme_trades` só para as colunas
   de carteira; (b) `net_sol_flow`/`buys`/`sells`/`unique_buyers` vindos de `swap_api_trades` sem
   página no minuto precisam ser **NULL com motivo** (`tape_partial`), nunca zero; (c) os estudos
   KB-0099/0102/0108/0112/0114 **não estão invalidados por isto** — eles leram majoritariamente o
   lote (96 % das linhas) —, mas as coortes deles herdam o viés de board do §4.

## 2. O método e o seu piso (q01, q02)

**Cadeia** = soma de `|Δ real_sol_reserves|` entre fotos consecutivas do mesmo mint em
`meme_curve_snapshots`, só com intervalo ≤ 60 s. **É um piso**: o que compra e vende dentro da mesma
janela de ~12 s se anula, e a série só fotografa a moeda **enquanto o radar a rastreia**. **Fita** =
`meme_trades` (bruto, `program = 'pump'`). A razão fita/cadeia é, portanto, um **teto** da cobertura.

**Fonte de trade (15–16/09):** a fita tem **uma** fonte, `swap_api` — 677 128 linhas em `pump`
(curva) e 28 805 em `pump_amm` (pool). Não há `trenches_ws` nem decodificador on-chain escrevendo
`meme_trades`; o `trenches_ws` entrega *boards* e `holders`, nunca negócios (`repo_tape.py` só grava
`source = 'swap_api'`).

## 3. Por hora BRT — 15/09 (q01)

| hora | cadeia (SOL) | fita `pump` | fita `pump_amm` | razão | moedas c/ foto | moedas c/ fita | % moedas |
|---|---|---|---|---|---|---|---|
| 00 | 5 001 | 6 925 | 410 | 138 % | 1 148 | 110 | 9,6 % |
| 06 | 4 493 | 5 482 | 934 | 122 % | 1 001 | 127 | 12,7 % |
| 12 | 9 911 | 7 977 | 66 | 81 % | 1 713 | 95 | 5,5 % |
| 16 | 10 993 | 6 949 | 291 | 63 % | 1 653 | 92 | 5,6 % |
| **19** | **16 034** | **6 671** | 320 | **42 %** | 2 308 | 123 | 5,3 % |
| **20** | **9 494** | **2 639** | 0 | **28 %** | 1 644 | 87 | 5,3 % |
| 22 | 18 025 | 19 033 | 1 418 | 106 % | 2 508 | 170 | 6,8 % |
| **dia** | **197 088** | **177 895** | ~9 973 | **90 %** | — | — | **5,3–13,3 %** |

Duas leituras, e a segunda é a que importa: **em SOL** a fita quase empata com a cadeia; **em
moedas** ela vê 5–13 %. Nas horas de pico da mesa (**12 h–20 h BRT**) a razão cai para 42–88 % e a
cobertura de moedas para ~**5,5 %** — e o orçamento de 16 chamadas/60 s é fixo enquanto o número de
moedas por hora dobra. A fita **piora exatamente quando há mais o que ver**.

## 4. Por idade e por board (q02, q04)

**Idade** (moeda a moeda, mesmo balde; 15/09 | 16/09 parcial):

| idade | moedas c/ cadeia | moedas c/ fita | % com fita | cadeia SOL | fita SOL | razão (só cobertas) | mediana |
|---|---|---|---|---|---|---|---|
| 0–60 s | 22 209 \| 15 179 | 1 341 \| 956 | **6,0 % \| 6,3 %** | 92 736 | 39 344 | 226 % | 247 % |
| 60–300 s | 16 877 \| 11 499 | 851 \| 624 | **5,0 % \| 5,4 %** | 94 366 | 41 794 | 124 % | 102 % |
| 300–1800 s | 2 054 \| 1 749 | 544 \| 389 | 26,5 % \| 22,2 % | 9 504 | 56 531 | 727 % | 607 % |
| > 1800 s | 58 \| 46 | 211 \| 121 | — | 480 | 40 226 | — | — |

Os dois últimos baldes têm **mais moedas na fita que na cadeia**: depois de ~5 min o *rastreamento*
para (a foto de curva acaba) e a fita continua só para as apostas abertas. **Nenhum dos dois
instrumentos cobre a moeda madura** — a cadeia menos ainda. Nos baldes jovens (o território da porta)
a fita vê 5–6 % das moedas e, nelas, conta 1,0–2,5× o Δ líquido de 15 s.

**Board** (15/09, uma linha por par board-moeda):

| board | moedas | c/ foto de curva | c/ fita | **% com fita** | fita SOL | negócios |
|---|---|---|---|---|---|---|
| `new` | 37 482 | 29 927 | 1 710 | **4,6 %** | 166 650 | 355 916 |
| `movers` | 5 285 | 3 605 | 1 031 | **19,5 %** | 167 633 | 350 141 |
| `graduating` | 1 530 | 1 197 | 1 010 | **66,0 %** | 170 111 | 357 440 |
| `graduated` | 855 | 717 | 264 | 30,9 % | 55 030 | 95 934 |

Os três boards trazem **o mesmo SOL** (≈ 167 mil cada) com populações de 1 530 a 37 482 moedas: a
fita é um censo do `graduating` e um sorteio no `new`. **A cobertura é a prioridade do puxador.**

## 5. Fluxo minuto a minuto: a fita erra, o lote acerta (q03, q05, q06)

Casando **só as moedas que a fita cobre**, minuto a minuto, contra o Δ líquido de `real_sol_reserves`
(15/09, 7 807 pares, 1 008 moedas): sinal igual **75,9 %**, dentro de ±20 % **28,0 %**, razão mediana
**0,70** (p25 **0,01**, p75 1,01), correlação **0,52**, bruto/líquido mediano **1,74**, e **7,6 %**
dos minutos batem na página de 100 negócios (truncagem). Num quarto dos minutos cobertos a fita vê
**1 %** do que se moveu.

**De onde vem o número que a porta lê** (15/09):

| série | `activity_1m` (lote) | `swap_api_trades` (fita) | sem número |
|---|---|---|---|
| `meme_features_1m` | 171 569 linhas / 31 403 moedas (**82,5 %**) | 20 892 / 1 810 (10,0 %) | 15 929 (`not_polled`, `no_trade_feed`, `unsupported_quote`) |
| `meme_features_15s` | 380 190 / 29 053 (**96,1 %**) | 15 235 / 1 392 (**3,9 %**) | 101 935 |

E o teste direto contra a cadeia (15/09, 18–24 h UTC, minuto a minuto):

| `tape_source` | pares | moedas | sinal igual | razão de fluxo (mediana) | correlação | razão de volume | `unique_buyers` mediano |
|---|---|---|---|---|---|---|---|
| **`activity_1m`** | 6 688 | 4 165 | **85,7 %** | **1,00** | **0,835** | 1,11 | 1,0 |
| `swap_api_trades` | 1 820 | 287 | **34,9 %** | **0,00** | 0,383 | 0,00 | **0,0** |

O lote da pump.fun **descreve a cadeia**. A nossa fita, nos minutos em que o fold a usou, escreve
**zero** enquanto a curva se movia — porque o puxador traz uma página por minuto e o fold atribui o
minuto inteiro a ela. E a precedência hoje é a errada: `activity.py` só preenche "quando a fita por
mint não cobriu", ou seja, **a fonte pior tem prioridade sobre a melhor**.

## 6. O que na porta e no executor depende da fita (q05, q06, `rules.py`)

| critério | fonte hoje | substituto pela cadeia | latência do substituto | veredito |
|---|---|---|---|---|
| `unique_buyers` / `unique_buyers_60s` | fita **e** lote (96 % lote) | **não há** pela cadeia (Δ de reserva não conta pessoas); `holders`/`holders_rising` do `trenches_ws` é o proxy | foto de curva: **cadência mediana 12 s, p90 18 s**; idade da foto na linha de 15 s: **13 s** | manter, **mas lendo o lote**; é o único número que só a contagem de agentes dá |
| `net_sol_flow_1m` / `_60s` | fita e lote | **Δ `real_sol_reserves`** (líquido, exato) | 12 s / p90 18 s | **substituir**: a cadeia é melhor e já está na linha (`mcap_delta_60s`) |
| `buys_1m` / `sells_1m` / `max_sells_to_buys` | fita e lote | não há (a cadeia não separa pernas); o lote conta as duas | lote: janela de 1 min, lida ~3 s antes do fechamento | manter pelo **lote**; pela fita é ruído |
| `curve_volume_1m_sol` → **`participation_pct`** (executor) | fita e lote | soma de `\|Δ real_sol\|` do minuto (piso, anula vaivém) | 12 s | **risco vivo**: volume subestimado infla a participação (recusa) e o bruto a deflaciona (superdimensiona) |
| `creator_sold` / `creator_net_seller` | **só fita** (0 linhas pelo lote) | **ATA do criador** por RPC (`creator_watch.py`) ou Δ de `dev_share` do leitor de holders | RPC direto: 1 chamada (~0,3–1 s); `dev_share`: cadência do board (~60 s) | **só a fita** — e por isso ela deve existir, mas hoje cobre 5,8 % das moedas |
| maior comprador (`e2b_top_buyer_share`) | **só fita** | nenhum pela cadeia; o leitor de holders dá top-10, não o maior *comprador* | — | **só a fita** |
| `holders`, `top10_share`, `snipers`, `dev_share` | `trenches_ws` / indexador | não dependem da fita | ~60 s (board) | sem mudança |
| `progress` / `mcap_delta_60s` / Mayhem | curva | já é cadeia | 12 s | sem mudança |

## 7. O que corrigir

1. **Inverter a precedência** em `features_tape`/`activity.py`: `activity_1m` primeiro para
   `net_sol_flow`, `buys`/`sells`, `unique_buyers` e `curve_volume_1m_sol`; `swap_api_trades` só
   quando o lote faltar — e sempre `meme_trades` para `creator_*` e maior comprador.
2. **Zero da fita é mentira**: quando o puxador não trouxe página do minuto, escrever `tape_reason =
   'tape_partial'` e **NULL**, não 0 (a regra "desconhecido recusa" já existe na porta e resolve).
3. **Trocar `net_sol_flow` por Δ `real_sol_reserves`** como critério de fluxo
   (`require_positive_flow`), e refazer `participation_pct` sobre a soma de `|Δ|` do minuto.
4. **Declarar o viés de board** em todo estudo que selecionar por fita: `graduating` 66 % vs `new`
   4,6 % não é demanda, é cobertura. As coortes de KB-0099/0102/0108/0112/0114 precisam do controle
   por board antes de qualquer leitura causal.

## Ligações

[[11-KNOWLEDGE/KB-0115-volta-ao-piso-e-real-ou-artefato|KB-0115 (a pergunta que gerou esta)]] ·
[[11-KNOWLEDGE/KB-0114-compradores-unicos-o-piso-e-o-r|KB-0114]] ·
[[11-KNOWLEDGE/KB-0112-volume-do-minuto-participacao-e-r|KB-0112]] ·
[[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]] ·
[[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos|KB-0098]] ·
[[03-TRADING/Meme/README|Meme (catálogo)]] ·
`infra/scripts/sql/research/2026-09-16-r34-q0{1,2,3,4,5,6,7}-*.sql`
