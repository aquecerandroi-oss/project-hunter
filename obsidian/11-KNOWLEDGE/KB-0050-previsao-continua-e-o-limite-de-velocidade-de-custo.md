---
tags: [knowledge, nota, livros, sizing, custos]
tema: sistemático / previsão contínua e custos
fonte: Robert Carver, *Systematic Trading* e o blog público do autor (pysystemtrade)
fonte_url: https://qoppac.blogspot.com/p/systematic-trading-start-here.html
lido_em: 2026-09-06
evidencia: backtest do autor
hipotese_testavel: sim
astra: concorda
---

# Previsão contínua, e o limite de velocidade que o custo impõe

## O que afirma

Carver desenha sistemas em três camadas separadas. **Previsão**: cada regra produz um número
contínuo, positivo ou negativo, reescalado para uma escala comum e limitado nas pontas — não um
"compra/não compra". **Dimensionamento**: a posição é proporcional à previsão dividida pela
volatilidade do instrumento, de modo que a carteira persiga uma volatilidade-alvo constante.
**Diversificação**: muitas regras sobre muitos instrumentos, com pesos que levam em conta a
correlação entre eles.

Duas consequências dele que interessam a esta base. A primeira: **em sistemas contínuos** ele
dispensa o stop como mecanismo separado — a proteção vem do tamanho escalado pela volatilidade, não
de um nível de preço. Ressalva obrigatória (**correção da Astra**): ele **distingue** esse caso dos
sistemas discretos, nos quais usa stops. Transformar isso num argumento geral a favor de tirar o
nosso stop seria deturpar a fonte.

A segunda: existe um **limite de velocidade imposto pelo custo** — e aqui o número existe e é
público: a heurística dele é **não gastar mais que um terço do retorno esperado antes dos custos**,
expressa também em unidades de Sharpe. Isso **não** vira `c = 1/3` no nosso caso, porque o nosso `R`
é o **risco inicial**, não o retorno esperado — são denominadores diferentes, e confundi-los seria o
erro mais fácil desta nota.

## Onde foi mostrado

Futuros e ETFs globais, barras diárias, carteira de mais de cem instrumentos, horizonte de semanas a
meses, com backtests do próprio autor e código aberto. Nada disso é perpétuo de cripto em 15 minutos,
e a maior parte do argumento é **sobre a carteira**, não sobre a regra.

## Como mediríamos aqui

**A camada de dimensionamento é inavaliável no Lab de sombra**, e essa fronteira já está escrita no
contrato: não há posição, não há capital, `PnL de carteira` e `Max Drawdown de carteira` são *não
aplicável*. É a mesma barreira que adiou a T-021 para o M4
([[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]]). Volatilidade-alvo, pesos por
correlação e crescimento composto ficam de fora desta rodada inteira.

**A camada de previsão já está declarada como o que é.** O nosso `confidence` é uma constante:
`base_confidence = 0,5` (`momentum_v1.py:90`), copiada para a decisão (`momentum_v1.py:285`) e
persistida em `agent_signals` (`persist.py:53`). E o envelope **não esconde isso**: o campo
`confidence_method` vale `"constant_uncalibrated_v1"`, com o comentário de que "confidence na v1 é
uma convenção, não uma probabilidade" (`envelope.py:122-125`, achado de uma revisão anterior da
Astra). Portanto: isto **não é uma descoberta desta rodada**; o sistema já se declara honesto.

O que Carver acrescenta é o **para quê**: uma previsão contínua vira **tamanho** onde existe
dimensionamento, e enquanto o Lab for binário calibrá-la não muda um único outcome.

Mas há um erro meu aqui que a Astra corrigiu: **isso não a torna inavaliável.** Um score não
vinculante não altera outcomes e ainda assim tem **capacidade preditiva testável** —
associação com `R_net`, médias por faixas declaradas antes, calibração contra um evento explícito.
O cenário de falha que ela nomeou é exatamente o que eu tinha proposto: "registrar um score durante
meses e adiar toda avaliação até o M4, embora já fosse possível verificar prospectivamente se ele
ordena outcomes". E uma função da `ER` **não vira probabilidade por se chamar `confidence`**: alvo,
horizonte e método têm de ser declarados.

