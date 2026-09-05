**STATUS: BLOCKED**

Implementação retomada por Astra, sem commit, sem leitura de `.env` e sem edições fora de `C:/dev/project-hunter`. As verificações abaixo foram executadas na raiz. O aceite integral depende dos quatro pontos externos descritos em DESVIOS; testes com fake não substituem esse aceite.

**ARQUIVOS CRIADOS/MODIFICADOS**

Conjunto T1.3 no worktree, incluindo arquivos herdados da implementação interrompida:

- `services/market-worker/hunter_market_worker/{__init__,__main__,config,funding,heartbeat,hot_state,ingest,main,persist,persist_rows,publication,queues,recovery,sampling,streaming,supervision,universe,wire}.py`.
- `services/market-worker/tests/{builders,conftest,db_helpers,fakes,universe_test_helpers}.py`.
- `services/market-worker/tests/{test_config,test_contracts,test_funding,test_heartbeat,test_hot_state,test_ingest_coalesce,test_ingest_integration,test_persist,test_persistence_contracts,test_recovery,test_recovery_contracts,test_role_registration,test_supervision,test_universe}.py`.
- `packages/core/hunter_core/runtime.py`: hook de readiness, timeout individual de 2 s, exceção = falso.
- `packages/core/tests/unit/test_runtime.py`: testes do hook.
- `packages/core/hunter_core/observability.py`: adição autorizada de `market_publish_failures_total`.
- `.env.example`: comentário de staleness por componente.
- `services/market-worker/README.md` e este relatório.

Os campos de mercado de `packages/core/hunter_core/settings.py`, a dependência no `services/market-worker/pyproject.toml` e o `uv.lock` já estavam alterados ao início. Foram preservados; não editei `uv.lock`. Alterações concorrentes de API, web, adapters e arquivos `.claude` não são desta retomada.

**CONTRATOS REDIS — VERBATIM DO BRIEF**

> 2. **Hot state** (`hot_state.py`), exact Redis contracts (the API task reads them): `mkt:{ex}:{sym}:ticker` HASH `last,bid,ask,bid_qty,ask_qty,volume_24h,quote_volume_24h,high_24h,low_24h,change_24h_pct,ts` TTL 30 s; `mkt:{ex}:{sym}:book` STRING msgpack `{"ts","bids":[[p,q]...],"asks":[...],"depth":20,"kind":"snapshot"}` TTL 10 s (each snapshot replaces the previous); `mkt:{ex}:{sym}:trades` LIST (LPUSH+LTRIM 2000) msgpack `{"ts","price","qty","side","trade_id"}`; `mkt:{ex}:{sym}:candles:1m` LIST (LTRIM 1500) of wire-format candles — **single writer** (the ingest task; REST backfill never writes Redis); same `open_time`: newer partial (by event `ts`) updates partial, final replaces partial, partial never replaces final, older `ts` discarded; larger `open_time` advances the head; a late final for an earlier open_time finalizes that entry without touching the head; `mkt:{ex}:{sym}:deriv` HASH `open_interest,open_interest_value,oi_ts,funding_rate,funding_kind(estimated|realized),next_funding_time,funding_ts,mark_price,index_price,mark_ts` — **each writer updates only its own fields and its own `*_ts`**, key TTL fixed 600 s (TTL is not a freshness signal). Decimals as str, timestamps ISO 8601 UTC. `ts` written is always the exchange event `ts` of the last **accepted** event (never the flush time); duplicates/late events do not refresh anything.

Implementado para ticker, book, trades, derivativos e finais. Campos opcionais desconhecidos são omitidos. O contrato de ordenação de candles está testado com `event_ts` explícito; no caminho real, a ausência de `NormalizedCandle.ts` impede aceitar parciais com segurança. Não foi inventado timestamp da exchange.

**CHECKLIST DE ACEITE — DECISÃO CONJUNTA RELIDA**

