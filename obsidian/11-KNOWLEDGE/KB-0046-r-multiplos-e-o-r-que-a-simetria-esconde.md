---
tags: [knowledge, nota, livros, risco, metricas]
tema: gestão de risco / métricas de resultado
fonte: material aberto do Van Tharp Institute sobre R e R-múltiplos (o livro *Trade Your Way to Financial Freedom* é a origem do vocabulário, **não** foi lido nesta rodada)
fonte_url: https://vantharp.com/wp-content/uploads/2018/06/A_Short_Lesson_on_R_and_R-multiple.pdf
lido_em: 2026-09-06
evidencia: anedótico
hipotese_testavel: sim
astra: concorda
---

# R-múltiplos, expectancy e o R que a nossa simetria esconde

## O que afirma

Tharp propõe medir todo resultado em unidades do risco assumido: `R` é a distância entre a entrada e
o stop inicial, e cada operação vira um **R-múltiplo** (ganhou 2R, perdeu 1R). Um sistema deixa de
ser uma promessa e passa a ser uma **distribuição de R-múltiplos**; a `expectancy` é a média dessa
distribuição. A tese seguinte, que é a mais citada dele, é que o **dimensionamento da posição** tem
peso grande no resultado de uma conta — a mesma distribuição de R produz contas muito diferentes
conforme quanto se arrisca por operação. Atribuição qualificada, exigida pela revisão: o material
aberto do instituto **não** opõe sizing a entrada; ele reconhece o papel do sistema de entrada e
saída. A versão absoluta ("não é a entrada, é o sizing") é folclore de segunda mão e sai desta nota.
Há ainda a ideia derivada de *expectunity* — expectancy multiplicada pela **frequência de
oportunidades** no período —, que tem definição no glossário público do instituto.

Ressalva de fonte: o PDF do instituto **não abriu para mim** (voltou binário ilegível); a Astra o
abriu na revisão e confirmou que ele sustenta risco inicial, R-múltiplos, expectancy e a importância
do sizing. É material do instituto sobre o simulador deles, **não** prova de leitura do livro.
Nenhum número da fonte entra nesta nota.

## Onde foi mostrado

Texto de praticante, sem estudo controlado, sobre ações e futuros com horizonte de dias a meses. Não
há amostra, população nem teste — é um vocabulário e um argumento aritmético, não uma medição. A
parte aritmética (a mesma distribuição com sizings diferentes dá contas diferentes) é verdadeira por
construção; a parte empírica (que sistemas reais têm expectancy positiva) não é afirmada por
evidência nenhuma aqui.

## Como mediríamos aqui

O Lab **já** fala essa língua: `SHADOW-LAB.md` §9 define *expectancy líquida hipotética em R por
entrada encerrada avaliável* e proíbe confundi-la com taxa de alvo e com taxa de lucro líquido. Até
aí, nada novo.

O que precisa ficar escrito é uma consequência aritmética: **o payoff nominal no alvo não é
necessariamente 1 R, e a simetria de 1,5 ATR esconde isso.** (Uma unidade de risco continua sendo 1
R por definição — o que varia é a razão entre ganho potencial e risco.)

`stop` e `target1` são postos a ±1,5 ATR **do fechamento de referência** (`momentum_v1.py:217`). A
entrada é a abertura de uma barra de 1 minuto **posterior**, acrescida do meio spread e do slippage
assumidos (`plan.py:48`, `pricing.py:47`); a taxa é descontada à parte, no cálculo do R líquido
(`pricing.py:79`). Como o denominador de R é `entrada − stop` (`pricing.py:74`) e o numerador do
payoff é `alvo − entrada`, chamando `a = 1,5·ATR` e `δ = P_entry − referência`:

```
risco                   = a + δ
ganho potencial nominal = a − δ
payoff nominal          = (a − δ) / (a + δ)
```

Uma entrada acima da referência **aumenta o denominador e diminui o numerador ao mesmo tempo** — o
efeito é duplo, não paralelo (correção da Astra; eu tinha escrito "os dois lados na mesma direção").

> Referência 100, ATR 2 → stop 97, alvo 103. Entrada a 101: risco 4, ganho potencial 2. O payoff
> nominal é **0,5**, contra 1 na referência. E isso é potencial **bruto**: taxas, funding e as
> fricções da saída ainda vêm depois.

Isto **não é descoberta desta rodada**: o mesmo exemplo `100 / 97 / 103 / 101 → 0,5 R` já está no
contrato do Lab (`docs/plans/SHADOW-LAB.md:13`), e a docstring da estratégia diz "1 R nominal **na
referência**" (`momentum_v1.py:6-7`). O que não existe é a **distribuição** disso na população real
de entradas — e sem ela ninguém sabe se o efeito é ruído de terceira casa ou se reordena as
candidatas.

Ressalva de medição, também da Astra: os **14,4 bps** medianos de deslocamento da quinta rodada são
`open` **bruto** contra a referência, não `P_entry − referência`
([[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]]). O diagnóstico abaixo tem de
usar `P_entry`, senão mede outra grandeza.