### O limite de velocidade, e por que ele é o piso de custo escrito em unidades legíveis

O custo por unidade, expresso como fração do risco inicial, é:

```
custo_em_R = custo_por_unidade / (P_entry − stop)
           = b / (10.000 · (P_entry − stop)/P_entry)          # b em bps de P_entry
```

Dimensionalmente correto — a Astra conferiu. **Mas duas ressalvas dela desmontam a versão simples que
eu tinha escrito:**

**(1) `b` é uma aproximação.** Escrever `b = spread + 2·slippage + 2·fee = 20 bps` não é o que o
código faz: spread e slippage entram nos **preços** de cada ponta, a taxa é cobrada sobre cada preço
e o funding é descontado à parte (`pricing.py:9,74`).

**(2) A equivalência com um piso constante de ATR é apenas nominal.** Com `C` o fechamento de
referência, `a = ATR/C`, `k = 1,5` e `g = P_entry/C − 1`:

```
(P_entry − stop)/P_entry = (g + k·a) / (1 + g)
```

Logo o teto `custo_em_R ≤ c` equivale a `a ≥ [(1+g)·b/(10.000·c) − g] / k` — que **depende de `g`**.
Não é um piso constante de ATR. O contraexemplo dela, com referência e abertura em 100, ATR 0,29,
entrada 100,06 e stop 99,565: o piso atual **rejeita** `atr_pct = 0,0029`, e o custo efetivo é
0,4043 R, **abaixo** do teto nominal de 0,4444 R. A minha "reparametrização sem mudar comportamento"
aceitaria essa entrada — ou seja, mudaria a população sem avisar.

**E há um obstáculo prático que fecha a questão: `P_entry` não é conhecido no instante da decisão.**
Um filtro sobre o R **efetivo** é impossível de aplicar na hora de decidir; seria outra hipótese, não
uma reescrita.

O que sobra, e é o que esta nota entrega, é uma **tradução exata do parâmetro atual**, medida na
referência (onde `g = 0`):

```
custo_R_nominal_referencia = b / (10.000 · k · atr_pct)
```

Isso não muda comportamento nenhum: é o mesmo corte, dito em unidades que significam alguma coisa. E
a diferença não é cosmética. Hoje `atr_pct_min = 0,003` é um número solto cujo significado muda toda
vez que a hipótese de custo muda — e a quinta rodada mostrou que ela **vai** mudar (`fee_bps` de 4
não é nem o maker nem o taker do exemplo da Binance,
[[KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker]]). Escrito como custo nominal em R, o parâmetro
sobrevive à revisão da taxa; escrito como piso de ATR, não.

## Hipótese testável no Lab

**(a) `C-COST` — tradução de contrato, não tentativa nova e não mudança de população.** Publicar,
junto de `atr_pct_min`, o `custo_R_nominal_referencia` que ele implica dado o `AssumedCosts` da
versão, e passar a **declarar o parâmetro nessa unidade**, com o piso de ATR derivado dele **na
referência** (`g = 0`). Não é um filtro sobre o R efetivo — esse não é aplicável na decisão, porque
`P_entry` ainda não existe. Qualquer valor diferente do que reproduz o corte atual **é a candidata #2
do backlog**, que já está na fila e já exige janela futura reservada; a tradução não pode ser usada
para mexer no piso por baixo do pano.

**(b) `C-FCAST` — previsão contínua não vinculante, com pergunta preditiva desde o primeiro dia.**
Gravar, ao lado do `confidence` constante, um score contínuo (por exemplo, uma função monótona de
`ER(20)` ou de `breakout_strength_20`), com nome de método próprio — **nunca reusando
`confidence_method`, para não fingir calibração** — e **sem alterar decisão nenhuma**. E, diferente
do que eu tinha escrito, **com hipótese declarada antes**: alvo (`R_net`), horizonte, e a leitura —
associação e média por faixas de score definidas **antes** da coleta.

