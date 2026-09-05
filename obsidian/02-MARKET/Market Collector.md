---
tags: [mercado, market-worker, m1]
updated: 2026-09-05
status: implementado
---

# Market Collector

## Status

**Implementado.** No ar: **um processo sobre os 50 maiores mercados**, com `markets_ok` 50/50 =
**100%**. Os 200 do plano estão **provados** (4 shards × 50, `markets_ok` 198/200 = 99,0%) mas
**não entregues**, porque com mais de um shard o heartbeat é compartilhado e a página System
passa a mentir — ver "Sharding" abaixo e [[Open Bugs]]. A prova completa, com comando e saída,
está em `.claude/state/t16b-proof.md`; a prova anterior (T1.6, resiliência) em
`.claude/state/t16-proof.md`.

**O que ficou provado na T1.6b** (medido, não inferido, contra a Binance ao vivo):

| Meta do plano | Resultado (22:11 UTC, 4 shards × 50 mercados) |
|---|---|
| 200 mercados com `markets_ok ≥ 95%` | **198/200 = 99,0%** · 0 stale · 0 unavailable · 2 degraded |
| CPU < 70% de um core por shard | média por shard **36,6% · 54,6% · 61,2% · 64,2%** em regime estável |
| Cobertura durável | **200/200 velas finais por minuto**, seis minutos seguidos |
| Backlog de recovery | 3.230 → 95 gaps abertos em ~20 min (os 95 são o defeito de mercados não monitorados) |

**Uma topologia funciona, as outras não** — e isso está medido, não suposto:

| Topologia | CPU por processo | Mercados com hot state completo |
|---|---|---|
| 1 processo × 200 mercados | média 103,2% de um core | **colapso**: 4,0% → 7,5% → **0%** em 15 min (ticker e book ausentes nos 200) |
| 2 shards × 100 | ~100% cada | oscilando 5% – 44,5% |
| **4 shards × 50** | **36,6% – 64,2%** | **99,0%** |

No processo único a série durável também ficou atrás: 188 velas/min contra as 200/min que a
exchange fecha. Com 4 shards, 200/200 por minuto.

**Onde a CPU vai** (py-spy, 11.110 amostras em 90 s no shard de 100 mercados): caminho quente do
WS `_handle_raw_message` **34,1%** cumulativo (`parse_book_ticker` 16,4%, `parse_depth20` 13,0%),
`model_construct` do pydantic **15,0%**, ssl 8,3%, websockets deflate 7,9%, sqlalchemy 6,2% —
e `run_recovery` só **4,4%**. O recovery consome latência de rede, não CPU; por isso quatro
processos drenaram 3.135 gaps em vinte minutos. O próximo ganho de performance é trocar os tipos
normalizados do caminho quente por `dataclass(slots=True)`, porque `model_construct` ainda
resolve defaults a cada evento (follow-up do M2, ver [[Open Bugs]]).

**A prova também encontrou uma regressão CRITICAL da própria T1.6b:** `shard_symbols` fazia
`s.encode("ascii")`, e a Binance USDS-M lista perpétuos com símbolo **em chinês** — quatro deles
no top 100 por volume (`牛来USDT` rank 19, `龙虾USDT` 42, `币安人生USDT` 63, `我踏马来了USDT` 81).
Um `UnicodeEncodeError` dentro do `try` de `run_universe` deixava o universo vazio: **um símbolo
não-ASCII cegava os 200 mercados**. Corrigido com teste de regressão usando os símbolos reais
(`4f9ab28`). Mesma lição da T1.6 (`EXPIRE` com float no Lua): um dublê de teste que não reproduz
a fronteira real esconde o defeito — aqui, um universo sintético só de ASCII.

**A configuração entregue, medida** (22:46 UTC, um processo, 50 mercados): `markets_ok` **50/50 =
100%**, 0 stale, 0 degraded, 0 unavailable, hot state completo nos três componentes; CPU média
**71,3%** de um core em regime estável, contra **95,1%** que o perfil pré-T1.6b media no mesmo
tamanho de universo. Cumpre o produto, sem folga — que é justamente por que o sharding existe.

**Por que 200 não está no ar.** Com N > 1 shards todos escrevem a mesma chave
`hb:market:{exchange}`: o `/system/market-status` mostrou `subscriptions: 636` (assinaturas de
**um** shard) com `markets_monitored: 200`, e um shard morto ficaria invisível atrás dos vivos que
continuam reescrevendo a chave. O M1 promete "página System com heartbeats reais"; uma topologia
cuja página System mente não é o que se entrega. Heartbeat por shard + agregação na API é item do
M2 — depois dele, habilitar 200 são quatro linhas de compose. A segunda opinião da Astra foi o que
fechou essa decisão (`.claude/state/astra-review-T1.6b-veredito.md`).

**O que continua aberto** (em [[Open Bugs]]): heartbeat compartilhado entre shards, gaps de
mercados não monitorados que nunca fecham, morte de shard sem rebalanceamento, corrida de 24–48 h
e a Bybit.

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

- **Corrida longa (24–48 h)** — a prova da T1.6 durou ~1h50 e a da T1.6b, 1h10 (três topologias em sequência). Falta uma corrida contínua longa e um apagão externo atravessando reinícios.
- **Morte de um shard com os outros vivos** — não há rebalanceamento: a fatia do shard morto para de ser coletada até ele voltar. Nunca exercitado.
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