## Hipótese testável no Lab

Duas coisas, e só a segunda é braço de sombra.

**(a) `D-VT` — diagnóstico, roda hoje, sem pré-requisito.** Sobre os outcomes já persistidos,
publicar por entrada:

```
payoff_nominal    = (target1 − P_entry) / (P_entry − stop)   # bruto, antes de taxa e funding
R_unidade         = P_entry − stop            # o denominador de R de fato usado (pricing.py:74)
desvio_referencia = (P_entry − reference_price) / reference_price   # P_entry, não o open bruto
```

com mediana, **média**, quartis e a fração de entradas com payoff nominal fora de `[0,8; 1,2]`, e a
expectancy estratificada por faixa desse payoff. Não é variante: não muda decisão nenhuma. Responde
se a assimetria induzida pelo relógio é ruído ou se é grande o bastante para reordenar as
candidatas.

**(b) `L1` — alvo assimétrico, três braços sobre as mesmas entradas** (a candidata #10 do backlog,
agora com parâmetros):

```
alvo_efetivo ∈ { 1.5·ATR₀ , 3.0·ATR₀ , 4.5·ATR₀ }   a partir da referência
stop_atr        = 1.5      # inalterado
invalidação     = atual    # inalterada
horizon_s       = 14400    # inalterado
```

Os multiplicadores **não são escolhidos por mim**: 3 e 4,5 são `target2_atr` e `target3_atr`, que a
estratégia já calcula e persiste (`momentum_v1.py:88-89`, `record.py:137`, `persist.py:59`) e que o
acompanhamento atual **não usa como barreiras** ([[KB-0054-a-cauda-direita-e-o-alvo-fixo-que-a-corta]]).

**Refutação:** `ΔR_net` pareado ≤ 0 contra o braço de 1,5, na janela futura reservada, com correção
de Holm sobre os dois contrastes e incerteza por reamostragem em blocos de tempo.

## Por que pode falhar

1. **Expectancy em amostra pequena é dominada pela cauda.** Com o limiar editorial em 100 outcomes
   avaliáveis e 30 dias distintos, uma média de R é descritiva, nunca conclusiva
   ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).
2. **A tese de sizing é inavaliável aqui.** O Lab não dimensiona posição; toda a parte de
   position sizing, crescimento composto e drawdown de conta é `não aplicável` por contrato — a mesma
   fronteira que adiou a T-021 ([[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]]).
3. **"Expectunity" não é propriedade da estratégia.** A frequência de oportunidades depende do
   universo, do tamanho dele, da máquina de rearme de slots (`episodes.py`) e da disponibilidade das
   features — mudar o universo muda o número sem mudar a estratégia. Publicá-lo como métrica de
   qualidade seria atribuir à regra um efeito da infraestrutura. (E a frase fácil "um sistema que
   dispara três vezes por ano não paga o aluguel" é retórica: não temos medição nenhuma que a
   sustente aqui.)
4. **Chamar 3 ATR de "3 R" é o erro previsível** (apontado pela Astra). O R efetivo tem denominador
   `entrada − stop`, que não é 1,5 ATR.
5. **Alvo maior interage com tudo ao mesmo tempo**: muda taxa de alvo, duração, exposição a funding e
   número de invalidações. É exatamente por isso que a #10 do backlog está separada de propósito.

## Segunda opinião (Astra)

Concordou com o diagnóstico e o pôs como candidata **2** da fila dela ("Distribuição de R e alvo
assimétrico"), com duas armadilhas nomeadas: **chamar 3 ATR de 3 R** e **escolher o braço pelo payoff
nominal ou só pelos vencedores**. Apontou `pricing.py:74` como o lugar onde o R efetivo se forma.

Na revisão da nota, corrigiu **a álgebra** (entrada acima da referência sobe o risco *e* baixa o
ganho — efeito duplo, não paralelo), exigiu distinguir `open` bruto de `P_entry` (que já embute meio
spread e slippage, enquanto a taxa entra depois), mostrou que o exemplo de 0,5 **já está no contrato
do Lab** — o que derruba a minha alegação de novidade — e trocou "o nosso R nominal não é 1" por "o
payoff nominal no alvo não é necessariamente 1 R", porque uma unidade de risco é 1 R por definição.
Também mandou tirar a frase "três vezes por ano não paga o aluguel", que é retórica sem medição.

Traçou ainda a fronteira que eu tinha borrado: "expectancy por entrada é pertinente; dimensionamento
por risco, volatilidade-alvo, combinação de previsões e crescimento composto **não são respondidos
pela média de R do Lab**" — e trocar escala de exposição por um filtro binário **muda a hipótese**,
não a implementa mais barato.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] ·
[[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] ·
[[KB-0045-turtles-a-entrada-que-ja-temos-e-a-saida-que-nao]] ·
[[KB-0054-a-cauda-direita-e-o-alvo-fixo-que-a-corta]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] · [[EXP-0001-momentum-v1]]
