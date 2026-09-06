---
tags: [knowledge, nota, regime, momentum, risco, custo]
tema: regime de mercado e volatilidade
fonte: Daniel & Moskowitz, "Momentum crashes", JFE 122(2):221-247 (2016) — resumo lido no NBER w20439; Barroso & Santa-Clara, "Momentum has its moments", JFE (2015) — números lidos em fontes secundárias; e o nosso `momentum_v1.py`
fonte_url: https://www.nber.org/papers/w20439 · https://mpra.ub.uni-muenchen.de/83510/1/MPRA_paper_83510.pdf
lido_em: 2026-09-06
evidencia: estudo revisado (Daniel & Moskowitz lido em resumo; Barroso & Santa-Clara lido em fonte secundária, o original **não foi aberto**)
hipotese_testavel: sim
astra: pendente
---

# Momentum crashes, escalar ≠ filtrar, e o piso de custo que virou filtro de regime

## O que afirma

Daniel & Moskowitz (2016) mostram que momentum, apesar do retorno médio positivo em muitas classes
de ativo, sofre **quebras infrequentes e persistentes** — e que elas são **parcialmente
previsíveis**: acontecem em "estados de pânico", isto é, **depois de quedas de mercado e quando a
volatilidade de mercado está alta**, e coincidem com a recuperação. A explicação que eles propõem é
de opcionalidade: nesses estados os perdedores passados carregam um payoff parecido com opção, com
prêmio condicionalmente alto, o que derruba o retorno esperado da perna vendida. Uma estratégia
dinâmica baseada em previsões da média e da variância do momentum **aproximadamente dobra o alfa e o
índice de Sharpe** da versão estática.

Barroso & Santa-Clara (2015) chegam ao mesmo lugar por um caminho mais simples: escalar o momentum
pelo inverso da volatilidade realizada recente, mirando volatilidade constante. Números citados em
fontes secundárias: Sharpe de **0,97** contra **0,53** da versão não gerenciada, alvo de volatilidade
anualizada de 12%, e a observação de que o **valor** do alvo não altera o Sharpe. Não abri o original;
os números entram como leitura de segunda mão.

**A lição operacional das duas, e ela é uma só: a resposta ao regime de alta volatilidade na
literatura é _escalar a exposição_, não _filtrar a entrada_.**

## Onde foi mostrado

Ações americanas, carteiras long-short mensais, décadas de história (Daniel & Moskowitz também
reportam robustez em mercados internacionais e outras classes). Frequência mensal, sem custo de
funding, com giro de carteira. Nada disso é um perpétuo de cripto em 15 minutos; a transferência é
declaradamente frouxa.

## O que isso ilumina no nosso desenho

Nós não escalamos nada — o Lab é de sombra e não dimensiona posição. O que nós fazemos é **filtrar
por volatilidade**, e o filtro é absoluto:

```python
# packages/core/hunter_core/strategies/momentum_v1.py:83-84
"atr_pct_min": Decimal("0.003"),
"atr_pct_max": Decimal("0.05"),
```

A entrada exige que o ATR%(Wilder 14 em 15m) esteja dentro de `[0,003 ; 0,05]`. E a
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] propõe subir o piso para `0,0089` por aritmética de
custo. O ponto desta nota:

> Um piso **absoluto** sobre uma quantidade cuja distribuição se move com o regime **é um filtro de
> regime disfarçado de filtro de custo** — e o seu ciclo de trabalho nunca foi medido.

A [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] observou, no BTC e em **dois dias com hora
e dia confundidos**, uma amplitude de 2,9× entre a hora mais calma e a mais agitada. **Se** isso for
efeito de hora — e a nota é explícita em que ainda não sabemos — e **se** a distribuição transversal
do ATR% respirar na mesma escala, então o mesmo piso admitiria populações muito diferentes conforme
a hora. Nesse cenário o piso não escolheria "operações com custo suportável"; escolheria **horas do
dia**, sem ninguém ter decidido isso. Nada disso está demonstrado: é o motivo de a H-KB0035a existir.

Duas notas de cuidado sobre o próprio `atr_pct_min`:

- **o ATR que o filtro usa não é o que está em `feature_snapshots`** — e eu quase escrevi uma
  hipótese que media a coisa errada (achado da Astra). A `momentum_v1` calcula o **seu próprio** ATR
  a cada avaliação, com `rolling_window_v1` sobre `ctx.candles_1m` agregado em 15m
  (`momentum_v1.py:80-82,137-154`: `atr_period=14`, `atr_timeframe=M15`, `atr_bars=97`). O
  `atr_14_pct` do `feature_snapshots` é o **checkpoint ancorado** do M2 (`features/atr.py`), com
  origem que não se move e política declaradamente diferente. Dois números, dois nomes, nenhum é o
  outro — e o filtro consome o primeiro;
