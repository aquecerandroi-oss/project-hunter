---
tags: [knowledge, nota, risco, capacidade, medicao, m3]
tema: dimensionamento e risco / a tabela de capacidade que o M3 vai precisar
fonte: medição própria — 200 livros de 20 níveis do hot state (Redis, VPS)
fonte_url: —
lido_em: 2026-09-06
evidencia: replicado (saída colada)
hipotese_testavel: sim
astra: pendente
---

# A tabela de capacidade — quantos mercados suportam 500, 2.000 e 10.000 USDT

## O que afirma

Esta é a tabela que o M3 precisa ter antes de escolher qualquer tamanho de posição, e que até hoje
não existia em lugar nenhum: **para cada mercado do universo monitorado, quanto notional cabe a um
custo de travessia de 5 bps contra o mid.**

O resumo, medido em 200 livros de 20 níveis lidos do hot state da VPS num intervalo de **11 segundos**
(2026-09-06 19:47:24 a 19:47:35 UTC):

| Notional por sinal | cabe no livro de 20 níveis | custo ≤ 5 bps (mid) | custo ≤ 10 bps (mid) | custo mediano (mid) |
|---|---|---|---|---|
| **500 USDT** | 199/200 | **164/200** | 197/200 | 2,48 bps |
| **2.000 USDT** | 194/200 | **106/200** | 172/200 | 4,48 bps |
| **10.000 USDT** | 165/200 | **50/200** | 90/200 | 9,36 bps |

E a distribuição do teto por mercado, a 5 bps contra o mid: **mediana 2.174 USDT**, decil inferior
**295 USDT**, decil superior **41.879 USDT**. Dois mercados têm capacidade **zero** a 5 bps, porque o
meio spread sozinho já custa mais que isso.

## Onde foi mostrado

Chaves `mkt:binance:{símbolo}:book` (msgpack, TTL de 10 s — `hot_state.py:45,201-235`), lidas de
dentro do contêiner `hunter-market-worker-1` da VPS. Para cada livro: `mid = (melhor bid + melhor
ask)/2`; caminhada pelos níveis do ask acumulando `preço × quantidade` até o notional alvo; custo em
bps = `(VWAP/mid − 1) × 10⁴`. O teto `N*` é obtido por busca binária sobre o notional, com 60
iterações, no maior valor cujo custo fica ≤ 5 bps.

```
livros lidos: 200   (chaves book encontradas: 200)
ts min/max dos livros: 2026-09-06T19:47:24.737000+00:00 .. 2026-09-06T19:47:35.002000+00:00

== distribuicao do notional que cabe a <= 5 bps de custo (USDT) ==
contra o mid (inclui meio spread): min=0 p10=295 p25=819 mediana=2,174 p75=9,620 p90=41,879 max=1,132,353
contra o melhor ask (so profundidade): min=52 p10=909 p25=1,650 mediana=3,536 p75=13,903 p90=46,823 max=1,283,125
contra o mid a <= 10 bps: mediana=8,212 p10=1,697 p90=95,961

== quantos mercados suportam cada tamanho ==
tamanho | cabe no livro | custo<=5bps(mid) | custo<=10bps(mid) | custo<=5bps(ask) | mediana custo mid
    500 | 199/200 | 164/200 | 197/200 | 194/200 | 2.48 bps
  2,000 | 194/200 | 106/200 | 172/200 | 142/200 | 4.48 bps
 10,000 | 165/200 |  50/200 |  90/200 |  60/200 | 9.36 bps

== 15 mercados com menor capacidade a 5 bps (contra o mid) ==
VELVETUSDT           max5=         0  spread=  12.63bps  prof_ask20=      72,152
MITOUSDT             max5=         0  spread=  11.68bps  prof_ask20=      41,708
SUSHIUSDT            max5=         3  spread=   3.86bps  prof_ask20=     105,267
ONUSDT               max5=        12  spread=   5.54bps  prof_ask20=      27,876
BUSDT                max5=        14  spread=   6.08bps  prof_ask20=      23,557
CHILLGUYUSDT         max5=        58  spread=   7.59bps  prof_ask20=       2,605
我踏马来了USDT            max5=        68  spread=   4.71bps  prof_ask20=       4,592
1000FLOKIUSDT        max5=        99  spread=   3.85bps  prof_ask20=     123,939
TRADOORUSDT          max5=       101  spread=   2.88bps  prof_ask20=       2,734
CLOUSDT              max5=       117  spread=   0.88bps  prof_ask20=       1,760
APRUSDT              max5=       143  spread=   4.90bps  prof_ask20=      23,973
哈基米USDT              max5=       149  spread=   8.84bps  prof_ask20=       5,845
1000CATUSDT          max5=       163  spread=   9.34bps  prof_ask20=      23,369
METISUSDT            max5=       194  spread=   5.89bps  prof_ask20=      18,462
BTWUSDT              max5=       238  spread=   2.75bps  prof_ask20=       1,171

== 10 mercados com maior capacidade a 5 bps ==
BTCUSDT              max5=   1,132,353  spread=   0.01bps  prof_ask20=     1,132,353
SOLUSDT              max5=   1,083,973  spread=   0.95bps  prof_ask20=     3,837,404
XRPUSDT              max5=     947,209  spread=   0.71bps  prof_ask20=     1,490,237
ETHUSDT              max5=     669,140  spread=   0.04bps  prof_ask20=       669,140
DOGEUSDT             max5=     463,114  spread=   1.12bps  prof_ask20=     1,033,067
BNBUSDT              max5=     170,991  spread=   0.13bps  prof_ask20=       170,991
ADAUSDT              max5=     154,515  spread=   4.57bps  prof_ask20=     1,943,788
TRUMPUSDT            max5=     122,323  spread=   4.33bps  prof_ask20=     1,866,420
AVAXUSDT             max5=     119,430  spread=   1.31bps  prof_ask20=       275,078
SUIUSDT              max5=     115,351  spread=   1.26bps  prof_ask20=       482,302

mercados com capacidade ZERO a 5 bps (meio spread ja > 5 bps): 2/200
   VELVETUSDT, MITOUSDT
```

