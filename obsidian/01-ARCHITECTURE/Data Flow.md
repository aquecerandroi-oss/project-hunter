---
tags: [arquitetura, pipeline, eventos]
updated: 2026-09-05
status: planejado
---

# Data Flow

O pipeline completo Market → Features → Anomaly → Regime → Opportunity → Agent → Risk → Execution → Analytics, definido em `docs/PIPELINE.md`. **Nada neste fluxo roda hoje** — é a especificação para M1–M5. O que existe no M0 é só a comunicação básica (Redis conectado, envelopes de evento definidos em `hunter_core.events`), sem nenhum produtor ou consumidor real ainda.

## Visão

```
Binance WS ─┐                                        ┌─ rt:* (pub/sub) ─► api ─► browser
Bybit WS   ─┤                                        │
            ▼                                        │
[market-worker] ─ market.ticks / candles.closed / derivatives / liquidations
       │                                              │
       ▼                                              │
[scanner-worker]  Feature Engine ── features.updated  │
                  Anomaly Engine ── anomalies.detected│
                  Regime Engine  ── regime.changed     │
                  Opportunity    ── opportunities.updated
                       │
                       ▼
[strategy-worker]  Agents ── signals.emitted ──► signal_outcomes (analytics)
                   Proposal builder + Risk Engine ── proposals.decided
                       │ aprovado
                       ▼
[execution-worker]  ExecutionAdapter(paper|shadow) ── executions.completed
                    Position manager (stops, alvos, MTM) ── positions.updated
                       │
                       ▼
[analytics-worker]  agent_stats, outcomes, retenção ── analytics.updated
                       │
                       └──► Learning Engine (Fase 3)
```

## Etapas (todas planejadas)

| Etapa | Onde | Gatilho | Milestone |
|---|---|---|---|
| Market Data | `market-worker` | contínuo (WS) | M1 |
| Feature Engine | `scanner-worker` | `market.ticks` / `market.candles.closed` | M2 |
| Anomaly Engine | `scanner-worker` | `features.updated` | M2 |
| Market Regime Engine | `scanner-worker` | a cada 1 min | M2 |
| Opportunity Engine | `scanner-worker` | `features.updated`, `anomalies.detected` | M2 |
| Strategy Agents | `strategy-worker` | `opportunities.updated` | M4 |
| Proposal builder + Risk Engine | `strategy-worker` | `signals.emitted` | M4 |
| Execution Engine | `execution-worker` | `proposals.decided` (approved) | M3 |
| Analytics e Learning | `analytics-worker` | 1 min / 1 h / diário | M5 |

## Comunicação (definida, não usada em produção ainda)

- **Redis Streams** (worker → worker): envelope fixo `{event_id, type, ts, producer, key, payload}`; `MAXLEN ~ N` por tipo; consumer groups por serviço; idempotência via `hunter:processed:{consumer}` + `processed_events` no Postgres.
- **Redis pub/sub** (workers → api → browser): canais `rt:market:{exchange}:{symbol}`, `rt:radar`, `rt:org:{org_id}:portfolio:{id}`, `rt:org:{org_id}:risk`, `rt:system`.
- **Redis hot state:** chaves como `mkt:{ex}:{sym}:ticker`, `feat:{ex}:{sym}`, `opp:{ex}:{sym}`, `radar:scores`, `hb:{role}:{instance}` — tudo perdível; o que importa para auditoria/contabilidade está no Postgres.

Lista completa de streams, produtores e consumidores em `docs/PIPELINE.md` §10.

## Anti-look-ahead (regra de design, ainda sem código para testar)

Bar-features usam só candles `is_final`; o candle em formação entra apenas nas tick-features, marcadas com sufixo `_live`. O Backtest Engine (M6) reusa o mesmo código de `Strategy`/`RiskEngine`/`PaperExecutionAdapter` do tempo real para eliminar look-ahead por construção.

## Relacionadas

[[System Overview]] · [[Market Collector]] · [[Features]] · [[Anomalies]] · [[Risk Engine]] · [[Execution Engine]]

## Fontes

`docs/PIPELINE.md`, `docs/ARCHITECTURE.md` §5
