---
tags: [knowledge, nota, execucao, microestrutura, custos, spread]
tema: Execução e microestrutura do preenchimento
fonte: Medição própria sobre `market_snapshots` (24 h, instância local) + `services/market-worker/hunter_market_worker/sampling.py` + "Explainable Patterns in Cryptocurrency Microstructure" (arXiv 2602.00776)
fonte_url: https://arxiv.org/html/2602.00776v1
lido_em: 2026-09-06
evidencia: replicado (53 mil observações, SQL colado) + preprint lido sem números de spread
hipotese_testavel: sim
astra: concorda após correções (recusou a primeira versão)
---

# O spread assumido (2 bps) contra o spread medido

## O que afirma

`spread_bps = 2` é uma constante única para 200 mercados. Medido nas últimas 24 horas de
`market_snapshots`, o spread **mediano** das observações é **2,30 bps** — a hipótese acerta a
mediana — mas **54,64% das observações ficam acima dela**, o p95 é **7,97 bps** e o p99 **11,66
bps**. Há diferença clara **entre mercados**: do decil mais líquido (0,97 bps) ao menos líquido
(4,93 bps) há um fator de cinco. A tendência é clara mas **não é monotônica** — os decis 2, 3 e 4
sobem (3,245 → 3,265 → 3,780) e o 6 sobe sobre o 5 (2,390 → 3,390). E eu **não** decompus variância
entre e dentro de mercado, então não afirmo que a dispersão seja "quase toda" entre eles: o p90
**dentro** de cada mercado é sempre maior que a mediana do decil, o que já mostra que há alargamento
intramercado a explicar.

A conclusão prática é menos dramática do que parece, e é preciso dizê-la com honestidade: no modelo
do Lab o spread entra **pela metade** (`spread_bps/2` por lado), então errar 2 bps para 3 bps de
spread total custa **1 bps na ida e volta** sobre um custo total assumido de 20 bps. O spread **não
é** onde a hipótese de custo está frágil. Os 5 bps de `slippage_bps` por lado — 10 bps de 20, metade
do custo total — é que carregam o peso, e são exatamente os que ninguém mediu.

## Onde foi mostrado

Instância local, `market_snapshots` de 2026-09-05T16:29Z a 2026-09-06T16:44Z, 234 mercados, **toda a
tabela** (a instância local só tem essa janela — as consultas abaixo não têm predicado de tempo, e
rodá-las amanhã descreveria outra população; quem repetir precisa acrescentar
`WHERE ts >= '2026-09-05T16:29Z' AND ts <= '2026-09-06T16:44Z'`). Quantis por
`percentile_cont` (interpolado). `spread_pct` é gravado como **fração** a partir de `bid`/`ask` do
hot state (`sampling.py:72-80`), `NUMERIC(9,6)` — resolução de 1e-6, ou seja **0,01 bps**,
suficiente.

**Cobertura, antes das tabelas.** A cadência do snapshot é de 1 minuto
(`market_snapshot_interval_s = 60`), mas só existem **535 minutos distintos** na janela de ~1.455, e
**apenas 8 dos 200 sinais** têm linha de `market_snapshots` no seu próprio minuto (1 de 90 do
momentum, 7 de 110 do volume). Nenhum número desta nota descreve "o spread no instante da decisão".

```sql
SELECT count(DISTINCT ts) AS instantes, min(ts), max(ts) FROM market_snapshots;
--  instantes |          min           |          max
-- -----------+------------------------+------------------------
--        535 | 2026-09-05 16:29:00+00 | 2026-09-06 16:44:00+00

WITH sig AS (
  SELECT a.id, a.market_id, s2.name AS estrategia, date_trunc('minute', a.emitted_at) AS minuto
  FROM agent_signals a
  JOIN strategy_versions sv ON sv.id = a.strategy_version_id
  JOIN strategies s2 ON s2.id = sv.strategy_id
)
SELECT sig.estrategia, count(*) AS sinais, count(ms.spread_pct) AS com_spread
FROM sig LEFT JOIN market_snapshots ms
  ON ms.market_id = sig.market_id AND ms.ts = sig.minuto
GROUP BY sig.estrategia ORDER BY sig.estrategia;
--    estrategia   | sinais | com_spread
-- ----------------+--------+------------
--  Momentum       |     90 |          1
--  Volume Anomaly |    110 |          7
```

