# H-003 — P2_revert_z em h = 60 min (lado à vista, universo U2) — NÃO CONFIRMA

> Origem: R68 parte B — h=240 ficou inconclusivo em 5 células (partb_U2.txt 28–32: IC atravessando zero em todas) · KB-0149 §7  ·  impressão digital do pré-registo: `fe88f129bfb6`
> Limiar congelado: **0.5**  ·  efeito mínimo relevante (MRE): **+0.0010**

## Pré-registo (escrito antes de correr)

- **Previsão:** pelo menos uma célula rende ≥ +0,10 % líquido por operação com Holm < 0,05 ao custo medido de 0,14 %
- **Refutação:** limite superior do IC 95 % abaixo do MRE de +0,10 % em todas as células
- **Regra de decisão:** CONFIRMA com D>0, D≥MRE, IC 95 % inferior>0, p de permutação<0,05, braço selecionado lucrativo em nível e a fatia de teste a repetir o sinal. PLANALTO DESLIGADO NO PRÉ-REGISTO: o preditor é booleano (entra/não entra), um degrau real, e não há limiar contínuo para varrer — varrer 0,4/0,5/0,6 sobre 0 e 1 devolveria a mesma partição e fingiria um planalto. LIMITE DO MOINHO: o walk-forward de várias dobras do R68 (treino 14 d / teste 7 d, passo 7 d) e o baseline 'sempre dentro' NÃO são reproduzíveis aqui; corre uma fronteira única treino/teste com purga de 1 bloco.
- **Política de limiar:** preditor booleano: limiar 0,5 separa 1 de 0, sem escolha nenhuma nos dados; os parâmetros internos dos 5 preditores são os do pré-registo do R68
- **Congelado em:** 2026-09-23

## Os números

| # | o quê | valor |
|---|---|---|
| 1 | população usada (de 22092 linhas lidas) | **20940** em 16 clusters |
| 2 | selecionados / resto no limiar congelado | 822 / 20118 |
| 3 | média do desfecho: selecionados / resto | -0.0002 / -0.0011 |
| 4 | **D = média(selecionados) − média(resto)** | **+0.0008** |
| 5 | IC 95 % de D (bootstrap de cluster por `mercado`) | [-0.0001, +0.0019]  P(D≤0) = 0.034 |
| 6 | IC 95 % de D (bootstrap de blocos) | [-0.0001, +0.0020] em 19 blocos |
| 7 | p de permutação (estratificada por `dia`) | 0.2585 |
| 8 | fatia de teste reservada: D | +0.0016 (244/5944; 1152 linhas purgadas) |

Censura: 0 linhas sem desfecho, 0 sem a variável, 0 recusadas pela guarda anti-antecipação. Ausente nunca virou zero.

## VEREDITO: NÃO CONFIRMA

- D = +0.0008 abaixo do MRE +0.0010
- IC 95 % inferior -0.0001 não está acima de zero
- p de permutação 0.2585 não é < 0,05
- o braço selecionado perde em nível (-0.0002); perder menos que o resto não é vantagem
- há dependência temporal declarada e o IC 95 % por blocos [-0.0001, +0.0020] cobre zero

## Curva de limiares — planalto ou pico?

Diagnóstico: **ausente** (0 limiares avaliáveis; maior corrida positiva 0 (0 com IC acima de zero)).

| limiar | n sel/resto | D | IC 95 % |
|---|---|---|---|

## Baldes por tercis (descritivo, não decide nada)

| balde | n | média | mediana |
|---|---|---|---|
| -0 | 20118 | -0.0011 | -0.0014 |
| 0-inf | 822 | -0.0002 | -0.0009 |

## A ressalva que mais importa

só 16 clusters independentes sustentam o IC

Outras ressalvas:

- 1308.8 linhas por cluster: a permutação troca rótulos linha a linha e, com linhas dependentes dentro do cluster, o p sai otimista — leia o IC de cluster/blocos antes do p

## Suposições numéricas declaradas

- custo de ida-e-volta 0,14 % por operação, já subtraído do desfecho
- desfecho = fecho da barra seguinte ÷ fecho da barra da decisão − 1 − custo
- a guarda que vale aqui é `Bars.take`/`assert_causal` do R68, dentro do loader: nenhuma feature lê barra que feche depois da decisão
- universo U2 do R68 (16 perpétuos), velas de 1 min `is_final` de 2026-07-25 em diante

Estatística em `float` (contrastes de retorno); dinheiro publicado em `Decimal`. Tempo em UTC.

> Nada aqui autoriza dinheiro real. Um CONFIRMA é candidato a **braço de papel pré-registado**, nunca parâmetro de mesa.
