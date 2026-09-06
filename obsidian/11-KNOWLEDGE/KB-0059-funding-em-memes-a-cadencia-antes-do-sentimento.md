---
tags: [knowledge, nota, memecoins, funding, perpetuos]
tema: meme coins / funding e posicionamento
fonte: medição própria — funding_rates da VPS (2.136 liquidações, 229 mercados) + documentação de funding da Binance
fonte_url: https://www.binance.com/en/support/faq/detail/360033525031
lido_em: 2026-09-06
evidencia: replicado (SQL colado) + documentação
hipotese_testavel: sim
astra: pendente
---

# Funding em memes — a cadência antes do sentimento

## O que afirma

"Meme coin tem funding extremo" é uma das frases mais repetidas do mercado. Medi as **2.136 taxas de
funding efetivamente liquidadas** na VPS, e a coorte de memes tem funding **menos** extremo que o
resto do universo: média do valor absoluto de **1,07 bps** contra **2,32 bps** do resto, e a cauda
negativa profunda (−64,8 bps) está fora das memes, não dentro.

E antes de qualquer leitura de sentimento vem um fato mecânico que engole metade da diferença entre
grupos: **a mediana de funding de um mercado depende de qual cadência de liquidação ele usa**, não
de quão eufórico ele está.

## Onde foi mostrado

**Medição própria, VPS, 2026-09-06**, sobre a tabela `funding_rates` (taxa **liquidada**, não a
estimativa em formação — a distinção é a da [[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]]).

```sql
SELECT cls.grupo, count(*) AS liquidacoes, count(DISTINCT f.market_id) AS mercados,
  round((10000*percentile_cont(0.5) WITHIN GROUP (ORDER BY f.rate))::numeric,4) AS mediana_bps,
  round((10000*percentile_cont(0.05) WITHIN GROUP (ORDER BY f.rate))::numeric,4) AS p05_bps,
  round((10000*percentile_cont(0.95) WITHIN GROUP (ORDER BY f.rate))::numeric,4) AS p95_bps,
  round((10000*min(f.rate))::numeric,4) AS min_bps, round((10000*max(f.rate))::numeric,4) AS max_bps,
  round((100.0*count(*) FILTER (WHERE abs(f.rate) >= 0.0005)/count(*))::numeric,1) AS pct_acima_5bps,
  round((10000*avg(abs(f.rate)))::numeric,4) AS media_abs_bps
FROM funding_rates f JOIN cls ON cls.id = f.market_id GROUP BY 1 ORDER BY 1;
```

```
      grupo       | liquidacoes | mercados | mediana_bps | p05_bps | p95_bps | min_bps  | max_bps | pct_acima_5bps | media_abs_bps
------------------+-------------+----------+-------------+---------+---------+----------+---------+----------------+---------------
 A_meme           |         204 |       21 |      0.5000 |  0.3355 |  4.7822 |  -0.9817 |  9.9453 |            4.4 |        1.0722
 B_meme_nao_ascii |          47 |        5 |      1.1217 |  0.5000 |  7.0158 |   0.5000 | 19.1238 |            8.5 |        2.4447
 C_btc            |           6 |        1 |      0.2109 |  0.0141 |  0.3395 |  -0.0150 |  0.3589 |            0.0 |        0.1964
 D_majors         |         138 |       23 |      1.0000 | -0.4892 |  1.0556 |  -1.9851 | 15.7967 |            4.3 |        1.0808
 E_resto          |        1491 |      150 |      0.5000 | -8.0194 |  3.3645 | -64.8302 | 15.1404 |            9.8 |        2.3160
```

Três leituras, em ordem de importância:

1. **A mediana das memes (0,50 bps) é metade da mediana das majors (1,00 bps) — e isso é cadência,
   não sentimento.** A taxa base da Binance é 0,01% por ciclo de 8 h (1 bps) e 0,005% por ciclo de
   4 h (0,5 bps). A segunda consulta confirma:

```
      grupo       | mercados | min_liq | media_liq | max_liq | cadencia_4h_ou_menor | cadencia_8h
------------------+----------+---------+-----------+---------+----------------------+-------------
 A_meme           |       21 |       6 |      9.71 |      11 |                   16 |           4
 B_meme_nao_ascii |        5 |       3 |      9.40 |      11 |                    4 |           1
 C_btc            |        1 |       6 |      6.00 |       6 |                    0 |           1
 D_majors         |       23 |       6 |      6.00 |       6 |                    0 |          23
 E_resto          |      150 |       3 |      9.92 |      43 |                  106 |          40
```

   **Todas as 23 majors e o BTC liquidam a cada 8 h; 16 das 21 memes liquidam a cada 4 h ou menos.**
   Comparar medianas de funding entre grupos sem normalizar por cadência é comparar a taxa de
   contratos diferentes. Um mercado do `E_resto` teve **43 liquidações** em dois dias — cadência de
   1 h, que é o piso comprimido da Binance quando a taxa bate no teto
   ([[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]]).

