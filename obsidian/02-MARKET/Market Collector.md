---
tags: [mercado, market-worker, m1]
updated: 2026-09-05
status: parcial
---

# Market Collector

## Status

**Parcial — código implementado (T1.3, `b8c4766`) e agora com prova operacional real (T1.6).** O `market-worker` rodou ~1h50 em Docker contra a Binance ao vivo, com 200 mercados perpétuos USDT, e a prova completa com comando e saída está em `.claude/state/t16-proof.md`.

**O que ficou provado:** 316.794 velas finais de 1 minuto persistidas, com **valores conferidos vela a vela contra o REST da Binance — 800 velas comparadas, zero divergência**; cobertura de 200/200 mercados na maioria dos minutos; reinício do container sem duplicar candle; `restart: unless-stopped` reiniciando de verdade (`RestartCount` 0 → 1 sozinho no caminho fatal do watchdog); `/ready` devolvendo 503 quando devido; gap detectado e recuperado (`open → recovered`) com valor correto; e queda de Postgres e de Redis com recuperação automática em 30 s.

**Por que continua `parcial` e não `implementado`:** com 200 mercados o processo satura um core (100 % de CPU) e o hot state de alta frequência não se sustenta — `mkt:*:ticker` e `mkt:*:book` chegam a zero chave viva e o contador novo mostrou **1,15 milhão de eventos descartados**. A série durável fica íntegra (o `BoundedEventQueue` nunca descarta kline final, por contrato), mas o tempo real não. Falta ainda corrida de 24–48 h, prazo definido de convergência do backlog de recovery e apagão externo longo atravessando reinícios.

**Seis defeitos encontrados só por rodar de verdade**, nenhum deles visível na suíte de testes: `EXPIRE` recebendo float no Lua do rate limiter (o worker **nunca** carregava o universo contra Redis real), `dropped_events` contado e nunca lido, queda de Postgres matando o processo pelo heartbeat, refresh de universo falhado dormindo 900 s e cegando o worker, restart de Redis congelando tudo em zumbi silencioso (cliente sem `socket_timeout`), e o healthcheck do Compose com teto de 3 s dando falso negativo. Todos corrigidos com teste. Ver [[Resolved Bugs]] e [[Monitoring]].

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

## Sharding e capacidade (T1.6b, `b8998cc`)

A T1.6 provou que **um processo satura um core com 200 mercados** e o hot state de alta frequência não se sustenta. A T1.6b atacou isso em três frentes, e a terceira mudou a topologia do worker:

| Frente | O que mudou | Arquivos |
|---|---|---|
| A — parse do adaptador | `model_construct` nos parsers quentes com guardas explícitas, cadência do book em `@depth20@500ms` (era 250 ms), varredura de fila mais barata | `hunter_exchanges/binance/{streams,normalize,event_queue,ws}.py` |
| B — caminho quente do worker | um `EVALSHA` por ticker aceito, pipeline Redis por ciclo (ticker + book + ticks + publish juntos), janela de dedupe de trades em memória, caminhos rápidos de candle (`LSET`/`LPUSH`) em vez de reescrever a lista | `hot_state.py`, `hot_state_candles.py`, `coalesce.py`, `ingest.py`, `streaming.py` |
| C — sharding | `MARKET_SHARD=i/N` validado na construção, fatia do universo por `crc32` do símbolo, **um líder por exchange** com lock por token e snapshot versionado por CAS, seguidores lendo o snapshot (ou o Postgres na falta dele) | `universe.py`, `universe_leader.py`, `config.py`, `heartbeat.py`, `main.py`, `hunter_core/settings.py` |

**Regra de compatibilidade:** o processo **solo** (sem `MARKET_SHARD`) mantém exatamente o comportamento do M1 — sem lock, sem snapshot. O sharding só entra quando existe mais de um processo, e nesse caso apenas o líder recalcula o universo e faz o upsert de `assets`/`markets`; os seguidores consomem o snapshot versionado. Isso evita duas instâncias disputando `ingestion_gaps` e `monitor_rank`.

**`tracking_hold` (previsto, ainda não implementado).** A [[Dialogos/SHADOW|decisão conjunta do Shadow Lab]] acrescenta um contrato ao Market Collector: um mercado que sai do universo monitorado, mas tem acompanhamento sombra `pending_entry` ou `active`, **continua com suas velas coletadas até o término do acompanhamento**. O hold é derivado do estado durável (`shadow_episodes`), reconciliado após restart, e é por acompanhamento — encerrar a v1 de uma estratégia não libera a coleta que a v2 ainda precisa. Impossibilidade de recuperar o dado gera censura explícita, nunca preço antigo. Entra em S2 (`services/market-worker/**`, só `tracking_hold`), depois de S0 e S1.

## O que falta

- **Corrida longa (24–48 h)** — a prova da T1.6 durou ~1h50 e a da T1.6b, 15 min. Falta uma corrida contínua longa e um apagão externo atravessando reinícios.
- **Prazo de convergência do backlog de recovery** — hoje não há prazo definido para o backfill fechar os gaps abertos depois de uma interrupção.
- **`tracking_hold` do Shadow Lab** — contratado na decisão SHADOW, implementado em S2.
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
