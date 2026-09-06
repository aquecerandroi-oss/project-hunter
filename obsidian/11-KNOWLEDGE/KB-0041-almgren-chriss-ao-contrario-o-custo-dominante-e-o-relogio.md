---
tags: [knowledge, nota, execucao, timing, custos]
tema: Execução e microestrutura do preenchimento
fonte: Almgren & Chriss, "Optimal Execution of Portfolio Transactions" (2000) — conceito lido em **fonte secundária**, o PDF não abriu; medição própria sobre `signal_outcomes.meta.entry_plan` e `candles`
fonte_url: https://questdb.com/glossary/optimal-execution-strategies-almgren-chriss-model/
lido_em: 2026-09-06
evidencia: conceito em fonte secundária + dado próprio (192 entradas, SQL colado, amostra selecionada — só entradas realizadas)
hipotese_testavel: sim
astra: concorda após correções (recusou a primeira versão)
---

# Almgren-Chriss ao contrário: o termo que sobra para nós é o relógio

## O que afirma

Almgren-Chriss formaliza a execução ótima como um problema de média-variância: minimizar
`E[C] + λ·Var[C]`, onde o custo `C` tem um termo de **impacto temporário** (executar rápido custa
caro) e um de **impacto permanente**, e a variância vem do **risco de tempo** — quanto mais devagar
você executa, mais o preço pode andar contra você antes de terminar. A aversão a risco `λ` decide
entre pressa e paciência.

