# H-008 — portão de tendência de 4 h (desvio declarado: feature_snapshots) — REFUTA

> Origem: Strategy Backlog item 6 · KB-0001 — transferência de horizonte não demonstrada  ·  impressão digital do pré-registo: `92151e082dd2`
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
| 1 | população usada (de 6538 linhas lidas) | **3179** em 239 clusters |
| 2 | selecionados / resto no limiar congelado | 2013 / 1166 |
| 3 | média do desfecho: selecionados / resto | -0.3205 / -0.1613 |
| 4 | **D = média(selecionados) − média(resto)** | **-0.1592** |
| 5 | IC 95 % de D (bootstrap de cluster por `mercado`) | [-0.3068, -0.0246]  P(D≤0) = 0.989 |
| 6 | p de permutação (estratificada por `dia`) | 0.0001 |

Censura: 0 linhas sem desfecho, 3359 sem a variável, 0 recusadas pela guarda anti-antecipação. Ausente nunca virou zero.

## VEREDITO: REFUTA

- IC 95 % superior -0.0246 abaixo do MRE +0.1000: evidência CONTRA uma vantagem útil desse tamanho — não é refutação de qualquer efeito, é refutação de um efeito que pague a mesa.

## Curva de limiares — planalto ou pico?

Diagnóstico: **pico** (6 limiares avaliáveis; maior corrida positiva 1 (0 com IC acima de zero)).

| limiar | n sel/resto | D | IC 95 % |
|---|---|---|---|
| -0.02 | 2649/530 | -0.0071 | [-0.2198, +0.1763] |
| -0.01 | 2341/838 | -0.1098 | [-0.2909, +0.0572] |
| 0 | 2013/1166 | -0.1592 | [-0.3071, -0.0193] |
| 0.01 | 1651/1528 | -0.0714 | [-0.2049, +0.0534] |
| 0.02 | 1206/1973 | -0.0080 | [-0.1318, +0.1137] |
| 0.03 | 855/2324 | +0.0530 | [-0.1056, +0.1999] |

## Baldes por tercis (descritivo, não decide nada)

| balde | n | média | mediana |
|---|---|---|---|
| --0.00376085 | 1060 | -0.1499 | -0.4868 |
| -0.00376085-0.0234917 | 1061 | -0.3830 | -0.6314 |
| 0.0234917-inf | 1058 | -0.2533 | -0.5286 |

## A ressalva que mais importa

3359 de 6538 linhas censuradas (51.4 %) — censura assimétrica entre braços inventa vantagem

Outras ressalvas:

- 13.3 linhas por cluster: a permutação troca rótulos linha a linha e, com linhas dependentes dentro do cluster, o p sai otimista — leia o IC de cluster/blocos antes do p
- sem fatia de teste reservada: o resultado é dentro da amostra

## Suposições numéricas declaradas

- desfecho = r_multiple do `signal_outcomes` terminal
- desvio declarado: `return_4h` do `feature_snapshots` do minuto da decisão

Estatística em `float` (contrastes de retorno); dinheiro publicado em `Decimal`. Tempo em UTC.

> Nada aqui autoriza dinheiro real. Um CONFIRMA é candidato a **braço de papel pré-registado**, nunca parâmetro de mesa.

