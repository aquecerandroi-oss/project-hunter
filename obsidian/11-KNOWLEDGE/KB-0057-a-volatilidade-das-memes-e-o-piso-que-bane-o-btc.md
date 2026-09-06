---
tags: [knowledge, nota, memecoins, volatilidade]
tema: meme coins / volatilidade e o filtro que já existe
fonte: medição própria na VPS (velas de 1 min, 229 mercados) + Xiang et al. (arXiv 2512.00377)
fonte_url: https://arxiv.org/abs/2512.00377
lido_em: 2026-09-06
evidencia: replicado (SQL colado) + preprint lido em resumo
hipotese_testavel: sim
astra: pendente
---

# A volatilidade das memes — e o piso que, na prática, bane o BTC

## O que afirma

O folclore diz "meme coin é volátil". Medi, e o rótulo **não separa volatilidade** dentro do nosso
universo: as memes da coorte A ficam em **0,84%** de ATR por barra de 15 min, contra **0,83%** do
resto do universo monitorado. O que separa é outra coisa — **BTC e majors contra todo o resto** —, e
a consequência é grande: `atr_pct_min = 0,003` exclui o **BTCUSDT em 100% das barras** medidas.

O Lab de sombra já é, por construção, um laboratório de altcoin e meme. Ninguém decidiu isso; o
piso de custo decidiu.

## Onde foi mostrado

**Medição própria, VPS, 2026-09-06.** Janela fixa de 2026-09-05 00:00 a 2026-09-06 18:00 UTC (42 h,
168 barras de 15 min). Barras de 15 min agregadas das velas de 1 min (`candles_15m` existe como
partição e está **vazia**: as 581.153 velas persistidas são todas de 1 min), exigindo as 15 velas
completas na barra. ATR aproximado por **média móvel simples de TR sobre 14 barras**, dividido pelo
fechamento.

**Aviso de instrumento, na lição da [[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]]:**
isto **não é** o ATR que a `momentum_v1` consome. Ela usa Wilder(14) sobre 15m com `atr_bars = 97`
(`momentum_v1.py:80-82`), recalculado a cada avaliação. Média simples e Wilder são dois estimadores
com o mesmo apelido; os números abaixo descrevem a **grandeza**, não reproduzem a decisão.

```sql
WITH cls AS (SELECT m.id, m.symbol, CASE WHEN m.symbol = ANY(ARRAY[...meme_universe_v1...])
  THEN 'A_meme' WHEN m.symbol !~ '^[A-Za-z0-9]+$' THEN 'B_meme_nao_ascii'
  WHEN m.symbol = 'BTCUSDT' THEN 'C_btc' WHEN m.symbol = ANY(ARRAY[...majors...]) THEN 'D_majors'
  ELSE 'E_resto' END AS grupo FROM markets m WHERE m.is_monitored),
b AS (SELECT c.market_id, to_timestamp(floor(extract(epoch FROM c.open_time)/900)*900) AS b15,
        max(c.high) AS hi, min(c.low) AS lo,
        (array_agg(c.close ORDER BY c.open_time DESC))[1] AS cl, count(*) AS n1m
      FROM candles_1m c WHERE c.open_time >= '2026-09-05 00:00+00'
        AND c.open_time < '2026-09-06 18:00+00' GROUP BY 1,2),
tr AS (SELECT market_id, b15, cl,
         greatest(hi-lo, abs(hi - lag(cl) OVER w), abs(lo - lag(cl) OVER w)) AS trv,
         lag(cl) OVER w AS pcl
       FROM b WHERE n1m = 15 WINDOW w AS (PARTITION BY market_id ORDER BY b15)),
atr AS (SELECT market_id, b15,
          avg(trv) OVER (PARTITION BY market_id ORDER BY b15
            ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) / nullif(cl,0) AS atr14p,
          count(*) OVER (PARTITION BY market_id ORDER BY b15
            ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS janela
        FROM tr WHERE pcl IS NOT NULL)
SELECT cls.grupo, count(*) AS barras, count(DISTINCT a.market_id) AS mercados,
  round((100*percentile_cont(0.5) WITHIN GROUP (ORDER BY a.atr14p))::numeric,4) AS atr14_pct_mediana,
  round((100*percentile_cont(0.05) WITHIN GROUP (ORDER BY a.atr14p))::numeric,4) AS p05,
  round((100*percentile_cont(0.95) WITHIN GROUP (ORDER BY a.atr14p))::numeric,4) AS p95,
  round((100.0*count(*) FILTER (WHERE a.atr14p < 0.003)/count(*))::numeric,1) AS pct_abaixo_piso,
  round((100.0*count(*) FILTER (WHERE a.atr14p > 0.05)/count(*))::numeric,1) AS pct_acima_teto
FROM atr a JOIN cls ON cls.id = a.market_id WHERE a.janela = 14 GROUP BY 1 ORDER BY 1;
```