```sql
SELECT count(*) AS observacoes,
       round(100.0*count(*) FILTER (WHERE spread_pct*10000 > 2)/count(*),2)  AS pct_acima_2bps,
       round(100.0*count(*) FILTER (WHERE spread_pct*10000 > 4)/count(*),2)  AS pct_acima_4bps,
       round(100.0*count(*) FILTER (WHERE spread_pct*10000 > 10)/count(*),2) AS pct_acima_10bps,
       round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY spread_pct*10000)::numeric,3) AS mediana_obs_bps,
       round(percentile_cont(0.95) WITHIN GROUP (ORDER BY spread_pct*10000)::numeric,3) AS p95_obs_bps,
       round(percentile_cont(0.99) WITHIN GROUP (ORDER BY spread_pct*10000)::numeric,3) AS p99_obs_bps
FROM market_snapshots WHERE spread_pct IS NOT NULL;
```

```
 observacoes | pct_acima_2bps | pct_acima_4bps | pct_acima_10bps | mediana_obs_bps | p95_obs_bps | p99_obs_bps
-------------+----------------+----------------+-----------------+-----------------+-------------+-------------
       53128 |          54.64 |          28.72 |            2.14 |           2.300 |       7.970 |      11.657
```

Por decil de liquidez (`markets.volume_24h_usd`, que vem do refresh REST do universo — **não** do
snapshot, ver [[KB-0044-o-que-morre-em-dez-segundos]]):

```sql
WITH per_market AS (
  SELECT s.market_id, m.volume_24h_usd AS qv, count(*) AS n,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY s.spread_pct)*10000 AS med_bps,
         percentile_cont(0.9) WITHIN GROUP (ORDER BY s.spread_pct)*10000 AS p90_bps
  FROM market_snapshots s JOIN markets m ON m.id = s.market_id
  WHERE s.spread_pct IS NOT NULL AND m.volume_24h_usd IS NOT NULL
  GROUP BY s.market_id, m.volume_24h_usd
), d AS (SELECT *, ntile(10) OVER (ORDER BY qv) AS decil FROM per_market)
SELECT decil, count(*) AS mercados, sum(n) AS obs,
       round((min(qv)/1e6)::numeric,1) AS qv_min_musd, round((max(qv)/1e6)::numeric,1) AS qv_max_musd,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY med_bps)::numeric,3) AS spread_med_bps,
       round(min(med_bps)::numeric,3) AS min_bps,
       round(max(med_bps)::numeric,3) AS max_bps,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY p90_bps)::numeric,3) AS p90_dentro_bps
FROM d GROUP BY decil ORDER BY decil;
```

```
 decil | mercados |  obs  | qv_min_musd | qv_max_musd | spread_med_bps | min_bps | max_bps | p90_dentro_bps
-------+----------+-------+-------------+-------------+----------------+---------+---------+----------------
     1 |       24 |  1704 |         1.2 |         3.8 |          4.930 |   0.410 |  12.350 |          6.902
     2 |       24 |  2689 |         3.9 |         5.3 |          3.245 |   0.470 |   8.620 |          4.638
     3 |       24 |  4169 |         5.3 |         6.7 |          3.265 |   0.790 |   7.260 |          5.120
     4 |       23 |  4035 |         6.8 |         9.3 |          3.780 |   0.020 |  11.400 |          5.496
     5 |       23 |  4723 |         9.6 |        14.5 |          2.390 |   0.020 |   8.030 |          4.710
     6 |       23 |  4726 |        14.6 |        19.9 |          3.390 |   0.590 |  11.320 |          5.950
     7 |       23 |  5346 |        20.7 |        33.9 |          2.600 |   0.300 |   8.150 |          4.370
     8 |       23 |  6051 |        34.6 |        62.9 |          1.990 |   0.180 |   9.630 |          3.450
     9 |       23 |  9211 |        64.5 |       175.3 |          1.700 |   0.210 |   4.550 |          2.710
    10 |       23 | 10289 |       180.0 |      6001.1 |          0.970 |   0.010 |   4.560 |          1.260
```