- ✔ Universo: bulk ticker, upsert de assets/markets, status/delisting, ranking, allow/blocklist, publicação por mudança. Tickers REST também inicializam o hot state, respeitando o timestamp já aceito.
- ✔ Diferenças de assinaturas com fake: entradas/saídas alteradas, permanentes não reassinados. Universo vazio em idle, sem watchdog.
- ✘ Diferenças no Binance real: falta `update_subscriptions`.
- ✔ Hot state: top 20/snapshot, TTLs 30/10/600 s, LPUSH/LTRIM de trades, valores Decimal como string, timestamps por componente e rejeição de duplicatas/eventos atrasados.
- ✔ Candles com timestamp disponível: duas parciais crescentes, parcial atrasada, final após abertura seguinte, final tardio sem mudar o head; REST não escreve no Redis.
- ✘ Candles parciais reais: o tipo normalizado não transporta o timestamp da exchange.
- ✔ Coalescência: dez trades em um evento; timestamp da fonte; nenhuma publicação ociosa; evento que chega durante o flush não é perdido.
- ✔ Eventos: EventEnvelope + publish + DEFAULT_MAXLEN; tick também em rt:market.
- ✔ Persistência: filas limitadas por itens/bytes/idade, substituição de snapshot, métrica e system_event nos descartes, gap para candle final descartado, retry sem limpar silenciosamente o lote.
- ✔ Chaves naturais: candle final; snapshot no minuto estável; OI no bucket de cinco minutos; funding realizado; liquidação por (id, ts).
- ✔ Recovery: watermark de finais, bootstrap 1500 fechadas, relógio da exchange com fallback registrado, buracos internos nas últimas 24 h, processamento de gaps registrados, contagem de cobertura e transição recuperado na mesma transação; rollback conjunto testado; failed após cinco tentativas permanece visível.
- ✔ Liquidações: UUID5 canônico determinístico; mesmo UUID no banco e event_id; publicação depois do commit; falha de XADD conta métrica e insere warning.
- ✔ Supervisão das tarefas do worker: TaskGroup/forever, retorno normal fatal, exceção de coalescer propagada e cancelamento de shutdown normal.
- ✘ Supervisão imediata dos leitores privados do adapter: ainda criados com ensure_future fora do grupo do worker.
- ✔ Watchdog: silêncio por conexão, aviso/restart em 30 s, fatal na terceira tentativa sem progresso; ConnectionState concreto de T1.2 aceito. Sem restart_connection, usa restart do stream, conforme fallback do brief.
- ✔ Readiness: initializing falso, conexão com dados recentes, graça monotônica de 120 s, timeout de conexão de 15 s; fila pendente sem flush por 30 s falsa; hooks com timeout de 2 s/exceção = falso.
- ✔ Heartbeat: hash com TTL 30 s, publicação a cada 5 s ou mudança, contagem das assinaturas/reconexões reportadas pelo adapter, system_events e mark_success/mark_error.
- ✔ Staleness do produtor: OI não altera mark_ts/funding_ts; publicação parada não renova estado. Classificação e cenários visuais da API pertencem a T1.4.
- ✔ Entry: RoleRegistry["market"], Settings/WorkerRuntime, import lazy e erro de startup registrado.
- ✔ Fonte explícita de funding realizado com fake; estimativa WS nunca inserida como taxa realizada.
- ✘ Fonte de funding realizado no Binance atual: falta fetch_realized_funding.
- ✘ Aceite ao vivo por rota WS, API e restart no Compose: não executado nesta tarefa.

**SAÍDAS REAIS DAS VERIFICAÇÕES FINAIS**

`uv run pytest services/market-worker -q -p no:cacheprovider`

```text
........................................................................ [ 98%]
.                                                                        [100%]
73 passed in 63.71s (0:01:03)
```

`uv run pytest packages/core/tests/unit -q -p no:cacheprovider`

```text
........................................................................ [ 42%]
........................................................................ [ 84%]
...........................                                              [100%]
171 passed in 6.23s
```

`uv run ruff check services/market-worker packages/core`

```text
All checks passed!
```

`uv run ruff format --check services/market-worker packages/core`

```text
102 files already formatted
```

`uv run pyright services/market-worker packages/core/hunter_core/runtime.py`

```text
0 errors, 0 warnings, 0 informations
```

`uv run python infra/scripts/check_file_size.py`

```text
scanned 119 files; 0 over budget, 0 grandfathered
```


**DESVIOS / BLOQUEIOS**

1. `packages/core/hunter_core/domain/market.py` não oferece `NormalizedCandle.ts`. O worker rejeita parciais sem ele e registra o problema; os finais continuam persistidos. Completar esse campo está fora da lista de escrita autorizada.
2. `BinanceAdapter` não oferece `update_subscriptions(added, removed, channels)`. Uma mudança real do universo falha explicitamente, sem reassinar os símbolos mantidos. O hook é implementado no fake próprio e testado.
3. `BinanceAdapter` não oferece histórico de funding realizado. O worker espera `fetch_realized_funding(symbol, start, end)`, com `ts` igual ao instante do settlement, registra warning quando ausente e não promove estimativas a taxas realizadas.
4. Os leitores internos do adapter são tarefas privadas criadas via `ensure_future`; o worker não consegue colocá-los no seu TaskGroup sem alteração de T1.2. O watchdog detecta falta de progresso, mas não equivale à propagação imediata da exceção do leitor.

T1.2 adicionou `server_time()` e `connection_states()` durante esta execução; o worker foi adaptado ao `ConnectionState` concreto. A ausência de restart individual usa o fallback de restart do stream autorizado no brief.

A limitação commit→XADD sem outbox é a aceita para M1: morte do processo nesse intervalo pode perder a publicação, preservando a linha no banco.

Diagnóstico inicial: `2 failed, 41 passed, 1 warning in 35.52s`; pyright apontava `342 errors`. Corrigidos os contratos e as esperas frágeis dos testes. Uma rodada intermediária teve `72 passed, 1 error in 68.18s` por timeout Redis no setup; a fixture de integração passou a usar timeouts de conexão/leitura de 15 s. Isso não muda timeouts de produção.

O gate oficial passou. A conferência adicional incluiu testes: 41 arquivos Python, nenhum acima de 350 linhas. Sem mudanças de schema, commit ou teste ao vivo com Binance.