**Três leituras do teto que só aparecem lendo a saída inteira:**

1. **Cinco dos dez maiores estão censurados pela profundidade de 20 níveis, não pelos 5 bps.**
   BTCUSDT, ETHUSDT e BNBUSDT têm `max5 = prof_ask20` exatamente — o livro acabou antes de o custo
   chegar a 5 bps. **O teto real deles é maior do que o medido**, e a nossa medição não sabe quanto.
2. **Spread e profundidade são defeitos independentes.** SUSHIUSDT tem 105 mil USD de profundidade e
   capacidade de **3 USDT** a 5 bps, porque o spread de 3,86 bps consome quase todo o orçamento antes
   de o primeiro nível ser tocado. 1000FLOKIUSDT tem 124 mil de profundidade e teto de 99 USDT. O
   contrário também: CLOUSDT tem spread de 0,88 bps e só 1.760 USD de profundidade.
3. **Contra o melhor ask** (só profundidade, sem o meio spread) a mediana sobe de 2.174 para 3.536
   USDT. A diferença é o custo que o spread cobra antes de qualquer impacto — e é ela que separa "o
   livro é fino" de "o mercado é caro".

## Como mediríamos aqui

**O que esta tabela decide, e é a pergunta do Everton.** Se o tamanho da posição é
`max_position_pct × equity`, então a tabela vira uma tabela de **capital**:

| Capital (equity) | Posição a 5% (`max_position_pct` Balanced) | Mercados operáveis a ≤ 5 bps | a ≤ 10 bps |
|---|---|---|---|
| 10.000 USDT | 500 | **164/200** | 197/200 |
| 40.000 USDT | 2.000 | **106/200** | 172/200 |
| 200.000 USDT | 10.000 | **50/200** | 90/200 |

Lida assim, ela diz uma coisa simples e útil: **com 10 mil USDT de capital, a capacidade do livro
praticamente não é um problema** — 197 dos 200 mercados absorvem a posição a 10 bps ou menos. A
capacidade só começa a morder a partir de dezenas de milhares.

**E ela desmente uma leitura fácil do piso de liquidez do contrato.** O `min_liquidity_usd_24h` de
50 M USD (perfil Conservative) desligaria 182 dos 232 mercados
([[KB-0066-o-risk-engine-ja-esta-escrito-e-a-medicao-o-contraria]]) — mas para uma posição de 500
USDT a maioria desses mercados custa menos de 5 bps. **O volume de 24 h e a capacidade do livro não
são o mesmo filtro**, e usar o primeiro como proxy do segundo desliga mercados que estavam baratos.

## Hipótese testável no Lab

**Nenhuma no Lab de sombra.** É a base da regra `R-CAP-1` do [[Strategy Backlog]] e do requisito de
proveniência que a torna avaliável:

`R-CAP-M` — **medir esta tabela periodicamente e guardar a série**. Uma leitura única de 11 segundos
não é uma tabela de capacidade; é uma fotografia. O que o M3 precisa é da **distribuição por hora e
por regime** do teto por mercado, e disso só se obtém gravando a leitura. Custo: uma varredura de 200
chaves por intervalo, fora do caminho da decisão.

O que a refutaria: nada — é medição. O que a tornaria **enganosa** é publicá-la sem a fração
censurada pela profundidade de 20 níveis, e sem a hora do dia. As duas coisas estão declaradas acima.

## Por que pode falhar

- **É uma fotografia de 11 segundos de uma tarde de domingo.** A `momentum_v1` dispara em movimento;
  o livro num rompimento não é este livro.
- **Vinte níveis é o que gravamos, não o que existe.** Os três mercados mais líquidos estão
  censurados por essa profundidade, e para eles a tabela **subestima** a capacidade.
- **Custo de travessia não é impacto.** Ele descreve o preço que pagaríamos varrendo o livro parado;
  não inclui a reação do mercado, a fila, nem a recomposição
  ([[KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso]]).
- **Só o lado do ask foi medido.** A saída é simétrica só por suposição, e a saída é onde o custo
  costuma doer mais ([[KB-0064-a-cauda-de-queda-e-o-que-o-risk-engine-vai-precisar]]).
- **O universo gira 26% em 20 h** ([[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]]): os 200
  mercados desta leitura não são os 200 de amanhã.

## Segunda opinião (Astra)

Pendente nesta versão.

## Relacionados

[[Strategy Backlog]] · [[Index]] ·
[[KB-0069-capacidade-e-impacto-o-teto-que-o-livro-impoe]] ·
[[KB-0066-o-risk-engine-ja-esta-escrito-e-a-medicao-o-contraria]] ·
[[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] ·
[[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]] ·
[[KB-0037-o-spread-assumido-contra-o-spread-medido]]
