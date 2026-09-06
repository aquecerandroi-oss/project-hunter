---
tags: [knowledge, nota, risco, sizing, kelly, r-multiplo]
tema: dimensionamento e risco / fração de risco por operação
fonte: MacLean, Thorp & Ziemba (capítulo aberto sobre o critério de Kelly); Grossman & Zhou (1993); material aberto do Van Tharp Institute; busca por Optimal f de Ralph Vince
fonte_url: https://webhomes.maths.ed.ac.uk/mckinnon/blackouts/StochOptFinanceAndEnergySpringer/Chap1_KellyZiemba.pdf · https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-9965.1993.tb00044.x
lido_em: 2026-09-06
evidencia: estudo revisado lido em resumo (Kelly, Grossman & Zhou) + anedótico (Vince, Tharp) + aritmética própria conferida
hipotese_testavel: sim
astra: pendente
---

# A fração de risco por operação — e o preço de errar a expectancy

## O que afirma

A pergunta "quanto arriscar por operação" tem uma resposta matemática exata (Kelly) e uma razão
igualmente exata para **não** usá-la: a resposta ótima é uma função da expectancy, e a expectancy
que temos é uma estimativa ruidosa de uma amostra de 16 horas. Errar a expectancy para cima faz o
tamanho ótimo crescer sem limite; e a curva de crescimento em torno do ótimo é **assimétrica** —
apostar o dobro do ótimo destrói o crescimento de longo prazo, enquanto apostar metade preserva a
maior parte dele.

A consequência prática, e é a única coisa que este projeto pode afirmar hoje: **a fração de risco
por operação não é derivável do nosso dado.** Ela é um parâmetro de tolerância, escolhido pelo dono
do capital, e limitado por cima por argumentos de ruína — não escolhido por otimização.

## Onde foi mostrado

**Kelly / fractional Kelly.** O capítulo aberto de MacLean, Thorp e Ziemba estabelece a propriedade
positiva (maximiza a taxa de crescimento composto no longo prazo; assintoticamente diverge quando as
odds são favoráveis) e as negativas: **o desempenho de curto prazo do Kelly cheio é muito arriscado**,
uma sequência ruim pode consumir a maior parte do capital inicial por mais favorável que seja a
oportunidade, e há um *trade-off* consistente entre crescimento e segurança em função do tamanho da
aposta. Kelly fracionário (misturar a aposta de Kelly com caixa) reduz esse risco ao custo de riqueza
final esperada menor.

**Declaração de leitura, obrigatória aqui:** o PDF abriu, mas a tabela 1.1 e a figura 1.1 — que são
onde estariam os números de drawdown e as probabilidades — **não ficaram legíveis** na extração.
**Nenhum número de Kelly entra nesta nota.** O que entra é a forma do argumento.

**Grossman & Zhou (1993), *Mathematical Finance* 3(3):241-276** — o problema de investir sob a
restrição `W_t ≥ α·M_t`, onde `M_t` é o máximo de riqueza atingido até `t` e `α ∈ (0,1)`. É a
formalização da ideia de "limite de drawdown" como **restrição**, e não como alarme. Li o resumo e a
ficha; **o artigo em si não foi aberto** (paywall Wiley).

**Ralph Vince, *optimal f*.** A busca por avaliação crítica devolveu **só material de praticante e de
fornecedor** (turtletrader.com, quantifiedstrategies.com, tradingview). Nenhuma fonte revisada.
**Nenhum número dessa busca foi citado** — inclusive porque um dos resultados afirmava um drawdown de
"cerca de 900%", que é aritmeticamente impossível para uma fração de capital. O que sobrevive da
leitura é uma objeção **estrutural**, não empírica: qualquer regra de tamanho que dependa da **maior
perda histórica** fica exposta no dia em que o mercado produz uma perda maior, e mercados produzem.

**Van Tharp.** Material aberto do instituto, já lido na
[[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]] — sustenta risco inicial, R-múltiplos,
expectancy e a importância do dimensionamento; **não é** evidência de qual fração usar.

## Como mediríamos aqui

A cadeia que liga R a tamanho, no nosso vocabulário:

```
R (risco de 1 operação, em USDT) = equity × fração_de_risco
notional                          = R / stop_distance
quantidade                        = notional / entry_ref
```

Três observações que a nossa própria medição impõe sobre essa cadeia:

