---
tags: [experimentos, indice]
updated: 2026-09-06
status: em-andamento
---

# Experiments Index

## Status honesto

**Dois experimentos abertos e coletando desde 2026-09-06.** S0 (migração `0002_shadow_lab`), S1
(estratégias) e S2 (`strategy-worker` em modo sombra) foram entregues e provados
(`.claude/state/s2-proof.md`), as duas versões foram ativadas pelo script auditado e o worker está
no ar emitindo sinais sobre o mercado real da Binance. Continua valendo o que o Shadow Lab **não**
é: não há carteira, ordem, posição nem PnL de portfolio — todo número é hipotético, com custos
assumidos declarados, e todo sinal carrega `purpose = research_only`.

Na primeira avaliação datada (`as_of = 2026-09-06T02:55:00Z`) os dois experimentos estão
**inconclusivos** pelo limiar editorial: **57** outcomes avaliáveis no `EXP-0001` (48 na coorte v1 +
9 na v2) e **72** no `EXP-0002` (66 + 6), todos em **1** dia distinto, contra os 100 outcomes **E**
30 dias exigidos. E há um segundo motivo, achado nessa mesma leitura: **nenhum** dos 57 do
`EXP-0001` teve o horizonte de 4 h maturado — a população avaliável é inteiramente composta de
acompanhamentos que resolveram cedo.

Cada experimento significativo (uma hipótese testada sobre uma estratégia, um conjunto de parâmetros, um mercado ou período) ganha seu próprio arquivo `EXP-NNNN-<slug>.md` nesta mesma pasta, numerado sequencialmente a partir de `EXP-0001`.

## Registro de IDs (decisão conjunta SHADOW, 2026-09-05)

| ID | Experimento | Origem | Estado |
|---|---|---|---|
| `EXP-0001` | [[EXP-0001-momentum-v1\|momentum em modo sombra]] (15 min, stop e alvo a 1,5 ATR da referência, horizonte 4 h) | Shadow Lab v0 — tarefa S4 | **aberto em 2026-09-06**, coortes `v1` (deprecated) e `v2` (active) |
| `EXP-0002` | [[EXP-0002-volume-anomaly-v1\|volume_anomaly em modo sombra]] (5 min, ATR de 15 min, stop na mínima da barra do sinal, horizonte 2 h) | Shadow Lab v0 — tarefa S4 | **aberto em 2026-09-06**, coortes `v1` (deprecated) e `v2` (active) |
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

| Arquivo | Estratégia | Aberto em | Última avaliação (`as_of`) | Result |
|---|---|---|---|---|
| [[EXP-0001-momentum-v1]] | `momentum` v1 (deprecated) + v2 (active) | 2026-09-06 | `2026-09-06T02:55:00Z` | **inconclusivo** — 57 avaliáveis (48 + 9), 1 dia, **0 com horizonte maturado** |
| [[EXP-0002-volume-anomaly-v1]] | `volume_anomaly` v1 (deprecated) + v2 (active) | 2026-09-06 | `2026-09-06T02:55:00Z` | **inconclusivo** — 72 avaliáveis (66 + 6), 1 dia, 35 com horizonte maturado |

### O que a próxima extração tem de fazer (achados da revisão da Astra, 2026-09-06)

O SQL das páginas já incorpora estes cinco pontos; ficam escritos aqui porque valem para **todo**
`EXP-NNNN` futuro, não só para estes dois:

1. **Coorte e propósito impostos na consulta**, não apenas declarados no protocolo
   (`supporting_features->>'cohort'` e `->>'purpose'`). No dia em que existir `replay:<run_id>`, um
   SQL sem esse filtro mistura prospectivo com retrospectivo em silêncio.
2. **Maturação do horizonte contada à parte** (`expires_at <= read_at`). Sem ela, uma leitura feita
   cedo mede só os acompanhamentos que resolveram rápido e a composição muda sozinha com o tempo.
3. **Motivos exatos**, agrupados pelo valor, nunca por `LIKE 'late%'` — `late:delay`,
   `late:missed_open` e `late:unconfirmed` são populações diferentes.
4. **PF nulo só com motivo verdadeiro:** ausência de **perdas** (denominador vazio) ou ausência de
   população. Ausência de **ganhos** dá PF **zero**, que é um resultado conhecido — chamá-lo de nulo
   esconderia o pior caso.
5. **Snapshot único** (`REPEATABLE READ READ ONLY`) para todas as consultas da mesma avaliação, e a
   ressalva escrita de forma dura: a leitura **não é reconstruível** depois, porque `signal_outcomes`
   avança no lugar e não há histórico de estados preservado.

### Por que existem duas coortes de versão em cada experimento

`v2` não é variante de pesquisa: nas duas estratégias ela nasceu da correção do `code_ref` (o
digest da árvore inteira invalidava toda versão congelada a cada módulo novo — MUST-FIX 1 do
`risk-engine-guardian`). Campo congelado não se corrige no lugar, então a correção obrigou uma
versão nova, e a `v1` foi `--supersede`d para `deprecated` **mantendo a população que já tinha**.
Código, `default_parameters`, `parameters_schema` e `params_hash` são idênticos entre as duas; o que
separa as populações é o `strategy_version_id` dentro do `uuid5` de cada sinal. Comparar `v1` com
`v2` como se fossem hipóteses concorrentes seria erro de leitura — está escrito em cada página.

### A VPS é uma população separada, ainda sem avaliação datada

Desde 2026-09-06 03:36 UTC o Shadow Lab também roda na VPS
(`.claude/state/vps-lab-proof.md`): `momentum v1` e `volume_anomaly v1` ativadas pelo script
auditado, 109 sinais em 1 h 18 min, todos `research_only` e `prospective`, `/ready` 200, outbox
109/109, zero exceção — e **zero `unavailable`**, ao contrário da máquina local.

Mas essas linhas **não** entram nas avaliações acima. São `strategy_version` próprias, com
`activated_at` e `code_ref` diferentes (o digest não é o mesmo entre Windows e Linux — [[Open Bugs]]),
logo são **coortes distintas**, com população própria. Vão virar avaliação datada no próximo
plantão, com o mesmo SQL, e com uma exclusão que a janela local não teve: **19 dos 70
acompanhamentos encerrados na VPS têm `R_net = NULL`** por funding não apurado
(`funding_missing:2026-09-06T04:00:00+00:00`, `funding_ambiguous_exit`), com `meta.r_ex_funding`
preservado — 27% dos encerrados ficam fora dos "encerrados avaliáveis".

### Rotina de plantão

A cada turno da [[Mente da Sexta-feira|Sexta-feira]] os experimentos ativos recebem **uma avaliação
nova, datada**, com o SQL colado, o `as_of` do turno e os números de saída real. Avaliação anterior
nunca é reescrita; hipótese e protocolo nunca mudam; a variante "vencedora" nunca é ativada
automaticamente. A rotina está em `.claude/agents/sexta-feira.md`, seção "Plantão permanente".

## Relacionadas

[[Strategies]] · [[Agents Overview]] · [[Momentum Agent]] · [[Volume Agent]] · [[Performance Overview]] · [[Strategy Performance]] · [[Dialogos/SHADOW]] · [[Architecture Decisions]]

## Fontes

`docs/plans/SHADOW-LAB.md` (itens 9 e 11 da decisão conjunta) · `docs/plans/M2.md` (T2.8) · `.claude/state/dialogue-SHADOW.md` · `docs/decisions/0003-base-de-conhecimento-obsidian.md` · `docs/DATABASE.md` §6 e §9
