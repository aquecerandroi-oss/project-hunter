---
tags: [performance, estrategias, m5, m6]
updated: 2026-09-05
status: planejado
---

# Strategy Performance

## Status honesto

**Sem dado.** Nenhuma `strategy_version` está ativa (ver [[Strategies]]) e não há Backtest Engine (M6). Não há trades reais nem backtest para reportar.

## O que vai alimentar esta página, quando existir

- **Ao vivo/paper (M4/M5):** `agent_stats` agregado por `strategy_version_id` em vez de por agente individual — permite comparar `momentum_v1` vs `volume_anomaly_v1`, ou uma versão contra a anterior da mesma estratégia.
- **Backtest (M6):** `backtest_results` por segmento (`full|train|validation|oos|wf_1..n`), com `metrics` JSONB, `equity_curve` e `warnings` (`overfitting`, `leakage`, `lookahead`) — o Backtest Engine reusa o mesmo código de `Strategy`, `RiskEngine` e `PaperExecutionAdapter` do tempo real, para eliminar look-ahead por construção.

## Versionamento (regra a valer quando houver a primeira `v2`)

Uma versão de estratégia nunca é sobrescrita. Quando `volume_anomaly_v2` existir, por exemplo, a comparação de performance antes/depois entre `v1` e `v2` vira conteúdo desta página ou de uma página dedicada em [[Strategies]], sempre citando janela e proveniência dos números — nunca estimativa.

## Relacionadas

[[Strategies]] · [[Performance Overview]] · [[Experiments Index]]

## Fontes

`docs/DATABASE.md` §6 e §9, `docs/ROADMAP.md` (Milestones 5 e 6)
