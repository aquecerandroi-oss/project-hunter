---
tags: [mercado, market-worker, m1]
updated: 2026-09-05
status: planejado
---

# Market Collector

## Status

**Planejado para o Milestone 1.** Hoje não existe nenhum código de coleta de mercado — nem `market-worker`, nem tabelas populadas (`markets`, `candles`, `market_snapshots`, `funding_rates`, `open_interest_history`, `liquidations` existem como schema vazio desde o M0). O dashboard mostra "mercados monitorados = 0" honestamente em vez de qualquer número inventado.

## O que está especificado (a implementar)

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
