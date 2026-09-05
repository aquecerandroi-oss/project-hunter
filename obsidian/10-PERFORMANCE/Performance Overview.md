---
tags: [performance, analytics, m5]
updated: 2026-09-05
status: planejado
---

# Performance Overview

## Status honesto

**Não existe nenhum dado de performance ainda.** Não há mercado sendo coletado, não há sinal gerado, não há trade paper executado. As tabelas que vão alimentar esta área (`agent_stats`, `signal_outcomes`, `portfolio_equity_snapshots`, `trades`) existem como schema vazio desde o M0. O `analytics-worker` que as populariam é planejado para o M5.

## O que vai alimentar cada visão (quando existir)

| Página | Fonte de dado planejada | Depende de |
|---|---|---|
| [[Agent Performance]] | `agent_stats` (materializado por janela 7d/30d/90d/all, por regime, mercado, hora, volatilidade) | M4 (agentes gerando sinal) + M5 (analytics-worker) |
| [[Strategy Performance]] | `agent_stats` agregado por `strategy_version_id`; `backtest_results` quando houver backtest | M4/M5, M6 (backtest) |
| Dashboard (`/analytics`) | `trades`, `portfolio_equity_snapshots`, `risk_events` | M3 (execução) + M5 (agregação) |

## Métricas previstas (definição, não dado real)

`agent_stats` vai calcular, por janela: `trades`, `wins`, `losses`, `win_rate`, `profit_factor`, `expectancy`, `avg_win`, `avg_loss`, `sharpe`, `sortino`, `max_drawdown_pct`, `pnl`, `pnl_pct`, mais quebras por regime, mercado, hora do dia e faixa de volatilidade (`by_regime`, `by_market`, `by_hour`, `by_volatility` em JSONB).

Todo sinal — mesmo sem agente ativo apostando nele — abre um `signal_outcomes` (shadow de sistema) rastreando MFE/MAE até stop, alvo, invalidação ou expiração, o que permite medir "teria funcionado" antes mesmo de qualquer agente operar de verdade.

## O que NÃO fazer nesta página até haver dado real

Não estimar win rate, PnL ou drawdown a partir de intuição, backtest informal ou expectativa de mercado. Quando o primeiro `agent_stats` real existir, esta página passa a citar números com a janela e a data de cálculo, nunca um valor solto sem proveniência.

## Relacionadas

[[Agent Performance]] · [[Strategy Performance]] · [[Experiments Index]]

## Fontes

`docs/DATABASE.md` §6, `docs/PIPELINE.md` §9, `docs/ROADMAP.md` (Milestone 5)