2. **O extremo mora fora das memes.** O funding mais negativo do universo foi de **−64,8 bps** num
   mercado do `E_resto`; a meme mais negativa da coorte A ficou em **−0,98 bps**. E 9,8% das
   liquidações do resto passaram de 5 bps em módulo, contra 4,4% das memes.

3. **A coorte B é a que mais parece com o folclore**: mediana 1,12 bps, máximo 19,1 bps, 8,5% acima
   de 5 bps, e **nenhuma taxa negativa** — todo mundo comprado, pagando para ficar. Cinco mercados
   novos e ilíquidos, e é exatamente onde a confusão meme × listagem recente da
   [[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]] impede atribuir isso a "ser meme".

## Como mediríamos aqui

Custo, não previsão. Para uma posição comprada com o horizonte de 4 h da `momentum_v1`, atravessar
uma liquidação custa a taxa daquele instante. Com a mediana de 0,5 bps das memes e um `R` efetivo
que a [[KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker]] estimou na casa de 51 bps para o
exemplo, um atravessamento na mediana consome cerca de **1%** de 1 R. No p95 da coorte B (7,0 bps),
consome cerca de 14%. **Isso é aritmética sobre um exemplo, não medição do nosso resultado.**

O que **não** dá para fazer com estes números: usar funding como filtro direcional. A T-016 já foi
retirada em 2026-09-06 pela evidência direta de que o poder preditivo à frente por ativo é ~zero
([[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]]), e nada aqui contraria aquilo. A
única coisa nova é que a **premissa empírica do folclore de meme também não se sustenta**: elas nem
sequer são o grupo de funding mais extremo.

## Hipótese testável no Lab

**`D-MEME-FUND` (diagnóstico, testável agora, perpétuo da Binance).** Duas perguntas, nesta ordem:

1. **Cadência antes de tudo.** Para cada mercado com sinal, o número de liquidações por dia e a
   cadência inferida, publicados **junto** de qualquer estatística de funding. Nenhuma comparação
   entre coortes é publicada sem essa coluna. Isto é convenção, não teste.
2. **Custo de funding realizado por coorte**, sobre os outcomes já colhidos: para cada
   acompanhamento, quantas liquidações ele atravessou (separando **confirmado**, **inferido** e
   **indeterminado**, como a [[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] exige) e
   quanto isso somou em bps sobre o notional. É o `D-016` da terceira rodada com a estratificação
   por `meme_universe_v1` acrescentada.

**Pré-requisito que continua faltando:** `next_funding_time` tem **zero linhas** em
`market_snapshots` na VPS (medido hoje: `count(next_funding_time) = 0` em 235.457 linhas). Sem ele,
"atravessou uma liquidação" continua sendo inferência a partir da cadência modal, com todo o
problema que a KB-0026 registrou.

**O que não proponho, e é deliberado:** nenhum braço de sombra sobre funding de meme. Duas rodadas
já registraram que a evidência aponta para poder preditivo nulo, e esta acrescenta que a premissa
descritiva do folclore também é falsa. Gastar tentativa contra duas priors desfavoráveis é o oposto
do que a [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] pede.

## Por que pode falhar

- **Amostra minúscula.** Seis liquidações para o BTC, 204 para as 21 memes, num intervalo de 45 h.
  Nenhum quantil aqui é estimativa estável, e o p05/p95 de um grupo com 47 observações é ruído.
- **Um regime só.** Dois dias sem stress. Funding extremo é fenômeno de euforia e de cascata; a
  janela não contém nenhuma das duas.
- **`funding_rates` é a taxa liquidada**, então ela **omite** a estimativa em formação — que é o que
  a feature `funding_rate` do M2 lê. As duas não são a mesma grandeza (KB-0019), e esta nota mede a
  primeira.
- **A comparação entre coortes está confundida por cadência, tamanho e idade ao mesmo tempo.** Eu
  publiquei a cadência justamente para não deixar isso implícito, mas publicar não desconfunde.
- **A coorte B tem 47 observações em 5 mercados novos.** Que ela não tenha nenhuma taxa negativa
  pode ser euforia ou pode ser que 47 amostras num mercado recém-listado simplesmente não contenham
  o outro lado.

## Segunda opinião (Astra)

_(pendente)_

## Relacionados

[[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]] ·
[[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] ·
[[KB-0023-funding-extremo-como-contrarian-a-afirmacao-mais-repetida]] ·
[[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] ·
[[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]] · [[Strategy Backlog]] · [[Index]]
