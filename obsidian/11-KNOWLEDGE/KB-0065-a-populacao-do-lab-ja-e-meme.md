---
tags: [knowledge, nota, memecoins, momentum, reversao]
tema: meme coins / momentum vs reversão e a população do Lab
fonte: medição própria — agent_signals e signal_outcomes da VPS
fonte_url: —
lido_em: 2026-09-06
evidencia: replicado (SQL colado), **abaixo do limiar editorial** — inconclusivo por construção
hipotese_testavel: sim, só diagnóstico
astra: pendente
---

# A população do Lab já é meme

## O que afirma

A pergunta do brief era se meme coins são "mais momentum ou mais reversão" que o resto do universo.
A resposta honesta é que **não dá para saber com 44 toques resolvidos**, e o achado é outro: **o Lab
já opera majoritariamente em altcoin e meme, sem que isso tenha sido decidido**, e a coorte de memes
produz **menos** sinais por mercado que o resto.

O que segue é coorte descritiva, **abaixo do limiar editorial** dos 100 outcomes e 30 dias. Nada
aqui pode ser lido como resultado.

## Onde foi mostrado

**Medição própria, VPS, 2026-09-06, sobre 1.009 sinais emitidos desde 03:40 UTC do mesmo dia**
(cerca de 15 h de operação). Primeiro, quantos sinais cada coorte produz por mercado:

```
      grupo       | mercados_no_grupo | sinais | mercados_com_sinal | sinais_por_mercado
------------------+-------------------+--------+--------------------+--------------------
 A_meme           |                21 |     84 |                 18 |               4.00
 B_meme_nao_ascii |                 5 |      8 |                  3 |               1.60
 C_btc            |                 1 |      1 |                  1 |               1.00
 D_majors         |                23 |     71 |                 21 |               3.09
 E_resto          |               150 |    814 |                133 |               5.43
```

**As memes não são a coorte mais prolífica.** 4,00 sinais por mercado contra 5,43 do resto. E a
coorte B, a mais volátil de todas por ATR%, é a **menos** prolífica das que emitem (1,60) — o que é
compatível com o teto `atr_pct_max = 0,05`, que a
[[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]] mediu recusando 7,0% das barras dessa
coorte, mas **não** demonstrado por este número.

**Estado dos acompanhamentos e resultados**, e é aqui que a leitura tem de parar antes de virar
conclusão:

```
      grupo       |  estado  |  n  |       grupo       |  resultado  |  n  | r_medio
------------------+----------+-----+-------------------+-------------+-----+---------
 A_meme           | active   |   3 |  A_meme           | invalidated |  33 | -0.6745
 A_meme           | no_entry |   3 |  A_meme           | stop        |  21 | -1.1813
 A_meme           | terminal |  78 |  A_meme           | target      |  23 |  1.3154
 B_meme_nao_ascii | terminal |   8 |  A_meme           | expired     |   1 |
 C_btc            | terminal |   1 |  B_meme_nao_ascii | invalidated |   6 | -0.6483
 D_majors         | active   |   1 |  B_meme_nao_ascii | stop        |   2 | -1.0838
 D_majors         | terminal |  70 |  C_btc            | stop        |   1 | -1.6034
 E_resto          | active   |  24 |  D_majors         | invalidated |  33 | -0.8110
 E_resto          | no_entry |  36 |  D_majors         | stop        |  21 | -1.3116
 E_resto          | terminal | 753 |  D_majors         | target      |  16 |  0.8937
                                     E_resto           | invalidated | 280 | -0.6523
 nao entradas por motivo:            E_resto           | stop        | 226 | -1.2479
  A_meme  | late:delay |  3         E_resto           | target      | 233 |  1.2293
  E_resto | geometry   | 28         E_resto           | expired     |  14 |  2.0390
  E_resto | late:delay |  8
```

**Taxa de alvo entre toques resolvidos** (alvo ÷ [alvo + stop], o denominador que a regra do plantão
manda nomear): memes **23/44 = 52,3%**; majors **16/37 = 43,2%**; resto **233/459 = 50,8%**; BTC
0/1. **Quarenta e quatro toques resolvidos não decidem nada** — a diferença entre 52,3% e 50,8% é
menor que a incerteza de amostras desse tamanho, e as observações nem são independentes
([[KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente]]).

O que vale ser olhado, como **descrição** e nada mais: o `r_medio` no alvo das memes (**+1,3154**)
contra o das majors (**+0,8937**), e o `r_medio` no stop (**−1,1813** contra **−1,3116**). Se
sobreviver a mais dados, isso é a assimetria de gap que a
[[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]] previu: barra grande atravessa o alvo por cima e
o stop por baixo, e em quem tem ATR% maior o desvio é maior nos dois sentidos. **Nesta amostra a
direção é favorável às memes nos dois lados, o que é curioso e provavelmente ruído.**

