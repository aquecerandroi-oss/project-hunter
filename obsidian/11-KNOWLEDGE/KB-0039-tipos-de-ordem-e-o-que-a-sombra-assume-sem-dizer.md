---
tags: [knowledge, nota, execucao, ordens, perpetuos]
tema: Execução e microestrutura do preenchimento
fonte: Documentação de USDⓈ-M Futures da Binance (Common Definition — order types e timeInForce) + `plan.py`/`walker.py`/`pricing.py` do Shadow Lab
fonte_url: https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition
lido_em: 2026-09-06
evidencia: documentação da exchange (lida) + leitura do nosso código
hipotese_testavel: sim
astra: concorda após correções (recusou a primeira versão)
---

# Tipos de ordem, e o que a sombra assume sem dizer

## O que afirma

A documentação da Binance para USDⓈ-M lista os tipos `LIMIT`, `MARKET`, `STOP`, `STOP_MARKET`,
`TAKE_PROFIT`, `TAKE_PROFIT_MARKET` e `TRAILING_STOP_MARKET`, e os `timeInForce` `GTC`, `IOC`, `FOK`,
`GTX` ("Good Till Crossing", **post only**), `GTD` e `RPI` (post only que só casa com ordem vinda do
app ou da web).

O Shadow Lab **não escolhe** nenhum deles — e é justamente isso que precisa ser dito em voz alta. O
que o modelo faz (`P_entry = open × (1 + 6/10000)`, saída no toque com deslocamento adverso, taxa nos
dois lados) é **preenchimento sintético por barras**, na linguagem do próprio `SHADOW-LAB.md` §3:
**preenchimento hipotético integral com deslocamento adverso**, compatível com uma **aproximação de
execução agressiva**. Não é a implementação de uma `MARKET` — não há quantidade, não há filtro de
lote, não há verificação de executável. É uma escolha de política embutida na aritmética, que nunca
aparece como parâmetro e portanto nunca pode ser questionada por um resultado.

As três consequências que ninguém escreveu:

1. **O perfil de custo é o de quem atravessa**, então a taxa coerente seria a de taker
   ([[KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker]]) — sem que isso identifique a ordem como
   taker, porque preço sintético sobre OHLC não identifica ordem nenhuma.
2. **A saída no stop usa o mesmo deslocamento de 6 bps da entrada.** Isso é uma hipótese de simetria
   entre dois instantes diferentes, e num stop, por definição, o mercado está indo contra. Não digo
   que a hipótese seja falsa — digo que ela é gratuita e nunca foi enunciada.
3. **Não existe recusa por não preenchimento.** O Lab tem `no_entry: late` e `no_entry: geometry`,
   nunca `no_entry: nao_preencheu`. E o preenchimento integral é **suposto**, não verificado: uma
   quantidade real que violasse o filtro `MARKET_LOT_SIZE` da Binance seria recusada pela exchange
   enquanto a sombra registraria a entrada.

## Onde foi mostrado

Documentação do produto. E o nosso código: `plan.py` escolhe a **barra** de entrada e valida a
geometria; `pricing.py` aplica o deslocamento; `walker.py` decide a saída por toque intrabar com a
convenção pessimista (stop e alvo na mesma barra → stop). Em nenhum ponto existe um campo "tipo de
ordem" ou "política de execução". O envelope congela `spread_bps`, `slippage_bps`, `fee_bps` e
`max_entry_delay_s`; a política é implícita.

## Como mediríamos aqui

O que a sombra pode e o que não pode, com honestidade:

| Política | Taxa | O que o Lab conseguiria modelar | O que ele **não** conseguiria |
|---|---|---|---|
| Aproximação agressiva (hoje) | taker | preço sintético e geometria | quantidade executável, filtros de lote, preenchimento parcial |
| `LIMIT` `IOC` no toque | taker | o preço-limite | quanto preencheu — não temos o book do instante |
| `LIMIT` `GTX` (post only) | maker | o preço, se preencher | **se** preencher, e quando — precisa de fila, não de OHLC |
| `STOP_MARKET` na saída | taker | o preço sintético do toque | o deslize real num stop em movimento adverso |

A coluna que importa é a última. Modelar post-only exigiria estimar probabilidade de preenchimento,
que depende de posição na fila e de fluxo agressor no nível — dado que **não persistimos**
([[KB-0044-o-que-morre-em-dez-segundos]]). Com OHLC de 1 minuto só se pode dizer "o preço tocou o
nível", e tocar não é preencher: é a mesma armadilha que a
[[KB-0009-o-efeito-do-quarto-de-hora]] já nomeou para o slippage.

## Hipótese testável no Lab

