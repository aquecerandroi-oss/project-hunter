---
tags: [agentes, m4]
updated: 2026-09-05
status: planejado
---

# Agents Overview

## Status

**Planejado para o Milestone 4.** A tabela `agents` (instância de uma `strategy_version` num portfolio, com alocação, filtros e status `enabled|paused|disabled`) existe como schema desde o M0, mas não há nenhum agente real criado — nem `strategy-worker`, nem CRUD de API, nem UI em `/agents`.

## O que um agente é (definição, não implementação)

Um `agent` é uma instância de uma `strategy_version` dentro de um portfolio: `parameters` (ou defaults), `capital_allocation_pct`, `max_open_positions`, `allowed_directions`, `market_filter`, `min_opportunity_score`, `min_confidence`. Um agente nunca executa — ele produz `Signal`, que vira `trade_proposal` por portfolio inscrito, que passa pelo Risk Engine (ver [[Risk Engine]]). Essa regra é hard rule do produto, não um detalhe de implementação futura.

## As quatro páginas desta pasta

[[Momentum Agent]], [[Volume Agent]], [[Breakout Agent]], [[Order Flow Agent]] documentam as estratégias previstas no roadmap. Hoje todas têm status `planejado` — nenhuma tem código, sinal gerado ou histórico.

| Agente | Estratégia (`strategies.key`) | Milestone |
|---|---|---|
| Momentum | `momentum` (`momentum_v1`) | M4 |
| Volume | `volume_anomaly` (`volume_anomaly_v1`) | M4 |
| Breakout | `breakout` | Fase 2 |
| Order Flow | `order_flow` | Fase 2 |

## Fluxo planejado (proposal builder)

1. Busca agentes `enabled` cuja `strategy_version_id` bate com o sinal e cujos filtros aceitam o mercado.
2. Cria `trade_proposals` com `idempotency_key = sha256(agent_id, signal_id)` — sem duplicata mesmo com reentrega de evento.
3. `RiskEngine.evaluate(...)` decide; só aprovado chega à execução.

## Relacionadas

[[Strategies]] · [[Risk Engine]] · [[Momentum Agent]] · [[Volume Agent]] · [[Breakout Agent]] · [[Order Flow Agent]]

## Fontes

`docs/DATABASE.md` §6, `docs/PIPELINE.md` §6–7, `docs/ROADMAP.md` (Milestone 4), `CLAUDE.md`