## Como mediríamos aqui

Não medimos ainda, e a ordem importa:

1. **Nada disto pode ser lido como diferença entre coortes** enquanto os 27 sinais de mercados que
   saíram do universo ([[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]]) estiverem sendo
   descartados em silêncio pelo `JOIN` com `is_monitored`, e enquanto a concentração temporal
   (`D-CONC`) não estiver medida.
2. **A pergunta "momentum ou reversão" exige um contraste, não uma taxa.** A `momentum_v1` só
   observa o que ela mesma seleciona; sem o grupo de comparação da `L5`
   ([[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]]) a taxa de alvo por coorte
   não distingue "meme tem momentum" de "meme tem ATR% maior, então o alvo de 1,5 ATR está mais
   longe em preço e mais perto em tempo".
3. **E há um confundidor que é quase determinante:** o alvo e o stop são múltiplos do ATR. Uma coorte
   com ATR% maior tem barreiras mais largas **em preço** e um horizonte igual **em tempo** — então
   qualquer diferença de taxa de alvo entre coortes é, em primeira ordem, uma diferença de
   volatilidade, não de comportamento.

## Hipótese testável no Lab

**`D-MEME-POP` (diagnóstico, roda hoje, sem pré-requisito):** publicar, por coorte de
`meme_universe_v1` e com todos os denominadores da regra do plantão (emitidos · pendentes · entradas
· não entradas por motivo · ativos · alvo · stop · expirados · invalidados · censurados por motivo ·
mercados distintos · dias distintos), a coorte inteira — **incluindo** os mercados que saíram do
universo. É o retrato que esta nota tentou fazer, feito direito.

**`D-MEME-ATRPAR` (diagnóstico, roda hoje):** a mesma taxa de alvo, mas **pareada por decil de
`atr_pct` no instante da decisão**. Se a diferença entre coortes some ao condicionar por
volatilidade, "meme" não acrescenta informação nenhuma sobre comportamento — só sobre volatilidade,
e aí a marcação vira redundante com o que a `momentum_v1` já mede. É a mesma prova de parcimônia que
a sexta rodada exigiu da `L4` ([[KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel]]).

**O que esta nota explicitamente NÃO propõe: nenhum braço de estratégia por coorte de meme.** Nem
"só memes", nem "sem memes", nem parâmetro diferente por coorte. Três razões: 44 toques resolvidos;
a marcação é julgamento meu ([[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]]); e o
confundidor de ATR% acima torna qualquer resultado atribuível a duas causas ao mesmo tempo. Gastar
uma tentativa de estratégia nisso hoje seria gastar mal
([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).

## Por que pode falhar

- **Quarenta e quatro toques resolvidos na coorte A**, em **quinze horas** de operação e um dia
  distinto. O limiar editorial é 100 outcomes **e** 30 dias. Isto é inconclusivo por construção, e a
  palavra "inconclusivo" está aqui de propósito.
- **A amostra é a mesma que gerou a suspeita.** Conta como inspeção, entra no
  [[Registro de Tentativas]], e nada pode ser confirmado nela.
- **Os 27 sinais de mercados que saíram estão fora de todas as tabelas acima**, porque o `JOIN` é
  com `is_monitored`. É viés de sobrevivência que eu introduzi, e está declarado.
- **Observações não independentes.** Cem altcoins reagindo ao mesmo movimento do BTC — e a
  [[KB-0060-correlacao-com-o-btc-e-a-meme-season]] mediu beta mediano de 2,80 nas memes — não são
  cem observações.
- **`r_medio` no alvo maior que 1 não é bom sinal por si.** Significa gap atravessando a barreira, o
  que é execução, não vantagem; e o mesmo mecanismo piora o stop.
- **A `volume_anomaly_v1` e a `momentum_v1` estão misturadas** nas tabelas de outcome acima. São
  estratégias com horizontes diferentes (7.200 s e 14.400 s) e regras diferentes; separá-las é
  requisito do `D-MEME-POP`, e não fazê-lo aqui é limitação desta nota.

## Segunda opinião (Astra)

_(pendente)_

## Relacionados

[[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]] ·
[[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]] ·
[[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] ·
[[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]] ·
[[KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente]] ·
[[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]] ·
[[EXP-0001-momentum-v1]] · [[EXP-0002-volume-anomaly-v1]] · [[Strategy Backlog]] · [[Index]]