E, separando por quem sinalizou (mediana das medianas por mercado):

```
   grupo   | mercados | p25_bps | mediana_bps | p75_bps | max_bps
-----------+----------+---------+-------------+---------+---------
 com sinal |       94 |   1.240 |       2.250 |   3.938 |   8.180
 sem sinal |      139 |   1.713 |       3.490 |   5.228 |  12.350
```

**Os mercados que a estratégia escolheu são mais estreitos que o universo** — 2,25 contra 3,49 bps de
mediana das medianas. É uma associação, não uma causa: as duas estratégias exigem volume relativo e
volume anda com spread, o que torna a explicação plausível, mas eu não a testei. E o número descreve
os **mercados**, ao longo de 24 h; não descreve os **instantes** em que os sinais saíram, que é o que
faltaria para dizer alguma coisa sobre o custo pago.

O preprint de microestrutura (arXiv 2602.00776, perpétuos da Binance, 01/01/2022 a 12/10/2025, cinco
ativos nas posições 1, 20, 40, 60 e 100 de capitalização) foi lido para buscar o número transversal
de spread por capitalização. **Ele não publica esse número**: recomenda explicitamente medidas
relativas (spread sobre o mid) em vez de valores absolutos, e a única passagem numérica sobre tick é
a comparação de um par spot (tick 1e-4) com o perpétuo (1e-5). Registro isso porque a alternativa
seria citar um número que a fonte não tem.

## Como mediríamos aqui

Já medimos o spread **cotado ao longo do dia** — este é o ponto. O que **não** temos é o spread no
instante da decisão (a cobertura acima) nem o spread **pago**: um spread cotado na decisão não
determina o que se paga numa abertura 60 a 120 s depois, e muito menos na saída.

Nota de unidade, declarada e conhecida: existem **três** `spread_pct` na árvore com **duas**
unidades. `market_snapshots.spread_pct` (`sampling.py`) e `SpreadPct` do M2 (`features/micro.py`) são
**fração**; `NormalizedTicker.spread_pct` e `NormalizedOrderBook.spread_pct` (`domain/market.py:176,
240`) são **×100**. O próprio `micro.py` documenta a divergência e aponta a reconciliação para a
T1.1c. Nenhum número desta nota passa pelos dois caminhos.

## Hipótese testável no Lab

**`EXEC-B` — carimbo de spread na decisão, diagnóstico puro.** Persistir no envelope do sinal o
`spread_pct` lido do book **no instante da avaliação** (o `SpreadPct` do M2 já calcula; falta chegar
ao envelope, o mesmo defeito de proveniência do ranking de liquidez em
[[KB-0018-volume-relatado-e-o-denominador-que-usamos]] e do regime em
[[KB-0030-o-regime-nao-chega-ao-sinal]]). Com ele: distribuição do spread na decisão por estratégia,
por decil e por hora UTC; e a diferença entre o spread real e os 2 bps, convertida em bps de ida e
volta e em fração de 1 R efetivo.

**Alvo do diagnóstico, declarado antes — e com a aritmética certa, porque a primeira versão desta
nota errou aqui.** Um spread real `s` custa `(s − 2)/2` bps a mais **por perna**, logo `s − 2` bps a
mais na **ida e volta**. Então:

| Spread real | erro por perna | erro na ida e volta | sobre 20 bps de custo assumido |
|---|---|---|---|
| 2,3 bps (mediana medida) | 0,15 | **0,30** | 1,5% |
| 4 bps | 1,0 | **2,0** | 10% |
| 5,9 bps (p90 do decil 1) | 1,95 | **3,9** | 19,5% |
| 11,7 bps (p99 medido) | 4,85 | **9,7** | 48,5% |