O que esta nota usa do modelo é só a **estrutura do trade-off**: existe um custo de agir rápido e um
risco de esperar, e o segundo cresce com o tempo. Não afirmo que o termo de impacto seja
desprezível para nós — eu tinha escrito que "500 a 5.000 USDT cabem em um a três níveis do book", e
isso não está publicado em lugar nenhum: a [[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] mediu
custo, não níveis consumidos, e **22 de 200 livros nem cobrem 5.000 USDT nos vinte níveis**. A frase
saiu.

O que fica é o outro termo, o **risco de tempo**, porque a nossa arquitetura **já** impõe uma espera e
ela nunca tinha sido medida. Medida agora: entre o fechamento da barra de referência e a abertura da
barra de entrada, o preço se desloca, em **mediana do valor absoluto**, **14,4 bps** (momentum) e
**15,0 bps** (volume anomaly), com **p90 de 44,1 e 49,6 bps**. O custo de execução assumido para a
mesma perna é **6 bps**. Há, portanto, **dispersão de deslocamento de ordem maior que a hipótese de
custo** — o que não é a mesma afirmação que "o relógio custa mais que o book", e a diferença entre as
duas está detalhada abaixo.

## Onde foi mostrado

Almgren-Chriss é conceito de ações institucionais dos anos 1990–2000. **O PDF original não abriu**
(binário ilegível pela ferramenta, duas tentativas); o que li foi um verbete secundário, e por isso
esta nota não cita nenhuma fórmula, coeficiente ou resultado do artigo — só a estrutura do trade-off,
que é o que uso. Correção da Astra aceita: **"a trajetória ótima é curva" não é universal** — sem
aversão a risco e sem drift o modelo admite trajetória linear.

O dado é nosso, da instância local, **sem `as_of` congelado, sem recorte de versão e restrito às
entradas que aconteceram** — a delimitação está em "Por que pode falhar" e não é detalhe:

```sql
WITH e AS (
  SELECT o.signal_id, a.market_id, s2.name AS estrategia,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz AS ref_close_ts,
         (o.meta->'entry_plan'->>'entry_bar_open')::timestamptz  AS entry_open_ts
  FROM signal_outcomes o
  JOIN agent_signals a ON a.id=o.signal_id
  JOIN strategy_versions sv ON sv.id=a.strategy_version_id
  JOIN strategies s2 ON s2.id=sv.strategy_id
  WHERE o.virtual_entry IS NOT NULL AND o.meta->'entry_plan'->>'entry_bar_open' IS NOT NULL
), j AS (
  SELECT e.*, cr.close AS ref_price, ce.open AS entry_open
  FROM e
  LEFT JOIN candles cr ON cr.market_id=e.market_id AND cr.timeframe='1m'
       AND cr.open_time = e.ref_close_ts - interval '1 minute'
  LEFT JOIN candles ce ON ce.market_id=e.market_id AND ce.timeframe='1m'
       AND ce.open_time = e.entry_open_ts
)
SELECT estrategia, count(*) AS entradas,
  round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY (entry_open-ref_price)/ref_price*10000)::numeric,3) AS drift_mediano_bps,
  round(percentile_cont(0.25) WITHIN GROUP (ORDER BY (entry_open-ref_price)/ref_price*10000)::numeric,3) AS p25_bps,
  round(percentile_cont(0.75) WITHIN GROUP (ORDER BY (entry_open-ref_price)/ref_price*10000)::numeric,3) AS p75_bps,
  round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY abs((entry_open-ref_price)/ref_price*10000))::numeric,3) AS abs_mediano_bps,
  round(percentile_cont(0.9)  WITHIN GROUP (ORDER BY abs((entry_open-ref_price)/ref_price*10000))::numeric,3) AS abs_p90_bps
FROM j WHERE ref_price IS NOT NULL AND entry_open IS NOT NULL AND ref_price > 0
GROUP BY estrategia ORDER BY estrategia;
```

```
   estrategia   | entradas | drift_mediano_bps | p25_bps | p75_bps | abs_mediano_bps | abs_p90_bps
----------------+----------+-------------------+---------+---------+-----------------+-------------
 Momentum       |       90 |            -0.065 | -13.339 |  17.000 |          14.362 |      44.068
 Volume Anomaly |      102 |             0.000 | -14.681 |  14.646 |          15.037 |      49.631
```

E o relógio que produz isso (mesma CTE `e` da consulta anterior):

```sql
SELECT estrategia, count(*) AS n,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM decision_at-ref_close_ts))::numeric,2)  AS decisao_menos_ref_s,
  round(percentile_cont(0.9) WITHIN GROUP (ORDER BY extract(epoch FROM decision_at-ref_close_ts))::numeric,2)  AS p90_decisao_s,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM entry_open_ts-ref_close_ts))::numeric,2) AS entrada_menos_ref_s,
  round(min(extract(epoch FROM entry_open_ts-ref_close_ts))::numeric,2) AS min_s,
  round(max(extract(epoch FROM entry_open_ts-ref_close_ts))::numeric,2) AS max_s
FROM e GROUP BY estrategia ORDER BY estrategia;
```

```
   estrategia   |  n  | decisao_menos_ref_s | p90_decisao_s | entrada_menos_ref_s | min_s | max_s
----------------+-----+---------------------+---------------+---------------------+-------+--------
 Momentum       |  90 |               62.16 |        104.66 |              120.00 | 60.00 | 120.00
 Volume Anomaly | 102 |               44.27 |         90.22 |               60.00 | 60.00 | 120.00
```

Mediana de **120 s** entre referência e entrada no momentum, **60 s** no volume. E os `no_entry`:

```sql
SELECT tracking_state, no_entry_reason, count(*) FROM signal_outcomes GROUP BY 1,2 ORDER BY 1,2;
--  tracking_state | no_entry_reason | count
-- ----------------+-----------------+-------
--  active         |                 |    14
--  terminal       |                 |   175
--  no_entry       | geometry        |     5
--  no_entry       | late:delay      |    19
--  censored       |                 |     3
```

**19 recusas por atraso e 5 por geometria, em 216.** A espera não só desloca o preço: às vezes anula
a operação — e é exatamente por isso que a distribuição de deslocamento acima é **de amostra
selecionada**, tema do próximo bloco.

## Como mediríamos aqui

**Primeiro, o que a medição sustenta e o que não sustenta.** A mediana **assinada** é ~zero (−0,065 e
0,000 bps) e a mediana **absoluta** é ~14 bps. Eu tinha concluído daí "é variância, não viés". A
Astra recusou, com um contraexemplo que não tem resposta: os deslocamentos `−1, 0, +100` têm mediana
zero e **média +33**. Quantis não determinam média. O enunciado correto é o mais fraco:

> **Há dispersão relevante do deslocamento referência→entrada, e a mediana assinada está próxima de
> zero. O viés médio, e o viés condicionado ao lado, ainda não foram estimados.**

**Segundo, a geometria congelada.** `stop` e `target` são fixados na referência e só revalidados
contra `P_entry` (`plan.py`), e o denominador de `R_net` é `P_entry − stop` (`pricing.py:74`). Logo
deslocamentos simétricos **não** produzem efeitos simétricos no R do alvo. Exemplo sem custos,
referência 100, stop 97, alvo 103:

| Entrada | Risco até o stop | Ganho até o alvo | R bruto no alvo |
|---|---:|---:|---:|
| 99 | 2 | 4 | **2,0** |
| 100 | 3 | 3 | **1,0** |
| 101 | 4 | 2 | **0,5** |

**E é só isso que a tabela demonstra: não linearidade no R do alvo.** Ela **não** demonstra queda de
expectancy — faltam probabilidade de toque, trajetória, expiração e a seleção pelas recusas. Mantida
a mesma saída e a mesma quantidade, o efeito no PnL bruto seria linear. Correção de vocabulário que a
Astra exigiu, porque eu tinha escrito ao contrário: para uma **compra**, alta antes da entrada
**piora o preço e afasta a entrada do stop**; queda **aproxima do stop e melhora o preço**.

É a versão quantitativa do "1 R nominal na referência, nunca 1 R garantido na entrada" que o
`SHADOW-LAB.md` já declara.

Comparação de escalas, com a advertência de que **as quatro linhas medem objetos diferentes** e a
última nem é custo:

| Componente | Mediana | p90 |
|---|---|---|
| Meio spread (medido, `market_snapshots`) | ~1,15 bps | ~4 bps |
| Atravessar o ask, 1.000 USDT (medido, book) | 3,47 bps | 8,08 bps |
| Taxa por lado (exemplo do FAQ, taker) | 5 bps | 5 bps |
| **\|Deslocamento referência→entrada\| (medido)** | **14,4 bps** | **44,1 bps** |

A última linha é **movimento de mercado**, não preço pago, e o seu efeito sobre o R **já está
incorporado** em `P_entry`. Cobrá-la de novo como custo seria contar duas vezes.

## Hipótese testável no Lab

**`EXEC-F` — decompor o que hoje chamamos de "custo".** Para cada entrada já colhida, publicar
lado a lado, em bps **e** em fração de 1 R efetivo: (a) o deslocamento referência→entrada, assinado e
absoluto; (b) os 6 bps assumidos; (c) a taxa; (d) o funding apurado. Estratificar por atraso efetivo
(60 s contra 120 s) e por decil de ATR%. **A pergunta:** o deslocamento explica parte da diferença
entre o R nominal na referência e o R efetivo na entrada?

**H2 já existe e é a variante certa.** A [[KB-0009-o-efeito-do-quarto-de-hora]] já especificou a
única variante de execução desta família: entrar na abertura `baseline + 60 s`, **pareada**, com as
recusas publicadas. Esta nota **não** propõe uma segunda.

**O que eu escrevi e retiro:** que "o efeito é da ordem de 14 bps, logo a H2 tem poder estatístico
plausível". Não segue. A dispersão do deslocamento **baseline** não determina nem o tamanho nem a
variância da **diferença pareada** entre baseline e `baseline + 60 s`, que é o que a H2 mede. O
cálculo de poder é da H2 e tem de ser feito com a distribuição da diferença, não com a do nível.

**Refutação do `EXEC-F`, também estreitada:** comparar as distribuições dos grupos de 60 s e 120 s
**não** isola o efeito do atraso — os grupos são observacionais e diferem em estratégia, mercado,
hora e volatilidade. O `EXEC-F` descreve a decomposição; quem testa o efeito do atraso é a H2, que é
pareada por construção.

## Por que pode falhar

- **Conceito lido em fonte secundária.** Nenhuma fórmula de Almgren-Chriss é citada, e a analogia
  "risco de tempo" é minha, não deles: eles falam de fatiar uma ordem grande, nós de esperar uma
  barra.
- **192 entradas, um dia, uma instância.** Está muito abaixo do limiar editorial de 100 outcomes **e**
  30 dias.
- **A amostra é selecionada.** A consulta pega **só as entradas que aconteceram**, sem `as_of`
  congelado e sem recorte de versão, e agrupa por nome de estratégia. Os 19 `late:delay` e os 5
  `geometry` **saíram** da distribuição — e são candidatos naturais a serem justamente os casos de
  maior deslocamento. Uma leitura ingênua conclui que a espera tem pouco risco porque os piores casos
  foram removidos.
- **A barra de referência é agregada, e o preço que usei está certo por acaso feliz.** A `momentum_v1`
  avalia sobre barras de **15 min** e a `volume_anomaly_v1` sobre **5 min**, tomando o `close` da
  última barra agregada; e `aggregate.py:86` define `close = minutes[-1].close`. Então, para uma
  referência às 12:00, tanto `[11:45,12:00)` quanto `[11:55,12:00)` fecham com a vela de 1 min
  `[11:59,12:00)` — que é exatamente a que o `JOIN` em `ref_close_ts − 1 minute` pega. Achado da
  Astra, conferido. **Quem repetir a medição não deve "corrigir" o JOIN para −15 min ou −5 min: isso
  introduziria o erro.**
- **Deslocamento não é custo de execução.** É movimento de mercado entre dois instantes. Cobrá-lo
  como slippage seria o erro que a [[KB-0009-o-efeito-do-quarto-de-hora]] nomeou. Aqui ele é
  apresentado como **risco de tempo**, categoria diferente, que afeta a geometria e não o preço pago.
- **Mediana ~zero não é ausência de viés.** Quantis não determinam média; a média e o viés
  condicionado ao lado continuam por estimar.

## Segunda opinião (Astra)

**Recusou a primeira versão em três pontos, todos aceitos.**

1. **"Variância, não viés" não é conclusão sustentada.** O SQL calcula quantis, não média nem
   variância. Contraexemplo dela: `−1, 0, +100` tem mediana zero e média +33. O enunciado foi
   substituído pelo mais fraco e correto, em bloco de citação no corpo.
2. **A não linearidade da geometria não prova deterioração.** A tabela 99/100/101 demonstra que o R
   do alvo muda de forma assimétrica; não demonstra queda de expectancy, porque faltam probabilidade
   de toque, trajetória, expiração e a seleção pelas recusas. E o efeito do deslocamento sobre o R
   **já está incorporado** em `P_entry` — cobrá-lo de novo seria contar duas vezes. Ela também
   corrigiu a minha frase invertida sobre o lado: para uma compra, alta piora o preço e **afasta** do
   stop.
3. **A amostra é selecionada e não estava declarada.** Só entradas realizadas, sem `as_of` nem
   recorte de versão; os 19 `late:delay` e 5 `geometry` estão fora e podem ser os de maior
   deslocamento. Acrescentei a consulta de recusas e a delimitação. Cortadas também a alegação de
   "poder estatístico plausível" da H2 e a refutação por comparação dos grupos de 60/120 s, que são
   observacionais.

**Achado dela que salvou a medição:** eu tinha declarado como risco a suposição de que a barra de
referência fosse de 1 minuto. Ela conferiu o código — momentum agrega 15 min, volume 5 min, e
`aggregate.py:86` define `close = minutes[-1].close` — e mostrou que o `JOIN` em `−1 minuto` está
**certo**, e que "consertá-lo" para −15 ou −5 min introduziria erro.

Divergência: nenhuma que sobreviva à revisão.

## Relacionados

[[Strategy Backlog]] · [[KB-0009-o-efeito-do-quarto-de-hora]] ·
[[KB-0042-o-open-nao-e-preco-executavel]] ·
[[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] ·
[[KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] · [[EXP-0001-momentum-v1]] ·
[[EXP-0002-volume-anomaly-v1]]
