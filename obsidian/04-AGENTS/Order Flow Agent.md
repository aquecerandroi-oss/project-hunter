---
tags: [agentes, order-flow, fase2]
updated: 2026-09-05
status: planejado
---

# Order Flow Agent

## Status

**Planejado para a Fase 2** (depois do M6). Igual ao [[Breakout Agent]], existe hoje só como chave prevista no catálogo (`strategies.key = order_flow`), sem versão, seed ou especificação de comportamento.

## O que se sabe hoje

O nome sugere uso das features de microestrutura já especificadas para o Feature Engine (M2): `orderbook_imbalance_5/25`, `buy_sell_pressure_1m/5m`, `trade_velocity_1m` (ver [[Features]]). Essas features também alimentam o componente "Order Flow" do Opportunity Engine (peso padrão 0.15), mas isso não implica que o agente em si tenha regras definidas — o componente de score e o agente/estratégia são coisas diferentes no pipeline (ver [[Data Flow]]).

## Relacionadas

[[Agents Overview]] · [[Strategies]] · [[Features]]

## Fontes

`docs/ROADMAP.md` (Fase 2), `docs/DATABASE.md` §6, `docs/PIPELINE.md` §5