```
      grupo       | barras | mercados | atr14_pct_mediana |  p05   |  p95   | pct_abaixo_piso | pct_acima_teto
------------------+--------+----------+-------------------+--------+--------+-----------------+----------------
 A_meme           |   3147 |       21 |            0.8396 | 0.4000 | 3.2532 |             0.5 |            0.4
 B_meme_nao_ascii |    644 |        5 |            2.2441 | 1.2246 | 5.7001 |             0.0 |            7.0
 C_btc            |    154 |        1 |            0.1273 | 0.0837 | 0.1984 |           100.0 |            0.0
 D_majors         |   3542 |       23 |            0.5019 | 0.1143 | 1.0439 |            14.7 |            0.0
 E_resto          |  22177 |      150 |            0.8271 | 0.3508 | 3.4465 |             2.9 |            1.7
```

E o detalhe por mercado, que é onde o rótulo morre (média simples de TR% sobre as 167 barras):

```
 A_meme | USELESSUSDT     |  3.6556      A_meme | SPXUSDT       |  0.8687
 A_meme | 1000CATUSDT     |  1.8990      A_meme | PENGUUSDT     |  0.7249
 A_meme | MUBARAKUSDT     |  1.6391      A_meme | TRUMPUSDT     |  0.7192
 A_meme | 1000000BOBUSDT  |  1.5782      A_meme | WIFUSDT       |  0.6839
 A_meme | TSTUSDT         |  1.5443      A_meme | PNUTUSDT      |  0.6788
 A_meme | BROCCOLI714USDT |  1.5238      A_meme | 1000FLOKIUSDT |  0.6292
 A_meme | CHILLGUYUSDT    |  1.5075      A_meme | NEIROUSDT     |  0.6204
 A_meme | BOMEUSDT        |  1.2459      A_meme | DOGEUSDT      |  0.5575
 A_meme | MOODENGUSDT     |  1.0365      A_meme | 1000PEPEUSDT  |  0.5319
 A_meme | 1000BONKUSDT    |  1.0221      A_meme | 1000SHIBUSDT  |  0.4457
 A_meme | FARTCOINUSDT    |  1.0122      C_btc  | BTCUSDT       |  0.1259
 B_meme_nao_ascii | 哈基米USDT 5.8676     B_meme | 牛来USDT     |  3.5055
 B_meme_nao_ascii | 龙虾USDT   2.2966     B_meme | 我踏马来了USDT 2.2069
 B_meme_nao_ascii | 币安人生USDT 1.5656
```

**DOGE (0,56%), PEPE (0,53%) e SHIB (0,45%) são menos voláteis que a mediana das majors seria de
esperar e ficam abaixo da mediana do resto do universo (0,83%).** As memes "azuis" viraram ativos
grandes; a volatilidade migrou para as listagens novas. Isso **concorda com o ordenamento** do ME2F
(memes estabelecidas em faixa intermediária, ETH/SOL resilientes) e **discorda em um ponto**: lá os
tokens políticos concentram o risco máximo; aqui TRUMPUSDT (0,72%) está no meio do pelotão.

## Como mediríamos aqui

Os dois parâmetros que já filtram por isto existem e nunca foram lidos como filtro de universo:

- `atr_pct_min = 0,003` (`momentum_v1.py:83`) — piso de custo, justificado pela
  [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]].
- `atr_pct_max = 0,05` (`momentum_v1.py:84`) — teto, sem justificativa escrita em nota nenhuma até
  hoje.

A medição diz o que eles fazem **como recorte de população**: o piso apaga o BTC inteiro e 14,7% das
barras das majors; o teto apaga 7,0% das barras da coorte B e 0,4% da coorte A.

