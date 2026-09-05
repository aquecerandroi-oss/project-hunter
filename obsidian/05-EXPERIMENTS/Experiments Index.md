---
tags: [experimentos, indice]
updated: 2026-09-05
status: planejado
---

# Experiments Index

## Status honesto

**Não existe nenhum experimento rodando ainda.** Não há paper trading, não há agente ativo, não há `signal_outcomes` real. O que mudou em 2026-09-05 é que os **IDs estão reservados** e o protocolo está congelado pela [[Dialogos/SHADOW|decisão conjunta do Shadow Lab]]: quando S0–S2 forem entregues e provadas, `EXP-0001` e `EXP-0002` nascem com hipótese e protocolo já escritos, e as avaliações passam a ser **acrescentadas** e datadas — nunca reescritas.

Cada experimento significativo (uma hipótese testada sobre uma estratégia, um conjunto de parâmetros, um mercado ou período) ganha seu próprio arquivo `EXP-NNNN-<slug>.md` nesta mesma pasta, numerado sequencialmente a partir de `EXP-0001`.

## Reserva de IDs (decisão conjunta SHADOW, 2026-09-05)

| ID | Experimento | Origem | Estado |
|---|---|---|---|
| `EXP-0001` | `momentum_v1` em modo sombra (15 min, stop e alvo a 1,5 ATR da referência, horizonte 4 h) | Shadow Lab v0 — tarefa S4 | **reservado**, arquivo só nasce após a prova de S0–S2 |
| `EXP-0002` | `volume_anomaly_v1` em modo sombra (5 min, ATR de 15 min, stop na mínima da barra do sinal, horizonte 2 h) | Shadow Lab v0 — tarefa S4 | **reservado**, idem |
| `EXP-0003` | Baselines por ativo/hora do M2 (T2.8) | `docs/plans/M2.md` | **reservado** — o M2 cedeu `EXP-0001` ao Shadow e passou para cá |

A reserva está consolidada nos três lugares que a decisão exige: aqui, em `docs/plans/SHADOW-LAB.md` (item 11) e em `docs/plans/M2.md` (T2.8).

## Protocolo — o que fica congelado e o que é acrescentado

A regra que vale para todo `EXP-NNNN` a partir daqui:

1. **Hipótese e protocolo são escritos uma vez e não mudam.** Estratégia, versão, `code_ref`, parâmetros completos, `params_hash`, timeframes, agregação, seed/âncora do ATR, política de reentrada, perfil de entrada/saída/custos, modelo de outcome e coorte (`prospective` | `replay:<run_id>`). Conteúdo diferente = **experimento novo**, linkado ao anterior. Nunca sobrescreva um `EXP-NNNN` existente.
2. **Avaliações são acrescentadas, datadas e rastreáveis.** Cada avaliação traz o SQL usado, os parâmetros da consulta, o `as_of`, a versão da métrica e a proveniência. A conclusão de ontem não é reescrita — ganha uma linha nova abaixo.
3. **Limiar editorial.** Abaixo de **100 outcomes avaliáveis E 30 dias distintos**, o campo `Result` só pode ser `inconclusivo`. Acima disso continua sendo pesquisa, nunca promessa: incerteza por reamostragem em blocos de tempo (mercados simultâneos são dependentes), sensibilidade a custos, variantes tentadas e avaliação futura reservada.
4. **Nada é ativado automaticamente.** A variante vencedora de um experimento nunca é promovida sozinha; ativar uma `strategy_version` é ato auditado, com pré-requisitos provados.
5. **Carteira não se aplica.** No Shadow Lab não há capital: `PnL de carteira` e `Max Drawdown de carteira` são **não aplicáveis**, e a soma de R hipotéticos, quando aparecer, vem com nome e ordenação explícitos.

## Template — `EXP-NNNN`

Ver [[_TEMPLATE-EXP]] para o arquivo pronto para copiar. Os campos e a distinção entre as métricas estão lá; o resumo do que cada uma significa:

| Campo | O que registra |
|---|---|
| Date / As of | Data de abertura do experimento e `as_of` de cada avaliação acrescentada |
| Hypothesis | O que se esperava provar ou refutar, em uma frase — **congelado** |
| Strategy / Version / code_ref / params_hash | Identidade exata do que está sendo medido — **congelada** |
| Cohort | `prospective` ou `replay:<run_id>` — replay nunca vira sinal prospectivo |
| Custos assumidos | Spread total, slippage por lado, taxa por lado — hipóteses declaradas, não tarifas verificadas |
| Cobertura | Emitidos, pendentes, entradas, não entradas por motivo, ativos, target, stop, expired, invalidated, censurados, funding indisponível |
| Taxa de alvo entre toques resolvidos | `target / (target + stop)` — **não** é taxa de lucro |
| Taxa de lucro líquido | Encerrados avaliáveis com `R_net > 0` / encerrados avaliáveis |
| Expectancy líquida hipotética em R | Média de `R_net` na mesma população |
| Profit Factor | Σ `R_net` positivos / \|Σ negativos\| — **nulo com motivo** se não houver perdas |
| PnL / Max Drawdown de carteira | **Não aplicável** (não há carteira no Shadow Lab) |
| Result | confirmou \| refutou \| inconclusivo (com o limiar editorial acima) |
| Conclusion / Next Action | Acrescentados por avaliação, nunca reescritos |

Todos os números vêm de `agent_signals` / `signal_outcomes` reais, com o SQL colado — nunca estimados ou inventados. Um experimento sem dado suficiente registra isso explicitamente em vez de preencher os campos com aproximação.

## Experimentos registrados

_Nenhum arquivo ainda._ `EXP-0001` e `EXP-0002` nascem quando S0 (migração), S1 (estratégias) e S2 (worker sombra) estiverem entregues e provados — ver [[Dialogos/SHADOW]].

## Relacionadas

[[Strategies]] · [[Agents Overview]] · [[Momentum Agent]] · [[Volume Agent]] · [[Performance Overview]] · [[Strategy Performance]] · [[Dialogos/SHADOW]] · [[Architecture Decisions]]

## Fontes

`docs/plans/SHADOW-LAB.md` (itens 9 e 11 da decisão conjunta) · `docs/plans/M2.md` (T2.8) · `.claude/state/dialogue-SHADOW.md` · `docs/decisions/0003-base-de-conhecimento-obsidian.md` · `docs/DATABASE.md` §6 e §9
