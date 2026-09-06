---
tags: [performance, analytics, shadow-lab, m5]
updated: 2026-09-06
status: parcial
---

# Performance Overview

## Status honesto

**Não existe dado de performance de carteira, e não vai existir antes do M3/M4.** Não há trade
paper, não há posição, não há capital. `agent_stats`, `portfolio_equity_snapshots` e `trades`
continuam vazias, e o `analytics-worker` que as popularia é do M5.

**O que passou a existir em 2026-09-06:** mercado real coletado (M1 aprovado) e `agent_signals` +
`signal_outcomes` reais, escritos pelo `strategy-worker` em modo sombra. São **medidas de
experimento**, hipotéticas e com custos assumidos declarados, e estão em
[[EXP-0001-momentum-v1]] e [[EXP-0002-volume-anomaly-v1]] — não nesta página, e não como
performance. As duas avaliações abertas estão `inconclusivo` pelo limiar editorial (100 outcomes
avaliáveis **E** 30 dias distintos). Definições das métricas em [[Strategy Performance]].

## O que vai alimentar cada visão (quando existir)

| Página | Fonte de dado planejada | Depende de |
|---|---|---|
| [[Agent Performance]] | `agent_stats` (materializado por janela 7d/30d/90d/all, por regime, mercado, hora, volatilidade) | M4 (agentes gerando sinal) + M5 (analytics-worker) |
| [[Strategy Performance]] | hoje: `agent_signals` + `signal_outcomes` por `strategy_version_id` (Shadow Lab, só como ponteiro para os `EXP-NNNN`); depois: `agent_stats` agregado e `backtest_results` | Shadow Lab (existe), M4/M5, M6 (backtest) |
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
