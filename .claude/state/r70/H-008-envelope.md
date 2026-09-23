# H-008 — portão de tendência de 4 h (população verbatim: envelope do sinal) — NÃO CONFIRMA

> Origem: Strategy Backlog item 6 · KB-0001 — transferência de horizonte não demonstrada  ·  impressão digital do pré-registo: `6900fdef1f1e`
> Limiar congelado: **0**  ·  efeito mínimo relevante (MRE): **+0.1000**

## Pré-registo (escrito antes de correr)

- **Previsão:** decisões com `return_4h` > 0 rendem mais +0,10 R que as demais
- **Refutação:** limite superior do IC 95 % abaixo de +0,02 R. Fração censurada acima de 20 % invalida o estudo (população diferente), não refuta nada
- **Regra de decisão:** CONFIRMA com D>0, D≥MRE, IC 95 % inferior>0, p de permutação<0,05, braço selecionado lucrativo em nível e curva planalto. RESSALVA DO MOINHO: a fila pré-registou dois números — o tamanho previsto e uma barra de refutação menor — e `DecisionPolicy` só tem um `minimum_effect`. Fixei `minimum_effect` = tamanho previsto; a barra de refutação da fila é lida à mão no relatório, sem tocar no moinho.
- **Política de limiar:** limiar 0 fixo (o sinal do retorno de 4 h), como a fila pré-registou
- **Congelado em:** 2026-09-23

## Os números

| # | o quê | valor |
|---|---|---|
| 1 | população usada (de 0 linhas lidas) | **0** em 0 clusters |
| 2 | selecionados / resto no limiar congelado | 0 / 0 |
| 3 | média do desfecho: selecionados / resto | — / — |
| 4 | **D = média(selecionados) − média(resto)** | **—** |
| 5 | IC 95 % de D (bootstrap de cluster por `mercado`) | — |
| 6 | p de permutação (estratificada por `dia`) | — |

Censura: 0 linhas sem desfecho, 0 sem a variável, 0 recusadas pela guarda anti-antecipação. Ausente nunca virou zero.

## VEREDITO: NÃO CONFIRMA

- amostra insuficiente: 0/0 contra o mínimo 20 por lado — sem potência, o que não é refutação.

## Curva de limiares — planalto ou pico?

Diagnóstico: **ausente** (0 limiares avaliáveis; maior corrida positiva 0 (0 com IC acima de zero)).

| limiar | n sel/resto | D | IC 95 % |
|---|---|---|---|
| -0.02 | 0/0 | — | amostra insuficiente |
| -0.01 | 0/0 | — | amostra insuficiente |
| 0 | 0/0 | — | amostra insuficiente |
| 0.01 | 0/0 | — | amostra insuficiente |
| 0.02 | 0/0 | — | amostra insuficiente |
| 0.03 | 0/0 | — | amostra insuficiente |

## A ressalva que mais importa

a guarda não correu (dispensa declarada: o envelope do sinal não carrega instantes por feature) — causalidade é afirmação do operador, não do moinho

Outras ressalvas:

- sem fatia de teste reservada: o resultado é dentro da amostra

## Suposições numéricas declaradas

- desfecho = r_multiple do `signal_outcomes` terminal
- população verbatim da fila: `return_4h` presente no envelope do sinal

Estatística em `float` (contrastes de retorno); dinheiro publicado em `Decimal`. Tempo em UTC.

> Nada aqui autoriza dinheiro real. Um CONFIRMA é candidato a **braço de papel pré-registado**, nunca parâmetro de mesa.

