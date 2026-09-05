---
tags: [trading, risco, m4]
updated: 2026-09-05
status: planejado
---

# Risk Engine

## Status

**Planejado para o Milestone 4.** `hunter_risk` (`packages/risk-core`) ainda não tem implementação — hoje só existe a interface (`RiskEngine.evaluate` como Protocol em `docs/ARCHITECTURE.md` §6) e o schema (`risk_profiles`, `trade_proposals.risk_decision`, `risk_events`, `kill_switch_transitions`). É a peça mais sensível do sistema — regra de ouro do produto (`CLAUDE.md`): **nenhum agente executa ordens**; todo caminho de entrada é AGENT → PROPOSAL → RISK ENGINE → EXECUTION, e o `risk-engine-guardian` (opus) é revisor obrigatório de qualquer mudança aqui quando ela for implementada.

## Contrato (definido, sem código)

`evaluate(proposal, portfolio_state, limits, market_liquidity, kill_switch) -> RiskDecision`. Função **pura e determinística** — sem IO, sem chamada de rede ou banco — testável com tabelas de casos e reutilizável no backtest (M6). LLM não tem acesso ao Risk Engine nem aos limites.

## Limites planejados (por preset de `risk_profiles.limits`)

| Chave | Conservative | Balanced | Aggressive |
|---|---|---|---|
| `max_position_pct` | 0.02 | 0.05 | 0.10 |
| `risk_per_trade_pct` | 0.0025 | 0.005 | 0.01 |
| `max_total_exposure_pct` | 0.30 | 0.60 | 1.00 |
| `max_daily_loss_pct` | 0.01 | 0.02 | 0.04 |
| `max_drawdown_pct` | 0.05 | 0.10 | 0.20 |
| `max_concurrent_positions` | 3 | 6 | 12 |
| `max_leverage` | 1 | 2 | 3 |

Tabela completa (13 chaves) em `docs/RISK_ENGINE.md` §2.

## Checks planejados (20, em ordem, todos registrados mesmo após o primeiro reprovado)

`kill_switch` → `portfolio_status` → `data_quality` → `signal_validity` → `stop_distance` → `daily_loss` → `drawdown` → `concurrent_positions` → `duplicate_position` → `liquidity` → `spread` → `sizing` → `position_size` → `total_exposure` → `asset_exposure` → `exchange_exposure` → `correlation` → `slippage_estimate` → `leverage` → `cash`.

## Kill switch (planejado, 3 escopos)

Sistema, organização, portfolio; estado efetivo = mais restritivo entre os três (`ACTIVE < WARNING < TRADING_DISABLED < EMERGENCY`). `WARNING` reduz tamanho pela metade; `TRADING_DISABLED`/`EMERGENCY` bloqueiam toda entrada nova; saídas (stop, alvo, fechamento manual) são sempre permitidas. `SYSTEM_KILL_SWITCH=ACTIVE` já existe em `.env.example` como flag de sistema, acionável sem redeploy — mas hoje não há nenhum worker lendo esse valor para agir sobre ele.

## Testes planejados

Tabela de casos do Risk Engine (cada check aprovando e reprovando isoladamente); kill switch por escopo; pipeline de integração candle sintético → sinal → proposta → fill paper.

## Relacionadas

[[Execution Engine]] · [[Agents Overview]] · [[Architecture Decisions]] (regra "nenhum agente executa")

## Fontes

`docs/RISK_ENGINE.md`, `docs/PIPELINE.md` §7, `CLAUDE.md` ("Hard rules"), `docs/ROADMAP.md` (Milestone 4)