**Confirmação independente, e é a mais barata da rodada:** a `momentum_v1` emitiu **0 sinais** para
BTCUSDT na VPS. O único sinal de BTC que existe é da `volume_anomaly_v1`, que **não tem
`atr_pct_min`** nos seus parâmetros (`volume_anomaly_v1.py:68-83`).

```
   estrategia   |      grupo       | sinais
----------------+------------------+--------
 Momentum       | A_meme           |     23
 Momentum       | B_meme_nao_ascii |      2
 Momentum       | D_majors         |     29
 Momentum       | E_resto          |    240
 Volume Anomaly | A_meme           |     61
 Volume Anomaly | B_meme_nao_ascii |      6
 Volume Anomaly | C_btc            |      1
 Volume Anomaly | D_majors         |     42
 Volume Anomaly | E_resto          |    574
```

A previsão "o piso bane o BTC da `momentum_v1`" tinha uma refutação simples — um sinal de Momentum
em BTCUSDT — e ela não apareceu em 1.004 sinais. Isso **não prova** o mecanismo (o BTC podia estar
falhando no rompimento ou no `rvol_min`), mas o piso é o candidato com previsão quantitativa e
100% de concordância.

## Hipótese testável no Lab

**`D-MEME-ATR` (diagnóstico, testável agora, perpétuo da Binance, sem pré-requisito):** ciclo de
trabalho dos dois limites, **medido no ATR que a `momentum_v1` de fato consome** (Wilder(14) sobre
15m com `atr_bars = 97`), por coorte de `meme_universe_v1` e por hora UTC — fração de avaliações
recusadas por `atr_pct < min`, por `atr_pct > max`, e admitidas. É o `D-024` da quarta rodada
([[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]]) com a estratificação por coorte
acrescentada, e responde: **quem o piso e o teto estão selecionando, por nome.**

**`M-A` — teto de ATR% mais apertado (candidata de estratégia, testável agora).**
Regra: manter tudo da `momentum_v1` e baixar só `atr_pct_max`.
Parâmetros: `atr_pct_max ∈ {0,05 (base), 0,03, 0,02}`.
Mecanismo declarado, e ele **não** é "volatilidade alta é ruim": é que ATR% alto e livro fino andam
juntos na nossa amostra (correlação de postos **−0,651** entre ATR%(14) e profundidade top-20 em
USD, nos 27 mercados de meme + BTC — [[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]]),
e o custo de execução assumido não acompanha.
O que a refutaria: diferença **pareada** de média de `R_net` contra a base sem exceder o efeito
mínimo declarado antes da janela, com os quatro números da convenção `C-META` (cobertura, `q`,
`μ_A − μ_B`, `q·μ_A − μ_B`).
Ressalva que não pode sumir: baixar o teto **encolhe a amostra**, e um filtro que melhora a média
cortando um terço dos sinais não é melhoria — é a armadilha que a `C-META` existe para pegar
([[KB-0052-meta-rotulagem-o-formato-de-todo-filtro-que-propusemos]]).

## Por que pode falhar

- **Estimador errado.** Média simples de TR não é Wilder; e o meu ATR é de barra corrente, enquanto
  a estratégia usa 97 barras de aquecimento. A ordem de grandeza sobrevive (o BTC tem 0,127% contra
  um piso de 0,300%: menos da metade), mas a fração exata de recusa não.
- **42 horas.** Um único regime, dois dias, sem stress. A [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]]
  já mostrou que hora do dia e dia se confundem nesta janela.
- **A coorte B tem 5 mercados**, um deles com 41 barras. Nada ali é estimativa estável.
- **O `M-A` é calibração sobre a mesma população que revelou o problema.** Vale a regra da
  [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]: os valores 0,03 e 0,02 saem de
  quantis declarados **antes** da janela, nunca de olhar resultado.
- **O piso pode estar certo.** Que ele exclua o BTC não é, por si, defeito: 0,127% de ATR contra 10
  bps de custo por ida e volta é exatamente o caso em que o custo come o movimento. O achado não é
  "o piso está errado" — é **"ninguém sabia que ele fazia isso"**.

## Segunda opinião (Astra)

_(pendente)_

## Relacionados

[[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]] ·
[[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]] ·
[[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0007-atr-e-escala-por-volatilidade]] · [[Strategy Backlog]] · [[Index]]
