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

O folclore diz "meme coin é volátil". Medi, e **as medianas agregadas da coorte de memes e do resto
do universo ficaram próximas nesta janela**: 0,84% contra 0,83% de ATR por barra de 15 min. (Isso
não é "as distribuições são iguais" — medianas próximas não estabelecem equivalência; a ressalva é
da Astra.) O contraste grande é outro: **BTC e majors contra todo o resto**.

E dele sai a consequência que dá nome à nota: o estimador que usei ficou **abaixo de
`atr_pct_min = 0,003` em 100% das 154 observações do BTCUSDT**. Isso *sugere* que o gate de ATR da
`momentum_v1` exclui o BTC de forma sistemática — não prova, pelas duas razões que a revisão desta
nota deixou escritas abaixo. Se sobreviver ao teste, quer dizer que ninguém decidiu que o Lab de
sombra seria um laboratório de altcoin e meme: o piso de custo decidiu.

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

**DOGE (0,56%), PEPE (0,53%) e SHIB (0,45%) ficam abaixo da mediana do resto do universo (0,83%) e
na mesma faixa das majors** (mediana 0,50%) — DOGE e PEPE ligeiramente acima dela, SHIB abaixo. O
que a nossa janela mostra é **heterogeneidade contemporânea grande dentro da coorte**: o mercado
mais volátil da coorte A (USELESS, 3,66%) tem oito vezes o ATR% do menos volátil (SHIB, 0,45%).

Isso **é compatível com o ordenamento** do ME2F, que põe as memes estabelecidas (DOGE, SHIB, PEPE)
em faixa intermediária e ETH/SOL como resilientes. **Duas coisas que eu tinha escrito e retirei:**
que "a volatilidade migrou para as listagens novas" — uma fotografia de 42 h sem data de listagem
não demonstra migração nenhuma, demonstra heterogeneidade num instante —, e que o nosso dado
discordaria do ME2F por TRUMPUSDT (0,72%) estar no meio do pelotão: o ME2F mede fragilidade
combinando volatilidade, concentração de carteiras e sentimento, e ATR de dois dias não refuta esse
objeto. As duas retiradas são da Astra.

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

**E aqui a revisão da Astra derrubou a minha palavra "confirmação".** A ordem dos testes na
`momentum_v1` é: rompimento (`momentum_v1.py:180`), retorno positivo (`:186`), `rvol_min` (`:192`)
e **só então** o gate de ATR (`:204`). Um mercado que nunca rompe o canal **nunca chega** ao gate.
Então "0 sinais de Momentum em BTCUSDT" é **compatibilidade observacional**, não confirmação
independente: o BTC pode estar sendo recusado antes, por rompimento ou por volume relativo, e
remover o piso continuaria dando zero. Os 1.009 sinais dos outros mercados **não são 1.009 testes**
da hipótese sobre o BTC.

A redação que sobrevive é a dela: *o estimador de média simples ficou abaixo de 0,3% em todas as 154
observações do BTC; isso sugere exclusão pelo gate da Momentum, a confirmar com o Wilder e com a
população efetivamente avaliável.* É exatamente o que o `D-MEME-ATR` abaixo mede.

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
Mecanismo **conjecturado** — e a palavra é essa depois da revisão —, e ele **não** é "volatilidade
alta é ruim": é que ATR% alto e livro fino parecem andar juntos na nossa amostra (correlação de
postos de **−0,651** entre ATR%(14) e profundidade top-20 em USD, nos 27 mercados de meme mais o
BTC), enquanto o custo de execução assumido não acompanha. **Essa correlação não demonstra o
mecanismo**: mistura dois instantes, é transversal entre mercados, e não diz nada sobre o custo
*condicionado ao sinal*. Quem decide se o mecanismo existe é o `D-MEME-LIQ` da
[[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]], e ele roda **antes** da `M-A`.
O que a refutaria: diferença **pareada** de média de `R_net` contra a base sem exceder o efeito
mínimo declarado antes da janela, com os quatro números da convenção `C-META` (cobertura, `q`,
`μ_A − μ_B`, `q·μ_A − μ_B`).
Ressalva que não pode sumir: baixar o teto **encolhe a amostra**, e um filtro que melhora a média
cortando um terço dos sinais não é melhoria — é a armadilha que a `C-META` existe para pegar
([[KB-0052-meta-rotulagem-o-formato-de-todo-filtro-que-propusemos]]).

