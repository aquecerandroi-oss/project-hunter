---
tags: [experimentos, indice]
updated: 2026-09-05
status: planejado
---

# Experiments Index

## Status honesto

**Não existe nenhum experimento ainda.** Não há paper trading rodando, não há agente ativo, não há dado real de sinal ou trade. Esta página existe para fixar o formato que será usado a partir do primeiro experimento real — provavelmente não antes do Milestone 4 (agentes gerando sinais) ou do M6 (Backtest Engine), quando houver `signal_outcomes` ou resultado de backtest suficiente para relatar.

Cada experimento significativo (uma hipótese testada sobre uma estratégia, um conjunto de parâmetros, um mercado ou período) ganha seu próprio arquivo `EXP-NNNN-<slug>.md` nesta mesma pasta, numerado sequencialmente a partir de `EXP-0001`. Esta página só serve como índice — quando o primeiro experimento existir, ele é listado na tabela abaixo.

## Template — `EXP-NNNN`

Ver [[_TEMPLATE-EXP]] para o arquivo pronto para copiar. Todo experimento documenta:

| Campo | O que registra |
|---|---|
| Date | Data em que o experimento foi rodado/fechado |
| Hypothesis | O que se esperava provar ou refutar, em uma frase |
| Strategy | `strategies.key` + `strategy_versions.version` testada |
| Parameters | Parâmetros não-default usados (JSON de `parameters`) |
| Markets | Mercados/exchanges incluídos |
| Sample Size | Número de sinais ou trades considerados |
| Trades | Contagem real de trades fechados |
| Win Rate | Fração de trades vencedores |
| Profit Factor | Soma de ganhos / soma de perdas |
| Expectancy | Retorno esperado por trade |
| PnL | Resultado agregado (paper — nunca dinheiro real antes da Fase 4) |
| Max Drawdown | Maior queda do pico de equity durante o experimento |
| Result | Confirmou, refutou ou inconclusivo |
| Conclusion | O que se aprendeu, em texto |
| Next Action | Ativar, ajustar parâmetro, descartar, ou rodar de novo com mais dado |

Todos os números vêm de `agent_stats`/`signal_outcomes`/`backtest_results` reais — nunca estimados ou inventados. Um experimento sem dado suficiente registra isso explicitamente em vez de preencher os campos com aproximação.

## Experimentos registrados

_Nenhum até o momento._

## Relacionadas

[[Strategies]] · [[Agents Overview]] · [[Performance Overview]]

## Fontes

`docs/decisions/0003-base-de-conhecimento-obsidian.md` (formato definido pelo dono do produto), `docs/DATABASE.md` §6 e §9
