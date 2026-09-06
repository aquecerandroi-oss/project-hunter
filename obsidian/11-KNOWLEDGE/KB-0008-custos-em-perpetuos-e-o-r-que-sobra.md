---
tags: [knowledge, nota, custos, perpetuos, funding]
tema: Perpétuos: funding, OI, liquidações
fonte: Documentação da Binance sobre funding em futuros perpétuos; aritmética própria sobre os custos assumidos do Shadow Lab (`docs/plans/SHADOW-LAB.md` item 3)
fonte_url: https://www.binance.com/en/support/faq/360033525031
lido_em: 2026-09-06
evidencia: documentação da exchange + aritmética verificada sobre dado próprio
hipotese_testavel: sim
astra: concorda
---

# Custos em perpétuos e quanto sobra de 1 R

## O que afirma

Como funciona o funding na Binance USDS-M, segundo a documentação: liquidação a cada **8 horas**, às
00:00, 08:00 e 16:00 UTC no calendário padrão; a taxa tem componente de **juros** e componente de
**prêmio** sobre o índice; o pagamento é transferido **entre traders**, não cobrado pela exchange;
existem teto e piso ligados ao índice de margem de manutenção.

Três precisões que evitam citação errada: **0,01% é o componente padrão de juros por intervalo de 8
horas**, não um funding fixo nem uma cobrança extra a somar ao funding calculado; a taxa pode ser
pagamento **ou** recebimento, conforme o lado; e ±0,3% aparece como **exemplo** para BTCUSDT — a
documentação admite ajuste de limites e de frequência, inclusive liquidação horária ao atingir
teto/piso. Nada disso é constante universal.

## Onde foi mostrado

Documentação do próprio produto, não estudo. Aplica-se diretamente ao que operamos (perpétuos USDT
da Binance), o que é raro entre as fontes desta base — e é justamente por isso que ela merece nota
própria.

## Como mediríamos aqui

Custos **assumidos** do Lab (hipóteses declaradas, **não** tarifas verificadas): `P_entry = O·(1+a)`
e `P_exit = B·(1−a)` com `a = 0,0006` (spread + slippage), taxa `f = 0,0004` por lado **fora** dos
preços, funding assinado. Com `C` = fechamento de referência, `S = C − 1,5·ATR`, `E = P_entry`,
`X = P_exit`, o custo exato por unidade sem funding é `K = a(O+B) + f(E+X)`, e
`R_net = (B − O − K − F) / (E − S)`.

**Aritmética verificada** (saída real, `uv run python`, e conferida de forma independente pela
Astra):

```
custo ida-e-volta aprox (fracao do preco): 0.0020 = 20.0000 bps
atr_pct=0.003: R nominal=0.0045 (45 bps); custo/R=0.4444
atr_pct=0.01 : R nominal=0.015  (150 bps); custo/R=0.1333
atr_pct=0.05 : R nominal=0.075  (750 bps); custo/R=0.0267

taxa de alvo de equilibrio com as medias observadas: 0.5777
observada 36/67: 0.5373
observada 40/75: 0.5333
```

Conferência da Astra usando o **denominador efetivo** `(E − S)/C = 1,5v + 0,0006` (caso `O = C`):

```
atr_pct nominal_bps effective_bps cost_over_nominal cost_over_effective
0.003   45.0000     51.0000       0.444444          0.392157
0.01    150.000     156.0000      0.133333          0.128205
0.05    750.000     756.0000      0.026667          0.026455
p_equilibrium 0.57768232
p_67 0.53731343   p_75 0.53333333
E_67 -0.07893731
floor_nominal 0.0088888889
floor_no_gap  0.0084888889
```

Ou seja: no piso atual `atr_pct_min = 0,003`, os 20 bps de custo assumido consomem **39,2% de 1 R
efetivo** (44,4% do risco *nominal*). Num exemplo sintético com abertura igual à referência, ATR% no
piso, saída exatamente no nível e funding zero, o alvo líquido vale **+0,489314 R** e o stop líquido
**−1,273628 R**. Não é azar de amostra: é aritmética da geometria com custo proporcional.