## Por que pode falhar

- **Estimador diferente, e o viés não tem direção fixa.** Eu tinha escrito que a diferença era
  "barra corrente contra aquecimento"; está errado. O código recebe 97 barras, calcula 96 TRs,
  inicializa com 14 e aplica **82 passos de suavização de Wilder**, dividindo pelo último fechamento
  (`packages/core/hunter_core/strategies/indicators.py:88`). As duas medidas incluem a última barra
  completa. O que muda é a **memória**: Wilder guarda choques que já saíram das últimas 14 barras.
  Contraexemplo aritmético da Astra (sintético, não é o BTC): fechamento constante, TR usual de
  0,1%, um choque de 10% e depois 14 barras normais → **SMA = 0,1%**, **Wilder ≈ 0,3506%**. O meu
  estimador reprovaria pelo piso; o da estratégia admitiria. Logo, **mediana distante do piso não
  prova ausência de inversões**, e as frações "abaixo do piso" e "acima do teto" valem para o
  estimador descrito, não como taxa de recusa operacional. Para o BTC especificamente, os 154 pontos
  ficaram todos abaixo de 0,3% com p95 em 0,198% — o que torna a inversão improvável ali, sem
  torná-la impossível.
- **A minha consulta atravessa lacunas; a estratégia não.** Eu descarto barras de 15 min incompletas
  e depois uso `lag` e `ROWS`, ou seja, costuro barras não adjacentes. A agregação real recusa a
  janela inteira quando falta qualquer minuto
  (`packages/core/hunter_core/strategies/aggregate.py:128`). Consequência concreta: uma listagem com
  pouco histórico recebe ATR na minha consulta mas ficaria `UNAVAILABLE` na estratégia — e a minha
  fração vira "recusa pelo teto" onde nenhuma avaliação seria possível. Achado da Astra.
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

Revisão de 2026-09-06 (`.claude/state/astra-review-KB-0056-0058-memecoins.md`). Ela recusou a
primeira versão desta nota em quatro pontos, todos já incorporados acima:

1. **"Confirmação independente" virou "compatibilidade observacional"** — o gate de ATR vem depois
   de rompimento, retorno e `rvol` (`momentum_v1.py:180,204`).
2. **O viés SMA↔Wilder não tem direção universal**, com o contraexemplo numérico (choque de 10% e
   14 barras normais: SMA 0,1%, Wilder ≈0,3506%).
3. **A minha consulta atravessa lacunas** que a `aggregate.py:128` recusa, então as frações não são
   taxas de recusa operacional.
4. **"A volatilidade migrou para as listagens novas" saiu inteira**, e a alegada discordância com o
   ME2F por causa do TRUMP também.

Ela também exigiu, para a `M-A`, que o `D-MEME-ATR` rode **antes** de promover a candidata, com três
números separados: gate de ATR isolado nas janelas válidas, exclusões adicionais depois dos demais
critérios, e emissões efetivas. E lembrou que rodar um braço como estratégia **independente** muda
ocupação e rearme de slots (`services/strategy-worker/hunter_strategy_worker/decide.py:144`) — o
resultado não pode ser apresentado como efeito pareado do filtro.

**Concordou** em não concluir que excluir o BTC torna o piso errado, e em manter tudo como pesquisa:
os dados não demonstram vantagem econômica nenhuma.

## Relacionados

[[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]] ·
[[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]] ·
[[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0007-atr-e-escala-por-volatilidade]] · [[Strategy Backlog]] · [[Index]]