**`EXEC-D` — descrição do contexto de saída e sensibilidade. Não é teste de simetria de execução.**
Hoje o deslocamento é `6 bps` igual nas duas pernas. Medir, sobre os encerramentos já colhidos:

- distribuição da amplitude da barra de saída (`(high − low)/open`) **separada por `result`**
  (target, stop, expired, invalidated) — como **descrição do contexto**, não como medida de custo;
- fração de saídas por **gap na abertura** (o `walker.py` já trata gap antes de toque) contra saídas
  por toque intrabar;
- e a sensibilidade do resultado a um deslocamento de saída **maior** que o de entrada (por exemplo
  9 bps na saída contra 6 na entrada), como coluna de sensibilidade, **sem** trocar a hipótese
  congelada.

**O que o `EXEC-D` explicitamente não pode fazer, e a Astra tem razão:** confirmar ou refutar a
simetria de execução com OHLC. Duas velas com a mesma amplitude podem ter profundidade dez vezes
diferente; uma vela ampla pode ter spread estreito e book fundo. Pior: selecionar as barras que
tocaram o stop já condiciona a distribuição da amplitude. Amplitude é **contexto**, não custo — e
concluir "a simetria de 6 bps é defensável" a partir dela seria o mesmo erro de "excursão é
slippage" que a [[KB-0009-o-efeito-do-quarto-de-hora]] nomeou.

**Refutação, então, do quê?** Da hipótese de que o contexto de saída seja indistinguível do de
entrada. Se a amplitude e a taxa de gap na saída por stop forem parecidas com as da barra de entrada,
não há motivo aparente para suspeitar de assimetria, e a sensibilidade de 9 bps vira exercício.
Se forem muito diferentes, continua-se sem medir o custo — mas com motivo para persistir book na
saída ([[KB-0044-o-que-morre-em-dez-segundos]]).

**O que esta nota NÃO propõe:** simular post-only. Sem book persistido, qualquer taxa de
preenchimento seria inventada, e um número inventado sobre execução é exatamente o tipo de coisa que
o Lab existe para não produzir.

## Por que pode falhar

- **Amplitude de barra não é custo de execução**, nem sequer indício confiável dele: a relação com a
  profundidade não é monotônica.
- **A convenção pessimista e o deslocamento são mecanismos separados.** Eu tinha escrito que somar um
  deslocamento maior no stop seria "dupla penalização"; não é. A prioridade intrabar (stop antes de
  alvo, `walker.py:155`) escolhe **qual evento** encerrou; o deslocamento (`pricing.py:53`) precifica
  **a execução desse evento**. Um stop que realmente ocorreu antes e encontrou pouca liquidez tem as
  duas coisas de verdade.
- **`RPI` e `GTX` são detalhes de venue.** Nada disso se aplica antes do M4, e o M4 tem Risk Engine na
  frente de qualquer ordem. Esta nota é preparação de vocabulário, não plano de execução.
- **Documentação muda.** A lista de `timeInForce` foi lida em 2026-09-06.

## Segunda opinião (Astra)

Concorda que o achado é "a política de execução existe e é implícita". **Recusou a primeira versão em
três pontos**, todos aceitos:

1. **"É o modelo de uma ordem a mercado", "sempre preenche" e "nada a acrescentar" são fortes
   demais.** O código calcula preço sintético e aceita a entrada por geometria; não verifica
   quantidade executável. Cenário dela: uma quantidade viola o filtro `MARKET_LOT_SIZE` da Binance, a
   ordem real é recusada e a sombra registra entrada. Formulação adotada: **preenchimento hipotético
   integral com deslocamento adverso, compatível com uma aproximação de execução agressiva**.
2. **Amplitude de barra não valida nem refuta simetria de execução.** Duas velas de mesma amplitude
   podem ter profundidade dez vezes diferente, e selecionar barras que tocaram o stop condiciona a
   própria distribuição da amplitude. O `EXEC-D` foi rebaixado a descrição de contexto mais
   sensibilidade.
3. **"Dupla penalização" estava errado.** Prioridade intrabar e deslocamento são mecanismos
   separados: um escolhe o evento, o outro precifica a execução dele.

Nice-to-have aceito: chamar o perfil de **preenchimento sintético por barras**, como no contrato do
`SHADOW-LAB.md`. Divergência: ela achava que o deslocamento assimétrico de saída deveria virar
variante prospectiva agora; na revisão desta rodada **retirou a exigência** — fica como sensibilidade
sobre dado já colhido.

## Relacionados

[[Strategy Backlog]] · [[KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker]] ·
[[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] ·
[[KB-0042-o-open-nao-e-preco-executavel]] · [[KB-0044-o-que-morre-em-dez-segundos]] ·
[[KB-0005-stops-quando-eles-param-perdas]] · [[EXP-0001-momentum-v1]] · [[Risk Engine]]
