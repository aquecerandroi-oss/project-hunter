---
tags: [performance, agentes, m5]
updated: 2026-09-06
status: planejado
---

# Agent Performance

## Status honesto

**Sem dado.** Nenhum agente existe (ver [[Agents Overview]]), então não há uma única linha em `agent_stats` para reportar. Esta página fica pronta para quando houver.

**Cuidado com a confusão que 2026-09-06 tornou possível.** O Shadow Lab está gerando `agent_signals`
e `signal_outcomes` reais desde 2026-09-06 ([[EXP-0001-momentum-v1]], [[EXP-0002-volume-anomaly-v1]]),
mas isso **não** é performance de agente: não há `agents`, não há portfolio, não há trade e
`agent_stats` continua vazia. Sinal sombra é pesquisa sobre uma `strategy_version`; agente é uma
configuração de um dono apostando num portfolio, e isso é Milestone 4.

## O que será medido, por agente, quando existir

`agent_stats` (PK `agent_id, window`) por janela `all|7d|30d|90d`: `trades`, `wins`, `losses`, `win_rate`, `profit_factor`, `expectancy`, `avg_win`, `avg_loss`, `sharpe`, `sortino`, `max_drawdown_pct`, `pnl`, `pnl_pct`, e quebras por regime de mercado, mercado, hora do dia e faixa de volatilidade.

Materializado pelo `analytics-worker` (M5), a partir de `trades` (fechamento real de posições paper/shadow — ver [[Paper Trading]]) e de `signal_outcomes` (shadow de sistema, aberto para todo sinal emitido, independentemente de ter virado trade).

## Quando os primeiros dados existirem

Cada agente relevante (`momentum_v1`, `volume_anomaly_v1` — ver [[Momentum Agent]], [[Volume Agent]]) deve ter sua performance citada com a janela e a data de cálculo, nunca um número solto. Comparações antes/depois de mudança de parâmetro ou versão vão para [[Experiments Index]] como `EXP-NNNN`, não para esta página.

## Relacionadas

[[Agents Overview]] · [[Performance Overview]] · [[Experiments Index]]

## Fontes

`docs/DATABASE.md` §6, `docs/PIPELINE.md` §9, `docs/ROADMAP.md` (Milestone 5)