Critério: se a mediana do spread na decisão ficar entre 1,5 e 3 bps **e** o p90 abaixo de 4, o erro
de ida e volta fica em 2 bps ou menos em 90% dos casos — e os 10% restantes continuam **sem cota**,
porque um p90 não limita a cauda. **Refutação:** p90 acima de 6 obriga a medir também **onde** o
alargamento acontece (mercado, hora UTC, regime) antes de qualquer conclusão; "é variável por
mercado" seria só uma das explicações possíveis, e não a que a tabela por decil demonstra.

**O que esta nota explicitamente NÃO propõe:** trocar 2 por 2,3 no `AssumedCosts`. Ajustar uma
constante para a mediana da amostra que a mediu, sem período reservado, é calibração retrospectiva
por **0,30 bps de ida e volta**. Não vale o preço de uma variante
([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).

## Por que pode falhar

- **`bid`/`ask` do hot state vêm do `bookTicker`**, cuja cadência é de evento, não de relógio: o
  snapshot pega o último valor que sobreviveu ao TTL de 30 s, não a média do minuto. Spread mediano
  de snapshot ≠ spread mediano ponderado pelo tempo.
- **Cobertura de 37% dos minutos.** 535 de ~1.455. O worker local ficou fora, e os minutos ausentes
  não são aleatórios — reinício de worker correlaciona com carga.
- **Não há decomposição de variância.** Falar de "entre mercados" contra "dentro do mercado" exigiria
  uma decomposição que não fiz; a tabela por decil e a coluna `p90_dentro_bps` são indícios das duas
  fontes, não a partição delas.
- **Um dia não é uma amostra de regimes.** Todo o material é de uma janela de 24 h.
- **O decil usa `volume_24h_usd` da tabela `markets`**, atualizado pelo refresh do universo, não o
  volume do instante. Estratificação com denominador defasado.
- **Spread cotado não é spread pago.** Quem atravessa paga o meio spread *mais* o que o tamanho
  arrasta ([[KB-0036-o-tamanho-que-a-sombra-nunca-declara]]), *menos ou mais* o erro de referência
  do `open` ([[KB-0042-o-open-nao-e-preco-executavel]]). O que o preço faz **depois** do fill não é
  spread pago e não entra nessa soma — está em
  [[KB-0043-selecao-adversa-o-custo-que-so-aparece-depois-do-fill]] e já vive dentro do `R_net`.

## Segunda opinião (Astra)

Concorda com a medição e, sobretudo, com a conclusão de que **o spread não é o elo fraco**. **Recusou
a primeira versão desta nota**, com dois erros aritméticos e três inferências não demonstradas.
Correções aceitas:

1. **"0,15 bps de ida e volta" estava errado** — a diferença de 2 para 2,3 bps vale **0,30 bps** na
   ida e volta (0,15 por perna). Corrigido, com tabela.
2. **"p90 abaixo de 6 ⇒ erro máximo de 2 bps de ida e volta" estava errado**: duas pernas com spread
   de 5,9 custam **3,9 bps** a mais. E p90 não limita os 10% restantes. O critério foi refeito.
3. **"Monotônico" é falso** — 3,245 → 3,265 → 3,780 e 2,390 → 3,390 são reversões.
4. **"A dispersão é quase toda entre mercados"** exige decomposição que eu não fiz. Cortado.
5. **"Isso não é sorte"** afirmava causalidade a partir de duas medianas. Vira associação declarada.
6. **Reprodutibilidade:** as consultas não delimitavam a janela, e a saída por decil trazia
   `min_bps`/`max_bps` que eu tinha aparado do `SELECT` colado. Consertados, e acrescentadas as
   consultas de cobertura (535 minutos, 8 de 200 sinais).
7. **Não citar número de spread do preprint 2602.00776**, que não publica esse número.

Divergência: ela queria propor já o carimbo de spread como requisito de implementação; mantive como
diagnóstico `EXEC-B`, porque quem decide o que entra no M3 é o Everton. Ela também observa, com
razão, que o `EXEC-B` mede **contexto** e não erro realizado de ida e volta — está dito no corpo.

## Relacionados

[[Strategy Backlog]] · [[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] ·
[[KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] · [[KB-0044-o-que-morre-em-dez-segundos]] ·
[[KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance]] · [[Features]] · [[Market Collector]]