**Refutação:** (a) não é falsificável — é definição; o que é falsificável é a #2. (b) **é
falsificável**, e prospectivamente: se as faixas de score declaradas antes não ordenarem `R_net` na
janela reservada, o score não tem capacidade preditiva nesta amostra — resultado que não depende de
existir dimensionamento.

## Por que pode falhar

1. **A tradução vale na referência, e só nela.** Fora dela, `(P_entry − stop)/P_entry = (g + k·a)/(1 + g)`
   depende do deslocamento `g` ([[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]]) — e é por isso
   que a nota entrega uma tradução nominal e não um filtro efetivo. O ATR usado tem de ser o que a
   estratégia **de fato consome** (`rolling_window_v1`, `atr_bars=97`), não o `atr_14_pct` do M2 — a
   armadilha que a [[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] registrou.
1b. **`b` não é a soma que eu escrevi.** Spread e slippage entram nos preços de cada ponta, a taxa
   incide sobre cada preço e o funding é separado (`pricing.py:9,74`). Publicar `custo_R_nominal` com
   um `b` agregado exige dizer, na própria publicação, que é aproximação.
2. **O piso é um filtro de população.** Mexer nele muda quais mercados e quais horas entram; o
   diagnóstico D-024 (ciclo de trabalho do piso por hora UTC) continua sendo pré-requisito de
   qualquer mudança de valor.
3. **Trocar escala de exposição por filtro binário muda a hipótese** (frase da Astra, e ela vale
   inteira aqui): Carver **escala**, não **filtra**. Implementar a ideia dele como corte é uma
   adaptação nossa, e o resultado dela não valida nem invalida a dele.
4. **A previsão contínua pode virar duas coisas ao mesmo tempo.** Se um dia `confidence` passar a
   filtrar e a dimensionar, ninguém consegue atribuir efeito. Por isso `C-FCAST` é explicitamente
   não vinculante.
5. **"Sem stops" é a candidata #9 do backlog, não uma novidade daqui** — o braço `STOP-B` já existe
   em [[KB-0005-stops-quando-eles-param-perdas]]. E o ceticismo de Carver vale para os **sistemas
   contínuos** dele; ele usa stops nos discretos. Não é voto a favor de tirar o nosso stop, e muito
   menos evidência de que o stop custa.

## Segunda opinião (Astra)

Na curadoria, pôs Carver junto de Van Tharp na categoria em que "expectancy por entrada é pertinente;
dimensionamento por risco, volatilidade-alvo, combinação de previsões e crescimento composto **não
são respondidos pela média de R do Lab**", e foi dela a frase que virou o item 3 acima: **trocar
escala de exposição por um filtro binário muda a hipótese**, não a implementa mais barato.

Na revisão da nota, **derrubou a peça central da minha primeira versão**: a equivalência entre teto
de custo em R e piso de `atr_pct` é **apenas nominal**, porque `(P_entry − stop)/P_entry` depende do
deslocamento `g` — e ela produziu o contraexemplo numérico (ATR 0,29, entrada 100,06: o piso atual
rejeita, o teto nominal aceitaria) que mostra que a minha "reparametrização sem mudar comportamento"
mudaria a população. Acrescentou o obstáculo decisivo: `P_entry` **não é conhecido na decisão**.
Também confirmou linha a linha que `confidence` é constante e já declarado
`constant_uncalibrated_v1`, tirou o limite de velocidade de "de memória" (a heurística publicada é um
terço do retorno esperado antes dos custos, que **não** é `c = 1/3 R`), e me obrigou a devolver à
previsão contínua uma pergunta preditiva prospectiva em vez de adiá-la para o M4.

Concordou também com a fronteira geral da rodada: "ausência de carteira não impede calcular um
contrafactual por unidade; impede concluir sobre alocação, margem, capacidade, crescimento ou
drawdown de capital" — que é exatamente por que esta nota entrega uma reparametrização e um item de
proveniência, e nenhuma candidata de sombra.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker]] ·
[[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] ·
[[KB-0005-stops-quando-eles-param-perdas]] ·
[[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]]
