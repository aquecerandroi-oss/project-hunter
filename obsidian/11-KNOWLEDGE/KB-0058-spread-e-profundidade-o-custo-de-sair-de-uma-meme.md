---
tags: [knowledge, nota, memecoins, execucao, custo]
tema: meme coins / spread, profundidade e custo de execução
fonte: medição própria — market_snapshots (VPS) e 50 livros de 20 níveis do hot state (Redis, VPS)
fonte_url: —
lido_em: 2026-09-06
evidencia: replicado (duas medições, saídas coladas)
hipotese_testavel: sim
astra: pendente
---

# Spread e profundidade — o custo de sair de uma meme

## O que afirma

O contrato de custo do Lab (`spread_bps=2`, `slippage_bps=5`, `fee_bps=4`) foi conferido na quinta
rodada contra a **mediana do universo inteiro** e acertou razoavelmente
([[KB-0037-o-spread-assumido-contra-o-spread-medido]]: 2,30 bps medidos contra 2 assumidos). Medido
**por coorte**, ele erra na direção que importa: nas memes o spread mediano é **3,12 bps** e
atravessar o ask com 5.000 USDT custa **7,07 bps** — contra **1,34 bps** nas majors e **0,01 bps**
no BTC. Três dos 21 livros de meme **não comportam** 20.000 USDT nos 20 níveis.

E há a relação que dá mecanismo à candidata da nota anterior: **quanto maior o ATR%, mais fino o
livro** — correlação de postos **−0,651**.

## Onde foi mostrado

**Medição 1 — spread cotado, `market_snapshots` da VPS**, mesma janela da
[[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]] (2026-09-05 00:00 a 2026-09-06 18:00 UTC).

```sql
SELECT cls.grupo, count(*) AS obs, count(s.spread_pct) AS obs_com_spread,
  count(DISTINCT s.market_id) AS mercados,
  round((10000*percentile_cont(0.5) WITHIN GROUP (ORDER BY s.spread_pct))::numeric,3) AS mediana,
  round((10000*percentile_cont(0.9) WITHIN GROUP (ORDER BY s.spread_pct))::numeric,3) AS p90,
  round((10000*percentile_cont(0.99) WITHIN GROUP (ORDER BY s.spread_pct))::numeric,3) AS p99,
  round((10000*max(s.spread_pct))::numeric,3) AS maximo
FROM market_snapshots s JOIN cls ON cls.id = s.market_id
WHERE s.ts >= '2026-09-05 00:00+00' AND s.ts < '2026-09-06 18:00+00' GROUP BY 1 ORDER BY 1;
```

```
      grupo       |  obs   | obs_com_spread | mercados | mediana |  p90   |  p99   | maximo
------------------+--------+----------------+----------+---------+--------+--------+---------
 A_meme           |  22193 |          21658 |       21 |   3.120 |  5.720 | 12.100 |  23.000
 B_meme_nao_ascii |   5079 |           4884 |        5 |   3.790 | 10.700 | 17.852 |  29.920
 C_btc            |   1138 |           1135 |        1 |   0.010 |  0.010 |  0.010 |   0.230
 D_majors         |  26139 |          26042 |       23 |   1.230 |  4.510 |  6.370 |   8.760
 E_resto          | 154039 |         150017 |      150 |   2.660 |  7.010 | 11.720 | 108.320
```

(valores em bps; cobertura de `spread_pct` entre 96% e 99,7% das leituras em todos os grupos.)

**Medição 2 — profundidade e custo de travessia, livros de 20 níveis do hot state.** Leitura única
das chaves `mkt:binance:{símbolo}:book` (msgpack, TTL curto — `hot_state.py:201-235`), executada
dentro do contêiner `hunter-market-worker-1` da VPS em 2026-09-06 ~18:50 UTC. Para cada livro:
profundidade somada dos 20 níveis dos dois lados em USD, notional no melhor ask, e custo em bps de
atravessar o ask contra o **mid** para 500 / 1.000 / 5.000 / 20.000 USDT.

```
grupo             livros  prof20_usd(med)  topo_ask(med)  spr_bps   500    1000    5000   20000
A_meme            21/21            66589            387     3.18   2.76    3.93    7.07   12.20
B_meme_nao_ascii    5/5            31359             15     1.85   3.54    5.16   10.97   13.44
C_btc               1/1           974581         516693     0.01   0.01    0.01    0.01    0.01
D_majors          23/23           343807           3313     1.24   0.63    0.65    1.34    2.65
  não cabe 5.000 USDT:  A_meme 1/21 · B 1/5
  não cabe 20.000 USDT: A_meme 3/21 · B 4/5
```

Extremos da coorte A que valem por si: CHILLGUYUSDT com **3.186 USD** nos 20 níveis (não comporta
5.000), USELESSUSDT com 9.006, 1000000BOBUSDT com spread de **10,66 bps**. E BROCCOLI714USDT
custando **42,82 bps** para 20.000 — sete vezes o custo total assumido por perna. No outro extremo,
DOGEUSDT custa **0,56 bps** para qualquer um dos quatro tamanhos, e TRUMPUSDT 2,54 bps para 20.000.
**A dispersão dentro da coorte A é maior que a distância entre coortes.**

