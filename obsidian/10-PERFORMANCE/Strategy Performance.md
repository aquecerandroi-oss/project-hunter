---
tags: [performance, estrategias, shadow-lab, m5, m6]
updated: 2026-09-06
status: parcial
---

# Strategy Performance

## Status honesto

**Não há performance de estratégia para reportar** — e isso continua verdadeiro mesmo agora que o
Shadow Lab está coletando. O que existe desde 2026-09-06 são **experimentos em andamento** com
avaliações datadas e `Result: inconclusivo`; o que **não** existe é trade real, trade paper,
`agent_stats` populado ou Backtest Engine (M6).

Nenhum número de performance mora nesta página. Os números moram nos experimentos, com o SQL que os
produziu, o `as_of` e o denominador de cada métrica:

| Experimento | Estratégia | Última avaliação | Result |
|---|---|---|---|
| [[EXP-0001-momentum-v1]] | `momentum` v1 (deprecated) + v2 (active) | `as_of = 2026-09-06T02:55:00Z` | **inconclusivo** — 57 outcomes avaliáveis, **1** dia distinto, **0** com horizonte maturado |
| [[EXP-0002-volume-anomaly-v1]] | `volume_anomaly` v1 (deprecated) + v2 (active) | `as_of = 2026-09-06T02:55:00Z` | **inconclusivo** — 72 outcomes avaliáveis, **1** dia distinto, 35 com horizonte maturado |

Limiar editorial da [[Dialogos/SHADOW|decisão conjunta]] (item 9): abaixo de **100 outcomes
avaliáveis E 30 dias distintos**, só descrição e `inconclusivo`. Acima disso continua sendo
pesquisa, nunca promessa.

## As métricas do Shadow Lab, com o nome certo

Estas são as definições que valem no Lab. Confundir duas delas é o erro que a decisão conjunta
existe para impedir.

| Métrica | Definição exata | Denominador | O que **não** é |
|---|---|---|---|
| **Taxa de alvo entre toques resolvidos** | `target / (target + stop)` | acompanhamentos que tocaram alvo ou stop | **não** é taxa de lucro: ignora `expired`/`invalidated` e ignora custos |
| **Taxa de lucro líquido** | encerrados avaliáveis com `R_net > 0` / encerrados avaliáveis | `tracking_state = terminal` com `r_multiple` não nulo (inclui `expired` e `invalidated` com resultado conhecido) | **não** é taxa de alvo |
| **Expectancy líquida hipotética em R por entrada encerrada avaliável** | média de `R_net` na mesma população | idem | **não** é retorno esperado de carteira |
| **Profit Factor** | Σ `R_net` positivos / \|Σ `R_net` negativos\| | idem | **nulo com motivo** só quando faltam **perdas** (denominador vazio) ou quando não há população avaliável. Faltar **ganhos** não é desconhecimento: a soma de um conjunto vazio é **zero**, e o PF é **zero** — chamá-lo de nulo apresentaria como indisponível o pior resultado possível (achado da Astra, 2026-09-06) |
| **MFE / MAE** | extremos canônicos, **nulos** quando o OHLC não determina o extremo nem o instante | barras completas; limites em `meta.excursions.bounds`, `ambiguous` explícito | **não** é "zero quando não sei" |
| **Soma de R hipotéticos** | soma escalar de `R_net` | encerrados avaliáveis | **não é equity** e não é trajetória: uma curva exigiria ordenação e capital, que não existe aqui |
| **Horizonte maturado** | `expires_at <= read_at` — quantos acompanhamentos tiveram a janela inteira disponível | encerrados avaliáveis | é a métrica que diz se as demais descrevem a população ou só os que resolveram cedo |
| **PnL de carteira** | **não aplicável** | — | não há capital no Shadow Lab |
| **Max Drawdown de carteira** | **não aplicável** | — | idem |

**Cobertura é parte da métrica, não nota de rodapé.** Toda avaliação traz contagens completas —
emitidos, pendentes, entradas, não entradas pelo motivo **exato** (`late:delay`, `late:missed_open`,
`late:unconfirmed`, `geometry`), ativos, `target`, `stop`, `expired`, `invalidated`, censurados por
motivo (`gap:<minuto>:*`), funding indisponível — mais mercados distintos, dias distintos, horizonte
maturado, `as_of`, `read_at`, versão da métrica e proveniência. Uma taxa sem a cobertura ao lado é um
número sem população.

**A leitura não é reconstruível, e isso fica escrito.** `signal_outcomes` avança no lugar; não há
histórico de estados preservado. `as_of` congela a *população* (`emitted_at <= as_of`); `read_at` diz
quando os *estados* foram lidos, e todas as consultas de uma avaliação rodam no mesmo snapshot
(`REPEATABLE READ READ ONLY`). Reexecutar amanhã dá outros estados sobre a mesma população, e nenhuma
consulta recompõe os de hoje — por isso a avaliação é **acrescentada e datada**, nunca recalculada.

**Custos assumidos, declarados:** spread total 2 bps, slippage 5 bps por lado, taxa 4 bps por lado,
funding assinado. São **hipóteses do experimento**, não tarifas verificadas com a corretora.

## Por que "v1 × v2" ainda não é comparação de versões

Nos dois experimentos existem duas coortes de versão, mas elas **não** são hipóteses concorrentes:
`v2` nasceu da correção do `code_ref` (digest da árvore inteira → digest do módulo mais o fecho dos
imports). Código, `default_parameters`, `parameters_schema` e `params_hash` são idênticos; só o
`code_ref` mudou. A comparação antes/depois entre versões **de conteúdo diferente** — que é o que
esta seção vai receber um dia — exige rodar as duas em paralelo, no mesmo intervalo e no mesmo
universo elegível, reportando cobertura e exclusões por versão.

## O que vai alimentar esta página quando existir mais

- **Shadow (hoje):** `agent_signals` + `signal_outcomes` por `strategy_version_id`, com coorte
  (`prospective` | `replay:<run_id>`) e `as_of` obrigatórios. Escritor único: `strategy-worker`
  ([[Workers]]); a transferência futura ao `analytics-worker` está registrada em `docs/PIPELINE.md`
  §6b.
- **Paper/ao vivo (M4/M5):** `agent_stats` agregado por `strategy_version_id`.
- **Backtest (M6):** `backtest_results` por segmento (`full|train|validation|oos|wf_1..n`), com
  `metrics`, `equity_curve` e `warnings` (`overfitting`, `leakage`, `lookahead`); o Backtest Engine
  reusa o mesmo código de `Strategy`, `RiskEngine` e `PaperExecutionAdapter` do tempo real.

## Regra de versionamento

Uma versão de estratégia nunca é sobrescrita: a trigger de `0002_shadow_lab` recusa `UPDATE` dos
campos congelados de qualquer linha já ativada. Conteúdo diferente = versão nova. E a variante com
melhor número **nunca** é ativada automaticamente — ativar uma `strategy_version` é ato auditado,
com pré-requisitos provados.

## Relacionadas

[[Strategies]] · [[Performance Overview]] · [[Agent Performance]] · [[Experiments Index]] · [[EXP-0001-momentum-v1]] · [[EXP-0002-volume-anomaly-v1]] · [[Momentum Agent]] · [[Volume Agent]] · [[Workers]] · [[Dialogos/SHADOW]]

## Fontes

`docs/plans/SHADOW-LAB.md` (item 9 da decisão conjunta) · `.claude/state/s2-proof.md` ·
`docs/DATABASE.md` §6 e §9 · `docs/ROADMAP.md` (Milestones 5 e 6)