1. **A fração de risco só é o limitante quando o stop é largo.** Medido na
   [[KB-0066-o-risk-engine-ja-esta-escrito-e-a-medicao-o-contraria]]: com
   `risk_per_trade_pct = 0,005` e `max_position_pct = 0,05`, o risco só vence quando
   `stop_distance > 10%`, e a maior distância observada em 992 entradas foi **9,32%**. Hoje a fração
   de risco **não dimensiona nada**.
2. **O "1 R" nominal não é o R efetivo.** A [[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]] já
   mostrou que a entrada é uma abertura posterior à referência: risco `a + δ`, ganho `a − δ`. Uma
   fração de risco definida sobre a referência **subestima** o risco realizado sempre que `δ > 0`.
3. **Custos entram dentro do R, não fora.** Com stop mediano de 1,52% e 10 bps de custo por perna
   ([[KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker]] mais spread medido), a ida e volta consome
   `20/152 = 13,2%` de 1 R. A fração de risco escolhida é uma fração do R **bruto**; o R líquido é
   menor por construção.

**O argumento de ruína, na forma em que ele é usável aqui.** Com fração fixa `f` de capital por
operação e `n` perdas seguidas, o capital cai para `(1−f)^n`. Isso é definição, não resultado:

| `f` por operação | após 10 perdas seguidas | após 20 | após 30 |
|---|---|---|---|
| 0,25% | −2,47% | −4,88% | −7,23% |
| 0,50% | −4,89% | −9,54% | −13,96% |
| 1,00% | −9,56% | −18,21% | −26,03% |
| 2,00% | −18,29% | −33,24% | −45,45% |

E o dado que dá escala a essa tabela: dos 986 acompanhamentos terminais medidos hoje na VPS, **292
terminaram em stop e 387 em invalidação** — ou seja, **69% terminaram sem tocar o alvo**. Uma
sequência de 20 resultados negativos não é excepcional numa taxa dessas; é o que se espera de vez em
quando. **Isso não é expectancy** (invalidação não é perda de 1 R) e não deve ser lido como tal — é
só a ordem de grandeza da frequência com que a conta acima é exercitada.

## Hipótese testável no Lab

**Nenhuma.** E isto é o resultado da nota, não uma falha dela: o Shadow Lab **não dimensiona
posição** e `PnL de carteira` é *não aplicável* — a mesma razão pela qual a candidata de escalar
exposição pelo inverso da volatilidade foi adiada para o M4 na quarta rodada
([[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]]).

O que sai daqui é uma **regra proposta para o Risk Engine** (`R-SIZE-1` no
[[Strategy Backlog]]) e uma marcação: **a fração de risco é decisão do Everton**, com um teto de
recomendação.

**A recomendação, e o motivo dela em uma frase:** começar em **0,25% por operação** e nunca passar de
**1%** enquanto a expectancy não tiver janela futura reservada e ≥ 100 outcomes em ≥ 30 dias. O
motivo não é o Kelly — é que a fração ótima é proporcional à expectancy estimada, a nossa expectancy
hoje **não é distinguível de zero em nenhuma coorte** ([[Strategy Performance]] e a
[[KB-0065-a-coorte-de-memes-nao-se-distingue-do-resto]]), e a assimetria da curva de crescimento pune
o erro para cima muito mais que o erro para baixo.

## Por que pode falhar

- **Kelly pressupõe reinvestimento contínuo de um mesmo processo estacionário.** Nós temos dezenas de
  posições simultâneas, correlacionadas, num universo que gira 26% em 20 h
  ([[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]]). A fórmula de aposta única não se aplica; o
  que se transfere é a **forma** do trade-off, não o número.
- **A tabela de perdas seguidas supõe perda de exatamente 1 R.** Gaps atravessam o stop
  ([[KB-0064-a-cauda-de-queda-e-o-que-o-risk-engine-vai-precisar]]), e invalidações saem por outro
  preço. Ela é piso, não previsão.
- **Fração fixa de *equity* é procíclica ao contrário do que parece:** cai em valor absoluto depois
  de perder, o que é bom para sobrevivência e ruim para recuperação. Isso é escolha, não otimização.
- **Nada disto foi medido no nosso mercado.** As duas fontes revisadas são de mercados e horizontes
  completamente diferentes.

## Segunda opinião (Astra)

Pendente nesta versão.

## Relacionados

[[Strategy Backlog]] · [[Index]] ·
[[KB-0066-o-risk-engine-ja-esta-escrito-e-a-medicao-o-contraria]] ·
[[KB-0068-sizing-por-volatilidade-a-posicao-sai-do-atr]] ·
[[KB-0072-drawdown-e-kill-switch-a-evidencia-e-a-convencao]] ·
[[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]] ·
[[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]
