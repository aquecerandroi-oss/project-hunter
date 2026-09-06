---
tags: [arquitetura, pipeline, eventos, shadow-lab]
updated: 2026-09-06
status: parcial
---

# Data Flow

O pipeline completo Market → Features → Anomaly → Regime → Opportunity → Agent → Risk → Execution → Analytics, definido em `docs/PIPELINE.md`.

**O que roda hoje (2026-09-06):** o primeiro trecho e um **desvio de pesquisa** que ainda não passa pelo meio.

```
Binance WS ──► [market-worker] ──► market.candles.closed ──┐
                     │                                      │
                     └─► Redis hot state + Postgres         │
                                                            ▼
                                         [strategy-worker]  modo sombra
                                            avalia strategy_versions ativas
                                            decisão + outcome + episódio + outbox
                                            (uma transação, ACK só após commit)
                                                            │
                                                            ▼
                                              shadow.signals.emitted
                                              (purpose = research_only)
                                                            │
                                                            ✗ nenhum consumidor de execução
```

O `strategy-worker` de hoje **pula** Feature/Anomaly/Regime/Opportunity (M2) de propósito: as
estratégias v0 calculam o que precisam direto das velas, e isso é parte do protocolo congelado
([[EXP-0001-momentum-v1]]). Uma versão futura sobre as features do M2 é outra versão, comparada em
paralelo — nunca a mesma renomeada.

**O que ainda não roda:** `scanner-worker` (M2), proposal builder + [[Risk Engine]] (M4),
`execution-worker` (M3/M4), `analytics-worker` (M5).

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

## Etapas

| Etapa | Onde | Gatilho | Milestone | Estado |
|---|---|---|---|---|
| Market Data | `market-worker` | contínuo (WS) | M1 | **no ar** |
| **Decisão sombra + outcome** | `strategy-worker` | `market.candles.closed` | Shadow Lab (S2) | **no ar** — stream próprio `shadow.signals.emitted`, `purpose = research_only`, escritor único dos outcomes do Lab ([[Workers]]) |

As etapas abaixo continuam planejadas:

| Etapa | Onde | Gatilho | Milestone |
|---|---|---|---|
| Feature Engine | `scanner-worker` | `market.ticks` / `market.candles.closed` | M2 |
| Anomaly Engine | `scanner-worker` | `features.updated` | M2 |
| Market Regime Engine | `scanner-worker` | a cada 1 min | M2 |
| Opportunity Engine | `scanner-worker` | `features.updated`, `anomalies.detected` | M2 |
| Strategy Agents | `strategy-worker` | `opportunities.updated` | M4 |
| Proposal builder + Risk Engine | `strategy-worker` | `signals.emitted` | M4 |
| Execution Engine | `execution-worker` | `proposals.decided` (approved) | M3 |
| Analytics e Learning | `analytics-worker` | 1 min / 1 h / diário | M5 |

## Isolamento do desvio de pesquisa

O caminho sombra é deliberadamente **inalcançável** a partir da execução, em quatro camadas:

1. **Stream separado** — `shadow.signals.emitted`, não `signals.emitted`; nenhum consumidor de
   execução assina esse stream.
2. **Rótulo persistido** — `purpose = research_only` no envelope imutável (`supporting_features`) e
   no payload do evento, escrito uma vez na decisão e nunca depois.
3. **Recusa no consumidor futuro** — o proposal builder do M4 recusa `research_only`, com teste.
4. **Ativação ≠ elegibilidade** — `strategy_versions.status = active` autoriza *avaliar*, nunca
   *executar*; o M4 terá um `execution_eligible` explícito e separado.

Consenso do Opportunity Engine do M2 recebe peso **zero** para sinais sombra.

## Comunicação (definida, parcialmente em uso)

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
