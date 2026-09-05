---
tags: [mercado, market-worker, m1]
updated: 2026-09-05
status: parcial
---

# Market Collector

## Status

**Parcial — implementado no M1 (T1.3, commit `b8c4766`), ainda sem prova operacional.** O serviço `market-worker` existe e roda contra o Protocol do adaptador (`services/market-worker/hunter_market_worker/`, 20 módulos, 20 arquivos de teste, 139 testes verdes). O que **ainda não** existe é a prova de que ele coleta dado real de ponta a ponta: a integração com o adaptador Binance da T1.2 nunca foi executada ao vivo por mais de um ciclo, e a validação operacional (subir o worker, ver `mkt:*` vivo no Redis e linhas entrando no Postgres por 60 s) é da **T1.6**. Enquanto isso não acontecer, o dashboard continua honesto: "mercados monitorados = 0" até haver linha em `markets`.

## O que existe (com caminho)

| Peça | Arquivo | O que faz |
|---|---|---|
| Universo | `hunter_market_worker/universe.py` | `list_markets(perpetual)` a cada `MARKET_UNIVERSE_REFRESH_S` (900 s), upsert de `assets`/`markets` com tick/step/min_notional, `volume_24h_usd`, `monitor_rank`, `is_monitored` no top `MARKET_UNIVERSE_SIZE`, allow/blocklist, aplica só entradas e saídas (não reassina os mantidos), publica `market.universe.changed` |
| Ingestão WS | `ingest.py`, `streaming.py` | assina os canais dos monitorados, coalescência de 250 ms, publica `market.ticks`, `market.candles.closed`, `market.derivatives`, `market.liquidations` e o pub/sub `rt:market:{ex}:{sym}` / `rt:system` |
| Hot state | `hot_state.py` | hashes `mkt:*:ticker` / `:book` / `:deriv` e as listas de trades e candles em Redis, com TTL e propriedade de campo por escritor (`mark_ts`, `oi_ts`, `funding_ts` independentes) |
| Fila limitada | `queues.py` | limite por itens, bytes e idade; snapshot pendente é substituído pelo mais novo; descarte é contado e vira `system_event` |
| Persistência | `persist.py`, `persist_rows.py`, `sampling.py`, `funding.py` | um `INSERT ... ON CONFLICT DO NOTHING` multi-linha por tabela por flush, role `hunter_worker`; candles 1m finais, `market_snapshots` por minuto, `funding_rates`, `open_interest_history` em buckets UTC de 5 min, `liquidations` com `id` uuid5 determinístico |
| Recovery | `recovery.py`, `recovery_queries.py` | detecção de buracos na janela de 24 h por consultas set-based (uma por universo, não uma por mercado), backfill REST com `source=rest`, `ingestion_gaps`, `failed` na 5ª tentativa com reabertura após 1 h |
| Partições | `partitions.py` | guarda fatal no startup quando falta partição para *agora*; falta de partição para *amanhã* só derruba `/ready`, com `system_event` critical |
| Supervisão | `supervision.py`, `main.py` | um `TaskGroup` com dez tarefas permanentes, retorno inesperado é fatal; watchdog por conexão (30 s sem dado → warning e reinício, 3 reinícios sem progresso → fatal) |
| Heartbeat | `heartbeat.py` | `hb:market:{exchange}` com `last_event_at`; `system_events` em reconexão, gap, descarte e falha de publicação |

Configuração em `.env.example`: `MARKET_EXCHANGE_CODE`, `MARKET_UNIVERSE_ALLOWLIST`/`BLOCKLIST`, `MARKET_UNIVERSE_REFRESH_S`, `MARKET_OI_POLL_S`, `MARKET_SNAPSHOT_INTERVAL_S`, `MARKET_STALE_AFTER_S`.

## O que falta

- **Integração real com o adaptador Binance da T1.2** — o worker foi desenvolvido e testado contra um `FakeAdapter` que implementa o Protocol. As duas peças nunca rodaram juntas contra a Binance por mais de um ciclo.
- **Prova operacional (T1.6)** — subir `docker compose`, rodar `HUNTER_ROLE=market`, e mostrar preço vivo em `mkt:binance:BTCUSDT:ticker`, `ts` avançando, e linhas reais em `candles_1m` / `market_snapshots`. Sem isso, esta página não vira `implementado`.
- **Agendamento diário de `infra/scripts/create_partitions.py`** — hoje o worker só *detecta* a falta de partição. Dono: T1.6/ops.
- **Follow-ups registrados em `docs/plans/M1.md`**: `command_timeout` de 30 s valendo para o engine da API; `market_snapshots.ts` como bucket do minuto e não instante da coleta; sufixo REST parcial no bootstrap; duplicidade de `ingestion_gaps` com duas instâncias por exchange (premissa do M1: uma instância por exchange); `spread_pct` ×100 nos helpers de domínio (T1.1c).
- **Bybit** — M1b, mesmo contrato.

## O que foi especificado no plano (referência)

**Universo.** A cada 15 min, `list_markets(perpetual)` em cada exchange; atualiza `markets` (novos, delistados, `volume_24h_usd`); recalcula `monitor_rank`; marca `is_monitored` para os N primeiros (`MARKET_UNIVERSE_SIZE`, padrão 200 por exchange, já em `.env.example`). Mudança no universo publica `market.universe.changed`.

**Streams WS** por mercado monitorado: `aggTrade`, `bookTicker`, `depth` (top 25, 250 ms), `kline_1m`, `markPrice`, `forceOrder` (Binance); `publicTrade`, `orderbook.25`, `kline.1`, `tickers`, `liquidation` (Bybit). Ver [[WebSockets]].

**Normalização** para `NormalizedTicker | NormalizedTrade | NormalizedOrderBook | NormalizedCandle | NormalizedFunding | NormalizedOpenInterest | NormalizedLiquidation`, com `ts` (hora da exchange) e `received_at` (hora local), ambos UTC.

**Hot state** em Redis a cada 250 ms por símbolo; ring buffer de trades e candles. **Trades brutos e order book não são persistidos no Postgres** — só o que está em `docs/DATABASE.md` §4.

**Persistência.** Candle 1m fechado → `candles` + evento `market.candles.closed`; snapshot por minuto → `market_snapshots`; open interest via REST a cada 5 min → `open_interest_history`; funding realizado → `funding_rates`; liquidações → `liquidations`.

**Recovery.** Ao reconectar ou detectar gap, busca candles via REST, grava com `source=rest`, registra em `ingestion_gaps`; enquanto há gap aberto, `data_quality` do mercado é `degraded` (isso bloqueia entradas no Risk Engine — check `data_quality`, ver [[Risk Engine]]).

## Falhas previstas (comportamento planejado)

WS caiu → reconnect com backoff (1 s → 60 s) + REST recovery. Redis caiu → buffer em memória por 60 s, depois descarta ticks (candles são recuperáveis via REST). Postgres lento → escrita em lote com fila limitada, alerta se > 10 s de atraso.

## Relacionadas

[[Exchange Adapters]] · [[WebSockets]] · [[Data Flow]] · [[Workers]]

## Fontes

`docs/PIPELINE.md` §1, `docs/ARCHITECTURE.md` §4, `docs/ROADMAP.md` (Milestone 1)