- `atr_pct_max = 0,05` é o outro lado da mesma moeda: um teto absoluto que, num regime de pânico,
  desliga a estratégia inteira — o que pode ser exatamente o certo (Daniel & Moskowitz), mas por
  acidente e sem ninguém ter escrito que era esse o objetivo.

## Hipótese testável no Lab

**H-KB0035a (diagnóstica, e é pré-requisito das outras).** Medir o **ciclo de trabalho do piso**: a
fração de mercados com ATR% dentro de `[atr_pct_min, atr_pct_max]` por hora UTC, com denominador em
cada célula (mercados avaliados, com leitura utilizável, excluídos por motivo).

> **O instrumento tem de ser o certo, e essa é a parte que eu errei na primeira escrita.** Medir
> isso em `feature_snapshots.atr_14_pct` **não responde a pergunta**, porque não é o número que o
> filtro consome. Dois caminhos honestos: (a) persistir no envelope do sinal o ATR% que a
> `momentum_v1` de fato calculou no instante da decisão — que é o carimbo pedido em
> [[KB-0030-o-regime-nao-chega-ao-sinal]], estendido; ou (b) recomputar `rolling_window_v1` sobre as
> velas persistidas, replicando `atr_bars=97` em 15m, e declarar que é uma reconstrução. Nunca (c)
> usar o ATR do M2 e chamar de o mesmo.

- **Confirmação de que o piso é um filtro de regime:** a fração admitida varia por um fator ≥ 2
  entre a hora mais calma e a mais agitada — **e** isso persiste depois de separar hora de dia, o
  que a [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] ainda não conseguiu fazer.
- **Refutação:** fração aproximadamente constante — o piso é mesmo só custo, e esta nota é ruído.
- **O que a confirmação muda:** a proposta de subir o piso para 0,0089
  ([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]) deixa de ser uma decisão só de aritmética de
  custo e passa a exigir a pergunta "quanto do universo, e em que horas, isso desliga?". Continua
  precisando de janela futura reservada.

**H-KB0035b (não é para agora, e digo por quê).** A resposta da literatura — escalar exposição pelo
inverso da volatilidade — **não tem onde ser testada no Lab de hoje**: sombra não dimensiona posição,
e `PnL de carteira` é explicitamente *não aplicável* nas avaliações. Registro a candidata para o M4,
onde existe tamanho de posição, e **não** abro braço de sombra para ela. Fazer o contrário seria
gastar dia de sombra numa pergunta que o instrumento não responde.

## Por que pode falhar

- **Transferência de horizonte e de mercado.** Momentum crashes são de carteiras mensais long-short
  em ações. A `momentum_v1` é um único mercado, 15 minutos, sem perna vendida sistemática. A
  intuição "cuidado com alta volatilidade após queda" pode valer; o mecanismo de opcionalidade dos
  perdedores **não transfere**, porque não temos perna de perdedores.
- **Confundir "escalar" com "filtrar" é o erro que a nota denuncia — e é fácil recair nele.** A
  tentação de ler Barroso & Santa-Clara e sair estreitando `atr_pct_max` é exatamente o movimento
  errado: eles reduzem exposição continuamente, não excluem observações.
- **Números de segunda mão.** Sharpe 0,53 → 0,97 e alvo de 12% vêm de fonte secundária. Se algum dia
  algum deles for citado numa decisão, é obrigatório abrir o original antes.
- **Circularidade com o piso de custo.** Se subirmos o piso e a expectancy melhorar, não saberemos
  se melhorou pelo custo ou por termos, sem querer, selecionado um regime. Só a H-KB0035a separa as
  duas — e ela precisa vir **antes**.

## Segunda opinião (Astra)

Revisão de 2026-09-06. **Um must-fix, e ele invalidava a hipótese principal:** a H-KB0035a, como eu
a escrevi, mediria o filtro com **um ATR que a estratégia não consome** (`atr_14_pct` do M2, em vez
do `rolling_window_v1` que a `momentum_v1` recalcula). Corrigido, com os dois caminhos honestos
declarados e o terceiro proibido explicitamente.

**Segunda correção:** eu tratava o ciclo diurno da KB-0032 como demonstrado ao cruzá-lo com o piso.
Reescrito em condicional.

**Concordância:** a distinção entre *escalar* exposição (o que a literatura faz) e *filtrar* entrada
(o que nós fazemos) é o núcleo da nota, e a decisão de **não** abrir braço de sombra para a H-KB0035b
— porque o Lab não dimensiona posição — é a chamada certa.

## Relacionados

[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0007-atr-e-escala-por-volatilidade]] ·
[[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] ·
[[KB-0030-o-regime-nao-chega-ao-sinal]] ·
[[KB-0001-momentum-academico-e-o-que-nao-se-transfere]] · [[Strategy Backlog]] · [[EXP-0001-momentum-v1]]