**Enunciado correto da taxa de equilíbrio** (o errado seria chamá-la de "taxa de acerto necessária da
estratégia"):

> Entre os encerramentos por alvo ou stop com R líquido conhecido nesta avaliação, mantendo fixas as
> médias observadas de +0,8258 R e −1,1296 R, a proporção de alvos que zeraria a média desse
> subconjunto seria aproximadamente **57,77%**. A proporção observada nesse mesmo subconjunto foi
> **36/67 = 53,73%**.

Isso **exclui invalidados e expirados** e os casos sem R conhecido. Os 40/75 = 53,33% incluem quatro
alvos e quatro stops adicionais **sem** R líquido, então servem como cobertura, não como população
das médias. Atingir 57,77% não zeraria a estratégia: os 24 invalidados (média −0,5768 R) continuam
lá; a média dos 67 é −0,0789 R e a dos 91 é −0,2102 R. E a diferença entre 53,73% e 57,77% é
**descritiva**, não demonstração de significância.

## Hipótese testável no Lab

Em duas etapas, nesta ordem.

**1. Diagnóstico (não é variante).** Decomposição de custo por faixa de ATR% **persistido na
decisão**, todos os componentes com o **mesmo denominador efetivo**: movimento bruto/R, spread e
slippage/R, taxas/R, funding/R e o deslocamento referência→entrada. Inclui invalidados, expirados e
a cobertura de funding. É o que separa custo de execução, geometria e comportamento do mercado.

**2. Candidata prospectiva única.** `momentum_v6_piso_de_custo`: idêntica à `momentum_v1`, com
`atr_pct_min = 0,0089` (orçamento aproximado de 15% do risco **nominal**; com o denominador efetivo
o equivalente seria 0,0084889). Alvo, stop, horizonte e invalidação **não** mudam.

- Descrita como **filtro nominal aproximado**, nunca como "garantia de custo efetivo ≤ 15%".
- Controle e candidata comparados no **mesmo período futuro** e mesmo universo, com datas, métrica
  primária (expectancy líquida de **todos** os encerramentos avaliáveis), tratamento de ausências e
  critério econômico congelados **antes** da coleta; dependência entre mercados por blocos temporais.
- Reportar também **quantas oportunidades sobram**: um piso que elimina 70% dos sinais é outra
  estratégia, não a mesma com menos ruído.

Ampliar o alvo **não** entra nesta intervenção: aumenta o ganho possível mas pode reduzir acertos,
prolongar exposição e aumentar invalidações, expirações e funding — e não reduz materialmente o
custo sobre o risco inicial. É candidata separada.

## Por que pode falhar

- **Calibrar na amostra que revelou o problema.** Descobrir a pressão de custo aqui é legítimo;
  usar a melhora **nesta mesma amostra** como prova é seleção retrospectiva. Até escolher "15%" é
  escolha de parâmetro se o valor foi preferido depois de olhar o resultado. Justificativa econômica
  não devolve independência aos dados
  ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).
- **Armadilha do denominador:** uma entrada **mais cara** aumenta `E − S` e portanto **reduz**
  custo/R, ao mesmo tempo que encolhe o espaço até o alvo. Qualquer regra baseada em custo/R tem de
  olhar também o ganho líquido potencial até o alvo — a validação atual só exige
  `stop < entrada < alvo` (`walker.py`).
- **Descontar duas vezes.** Spread e slippage já estão dentro dos preços sintéticos; subtraí-los de
  novo na análise falsearia o resultado.
- **Funding esquecido.** Um horizonte de 4 h **pode** atravessar uma liquidação de funding; chamar
  o filtro de "limite de custos totais" seria falso, porque os 20 bps não incluem funding.
- Os 20 bps são **hipótese declarada**, não tarifa verificada. Se as tarifas reais diferirem, toda a
  conta muda de escala (não de direção).

## Segunda opinião (Astra)

Conferiu a aritmética de forma independente com `Decimal` e confirmou os números, acrescentando o
denominador **efetivo** (51 bps e 39,22% no piso, contra 44,44% nominal), o exemplo sintético
(+0,489314 R no alvo, −1,273628 R no stop), `E_67 = −0,07894 R` e o piso equivalente 0,0084889.
Correções aceitas: (1) estreitar a conclusão para "pressão estrutural dos custos sob as hipóteses do
Lab", sem atribuir a perda observada exclusivamente ao piso; (2) enunciar os 57,77% como equilíbrio
**condicional e estimado na própria amostra**, excluindo invalidados e expirados; (3) qualificar o
funding — 0,01% é o componente de juros por intervalo, ±0,3% é exemplo, os limites e a frequência
podem mudar; (4) não misturar denominadores ao dizer "sobra 1 − 0,4444 R"; (5) priorizar o piso sobre
o alvo, como candidata única e prospectiva.

Divergência: nenhuma. Frase dela que fica: o diagnóstico justifica investigação e uma candidata; ele
**ainda não** justifica concluir que o piso maior terá expectancy melhor.

## Relacionados

[[Strategy Backlog]] · [[KB-0007-atr-e-escala-por-volatilidade]] ·
[[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] · [[KB-0009-o-efeito-do-quarto-de-hora]] ·
[[EXP-0001-momentum-v1]] · [[Funding]] · [[Risk Engine]]