**Medição 3 — a relação entre as duas.** Correlação de postos (Spearman) entre o ATR%(14) da
KB-0057 e a profundidade top-20 em USD, sobre os 27 mercados de meme mais o BTC: **−0,651**.
Ressalva obrigatória: os dois números vêm de **instantes diferentes** (o ATR de uma janela de 42 h;
o livro de uma leitura única), então isto é associação transversal grosseira, não medição pareada.

## Como mediríamos aqui

O que estes números fazem com o contrato de custo:

| Componente | Assumido | Medido nas memes (A) | Medido nas majors |
|---|---|---|---|
| Spread total | 2 bps | 3,12 bps (p99 12,10) | 1,23 bps |
| Travessia a 5.000 USDT (inclui o meio spread) | não existe no contrato | 7,07 bps | 1,34 bps |
| Cabe 20.000 USDT em 20 níveis? | não perguntado | 18 de 21 | 23 de 23 |

A comparação **não é termo a termo** — a lição da [[KB-0036-o-tamanho-que-a-sombra-nunca-declara]]
continua valendo: `slippage_bps = 5` é "por lado, sem o meio spread", e o meu custo de travessia é
contra o mid e **já inclui** o meio spread. O que dá para dizer sem esticar: para um notional de
5.000 USDT, o custo estático da perna de entrada numa meme mediana (7,07 bps) **já é maior que os 6
bps** que o Lab assume para spread mais slippage somados, antes de qualquer taxa.

## Hipótese testável no Lab

**`M-B` — piso de liquidez no instante da decisão (candidata de estratégia, testável agora, com uma
ressalva de disponibilidade).**
Regra: recusar o sinal quando o **volume de cotação de 24 h** do mercado no instante da decisão for
menor que θ.
Parâmetros: `min_quote_volume_24h_usd = θ`, com θ saindo de um quantil da distribuição **condicionada
a sinal**, congelado antes da janela; um único braço.
Dado: `quote_volume_24h` em `market_snapshots` e no hash `ticker` do hot state.
**Ressalva medida hoje, e ela é a novidade:** até 2026-09-06 17:59 UTC a cobertura era praticamente
zero (o defeito de escritores da [[KB-0044-o-que-morre-em-dez-segundos]]); depois do deploy do
commit `fa9f957` na VPS ela pulou para **6.264 de 9.901 leituras (63%) na hora das 18:00**. Ou seja:
a candidata **passou a ser testável hoje**, e não era ontem.
O que a refutaria: os dois denominadores da `C-META` não positivos — nem `delta_por_aceito`, nem
`delta_por_oportunidade`.

**`D-MEME-CUSTO` (diagnóstico, roda hoje, sem pré-requisito):** repetir o `EXEC-C` da quinta rodada
(sensibilidade a `fee_bps ∈ {4; 4,5; 5}`) **estratificado por coorte**, e acrescentar uma linha nova:
recomputar o `R_net` de cada outcome trocando `spread_bps` de 2 pelo spread **medido** da coorte
(3,12 nas memes, 1,23 nas majors). Não é calibração — é sensibilidade sobre população fixa, e serve
para saber se o vermelho publicado cabe dentro do erro da hipótese de custo **naquela coorte**.

**Bloqueada, e fica registrado por quê:** a versão boa disto exige o **carimbo de execução** do item
20 do backlog ([[KB-0044-o-que-morre-em-dez-segundos]]). Sem ele, não existe livro gravado no
instante do sinal, e tudo que eu medir de profundidade é de um instante arbitrário — como estes
números são.

## Por que pode falhar

- **Os livros são de uma leitura só**, numa tarde de domingo. Não descrevem stress, que é
  exatamente quando a `momentum_v1` dispara. A mesma ressalva da
  [[KB-0036-o-tamanho-que-a-sombra-nunca-declara]], agora com coorte.
- **Vinte níveis não são o livro.** Um mercado que "não comporta 20.000 USDT" pode comportar no
  nível 21. O que medi é o custo dentro do que gravamos, e é limite superior de otimismo só até o
  nível 20.
- **Símbolos com multiplicador** (1000PEPE, 1000000BOB) têm preço por 1.000 ou 1.000.000 unidades.
  Para spread relativo e para `preço × quantidade` em USDT isso é neutro — conferi que a conta de
  notional não depende do multiplicador —, mas para qualquer conta em unidades do token, não é.
- **`quote_volume_24h` é volume relatado**, com toda a ressalva da
  [[KB-0018-volume-relatado-e-o-denominador-que-usamos]]; e 63% de cobertura numa hora não é 63% de
  cobertura no instante de cada decisão.
- **A correlação de −0,651 tem 27 pontos** e mistura dois instantes. É indício de mecanismo, não
  medição de mecanismo.

## Segunda opinião (Astra)

_(pendente)_

## Relacionados

[[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]] ·
[[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] ·
[[KB-0037-o-spread-assumido-contra-o-spread-medido]] ·
[[KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker]] ·
[[KB-0044-o-que-morre-em-dez-segundos]] · [[Strategy Backlog]] · [[Index]]
