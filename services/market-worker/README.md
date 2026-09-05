# market-worker

T1.3: universo, ingestao, hot state Redis, coalescencia, persistencia,
recovery, heartbeat e readiness. Entrada: `uv run python -m hunter_market_worker`
na raiz, com configuracao nas variaveis de ambiente. Nenhum arquivo `.env` e carregado.

O runtime registra `RoleRegistry["market"]`. As tarefas do worker pertencem
 a um `asyncio.TaskGroup`; retorno inesperado e fatal. Testes usam fake proprio,
Postgres 16 e Redis 7 via testcontainers.

Contratos Redis:

- `mkt:{ex}:{sym}:ticker`: HASH, TTL 30 s; timestamps da fonte.
- `mkt:{ex}:{sym}:book`: STRING msgpack, TTL 10 s; snapshot top 20 substitui o anterior.
- `mkt:{ex}:{sym}:trades`: LIST msgpack, LPUSH + LTRIM 2000, mais novo no indice 0.
  Deduplicacao/ordenacao por `trade_id`/`ts` le apenas os 50 itens mais novos
  (`TRADE_DEDUPE_WINDOW`, hot_state.py) — um reconnect de WS so repete um
  punhado de trades recentes, nunca a lista inteira; ler os 2000 itens em
  todo trade satura o event loop sob volume real (H7).
- `mkt:{ex}:{sym}:candles:1m`: LIST wire/msgpack, limite 1500, mais novo no indice 0;
  escritor unico WS. REST escreve apenas Postgres. `push_candle` tem dois
  caminhos rapidos sobre as 16 entradas mais novas (`CANDLE_FAST_WINDOW`,
  hot_state.py): `LSET` quando o `open_time` ja esta na janela, ou
  `LPUSH`+`LTRIM` quando e um `open_time` novo e mais recente que a cabeca;
  so uma escrita mais antiga que a janela cai no fallback raro de
  reescrita completa (`DELETE`+`RPUSH`) — o caminho comum nunca esvazia
  a lista para um leitor concorrente (H8). Final sempre substitui parcial
  da mesma `open_time`, mesmo com `event_ts` igual ao do ultimo parcial (H9);
  parcial nunca substitui final; parcial mais antigo (ou duplicado) e
  rejeitado.
- `mkt:{ex}:{sym}:deriv`: HASH, TTL 600 s; `mark_ts`, `oi_ts`, `funding_ts`
  independentes. TTL nao e frescor. Cada escritor (ticker/funding/mark/OI)
  possui um conjunto fixo de campos; num write aceito, campos proprios cujo
  valor e `None` sao removidos com `HDEL` na mesma transacao do `HSET`, para
  que um campo opcional que a exchange parou de enviar desapareca em vez de
  ficar obsoleto ao lado de um `ts` novo (H4). Um escritor nunca remove campo
  que nao possui — os hashes de ticker/deriv sao compartilhados.
- `hb:market:{exchange}`: HASH, TTL 30 s; status a cada 5 s e nas mudancas.
- `market.ticks` (evento coalescido, `ingest.py:build_tick_payload`): alem de
  `price`/`bid`/`ask`/etc., carrega tres timestamps distintos — `ts` e o
  instante do ultimo evento aceito de qualquer tipo (ticker, trade ou book);
  `price_ts` e o instante do ultimo evento que carregava preco (ticker ou
  trade); `book_ts` e o instante da ultima atualizacao de book. Sem essa
  separacao, um book que continua atualizando sozinho reenvia o mesmo
  `price` sob um `ts` novo, parecendo um preco vivo que na verdade esta
  congelado (H10).

Limites da fila: 5000 itens, 8 MiB, 60 s de idade; lote ate o limiar de
500 itens / 1 MiB ou 1 s. Snapshot pendente pode ser substituido. Descarte
registra metrica e system_event; candle final descartado abre gap recuperavel.
Liquidacao usa UUID5 compartilhado entre banco e evento, publicado apos commit.
A identidade e `uuid5` sobre a tupla `(exchange, symbol, side, preco
normalizado, quantidade normalizada, ts_ms)`: duas liquidacoes reais
distintas que compartilhem exatamente essa tupla colapsam em uma unica
linha — consequencia aceita e documentada do M1 para um id deterministico
sem depender de um id nativo da exchange.
Nao ha outbox: morte entre commit e publicacao continua sendo a limitacao aceita do M1.

Dependencias de integracao ainda pendentes em T1.1/T1.2:

- `NormalizedCandle.event_ts`: campo real (`datetime | None`), preenchido
  pela exchange quando disponivel; parciais sem `event_ts` nao podem ser
  ordenados com seguranca e sao rejeitados (log/metric uma unica vez por
  worker). O caminho de producao (`handle_event`) encaminha
  `event.event_ts` para `hot_state.push_candle`.
- `update_subscriptions(added, removed, channels)`: sem esse hook, mudanca real
  do universo falha explicitamente; os simbolos mantidos nao sao reassinados.
- `fetch_realized_funding(symbol, start, end)`: retorna NormalizedFunding cujo
  `ts` e a liquidacao efetiva obtida do historico REST. Sem a capacidade,
  registra aviso; estimativas WS nunca viram funding realizado.
- Leitores internos do adapter precisam propagar falhas; o worker nao pode
  supervisionar tarefas privadas criadas com ensure_future pelo adapter.

`connection_states()` aceita os ConnectionState de T1.2; na falta de
`restart_connection(id)`, o watchdog solicita restart do stream completo.
`server_time()` e usado pelo recovery, com fallback UTC explicitamente registrado
apenas para adapters que nao expoem esse metodo.

O fechamento e as saidas de verificacao estao em [T1.3-report.md](T1.3-report.md).
