# Pipeline — Market → Features → Anomaly → Regime → Opportunity → Agent → Risk → Execution

Definição exata do fluxo (item 80.6). Cada etapa: gatilho, entrada, saída, onde roda, o que persiste, o que acontece quando falha.

## 0. Visão

```
 Binance WS ─┐                                            ┌─ rt:* (pub/sub) ─► api ─► browser
 Bybit WS   ─┤                                            │
             ▼                                            │
 [market-worker] ─ market.ticks ──────────────────────────┤
        │        ─ market.candles.closed ─┐               │
        │        ─ market.derivatives ────┤               │
        │        ─ market.liquidations ───┤               │
        ▼                                 ▼               │
   Redis hot state                 [scanner-worker]       │
   Postgres candles                 Feature Engine ── features.updated
                                    Anomaly Engine ── anomalies.detected
                                    Regime Engine  ── regime.changed (1 min, global)
                                    Opportunity    ── opportunities.updated
                                          │
                                          ▼
                                   [strategy-worker]
                                    Agents (global) ── signals.emitted ──► signal_outcomes (analytics)
                                    Proposal builder (por portfolio com agente inscrito)
                                    Risk Engine ── proposals.decided
                                          │ approved
                                          ▼
                                   [execution-worker]
                                    ExecutionAdapter(paper|shadow) ── executions.completed
                                    Position manager (stops, alvos, MTM 1 s) ── positions.updated
                                    Trades, equity snapshots
                                          │
                                          ▼
                                   [analytics-worker]
                                    agent_stats, outcomes, retenção ── analytics.updated
                                          │
                                          └──► Learning Engine (Fase 3): pesos, versões, recomendações
```

## 1. Market Data

**Onde:** `market-worker`. **Gatilho:** contínuo.

1. **Universo.** A cada 15 min, `list_markets(perpetual)` em cada exchange; atualiza `markets` (novos, delistados, `volume_24h_usd`); recalcula `monitor_rank`; marca `is_monitored` para os N primeiros (`MARKET_UNIVERSE_SIZE`, padrão 200 por exchange). Mudança no universo publica `market.universe.changed` e o worker ajusta as assinaturas WS.
2. **Streams WS** por mercado monitorado: `aggTrade`, `bookTicker`, `depth` (top 25, 250 ms), `kline_1m`, `markPrice` (funding, mark, index), `forceOrder` (liquidações). Bybit: `publicTrade`, `orderbook.25`, `kline.1`, `tickers`, `liquidation`.
3. **Normalização** para `NormalizedTicker | NormalizedTrade | NormalizedOrderBook | NormalizedCandle | NormalizedFunding | NormalizedOpenInterest | NormalizedLiquidation`. Timestamps da exchange em `ts`; hora local em `received_at`.
4. **Hot state** em Redis a cada 250 ms por símbolo (coalescido). Ring buffer de trades e candles.
5. **Persistência.** Candle 1m fechado → `candles` (`is_final=true`); o evento `market.candles.closed` é enfileirado na mesma transação e publicado pela outbox (§10b). Snapshot por minuto → `market_snapshots`. Open interest via REST a cada 5 min → `open_interest_history`. Funding realizado → `funding_rates`. Liquidações → `liquidations` (`qty`/`price` = quantidade **executada acumulada** `o.z` e **preço médio** `o.ap` do `forceOrder`, nunca a quantidade/preço originais `o.q`/`o.p` — KB-0017, `.claude/state/notes-liquidations.md`; linhas persistidas antes de 2026-09-06 usam a semântica antiga e não foram reescritas).
6. **Recovery.** Ao reconectar ou detectar gap (`open_time` esperado ausente), busca candles via REST, grava com `source=rest`, registra `ingestion_gaps`. Enquanto há gap aberto para um mercado, seu `data_quality` no hot state é `degraded`.
7. **Rate limit do REST (fail-closed).** Todo request REST passa por um token bucket compartilhado em Redis (`rl:{exchange}:{bucket}`) e pelo bloqueio por IP (`rl:{exchange}:ip:blocked_until`, deadline no relógio do Redis): todo processo que sai pelo mesmo IP divide **uma** cota da exchange. **Com o Redis indisponível o portão fecha:** nenhuma admissão REST nova, motivo `redis_unavailable`, re-tentativa com backoff curto e jitter — nunca um orçamento em memória por processo, porque N shards com bucket próprio somam N cotas contra uma cota única e o preço do erro é um ban de IP da Binance, irreversível no curto prazo (aceite conjunto da M2, T2.9). Uma exceção do Redis nunca sobe para o worker: o limitador devolve `RateLimited` com `reason=redis_unavailable`, que os laços já sabem sobreviver. O WS continua ingerindo e o **recovery de gaps espera** em vez de gastar tentativas (`ingestion_gaps.attempts` não avança), retomando sozinho quando o Redis volta — sem burst de compensação, porque o bucket compartilhado vale uma janela e não uma janela por minuto de queda. Observabilidade: contador `exchange_rest_admissions_suspended_total{exchange,bucket,reason}` e campo `rest_gate` (`ok`/`suspended`) em três lugares — no heartbeat `hb:market:{exchange}`, no `rt:system` e no corpo do `/ready` do market-worker. No `/ready` ele entra como *status detail* (`WorkerRuntime.status_details`), não como readiness check: é uma string ao lado do veredito e **não** altera o status code — o gate suspenso, por si só, nunca deixa a prontidão vermelha. Ressalva honesta: numa queda **total** do Redis o `/ready` fica vermelho de qualquer jeito, pelo check `redis` (o worker também depende do Redis para coalescer, streams e heartbeat); o que o `rest_gate` faz é dizer *qual* degradação está em curso. A ingestão pelo WS e a persistência em Postgres continuam, o heartbeat degrada para "não publicado" em vez de derrubar o TaskGroup, e um gap cuja recuperação esbarre na indisponibilidade **não** gasta `ingestion_gaps.attempts`.

8. **Shards do coletor (T2.5g).** Um processo com 200 mercados satura um core e o tick nasce velho: `publication delay` (XADD − `payload.ts`) mediana **25,8 s** no stack local e 3,7 s na medição anterior da T2.5d, com o *leg* de Redis em 18 ms — o atraso é inteiramente a montante, no parse por mensagem do WS (py-spy: `_handle_raw_message` 43,7 % cumulativo), não no coalescer de 250 ms. Com `MARKET_SHARD=i/N` o universo é dividido por `crc32(symbol) % N` (T1.6b-C2) e cada processo passa a:
   - escrever **seu próprio heartbeat** `hb:market:{exchange}:{i}of{N}` (com `shard_index`/`shard_total`), nunca a chave compartilhada. `N == 1` mantém `hb:market:{exchange}` byte a byte. A API une os shards (`/api/v1/system/market-status`): `ws_state` é o do pior shard, ou `stale` se `shards_reporting < shards_expected`; `last_event_at` é o **mais antigo**; `reconnects` é a soma; `markets_monitored` e `open_gaps` continuam vindo do Postgres, nunca da soma dos campos auto-declarados (que perderia justamente o shard ausente). Sem nenhum heartbeat, `shards_expected` é `null` — topologia desconhecida, nunca "1";
   - **não publicar `rt:system`** quando `N > 1`: essa mensagem substitui a linha inteira da exchange na página System, e um shard conhece só a própria fatia. Em modo sharded o widget é atualizado pelo polling do agregado;
   - publicar a **cobertura** (`mkt:{exchange}:coverage`, item 6 do §2 do scanner) por um script Lua que funde os N shards numa hash só, porque o leitor é único por exchange: `covered_until` = **mínimo** entre os shards vivos (o coletor mais atrasado limita a exchange), `session_since` = mínimo (apenas piso — cada `sym:{symbol}` carrega a sessão do seu próprio dono, então um shard que reiniciou penaliza só os mercados dele), e um shard que para de carimbar **perde seus símbolos** em vez de herdar a prova do vizinho. Um `HSET` direto seria last-writer-wins: o shard saudável provaria cobertura dos mercados do shard travado.

9. **Bybit (T3.44b).** A tabela `exchanges` tem a linha `bybit` cadastrada com `status=active`, mas nenhum coletor jamais rodou para ela — `system_status.py` (`build_market_status`) reporta isso honestamente como `ws_state=unavailable` por exchange sem heartbeat, o que aparecia no topbar como "2 exchanges · UNAVAILABLE" e foi lido como um bug de tempo real do navegador (não era: a Binance seguia `connected`). **Resolvido pela T3.44c** (`docs/DATABASE.md` §28): a migração `0016_exchange_status_planned` acrescentou o rótulo `planned` a `exchange_status` (`BEFORE 'active'`), `seed_reference.EXCHANGES` passou a carregar o status por linha (`bybit` = `planned`; `seed_exchanges` não escrevia `status` em nenhuma metade do upsert antes disso) e `build_market_status` deixou de renderizar exchanges `planned` como linha — elas vão em `MarketStatusOut.exchanges_planned` (aditivo, default `[]`), não são lidas no Redis, não contam no teste "todas as leituras falharam" (que decide o `503`) e não entram em `markets_monitored_total`. O topbar passa a ler `binance · CONNECTED · N mercados · há Xs (bybit planejada)`. O comando do operador para aplicar é `seed.py --only exchanges` (que também nasceu nesta tarefa; o `--only` só cobria quatro tabelas).

**Eventos publicados:** `market.ticks` (coalescido 250 ms; payload: preço, bid, ask, volume incremental, trades_count, book_imbalance top 5), `market.candles.closed`, `market.derivatives` (OI, funding, mark), `market.liquidations`, `market.universe.changed`.

**Falha:** WS caiu → reconnect com backoff (1 s → 60 s), REST recovery; Redis caiu → buffer em memória por 60 s, depois descarta ticks (efêmeros); os eventos duráveis ficam pendentes em `outbox_events` e saem quando o Redis volta (§10b) e as admissões REST ficam suspensas até lá (item 7, sem orçamento independente por processo); Postgres lento → escrita em lote com fila em memória limitada, alerta se > 10 s de atraso.

## 1b. Backfill sob demanda — `market.backfill.requested` (T2.5-backfill)

**Onde:** `market-worker` (`hunter_market_worker/backfill*.py`). **Gatilho:** um pedido no stream. **Quem pede:** o `scanner-worker` (bootstrap de baseline, referência de 30 dias do regime), que pela decisão conjunta do M2 **nunca chama a exchange**.

1. **O pedido é um fato sobre uma janela, não um comando.** Payload: `market_id`, `exchange`, `symbol`, `timeframe`, `gap_start`, `gap_end` (intervalo **semiaberto** `[gap_start, gap_end)`), `reason`, `requested_by`. A identidade (`event_id`) é a janela, então pedir duas vezes é um pedido só.
2. **Um consumer group por shard** (`market-worker.backfill.{exchange}.{i}of{N}`): toda mensagem chega a **todos** os shards e só o dono do mercado (`crc32(symbol) % N == i`, a mesma fatia de `universe.shard_symbols`) planeja; os outros dão `XACK` sem efeito. Um grupo único entregaria cada pedido a um shard só, que na maioria das vezes não seria o dono — o pedido se perderia. Custo declarado: mudar `N` deixa grupos órfãos (removidos à mão) e cada grupo tem seu próprio `hunter:processed:{group}`.
3. **O consumidor planeja; quem busca é o recovery.** O pedido vira linhas de `ingestion_gaps` e nada mais — nenhuma chamada REST sai daqui. O intervalo semiaberto do pedido é traduzido para o intervalo **inclusivo** da tabela (`last_minute = gap_end − 1 min`), limitado ao último minuto que a detecção considera fechado (`align_open_time(server_now) − DETECTION_GRACE`).
4. **Tetos e recusas.** Teto de **7 dias (10 080 min)** por pedido, truncando pelo lado antigo (o recente é o que a baseline precisa primeiro) e dizendo no log; pedaços de **240 min** por linha (uma página de klines, peso 10 — desde a T2.9c isso não é mais também um teto de anúncios de outbox: um pedaço do estrato histórico vira **um** `market.candles.backfilled`, não 240 `market.candles.closed`, item 9 abaixo); minutos já persistidos são subtraídos e minutos já cobertos por um gap `open`/`failed` são **barreira** (nunca refeitos, nunca fundidos por cima — isso contornaria o cooldown do `failed`); mês sem partição de `candles` não é planejado, e o motivo aparece (`no_partition`). Recusas: `market_not_monitored`, `unknown_market`, `unsupported_timeframe`, `future_window`, `empty_window`, `naive_timestamp`, `unreadable_payload`.
5. **`XACK` nem sempre é marca.** Recusa que depende do estado de agora (fora do universo, mercado desconhecido, partição ausente), **cauda ainda não liquidada** (o pedido nomeou minutos além do último que a detecção considera fechado, e eles fecham daqui a pouco) e planejamento **parcial** recebem `XACK` **sem** gravar o `event_id` em `hunter:processed:{group}`: a republicação horária do mesmo id é reavaliada e avança sobre o que faltou. Só um pedido planejado por inteiro é marcado. Erro transitório (Postgres/Redis) **não** é recusa: a mensagem fica pendente e volta pelo `XAUTOCLAIM`, e depois de 3 tentativas é largada com `outcome=failed` e log de erro — nunca um laço silencioso.
6. **Mensagem ilegível não derruba o coletor.** O leitor deste stream tolera envelope inválido (`market_backfill_unreadable_message`, `XACK`, `outcome=malformed`) em vez de morrer dentro do gerador e levar o `TaskGroup` junto.
7. **Prioridade: a coleta ao vivo nunca espera o bootstrap.** O recovery divide as lacunas `open` em dois estratos pela **idade da janela** (`gap_end` dentro dos 1 499 min da detecção = coleta ao vivo; mais antigo = histórico) e só gasta com histórico o que sobrar do orçamento do ciclo (`MAX_GAPS_PER_CYCLE = 50`), com teto próprio (`MAX_HISTORY_GAPS_PER_CYCLE = 6`) e **prazo em relógio**: `min(30 s, o que falta do ciclo de 60 s menos 5 s de margem)`, aplicado à **unidade inteira** de recuperação (leituras, lock de linha e escrita, não só o fetch). Uma unidade cancelada pelo prazo faz rollback e **não gasta tentativa** do gap — ficar sem orçamento não é falha da lacuna. O estrato **vivo** continua ordenado por `gap_end DESC` (o minuto ausente mais novo primeiro, de um mercado só — a coleta ao vivo é sempre por mercado). O estrato **histórico** não é mais um `gap_end DESC` único sobre o shard inteiro (T3.7d, item 11) — um mercado com um `gap_end` cronicamente mais novo (uma listagem recente cujo pedido incluiu janelas anteriores à listagem, ou simplesmente um backlog maior) monopolizava os seis slots para sempre.
8. **Criação de lacuna é serializada.** São **três** os escritores de `ingestion_gaps` com o mesmo protocolo (ler cobertura → inserir o que falta): a detecção periódica, este consumidor e `persist.report_losses` (a vela final que a fila descartou). A tabela não tem unicidade por intervalo, então os três tomam o mesmo `pg_advisory_xact_lock` por exchange **antes** de ler, e nenhuma chamada REST acontece com o lock na mão. `report_losses` usa a variante **não bloqueante** (`pg_try_advisory_xact_lock`): ela roda uma vez por iteração do `drain_loop` e esperar ali atrasa o flush das velas vivas — quem não pega o lock não escreve nada e tenta na iteração seguinte.
9. **A resposta é a que o pipeline já tem — mas o anúncio não é mais um por minuto para histórico (T2.9c).** No estrato **vivo** (item 7), cada minuto preenchido continua virando `market.candles.closed` pela outbox, na mesma transação que gravou a vela (`upsert_candles`), exatamente como um minuto ao vivo — nenhum consumidor existente muda de comportamento. No estrato **histórico**, a mesma transação enfileira **um** `market.candles.backfilled` agregado para o lote que aquela chamada realmente inseriu (`{exchange, symbol, timeframe, start, end, count, source="rest", reason="historical_recovery"}`), em vez de até 240 eventos por pedaço. Motivo: anunciar cada minuto de histórico é o gargalo de vazão do bootstrap (~1 dia de histórico por minuto de relógio, notes-T2.5.md §28) e ainda deixava minutos antigos na frente de velas ao vivo na ordem `(created_at, id)` do despachante (§10b). O `reason` é **descritivo, não causal**: `ingestion_gaps` não guarda quem pediu uma janela, e uma lacuna que a própria coleta ao vivo criou pode *envelhecer* para o estrato histórico sem que ninguém tenha publicado `market.backfill.requested` (REST ou o worker parados por mais que a janela de detecção) — por isso o motivo é sempre "a janela envelheceu", nunca "alguém pediu". Identidade do evento agregado: uuid5 sobre mercado + timeframe + `source` + o intervalo **realmente inserido** por aquela chamada (não os limites nominais do gap) — dois lotes commitados para a mesma chave `(mercado, timeframe)` nunca compartilham mínimo, porque o `ON CONFLICT DO NOTHING` do candle nunca deixa o mesmo minuto ser inserido duas vezes, então a identidade nunca colide entre passadas sucessivas sobre o mesmo gap parcial. **Ainda não implementado:** um consumidor de `market.candles.backfilled` no scanner-worker para invalidar/reagendar o bootstrap afetado em vez de esperar a releitura periódica de cobertura — registrado como requisito para a T2.5d/T2.5e (notes-T2.9.md T2.9c). Observabilidade: `market_backfill_requests_total{outcome}` (`accepted`, `partial`, `truncated`, `empty`, `refused`, `ignored`, `duplicate`, `malformed`, `failed`), `market_backfill_minutes_total` e o log `market_backfill_planned` com mercado, shard, intervalo pedido/efetivo, minutos, pedaços, adiados e sem partição.

**Limite conhecido:** `infra/scripts/create_partitions.py` provisiona o mês corrente e os seguintes, então um pedido de 7 dias no começo do mês nomeia minutos sem partição — eles são recusados com motivo em vez de abortar a transação, e o pedido volta a ser avaliado na republicação seguinte. Provisionar meses **para trás** é trabalho do job de partições. E o teto de 7 dias por pedido é política: a referência de 30 dias do regime precisa pedir o restante em outras janelas, o que ainda não está combinado.

10. **`kind: candles|funding` (T3.7c), aditivo.** O payload do item 1 ganhou um campo opcional, `kind`, default `candles` — um produtor escrito antes deste campo existir (o scanner) continua entendido exatamente como antes. `kind: funding` pede histórico de funding realizado em vez de candles, e é servido por um caminho bem mais curto (`hunter_market_worker/funding_backfill.py`): o motor de replay (§6c) não precifica a perna de funding de um outcome sem liquidações anteriores à entrada (`hunter_strategy_worker.funding`, `_CADENCE_LOOKBACK` de 3 dias), e `funding_rates` só carrega o que a coleta ao vivo gravou. Diferente de candles: **uma** chamada basta — `BinanceRestClient.fetch_realized_funding` já pagina até ~333 dias a 3 liquidações/dia — então o consumidor busca e persiste ali mesmo, sem `ingestion_gaps` nem o recovery loop, sob o bucket de peso de funding que a coleta ao vivo (`funding.poll_realized`) já usa (é isso que mantém a prioridade deste laço abaixo da coleta ao vivo, sem fila própria). Persistência: `persist_rows.upsert_funding`, mesma identidade do poller ao vivo (`market_id, funding_time`) e o mesmo `ON CONFLICT DO NOTHING` — quem chega primeiro, ao vivo ou histórico, nunca é sobrescrito; a tabela não tem coluna `source`/`received_at` para diferenciar os dois depois do fato (`docs/DATABASE.md` §2), o que não faz falta para essa garantia. `funding_rates` não é particionada, então não há checagem de partição. Teto de janela: 370 dias, truncados para a ponta mais recente se excedido. Um `429`/`418` do bucket de funding é recusa `rate_limited` com `system_event` (`funding_backfill_rate_limited`, severidade `warning`) e **nunca** um laço de retentativa silenciosa — a mensagem não é marcada processada e a republicação tenta de novo. Anúncio de conclusão: `market.funding.backfilled` (`{exchange, symbol, start, end, count, source="rest", reason}`), um por pedido servido — distinto de `market.derivatives`, que continua anunciando cada liquidação individualmente (`durable.enqueue_realized_funding`, inalterado). Publicação em lote: `infra/scripts/request_backfill.py --kind funding --days N --markets ...`, um pedido por mercado (sem fatiar em janelas de 7 dias), com identidade que inclui o literal `"funding"` para nunca colidir com um pedido de candles do mesmo mercado e janela (`docs/DEPLOYMENT.md`, "Histórico de funding para o replay").

11. **Estado terminal para janela impossível, e vez limitada no estrato histórico (T3.7d).** Incidente na VPS em 2026-09-08 (`.claude/state/notes-T3.7b-diag.md`): `MARSCOINUSDT`, listada no meio de um pedido de 31 dias, ganhou quatro lacunas cujo intervalo é inteiramente anterior à sua listagem — a exchange responde `200 OK` com zero candles para sempre, `recover_registered` não distinguia isso de uma falha transitória, e essas lacunas venciam sempre a disputa pelos seis slots do estrato histórico (ordenado globalmente por `gap_end DESC`) porque seu `gap_end` era o mais novo do shard. BTCUSDT e UNIUSDT, no mesmo shard, ficaram com `attempts=0` por 8h30.
    - **Sinal mais barato, sem migração e sem chamada extra à exchange — revisado na T3.7e.** `recovery_lifecycle.earliest` (o espelho de `watermarks`, com `min` em vez de `max`) lê, uma vez por ciclo, a primeira vela final já persistida de cada mercado. Uma lacuna cujo `gap_end` é anterior a essa vela é *suspeita* de pedir histórico anterior à existência (ou ao monitoramento) do mercado, mas desde a T3.7e (hotfix do commit 50932ec, 2026-09-08) isso não basta sozinho: `recover_registered` busca a janela **uma vez** sobre REST e só conclui `unrecoverable` (motivo `before_listing`) se a própria exchange responder vazio (`200`, zero linhas) para aquele intervalo — nunca a partir só de `earliest_known`. Motivo (achado MÉDIO do revisor): um mercado com velas recentes que acaba de receber um backfill profundo (`request_backfill.py --days 90`) tem `earliest_known` igual ao início da coleta *ao vivo*, não à listagem — uma janela mais antiga que isso, mas nunca buscada, merece uma tentativa real antes de virar terminal. **Defeito e correção do mesmo commit:** `check_gaps` lê `earliest_known` uma vez por ciclo, mas um mercado que ganha mais de um slot do estrato histórico no mesmo ciclo (item abaixo) pode ter uma lacuna mais nova, processada primeiro, cuja recuperação bem-sucedida empurra o mínimo verdadeiro para antes do que `earliest_known` dizia — comparar uma lacuna mais antiga, no mesmo ciclo, contra esse valor agora obsoleto foi exatamente como BTCUSDT e UNIUSDT perderam janelas legítimas de agosto na VPS (`.claude/state/notes-T3.7e.md`). `check_gaps` agora rastreia, por ciclo, se algum pedaço de um mercado já *persistiu* uma vela que alcança antes de `earliest_known` e, se sim, **adia** a classificação `before_listing` desse mercado para o próximo ciclo (quando `earliest()` é relido do Postgres) em vez de reabrir `unrecoverable` — a lacuna cai no caminho comum de tentativas/`failed` até lá. Um `onboardDate` de `exchangeInfo` ou uma sondagem dedicada à exchange seriam sinais válidos também, mas custariam uma mudança de schema (`markets` não tem essa coluna) ou peso de REST extra; o candle mínimo já coletado é gratuito.
    - **T3.7f (re-revisão HIGH, 2026-09-08): o sinal é "persistiu", nunca "chegou a `recovered`".** O ponto acima falhava quando o pedaço mais novo não fechava totalmente a lacuna — uma pausa real de negociação dentro da própria janela deixa um minuto esperado faltando, então o `gap.status` continuava `open`, mas a lacuna já tinha inserido velas anteriores a `earliest_known`; sem contar isso, o pedaço mais antigo do mesmo mercado, processado depois no mesmo ciclo, ainda virava `unrecoverable`/`before_listing` por engano. `recover_registered` agora devolve o `open_time` mínimo que realmente inseriu nesta chamada (não apenas se `gap.status == "recovered"`), e `check_gaps` usa esse valor — não o status da lacuna — para marcar `earliest_known` obsoleto. SQL de correção do incidente restrito aos dois símbolos e à janela real (`infra/scripts/sql/2026-09-08-reopen-false-unrecoverable.sql`), porque `ingestion_gaps` não guarda motivo e reabrir cegamente todo `unrecoverable` também reabriria uma lacuna `exhausted` sem relação.
    - **Estrato histórico com vez, não `gap_end DESC` global (item 7).** `recovery_lifecycle.history_candidates` busca, por mercado, até `MAX_HISTORY_GAPS_PER_CYCLE` lacunas (uma função de janela, não mais uma única `ORDER BY ... LIMIT` sobre o shard inteiro) e `backfill_priority.interleave` distribui o orçamento do ciclo em rodízio, um slot por mercado por rodada, até esgotar o orçamento ou os candidatos. Um mercado com backlog maior nunca é impedido de crescer — ele só para de conseguir *todos* os slots.
    - **`failed` não é um laço.** `recovery_lifecycle.reopen_stale_failed` não zera mais `attempts` ao reabrir — o campo passa a ser o total acumulado de tentativas em todas as vidas da lacuna, e `life_count = attempts // MAX_ATTEMPTS` é ao mesmo tempo essa contagem e "quantas vidas essa lacuna já esgotou". Cada reabertura espera um cooldown que dobra por vida (`FAILED_RETRY_AFTER_S * 2 ** (life_count - 1)`); depois de `MAX_REOPEN_ATTEMPTS` reaberturas (3), a próxima falha vira `unrecoverable` (motivo `exhausted`) em vez de reabrir de novo — visível no log e em `system_events`, nunca um laço silencioso de uma hora em uma hora.
    - **`unrecoverable_gaps` no heartbeat, à parte de `open_gaps`.** `hb:market:{exchange}` (e `hb:market:{exchange}:{i}of{N}` sob sharding) ganha o campo `unrecoverable_gaps`; `open_gaps` nunca inclui uma lacuna terminal — é exatamente o número que, no incidente, o operador teria lido como "ainda em progresso" enquanto eram 148 linhas que nada jamais buscaria. `docs/DEPLOYMENT.md` descreve como lê-lo.

## 1c. Câmbio USDTBRL — `fx_observations` (T3.11a)

**Onde:** `market-worker` (`hunter_market_worker/fx.py`). **Gatilho:** contínuo, independente do pipeline de mercado acima — não consome nem publica em nenhum stream de `market.*`.

A carteira paper (M3) opera em USDT mas a diretiva parte de R$100.000; a abertura (`hunter_core.portfolio.opening.open_paper_wallet`, T3.3b) e a curva de equity (`record_equity_point`) precisam de uma cotação `USDTBRL` sempre disponível e nunca fabricada, sob a mesma política de frescor (`FxPolicy`, `docs/DATABASE.md` §18.2): `available_at` ≤ 300 s e `observed_at` ≤ 600 s no instante do ato.

1. **Coleta.** A cada ~60 s (± 5 s de jitter), `GET /api/v3/ticker/24hr?symbol=USDTBRL` (peso 2) no bucket de peso do spot (`rl:binance:spot_request_weight`, token bucket Redis, pesos oficiais — `packages/exchange-adapters/hunter_exchanges/binance_spot/http.py`). `429`/`418` vira `RateLimited` e um `system_event` (`warning`), nunca um laço de retentativa silenciosa; falha de transporte após as retentativas internas do `SpotHttp` também não fabrica cotação — o ciclo seguinte tenta de novo, com backoff (5 s → 60 s, com jitter) entre tentativas mal sucedidas.
2. **Persistência.** `fx_observations` recebe `pair="USDTBRL"`, `source="binance.spot.ticker"` (a mesma constante que `PAPER_FX_POLICY.source`, T3.3 — uma fonte com outra grafia nunca abre carteira), `rate` = `lastPrice`, `observed_at` = `closeTime` (relógio da Binance), `available_at` = `utcnow()` no instante do INSERT, `raw` = corpo cru da resposta. Idempotente por `(pair, source, observed_at)` (`uq_fx_observations_observation`) via `ON CONFLICT DO NOTHING`: uma repetição do mesmo segundo fechado nunca duplica.
3. **Banda de plausibilidade.** Uma cotação fora de `[1, 100]` (a banda declarada em `FxPolicy`, revisão adversarial de `8a6a69f`, bloqueante 3) é **gravada do mesmo jeito** — o coletor registra o que a exchange imprimiu, sem editar — mas loga em `warning` e incrementa `hunter_fx_implausible_total`. Quem recusa uma cotação implausível é o **consumo** (`validate_fx_observation`), no instante do ato, nunca o coletor.
4. **Sharding: um coletor por venue, nunca N.** Só o shard 0 do market-worker cujo `exchange_code == "binance"` coleta câmbio (`MARKET_SHARD=i/N`, `hunter_core.settings.Settings.shard_index`); todo outro shard — e qualquer market-worker de outra exchange — idla essa tarefa para sempre. A fonte é fixa em Binance spot independentemente de qual perpétuo o processo ingere.
5. **Observabilidade.** `hunter_fx_observations_total{outcome}` (`ok`, `duplicate`, `malformed`, `rate_limited`, `network_error`, `error`), `hunter_fx_implausible_total`, `hunter_fx_age_seconds` (idade da última coleta bem-sucedida). A idade também aparece como *status detail* — nunca um readiness check — em `WorkerRuntime.status_details["fx"]` (`"ok"`/`"stale"`/`"unknown"`, limiar igual a `FxPolicy.availability_max_age_s`, 300 s): uma cotação velha pode impedir a abertura da carteira ou a valorização em BRL da curva, mas o resto da coleta de mercado continua, então `/ready` nunca fica vermelho por isso.

**Falha:** Redis fora do ar suspende o bucket de peso do spot como qualquer outro REST do worker (§1 item 7); Postgres fora do ar propaga da inserção (nunca silenciada) e o ciclo seguinte tenta de novo. Nunca há aporte, fabricação de cotação nem escrita sob o lock de `portfolio_risk_state` — a transação do coletor é só o INSERT em `fx_observations`, fora de qualquer unidade de trabalho da carteira.

## 1d. Caminho de dados SPOT — preço de execução do wallet (T3.0c/T3.0d)

**Onde:** `market-worker` (`hunter_market_worker/spot.py`, `spot_universe.py`). **Gatilho:** contínuo, só no shard 0 (`MARKET_SHARD=0/N`; todo outro shard cria a task e a deixa ociosa — a topologia fica visível na lista de tasks). **Por quê existe:** D1 — a carteira paper executa no livro **spot** da Binance enquanto todo o resto do pipeline (Feature/Anomaly/Regime/Opportunity/Agents) continua raciocinando só sobre o perpétuo. Isso faz do spot um **segundo caminho de dados no mesmo processo**, com adaptador, universo, fila de persistência, cobertura, heartbeat e recovery próprios — nunca um segundo modo do caminho perpétuo (`.claude/state/notes-T3.0c.md` §1).

1. **Universo — um piso, não um top-N.** A cada 15 min (mesma cadência do perpétuo): `quote_volume_24h ≥ 50.000.000 USDT` medido **no spot**, quote `USDT`, status `ACTIVE`, fora da blocklist (`.claude/state/decisions-M3-delegated-2026-09-06.md` D1). Sem ticker = fora — o piso é uma permissão, e permissão não se concede por leitura que falhou. `monitor_rank` continua escrito (por volume) mas não decide nada. **A admissão não tem banda** — nenhum par entra abaixo dos 50M, nunca.
2. **Histerese de saída (D12, T3.0e).** `PROMUSDT` entrou e saiu do universo **entre dois refreshes** durante a prova de T3.0c, com o volume 24h oscilando em torno dos 50M (`notes-T3.0c.md` §8, `t30-proof.md` §2). A banda fica só do lado da saída: um par **já admitido** só sai por volume quando lê `< 40.000.000 USDT` (80% do piso) em **3 refreshes consecutivos** (~45 min na cadência de 15 min); um ticker ilegível conta como uma observação abaixo, nunca como acima, e um par com duas leituras abaixo seguidas de uma acima zera a contagem. A contagem é **durável** — vive em `mkt:{exchange}:spot:band_state` (Redis, um hash `{symbol: streak}`), sobrevive a um restart do processo do shard 0 porque Redis é um processo separado que não reinicia junto (`hunter_market_worker/spot_band.py`). Deixar de ser `TRADING`, deixar de ser quote `USDT` ou entrar na blocklist tira o par **na hora**, sem banda e sem contagem. Cada entrada ou saída publica `market.universe.changed`; uma saída carrega `removed_reasons` (`below_band_3x`, `not_trading`, `quote_not_usdt`, `blocklisted`) — campo aditivo, o perpétuo nunca o usa. Sair do universo não encerra gestão de posição aberta (a regra do hold durável da T3.0 continua valendo).
3. **Identidade — mesma exchange, tipo diferente.** `exchange` continua `"binance"` para os dois adaptadores (uma linha em `exchanges`, um IP, uma cota de rate limit); o discriminador é `market_type` em `NormalizedMarket`/`NormalizedTicker`/`NormalizedTrade`/`NormalizedOrderBook`/`NormalizedCandle` (default `PERPETUAL`, então todo payload que já existia continua significando o mesmo). Toda chave de hot state de `hunter_core.redis.keys` recebe o mesmo `market_type` e dobra-o no **segmento de venue**: o perpétuo fica byte a byte igual ao que sempre foi (`mkt:binance:BTCUSDT:ticker`), o spot ganha o seu (`mkt:binance:spot:BTCUSDT:ticker`) — nunca o inverso.
4. **Chaves do hot state (spot):** `mkt:{ex}:spot:{sym}:ticker`, `:book`, `:trades`, `:candles:1m`, `:deriv` (sempre vazio — spot não tem funding/OI/liquidação), `mkt:{ex}:spot:coverage`; heartbeat `hb:market:spot:{ex}` (solo, `shard=(0,1)`, nunca `0of4` — declarar-se "0 de 4" faria a API esperar por shards spot que não existem). **Exceção deliberada (KB-0044):** o hash `mkt:*:ticker` nunca carrega `market_type` como campo — o discriminador já é a chave, e o hash é escrito por dois produtores disjuntos (REST 24h / WS `bookTicker`) cujo contrato é tocar só o que possuem.
5. **Canal pub/sub:** `rt:market-spot:{exchange}:{symbol}` — **e não** `rt:market:{ex}:spot:{sym}`. Decisão registrada em `.claude/state/notes-T3.0c.md` §3: mudar a gramática de `apps/api/hunter_api/realtime/channels.py` (`_MARKET_RE` recusa um `:` extra de propósito, com teste afirmando a recusa) e o consumidor do `apps/web` está fora do escopo desta tarefa; publicar spot no canal do perpétuo colocaria dois preços diferentes na mesma linha, que é exatamente a colisão que a T3.0a bloqueou. **Nenhum cliente assina `rt:market-spot:*` hoje** e a gramática atual recusa esse nome — melhor um canal inalcançável e correto do que um canal alcançável e ambíguo. Dar rota a ele (gramática + autorização + cliente web) é trabalho registrado para a T3.8c. Não há perda de dado: `market.ticks` (stream durável) carrega o tick spot com `market_type` e chave de roteamento `binance:spot:BTCUSDT`.
6. **Identidade dos eventos duráveis.** `market.candles.closed`, `market.candles.backfilled` e `market.universe.changed` derivam o `event_id` de um uuid5 sobre `(stream, venue, símbolo, ...)`, onde `venue` é `keys.market_slug(exchange, "", market_type).rstrip(":")` — `exchange` puro para `PERPETUAL` (nenhum id já anunciado em produção muda) e `{exchange}:spot` para `SPOT`. **Bloqueante fechado na T3.0d:** antes disso os três eventos derivavam o id só de `(exchange, symbol, ...)`, então o perpétuo e o spot do mesmo símbolo/minuto colidiam e o `ON CONFLICT (event_id)` do outbox descartava em silêncio o segundo `market.candles.closed` do par — a linha em `candles` ficava correta para os dois produtos, mas nenhum consumidor via o fechamento do lado que perdeu a corrida. O payload de cada um desses três eventos carrega `market_type` de forma aditiva (o perpétuo continua dizendo `"perpetual"`).
7. **O scanner não consome spot.** Nenhuma baseline, nenhum regime, nenhuma oportunidade é calculada sobre o livro spot — o scanner avalia só o perpétuo. Como todo símbolo já recebe tick de perpétuo a ~4 Hz, o `symbol` de um tick spot (`BTCUSDT`, sem segmento de tipo) lê como "o mesmo mercado" para `ScannerState.touch`; `hunter_scanner_worker.main.touch_batch_handler` descarta (com ACK, sem reprocessar) toda entrega cujo `payload.get("market_type", "perpetual") != "perpetual"`, **antes** de coalescer o lote — sem isso um tick spot sujaria o perpétuo e contaminaria `scanner_stream_delay_seconds` com a latência de outro venue (medido ao vivo em `.claude/state/notes-T3.0c.md` §6).
8. **Readiness.** `spot: "connected"|"degraded"|"absent"` é *status detail* (`WorkerRuntime.status_details`), nunca check — `absent` significa "este processo não coleta spot" (shard ≠ 0 ou `MARKET_SPOT_ENABLED=false`), não "está quebrado". Um socket spot ruim não derruba `/ready`: o que a M2 entregou e de que o Radar inteiro depende é o perpétuo.

**Condição para ligar `MARKET_SPOT_ENABLED=true` em qualquer ambiente compartilhado:** medir a folga do event loop do shard 0 **antes**, nunca supor. A/B controlado, mesma máquina, universo perpétuo cheio (200) nos dois braços, 6 min cada (`.claude/state/t30-proof.md` §1):

| | spot OFF | spot ON |
|---|---|---|
| idade do `last_event_at` perpétuo | 28 s | **5 min** |
| velas perpétuas / 5 min | **600** | **0** |
| reconnects do WS perpétuo | 2 | **8** |
| erro no log | `no close frame received` | `sent 1011 — keepalive ping timeout` |

Causa: um coletor perpétuo com 200 mercados já satura um core (T2.5g); somar o parse do spot no mesmo event loop faz o socket perpétuo perder o orçamento de keepalive, a Binance derruba com `1011`, ele reconecta 1.200 streams e entra em backlog — não é bug do spot, é falta de folga de event loop no shard. Com folga de verdade (universo perpétuo reduzido a 20, diagnóstico) o caminho spot roda 15 min 41 s com 0 reconnects, 0 exceções e vela spot na hora (`t30-proof.md` §2). Na VPS o shard 0 carrega ~50 perpétuos (4 shards) contra 200 aqui, então a folga provavelmente existe — mas **não é medida por default**, e a checagem (`hb:market:spot:{ex}` presente e `reconnects=0`; `hb:market:{ex}` com `last_event_at` fresco e `reconnects` não subindo; velas perpétuas continuando a entrar, nos primeiros minutos) é obrigatória antes de considerar o ambiente estável. Some a essas três um quarto sinal, específico do T3.0e: **`market_spot_dropped_events_total{exchange}`**, não `market_dropped_events_total` — a série compartilhada mistura o descarte do spot com o do perpétuo (os dois adaptadores respondem `adapter.code == "binance"`), então um reconnect rotineiro do spot não pode ser lido como o perpétuo perdendo fita.

**Resolvido (D12, `.claude/state/decisions-delegated-2026-09-07.md`):** o universo spot flapava na borda do piso (`PROMUSDT` entrou e saiu entre dois refreshes de 15 min durante a prova de T3.0c, oscilando em torno de 50M de volume 24h). A T3.0e fechou a pergunta com uma banda **só na saída** — item 2 acima.

## 2. Feature Engine

**Onde:** `scanner-worker`. **Gatilho:** `market.ticks` (tick-features, throttle 1 s por símbolo) e `market.candles.closed` (bar-features).

- Cada `FeatureCalculator` é registrado com `FeatureDefinition {name, version, parameters, description, inputs}`. A versão do conjunto (`feature_set_version`) é o hash ordenado de todas as definições ativas.
- Contexto por mercado em memória: últimos 1500 candles 1m, book atual, últimos trades, derivativos, mais BTC como referência.
- Features do MVP (v1):

| Grupo | Features |
|---|---|
| Preço | `price_return_1m/5m/15m/1h/4h`, `distance_from_24h_high_pct`, `distance_from_24h_low_pct`, `breakout_strength_20` (fechamento vs máxima de 20 barras em ATR) |
| Volume | `relative_volume_5m/15m/1h` (vs mediana dos últimos 7 dias mesma hora), `volume_acceleration` (dv/dt normalizado), `quote_volume_1h` |
| Volatilidade | `volatility_5m/1h` (desvio de retornos log), `atr_14_pct`, `volatility_ratio` (5m/1h) |
| Microestrutura | `spread_pct`, `orderbook_imbalance_5/25`, `buy_sell_pressure_1m/5m` (taker buy / total), `trade_velocity_1m` (trades/s vs média) |
| Momentum | `momentum_15m` (ROC), `momentum_acceleration`, `rsi_14`, `ema_ratio_9_21` |
| Derivativos | `funding_rate`, `funding_change_8h`, `open_interest_change_1h/4h`, `oi_price_divergence` (OI sobe e preço cai, etc.), `liquidation_pressure_1h` (long vs short notional) |
| Cross | `btc_correlation_1h` (rolling), `market_beta_1h`, `relative_strength_vs_btc_1h` |

- Saída: `FeatureVector {market_id, ts, feature_set_version, values}` para Redis `feat:*` e evento `features.updated`. Persistência em `feature_snapshots` **apenas** no fechamento de minuto.
- **Anti-look-ahead:** bar-features usam só candles `is_final`; o candle em formação entra apenas nas tick-features, marcadas com sufixo `_live`.

**Falha:** dados `degraded` → features marcadas `quality=degraded` e não alimentam anomalias nem oportunidades até o gap fechar.

**Como o `scanner-worker` executa isto na prática (T2.5).** As etapas 2 a 5 são um pipeline de
*streams* neste documento e um **único passo síncrono por corte** dentro do processo: um dono avança
cada mercado (`hunter_scanner_worker/evaluate.py`) porque `ScoreContext` recusa um score cujo
estágio, regime ou anomalias venham de outro instante, e cinco consumidores independentes leriam
estados que outro já moveu. `features.updated` continua sendo publicado — para consumidores de fora
—, mas não é o transporte deste pipeline. Consequências que valem registrar:

- **cadência real:** o laço acorda a cada 0,25 s e avalia os mercados "sujos" cujo throttle de 1 s
  venceu; o scorer tem o seu próprio de 2 s. Uma passada completa sobre 200 mercados custa hoje ~7 s
  (medida em `services/scanner-worker/tests/test_load.py`), acima do alvo p99 ≤ 3 s da decisão
  conjunta — o gargalo é o custo por vetor herdado da T2.2 e está registrado em
  `.claude/state/notes-T2.5.md` §7;
- **o corte é a prova de cobertura, não o relógio:** o `market-worker` publica em
  `mkt:{exchange}:coverage` o intervalo em que ele consegue provar que estava conectado e assinado, e
  o scanner avalia em `as_of = covered_until`. Sem essa prova, `trade_velocity_1m`,
  `buy_pressure_5m` e `sell_pressure_5m` saem `insufficient_coverage` e nenhum EARLY é confirmado;
- **o scanner nunca chama REST:** falta de histórico vira `market.backfill.requested`, que o
  `market-worker` — dono do rate limit e da tabela de gaps — atende.

O mesmo `scanner-worker` roda dois produtores horários ao lado deste laço, com a mesma regra de corte (a barra fechada, nunca o relógio): o β contra o BTC (§2b) e o **regime horário** (§4b), que grava uma linha de `market_regimes` por hora para que qualquer avaliação possa ser cortada por contexto.

## 2b. β horário contra o BTC — `market_betas` (T3.7b)

**Onde:** `scanner-worker` (`hunter_scanner_worker/beta*.py`). **Gatilho:** cada hora fechada, um produtor por exchange. **Quem consome:** o Risk Engine, pela §6 do `docs/RISK_ENGINE.md` (`bridge_universe.current_beta`). **Por quê existe:** a T3.7 entregou o estimador (`beta_v1`) e o esquema (`0006`), e o job nunca foi escrito — com `market_betas` vazia a admissão responde `unavailable` para todo candidato ("sem β validado só shadow") e a carteira nunca abre posição. β existir é **pré-condição**, nunca uma operação.

1. **O corte é a barra fechada, nunca o relógio.** `as_of` gravado na linha é `floor_bar(now)` — rodar às 12:37 mede a janela que terminou às 12:00 —, então uma reexecução dentro da mesma hora é o **mesmo corte** e a idempotência é propriedade da chave, não da disciplina de quem chama. O relógio de parede sobrevive em `computed_at`/`available_at`. `valid_until = window_end + 1 h` (ancorado na barra, não no cálculo — T3.7 §5).
2. **As barras são agregadas em SQL.** Trinta dias de um mercado são 43 200 velas de 1 min e o job passa por 200 mercados por hora; trazer 8,6 milhões de linhas para o Python uma vez por hora não é opção. `beta_repo.bar_closes` dobra os sessenta minutos de cada barra no servidor (`date_bin` a partir da época, `is_final` apenas, `open_time < window_end`, `count(*) = 60` **e** último minuto exatamente em `bucket + 59 min`) e devolve só os fechamentos. A aritmética que vem depois é a do indicador (`returns_from_closes`, extraída de `hourly_returns` na T3.7b **sem mudança de valor**) — o contrato numérico tem uma implementação só.
3. **Anti-look-ahead.** Só vela `is_final`; a barra que começa no corte não entra nem que os sessenta minutos dela já existam (o coletor pode estar à frente do job). Provado por teste contra Postgres: os mesmos sessenta minutos com o último `is_final = false` produzem `gaps` e nenhum coeficiente; virar aquele bit para `true` — o que o coletor faz quando o minuto fecha — é o que faz a hora existir (`test_beta_job.py::test_a_minute_that_is_not_final_does_not_complete_its_bar`).
4. **Uma revisão imutável por mercado por hora.** `beta_writer.write_revision` **reconhece primeiro** (mesmo `input_digest` no mesmo corte = retentativa, escreve nada), depois aposenta a vigente (`superseded_at`, na mesma transação, como `uq_market_betas_current` exige) e só então insere. `input_digest` é o `params_hash` de `BetaEstimate.as_wire()` mais o **id** do mercado de referência: cobre coeficientes, janela, `n`, `contiguous_bars`, `last_pair_end`, validade e motivo, então uma reexecução que um backfill transformou de `gaps` em β entra como revisão nova em vez de colidir. Uma transação **por mercado**: um coeficiente largo demais para `NUMERIC(18,8)` custa a hora daquele mercado, não a dos outros 199.
5. **Motivo, nunca número inventado.** Vocabulário congelado da T3.7 §3, nesta precedência: `btc_missing` (nenhuma hora da referência pareia), `insufficient_history` (o alcance não chega a 480 barras — é warm-up, espera), `gaps` (alcança, mas a corrida contígua quebrou ou não chega ao corte — precisa de backfill), `degenerate_variance` (série constante). Linha inválida tem `beta`/`alpha`/`r_squared` nulos e `reason` preenchido; `valid = (reason IS NULL)` é constraint do banco.
6. **BTC é 1 por identidade.** `reference_beta`: `estimator = 'definition'`, `n = 0`, `r_squared` nulo, sem porta de maturidade. Passar a referência pelo estimador daria o mesmo 1 com um `R² = 1` fabricado ao lado, e um consumidor que mediasse isso numa distribuição de estimativas estaria mediando uma tautologia.
7. **Mercado sem referência não vira linha.** `reference_market_id` é `NOT NULL`: um β contra nada não é representável e uma auto-referência faria o mercado parecer um segundo BTC. A passada conta (`outcome="no_reference"`) e não escreve — o único caso em que o silêncio é a resposta honesta, porque toda outra recusa **é** representável e por isso fica gravada com o motivo.
8. **Um produtor por exchange por hora.** A chave é `beta:producer:{exchange}:{corte}` (`SET NX`, TTL 2 h, sem release): quem a pega calcula aquele corte. Correção nunca depende dela — `uq_market_betas_revision` faz de uma passada duplicada um no-op —, é economia de banco, não de integridade. Custo declarado: um líder que morre no meio pula aquela hora, e a hora seguinte é calculada normalmente; pular uma hora é seguro por construção (a revisão vale uma hora e a admissão recusa a vencida) e aparece como `beta_last_run` envelhecendo no heartbeat.
9. **Observabilidade.** `hunter_beta_revisions_total{outcome}` (`valid`, `invalid`, `unchanged`, `no_reference`, `failed`), `hunter_beta_valid_markets`, log `scanner_beta_pass` (corte, mercados, válidos, barras da referência, contagem por outcome, duração) e os campos `beta_last_run`/`beta_valid` em `hb:scanner:{instance}`. **Prontidão: degradado, não fora.** β é *status detail* (`WorkerRuntime.status_details["beta"]`), nunca readiness check — um produtor parado há duas horas significa que a carteira para de abrir posição, o que o operador tem de ver, e não significa nada para o Radar, as baselines ou o regime, que é tudo o que o `/ready` do scanner protege.
10. **Manivela manual.** `uv run python -m hunter_scanner_worker.beta --once` roda uma passada e sai, sem tomar a trava (quem pede à mão já decidiu, e a passada é idempotente). A saída é o próprio log estruturado.

**Consequência a declarar, não a esconder (medida em 2026-09-08 no stack local):** com 11 dias de `candles` a passada sobre 200 mercados levou 13,1 s e produziu **1 válido** (o BTC, por identidade) e **199 `insufficient_history`** — 225 barras contíguas contra as 480 exigidas. Isso é a regra do Everton funcionando, não defeito de cálculo: enquanto o histórico não chegar a 20 dias contíguos, a carteira não admite ninguém. A profundidade se resolve pelo `infra/scripts/request_backfill.py` (§1b), não relaxando `min_contiguous_days` — relaxar é `beta_version` novo, por construção.

## 3. Anomaly Engine

**Onde:** `scanner-worker`. **Gatilho:** `features.updated`.

- Cada `AnomalyDetector` compara valor atual com baseline (mediana + MAD sobre janela de 7 d, mesma hora do dia) e emite `Anomaly {type, severity 0–100, confidence, baseline, current_value, deviation (em MADs), metadata}`.
- MVP (v1): `VOLUME_SPIKE`, `PRICE_ACCELERATION`, `VOLATILITY_EXPANSION`, `ORDERBOOK_IMBALANCE`, `OPEN_INTEREST_SPIKE`, `FUNDING_ANOMALY`, `LIQUIDATION_CLUSTER`, `CROSS_EXCHANGE_DIVERGENCE` (mesmo símbolo Binance vs Bybit).
- Fase 2/3: `SOCIAL_SPIKE`, `WHALE_ACTIVITY`.
- Deduplicação: uma anomalia `active` por (market, type); atualiza severidade enquanto persistir; `resolved` quando o desvio cai abaixo do limiar por 5 min; `expired` após 4 h.
- Persiste em `anomalies` com `feature_snapshot`. Publica `anomalies.detected` (novas ou severidade +20).

**Nenhum detector fica mudo sem motivo (T3.46b).** A T3.46 mediu três detectores com **zero linha** em toda a série (`ORDERBOOK_IMBALANCE`, `OPEN_INTEREST_SPIKE`, `TRADE_VELOCITY_SPIKE`) e sem nenhuma entrada em `detectors_disarmed`, mais dois tipos do enum (`SOCIAL_SPIKE`, `WHALE_ACTIVITY`) que nem estavam no roster — e um tipo ausente do roster não produz avaliação, logo não consegue nem se declarar. Duas mudanças fecham isso. (i) O roster passa a cobrir **todos os doze** `AnomalyType`: os dois de fase 2/3 entram registrados e desarmados com `feature_not_implemented`, apontando para as features que a ingestão deles teria de criar. (ii) O campo `detectors_disarmed` do `hb:scanner:{instance}` deixa de ser só *capacidade do deploy* e passa a ser derivado, por ciclo e por mercado, do veredito que `evaluate_detector` **já produz** (`hunter_indicators.anomalies.silence`): um detector sem anomalia aberta e sem leitura crível se nomeia com a palavra do operador — `baselines_under_construction` (a baseline daquele bucket não passa o portão da `opportunity_weights`), `baseline_absent`, `baseline_without_dispersion`, `data_degraded`, ou `feature_*` para o que falhou do lado da entrada (`feature_after_cut`, `feature_warmup`, `feature_insufficient_coverage`…). Três regras que valem registrar: uma avaliação `ok` **nunca** aparece ali, porque severidade 0 é resposta ("o mercado está normal") e não ausência; um detector com anomalia `active` também não, porque ele está produzindo mesmo quando a leitura do minuto é cega; e o motivo publicado é o mesmo que a decisão usou, nunca um diagnóstico paralelo — um segundo cálculo teria liberdade para discordar do primeiro. Consequência medida em 2026-09-08: os três detectores calados eram `baselines_under_construction` (tape e OI só têm baseline da fonte `live`, que o bootstrap por velas não reproduz) e `feature_after_cut` (o snapshot de livro no Redis carrega o relógio da exchange e a avaliação corta em `covered_until`, então em 97,7 % dos minutos o livro está no futuro do próprio corte e nenhuma feature de livro existe).

## 4. Market Regime Engine

**Onde:** `scanner-worker`. **Gatilho:** a cada 1 min (fechamento de candle do BTC). **Escopo:** global.

- v0 (M2): entrada = BTC features (retornos 1h/4h/1d, volatilidade 1h vs 30 d, EMA ratio) + breadth (fração de mercados monitorados com retorno 4h > 0, com `relative_volume_1h` > 1,5).
- Regras determinísticas com histerese (não muda de regime sem 3 leituras consecutivas). Regimes v0: `BTC_BULL`, `BTC_BEAR`, `SIDEWAYS`, `HIGH_VOLATILITY`, `LOW_VOLATILITY` (volatilidade é uma dimensão separada; o estado é `{trend, volatility}` e o `regime` principal é o mais relevante para o Risk Engine).
- Persiste `market_regimes` (fecha o anterior com `end_time`). Publica `regime.changed` só em transição.
- v1 (Fase 2) adiciona `RISK_ON/RISK_OFF`, `ALT_EXPANSION`, `PANIC`, `LIQUIDITY_CONTRACTION` com breadth, funding agregado e liquidações agregadas.

## 4b. Regime horário — uma linha de `market_regimes` por hora (T3.43)

**Onde:** `scanner-worker` (`hunter_scanner_worker/regime_job.py`, `regime_repo.py`,
`regime_window.py`, `regime_writer.py`, `regime_hourly.py`; a aritmética é pura, em
`hunter_indicators.regime.hourly*`). **Gatilho:** cada hora fechada, um produtor por
exchange, do lado do `beta_job` (§2b). **Quem consome:** a pesquisa — o corte de coorte
por contexto (`infra/scripts/sql/research/2026-09-09-regime-split.sql`). **Por quê existe:**
o §4 grava **por transição**, e um classificador que está em aquecimento desde que subiu
nunca transicionou: em 2026-09-08 `market_regimes` tinha **uma linha** (`global`,
`UNKNOWN`), então nenhuma coorte do Shadow Lab ou de replay podia ser cortada por regime
(C4 da Astra, T3.32, T3.33e/g). Este produtor é a série que faltava: uma linha por hora,
tenha mudado alguma coisa ou não, trinta e um dias para trás.

1. **`ts` é o corte, e é por isso que não há antecipação.** Toda entrada da hora `ts`
   fechou **antes** de `ts` (a última vela horária lida é a de `[ts-1h, ts)`), e a linha
   vale em `[ts, ts+1h)`. Um sinal das 12:34 casa com a linha das 12:00, decidida com
   velas que já eram finais às 12:00. Rotular a hora **seguinte** ao dado é o que faz a
   junção honesta; rotular a hora de onde o dado veio poria os movimentos da hora dentro
   do próprio rótulo dela.
2. **Duas versões, duas perguntas, duas séries.** O §4 (`regime_v0`, `scope = global`,
   intervalos abertos, histerese) responde "como está o mercado agora"; este
   (`regime_hourly_v1`, `scope = btc`, uma linha fechada por hora) responde "como estava
   o mercado naquela hora". Escopos separados de propósito: duas séries no mesmo escopo
   dariam intervalos sobrepostos e `regime_at` escolheria a que mexeu por último. Leia
   sempre por `scope` **e** `classifier_version`; nunca some as duas numa média.
3. **O que a hora mede** (`RegimeSnapshot`), tudo sobre fechamentos horários do BTC
   completos (60 minutos `is_final`, o último exatamente em `bucket+59min`):

   | dimensão | regra | limiar declarado |
   |---|---|---|
   | `trend` | fechamento vs SMA200h, SMA50h vs SMA200h **e** inclinação da SMA50 em 24 h | 3 de 3 → `up`/`down`; senão `flat`; inclinação mínima 0,2 % |
   | `vol_regime` | percentil (mid-rank) da vol realizada de 24 h contra as leituras horárias dos 30 dias anteriores | ≥ 80 → `high`, ≤ 20 → `low` |
   | `breadth_pct` | % dos mercados **usáveis** acima da própria SMA de 24 h **e** com retorno 24 h positivo | cobertura mínima de 50 % do universo |
   | `funding_avg` | média da **última** liquidação de funding de cada mercado dentro de 8 h | fora da janela não entra (nunca vira zero) |
   | `drawdown_pct` | queda do fechamento contra a máxima horária de 30 dias | mínimo de 168 horas para a máxima existir |

4. **`score_0_100` é uma decomposição, não um número.** Cinco componentes, cada um com
   `raw`, `normalized`, `weight` e `contribution` gravados na linha: tendência 0,35 ·
   breadth 0,25 · volatilidade 0,20 · drawdown 0,10 · funding 0,10 (todos na direção
   "maior = fita mais saudável"; funding positivo — comprado pagando — pontua **menos**).
   Componente sem leitura é `None` e **o peso dele é redistribuído**, nunca lido como
   zero; `confidence` publica quanto do peso respondeu e abaixo de metade não há score,
   só `insufficient_components`.
5. **`unknown` é classificação, não buraco.** Enquanto não houver 224 horas fechadas
   (tendência) ou 193 (percentil de volatilidade), a resposta honesta é `unknown` com o
   motivo na linha — e o rótulo projetado é `UNKNOWN`. Medido sobre as velas reais do
   stack local em 2026-09-08 (762 horas completas desde 2026-08-08): **207 das 745 horas**
   do backfill saem em aquecimento e 538 saem classificadas.
6. **Idempotência é do trabalho, não do esquema.** `market_regimes` não tem coluna
   `exchange` nem índice único em `(scope, start_time)`: o job procura a hora
   (escopo + versão + `supporting_features->>'exchange'`), compara o **digest** do que
   escreveria e então não faz nada, atualiza no lugar ou insere. Atualiza — nunca apaga e
   reinsere — porque `agent_signals.regime_id`, `trade_proposals.regime_id` e
   `paper_trades.regime_id` apontam para esses ids com `ON DELETE SET NULL`. A corrida que
   um índice único fecharia é fechada pela trava `regime:producer:{exchange}:{corte}`
   (`claim_cut`, provada com dois produtores simultâneos em
   `test_two_producers_of_the_same_cut_write_one_row_per_hour`); **a guarda de verdade é o
   índice único**, ainda pedido em `.claude/state/brief-T3.43-db-market-regimes-hourly.md`
   — enquanto ele não existir, a trava é tudo o que separa duas passadas simultâneas de
   uma hora duplicada.
7. **Duas regras decidem quais horas uma passada produz** (`regime_window.py`), e é a
   segunda que faz um buraco sarar. *Backfill:* toda hora da janela **sem linha** — 31 dias
   na primeira passada, nada depois. *Reparo:* toda hora das últimas **72 h**, tenha linha
   ou não — porque a hora escrita `unknown` durante uma falta de vela **tem** linha e a
   primeira regra nunca mais olharia para ela; era assim até a T3.43c e a série ficava com
   o buraco para sempre. Recalcular é barato; **reescrever** é o que custa, e quem decide é
   o digest: hora cujas velas não mudaram sai `unchanged` sem sequer abrir transação, hora
   cujas velas mudaram é atualizada **no lugar** (o id sobrevive para as FKs). Mais fundo
   que 72 h — depois de um backfill grande de velas, como os buracos da T3.7 — é decisão do
   operador: `--repair-days N` (que também alarga `--backfill-days` para pelo menos N,
   senão pediria reparo de hora fora da janela). O corte atual está sempre dentro da janela
   de reparo: é a hora cujas velas ainda podem estar chegando.
8. **Manivela e observabilidade.** `uv run python -m hunter_scanner_worker.regime_hourly
   --once [--backfill-days N] [--repair-days N]` roda uma passada e sai (sem trava: quem
   pede à mão já decidiu). Métricas `hunter_regime_rows_total{outcome}` (`inserted`,
   `updated`, `unchanged`, `no_reference`, `failed`) e
   `hunter_regime_last_hour_timestamp_seconds`;
   campo `regime_last_ts` no `hb:scanner:{instance}`; log `scanner_regime_pass`.
   **Prontidão: detalhe de status, nunca check.** Um buraco nesta série custa a uma coorte
   o corte por contexto e não custa nada à faixa viva.
9. **Custo declarado** (stack local, 2026-09-08, 217 mercados monitorados): a dobra
   horária do BTC em 62 dias custa **0,48 s**; a do universo em 32 dias, **2,3 s por lote
   de 25 mercados** (~21 s no total, uma vez); em regime permanente a leitura do universo
   é de 25 horas e custa **0,12 s por lote** (~1,1 s) — **número obsoleto desde a T3.43c:**
   com a janela de reparo de 72 h a leitura em regime permanente passa a cobrir **97 horas**
   (~4× o volume; estimativa ~4 s por passada, ainda não medida contra o stack real — remedir
   e substituir esta linha). Classificar as 745 horas do
   backfill custa **1,7 s** de CPU. Cobertura de breadth medida: 199 de 217 mercados com
   as 25 horas completas. **Escrita** (testcontainer, T3.43c): as 745 linhas do backfill
   custavam **186,5 s** com uma transação por hora e custam **11–12 s** com uma transação
   por dia (`WRITE_BATCH_HOURS = 24`; uma leva que falha é repetida hora a hora, então uma
   hora impossível continua custando só a própria hora). A passada em regime permanente
   recalcula as 73 horas da janela de reparo, não reescreve nenhuma e custa **0,52 s**.

## 5. Opportunity Engine

**Onde:** `scanner-worker`. **Gatilho:** `features.updated`, `anomalies.detected`, `signals.emitted` (para o componente de consenso), throttle 2 s por símbolo.

- Cada componente produz um valor normalizado 0–100 e uma direção sugerida:

| Componente | Origem (v1) | Peso padrão |
|---|---|---|
| Momentum | `momentum_15m`, `momentum_acceleration`, `ema_ratio`, `breakout_strength` | 0.20 |
| Volume | `relative_volume_*`, `volume_acceleration` | 0.20 |
| Liquidity | `quote_volume_1h`, `spread_pct` (inverso), profundidade top 25 | 0.10 |
| Order Flow | `buy_sell_pressure`, `orderbook_imbalance`, `trade_velocity` | 0.15 |
| Derivatives | `oi_change`, `funding`, `liquidation_pressure`, `oi_price_divergence` | 0.10 |
| Market Regime | compatibilidade direção × regime (long em BTC_BEAR penaliza) | 0.10 |
| Anomalies | soma ponderada de severidade das anomalias ativas | 0.10 |
| Agent Consensus | nº e confiança de sinais ativos concordantes | 0.05 |
| External Intelligence | 0 no MVP (componente registrado, peso 0) | 0.00 |

- `score = Σ weight_i × normalized_i`, com pesos de `opportunity_weights` (versão ativa). `confidence` é função da qualidade dos dados, quantidade de componentes com dado válido e concordância de direção entre componentes.
- **Decomposição completa** persiste em `opportunities.decomposition` e em `opportunity_history` a cada mudança de ≥ 3 pontos ou de status.
- Status: `NORMAL` (< 40) → `WATCHING` (40–60) → `ANOMALY` (≥ 1 anomalia severidade ≥ 60) → `HOT` (≥ 75) → `ENTRY_CANDIDATE` (≥ 80 e ≥ 1 sinal de agente ativo concordante) → `EXPIRED` (score < 40 por 15 min ou sinais expirados). `IN_POSITION` e `BLOCKED_BY_RISK` são derivados por org na leitura.
- Publica `opportunities.updated`; atualiza `radar:scores` (ZSET) e `rt:radar`.

## 6. Strategy Agents

**Onde:** `strategy-worker`. **Gatilho:** `opportunities.updated` (para o mercado) e `market.candles.closed` (reavaliação de sinais ativos: invalidações e expiração).

- Para cada `strategy_version` ativa, `Strategy.evaluate(ctx, opportunity, regime, default_params)` → `Signal | None`. Função pura.
- Um sinal ativo por (strategy_version, market). Novo sinal com mesma direção atualiza; direção oposta invalida o anterior.
- Persiste `agent_signals`; `analytics-worker` abre `signal_outcomes` para **todo** sinal (shadow de sistema) e acompanha MFE/MAE até stop, alvo, invalidação ou `expires_at`.
- MVP: `momentum_v1` (entrada em continuação com volume relativo e breakout; stop em ATR; alvos em múltiplos de R) e `volume_anomaly_v1` (entrada após `VOLUME_SPIKE` + pressão compradora/vendedora; stop na mínima/máxima do spike). Fase 2: breakout, order flow, mean reversion, derivatives, ensemble.
- Publica `signals.emitted`.

## 6b. Shadow Lab: `strategy-worker` em modo sombra (S2)

**Onde:** `strategy-worker` (`HUNTER_ROLE=strategy`, serviço `strategy-worker` no compose). **Gatilho:** `market.candles.closed`, grupo próprio `strategy-worker.shadow`. Contrato completo em `docs/plans/SHADOW-LAB.md`; estado durável em `docs/DATABASE.md` §16.

Trilha de **pesquisa**, paralela ao §6: mede o que as estratégias teriam feito sobre o dado real do M1, sem carteira, sem ordens, sem posições e sem PnL de portfolio. Difere do §6 em pontos que valem registrar porque a §6 descreve o caminho de M4:

- avalia cada `strategy_version` **ativa** apenas nos fechamentos alinhados do timeframe dela (15 min em `momentum_v1`, 5 min em `volume_anomaly_v1`), com o contexto cortado em `source_bar_close` — o gatilho é a vela de 1 min fechada, não `opportunities.updated`;
- persiste sinal, outcome inicial, slot de episódio (`shadow_episodes`) e linha de outbox (`shadow_outbox`) na **mesma transação**; o ACK do stream só vem depois do commit e a publicação em `shadow.signals.emitted` é feita pelo despachante da outbox;
- `agent_signals.supporting_features` é escrito uma vez e nunca reescrito, com o `purpose` **da versão** (`strategy_versions.purpose`, `0010_strategy_purpose`: `research_only` ou `paper`; `live` é recusado na origem pelo catálogo do worker), coorte, `decision_at` e proveniência — o worker não crava rótulo nenhum;
- todo evento sai em `shadow.signals.emitted` — **nunca** em `signals.emitted`. O proposal builder do §7 não vê sinais de pesquisa, e quando vier a vê-los deve recusar `purpose = research_only` (item 10 da decisão conjunta).

**Escritor único de outcomes.** No §6 quem abre e acompanha `signal_outcomes` é o `analytics-worker`. Enquanto o Shadow Lab existir, **quem escreve os outcomes de sombra é o `strategy-worker`, e só ele** (`hunter_strategy_worker/outcomes.py` + `tracking_repo.py`): a decisão, a entrada, a saída e a liberação do slot precisam acontecer sob o mesmo lock de `shadow_episodes`, e dois escritores produziriam dois acompanhamentos do mesmo episódio. A transferência para o `analytics-worker` é prevista e fica registrada aqui como pendência explícita: quando acontecer, `advance_tracking`, `settle` e a liberação do slot mudam de processo (não são duplicados), e o `strategy-worker` deixa de escrever `signal_outcomes` no mesmo commit em que o analytics passa a escrever.

**`tracking_hold`.** O `market-worker` mantém a coleta de um mercado que saiu do top N enquanto houver `shadow_episodes.open_outcome_signal_id IS NOT NULL` apontando para ele (`universe.with_tracking_holds`). O hold amplia a *coleta*, nunca a *elegibilidade*: `markets.is_monitored` continua sendo o conjunto elegível e é o que o `strategy-worker` lê. A blocklist explícita do operador prevalece sobre o hold; os acompanhamentos afetados terminam como `censored`.

**Backfill.** O `strategy-worker` nunca chama REST: quando falta uma vela, ele espera a recuperação do `market-worker` (dono único do REST) e, esgotado o prazo, encerra o acompanhamento como `censored` com o minuto que faltou — nunca como `expired`.

## 6c. Replay histórico: o mesmo código sobre velas persistidas (T3.19b)

**Onde:** `services/strategy-worker/hunter_strategy_worker/replay/` (job, não serviço). **Gatilho:** um comando ou a fila `replay:queue` no Redis. **Nada aqui ativa nada e nada chega à carteira.**

O §6b mede o que as estratégias fariam **para a frente**, e por isso rende ~600 sinais/dia: uma versão só decide quando o mercado real dispara. A massa de validação que o protocolo de replicação precisa (`docs/plans/REPLICATION.md`) vem daqui: a **mesma** versão, os **mesmos** custos, as **mesmas** regras de não-antecipação, rodadas sobre as velas já persistidas.

```
uv run python -m hunter_strategy_worker.replay.run \
    --version <strategy_version_id | key:version> \
    --from 2026-08-08 --to 2026-09-08 \
    --markets all|BTCUSDT,ETHUSDT --cohort replay:<uuid> [--workers N] [--ledger x.jsonl] [--dry-run]
```

**Não existe um segundo caminho de avaliação.** Uma barra replayada é uma chamada a `decide.evaluate_slot` — a mesma função que o consumidor chama quando uma vela fecha. O replay só fornece os dois pontos que a função já lê do mundo (`replay/environment.py`):

- **o relógio**: `evaluate_slot` já recebe `clock` por parâmetro; o replay devolve `bar_close + REPLAY_DECISION_LAG_S` (2 s), o que põe a entrada na abertura de `bar_close + 1min`, dentro do `max_entry_delay_s` congelado. Qualquer lag ≥ 60 s moveria a barra de entrada e mudaria a população;
- **o hot state**: para uma barra que fechou dias atrás o Redis está vazio por construção (o corte descarta tudo ≥ `source_bar_close`), então o adaptador responde "nada" às três leituras que o caminho vivo faz, e o replay lê só a série durável.

Consequências que vêm de graça, por reuso e não por repetição: contexto cortado em `source_bar_close` só com velas `is_final`; máquina de estados do slot, barreira de re-arme e uma-tracking-por-slot; barra de entrada, custos assumidos, níveis congelados, envelope e identidade `uuid5`; saídas pelo `walker.walk` e liquidação pelo `settle.settle` (funding incluído, com o mesmo motivo quando não dá para estabelecer).

**A coorte é o isolamento.** Toda decisão sai com `replay:<run_id>` (gramática de `0002_shadow_lab`, mantida pela `0012_replication`): ela entra no `signal_id`, é a terceira coluna do slot de episódio, e **impede a linha de outbox** — `persist.is_published_cohort` recusa publicar uma coorte de replay, porque um replay não é o evento de ninguém e meio milhão de linhas/dia atravessariam um despachante cujo atraso é check de prontidão. A ponte de execução recusaria de qualquer forma (`cohort_not_live`, T3.15e), e isso continua provado por teste.

**Custo e paralelismo.** O paralelismo é **por mercado, em processos** (não threads: o custo está em `Decimal` sob o GIL; não por fatia de tempo do mesmo mercado: o slot é uma máquina de estados sequencial). As velas da fatia inteira são lidas **uma vez** por mercado (`replay/candles.py`), com a garantia — testada — de devolver exatamente o que `repo.load_candles` devolveria. O orçamento (`REPLAY_*`, `replay/budget.py`) limita CPU e corridas simultâneas e **pausa quando o heartbeat da faixa viva degrada**. Números medidos e projeção em `docs/DEPLOYMENT.md` §5.2 e `.claude/state/notes-T3.19b.md`.

**Livro-razão.** Cada corrida grava um recibo (versão, janela, mercados, início/fim, barras, sinais, desfechos, segundos, lag assumido, workers) em `system_events` (`component = 'replay_engine'`) e, opcionalmente, num JSONL. A tabela `replay_runs` ainda não existe — o brief está em `.claude/state/brief-T3.19b-db-replay-runs.md`.

**O que um replay não prova.** A elegibilidade é lida de `markets.is_monitored` **hoje**: não há histórico de pertencimento por barra no schema, então o conjunto replayado é o conjunto atual, não o da janela. Está declarado no envelope (`provenance.eligibility_observed_at` carrega o relógio da corrida) e é a limitação principal do método.

## 7. Proposal builder e Risk Engine

**Onde:** `strategy-worker`. **Gatilho:** `signals.emitted`.

1. Busca agentes `enabled` cuja `strategy_version_id` bate com o sinal e cujos filtros aceitam o mercado (`market_filter`, `min_opportunity_score`, `min_confidence`, `allowed_directions`). Varre todas as orgs (role `hunter_worker`).
2. Para cada agente, cria `trade_proposals` com `idempotency_key = sha256(agent_id, signal_id)` (`INSERT ... ON CONFLICT DO NOTHING`). Sem duplicata mesmo com reentrega.
3. `RiskEngine.evaluate(proposal, portfolio_state, limits, market_liquidity, kill_switch)`:
   - `portfolio_state` = cash, equity, exposição, posições abertas, perda do dia, drawdown atual, correlação das posições (v1: mesmo base asset ou beta > 0,8 com BTC).
   - Checks em ordem, todos registrados em `risk_decision.checks` (o primeiro reprovado encerra com `rejected`, mas todos os checks avaliáveis são anotados para o Explanation Panel).
   - Aprovado → **sizing**: `qty = min(risco por trade em USDT / distância ao stop, limite por posição, limite por ativo, limite por exchange, exposição restante)`; arredonda por `step_size`; rejeita se abaixo de `min_notional`.
4. Persiste decisão em `trade_proposals`; se rejeitado por limite, gera `risk_events` (`severity=info`). Publica `proposals.decided`.
5. Kill switch: estado efetivo = max(sistema, org, portfolio). `WARNING` reduz `max_position_pct` pela metade; `TRADING_DISABLED` e `EMERGENCY` rejeitam toda proposta de entrada.

Lista completa de checks em `RISK_ENGINE.md`.

## 8. Execution Engine

**Onde:** `execution-worker` (`HUNTER_ROLE=execution`, T3.5). **Papel de banco:** `hunter_worker` em
todos os ciclos — desde a `0007_paper_roles` (§19.1) a trava da carteira, o `fifo_v1`,
`portfolios.kill_switch_state`, a curva de equity e a outbox são do motor. **Gatilhos:** relógio,
não evento: seis laços com cadência própria, cada passada uma transação, sob a trava da carteira
(`portfolio_risk_state`, ordem sistema → organização → carteira).

| Laço | Cadência | O que faz |
|---|---|---|
| `admission` | 1 s | lê os pedidos que a API arquivou (`status='pending'`) e decide **a própria linha** (`hunter_core.admission.decide_pending`); nunca insere uma segunda proposta para o mesmo pedido |
| `entries` | 1 s | proposta `approved` com reserva `held` → uma tentativa → aplica o `ExecutionReport` |
| `protection` | 1 s | `check_triggers` pelo último negócio SPOT válido; disparo → tentativa de saída |
| `expiry` | 5 s | `expire_reservations` sob a trava (30 s sem ordem) |
| `kill_switch` | 10 s | relê o estado efetivo; BLOQUEADO cancela pendentes e **não** toca proteções |
| `mtm` | 60 s, **na grade do minuto** | ponto da curva `1m` → `evaluate_and_persist` → publica `kill_switch.changed`; grava um ponto extra 5 s antes da virada em São Paulo, para a referência do dia sempre ter uma âncora dentro dos 60 s que ela aceita (`hunter_execution_worker.schedule`) |

1. **Entrada — uma tentativa, e só contra livro elegível.** A ordem carrega a `RiskDecision`
   aprovada (`MarketEntryOrder`), o `client_order_id` e o `execution_key` são `entry:{proposal_id}`
   (derivados, nunca aleatórios) e o fill sai de uma caminhada única no **livro spot** recebido
   depois da latência declarada. Enquanto o livro não é elegível — ausente, velho, anterior à
   latência, de outro mercado — a proposta é **adiada**, não recusada: nada é escrito e a tentativa
   não é gasta; se o livro nunca chegar, a reserva expira em 30 s e é liberada com o motivo. Já
   *dentro* da tentativa, filtro, banda de preço ou profundidade recusam em definitivo.
2. **O fill vira ledger na mesma transação:** `orders`, `fills` (com `execution_key`,
   `submitted_qty` e `decision_fingerprint`), `positions` com a **quantidade líquida da taxa em
   ativo-base**, `participation_consumptions` (`kind='executed'`, único por `fill_id`), a reserva
   → `consumed`, a **intenção de proteção durável** (`portfolio_exit_intents`, nunca uma posição
   sem stop), a auditoria e a outbox. Reentrega do mesmo relatório não escreve nada:
   `uq_orders_client_order_id` e `uq_fills_execution_key` são a idempotência, não uma flag.
3. **Proteção — a tentativa acaba, a intenção não.** Cada tentativa tem identidade própria
   (`exit:{attempt_id}`); sem livro utilizável a saída fica `pending_degraded`, com alerta, e a
   intenção guarda a quantidade — vela **nunca** dá fill retroativo. Uma tentativa degradada é
   repetida sem esperar novo cruzamento, com **backoff de 1 s dobrando até 60 s**: cada tentativa
   escreve uma linha `orders`, e uma por segundo eram 86.400 por dia para um mercado sem livro
   (T3.5b item 5). Stop, alvo e fechamento manual dividem a mesma quantidade vendável
   (`allocate_sellable`) sob a trava da carteira e depois a da posição.
4. **Resíduo — o pó não é posição.** Uma compra spot paga a taxa em moeda, então a quantidade
   líquida quase nunca é múltiplo do `step_size`: o que sobra abaixo do mínimo é **pó**, fica na
   posição (status `closing`), e a intenção termina em `blocked_residual` — nunca `fulfilled`. O
   `trades` é escrito nesse instante, com a quantidade realmente liquidada e o preço de saída
   **efetivo** (o que faz `qty × (saída − entrada)` bater com o realizado acumulado).

   **Semântica do pó (T3.5b, revisão do `7ecafd2` item 3).** O resíduo continua **visível e
   valorizado no patrimônio** pela mesma marca das outras posições — as moedas são da carteira e a
   exposição e o equity dizem isso. Mas ele **não é uma posição** para o Risk Engine: não ocupa
   vaga (`slots_used`), não conta como a moeda "já na carteira" da D3 (`duplicate_position`) e não
   compromete risco planejado. Antes disso, 0,000482 unidades valendo 4,6 centavos seguravam uma
   das cinco vagas e recusavam aquela moeda para sempre — quatro horas depois do stop a carteira
   ainda tinha `slots_used=1`. O marcador de leitura é `positions.status='closing'` mais a intenção
   `blocked_residual` (`LedgerRepository.PositionRow.is_residual`); uma coluna durável
   `positions.is_residual` está pedida à T3.1e. **Assentamento:** quando o pó acumulado da moeda
   voltar a ≥ `min_qty` (ou `min_notional`), a proteção o vende junto da próxima saída, ou num
   ciclo de varredura diário; até lá ele não é tentado de novo (uma tentativa por segundo numa
   quantidade invendável era uma linha `orders` recusada por ciclo, para sempre).
5. **MTM e curva.** `build_portfolio_state` com marcas do último negócio válido → ponto em
   `portfolio_equity_snapshots` na resolução `1m`, com `fx_observation_id` **ou**
   `brl_unavailable_reason`, e `marks_stale` quando alguma marca é estimada. O ponto é escrito
   **antes** da avaliação do kill switch: o pico e a referência do dia são limitados pelo maior
   patrimônio que a curva mostrou (DATABASE.md §18.7), então um pico gravado antes do ponto que o
   sustenta é recusado pelo banco. Na virada do dia o ponto que ancorou a referência é espelhado na
   faixa `1h`, que não é podada.
6. **Kill switch.** Relido a cada 10 s **e** na transação de cada efeito. `TRADING_DISABLED`
   bloqueia entradas novas e libera as pendentes (`held → released`, auditado, devolvendo só o não
   executado) e **não** toca em nenhuma proteção — "travas de entrada não podem impedir saídas de
   proteção". O worker é o único papel que move a trava e publica `kill_switch.changed` na mesma
   transação. **Um único formato, uma única publicação por transição** (T3.5d): o evento é sempre o
   de `hunter_core.risk.transitions.record_transition` — `{scope, scope_id, organization_id,
   from_state, to_state, reason, actor_type, evidence}`, `event_id = transition_id` — nunca um
   segundo formato próprio do ciclo de MTM. Uma retomada (`resume`) que um OWNER autoriza pela API
   roda como `hunter_app`, que `0007_paper_roles` proíbe de escrever no outbox; o ciclo de 10 s do
   kill switch lê as transições `actor_type='user'` desta carteira ainda sem linha no outbox e as
   enfileira nesse mesmo formato — idempotente por `transition_id`, então uma releitura (ou um
   processo morto entre a leitura e o `enqueue`) nunca produz uma segunda publicação da mesma
   transição.
7. **Live.** `LiveExecutionAdapter` levanta `LiveTradingDisabled` sempre, e o processo **recusa
   subir** com `ENABLE_LIVE_TRADING=true`: um worker de papel que subisse assim seria um que o
   operador acredita estar operando de verdade.
8. **Ponte shadow → admissão (T3.14/T3.15b).** A ponte admite `purpose = "paper"` apenas;
   `live` é recusado **por nome** (`live_forbidden`, "live é Fase 4; `ENABLE_LIVE_TRADING=false`")
   até a Fase 4, `research_only` é recusado como sempre (evidência nunca vira ordem) e qualquer
   outro rótulo desconhecido é recusado como `unknown_purpose`. A flag `ENABLE_PAPER_AUTONOMY`
   (default `false`) governa se a ponte chega a consumir; mesmo ligada, nunca em produção antes do
   aceite da T3.9.

**Falha e reinício:** não há estado em memória para perder. Cada passada relê posições, intenções e
reservas do Postgres, então o worker depois de um `kill -9` é o worker de antes, menos o que a
última transação não comitou. A única coisa em memória é a marca-d'água do gatilho, e perdê-la causa
uma reavaliação, nunca uma segunda venda. Propostas `approved` sem ordem após 30 s **perdem a
reserva** (`reservation_state=expired`, `reserved_slot=false`), nunca são executadas tarde — o
`status` continua `approved`, porque ele registra o que o Risk Engine decidiu e isso não deixa de ser
verdade; o que expira é o compromisso, que é o outro eixo (DATABASE.md §18.3, T3.12).

**Prontidão** (`/ready`, cinco checks próprios): schema paper aplicado, kill switch legível, atraso
do MTM ≤ 120 s, nenhuma proteção disparada esperando > 5 s, outbox sem atraso. **Métricas:**
`hunter_execution_orders_total{kind,outcome}`, `hunter_execution_protection_delay_seconds`,
`hunter_execution_mtm_age_seconds`, `hunter_execution_pending_degraded_total{reason}`.
**Heartbeat:** `hb:execution:paper` (patrimônio, kill switch, posições, atraso de proteção, erros).

**Acoplamento aberto (T3.0b/T3.1d):** o `avgPrice` que o filtro `NOTIONAL` de uma ordem MARKET exige
não é coletado por ninguém ainda; num mercado que o exige (`avgPriceMins > 0`) a entrada é **adiada
com motivo**, nunca julgada pelo último negócio. E `trade_proposals` não tem coluna para a geometria
do pedido (`entry_ref`, `stop`, `assumed_costs`), então um pedido arquivado pela API ainda não pode
ser decidido a partir da linha — o worker registra `pending_request_without_geometry` e não inventa
número nenhum.

## 9. Analytics e Learning

**Onde:** `analytics-worker`.

- A cada 1 min: `signal_outcomes` (MFE/MAE/resultado), agregação de equity.
- A cada 1 h: `agent_stats` por janela (7d/30d/90d/all), por regime, por mercado, por hora do dia, por bucket de volatilidade.
- Diário: retenção, partições, consolidação de heartbeats.
- Learning (Fase 3): importância de features (correlação de componentes da decomposição com `r_multiple`), taxa de falso positivo por anomalia, degradação de performance por versão; produz **recomendações** de pesos (`opportunity_weights` nova versão `is_active=false`) que um OWNER precisa ativar. Nunca altera capital ou risco sozinho.

## 9b. Operações traçadas — o gráfico de cada operação concluída (T3.50)

**Onde:** `infra/scripts/render_operations.py` + os irmãos `_chart.py` (modelo e geometria) e
`_draw.py` (matplotlib). **Não é serviço, não é worker, não escreve nada na VPS:** é uma ferramenta
de leitura, rodada à mão, que transforma cada desfecho `terminal` com `r_multiple` conhecido num PNG
no vault e numa linha de tabela numa nota do Obsidian.

```bash
# 1. exportar (SOMENTE LEITURA; a consulta viaja pelo stdin do psql e o JSON volta pelo stdout)
uv run python infra/scripts/render_operations.py export     --version momentum v6 --cohort all --out /tmp/momentum-v6.jsonl
# 2. desenhar (matplotlib NÃO está no pyproject — árvore compartilhada, lock intocado)
uv run --with matplotlib python infra/scripts/render_operations.py render     /tmp/momentum-v6.jsonl --max 200          # destino padrão: obsidian/attachments/operacoes/<slug>
# 3. escrever a nota da versão e reconstruir o índice
uv run python infra/scripts/render_operations.py note /tmp/momentum-v6.jsonl
```

1. **O corte da barra da decisão é `date_bin('15 min', observation_ts, 'epoch')`** — a última barra
   de 15 min **completamente fechada** no instante da decisão. Para uma versão de 15 min é
   exatamente a barra que ela leu; para uma de 5 min (`volume_anomaly`) é a última barra de 15 min
   que já existia, nunca a que ainda estava se formando.
2. **As velas são as de 1 min `is_final`, dobradas em SQL com exigência de completude**
   (`date_bin` desde a época, `count(*) = 15`): balde a que falta um minuto não é exportado. A
   janela vai de 96 barras de 15 min terminando na decisão (`pattern_bars` de
   `trendline_breakout_v1`) até 4 barras depois da saída.
3. **As linhas de tendência do gráfico são `tl_scan` cortado na barra da decisão**, com
   `pattern_params(trendline_breakout_v1.default_parameters)` — o mesmo código congelado que decide,
   não uma reimplementação para desenhar. A janela é a corrida **contígua** de até 96 baldes
   completos terminando na decisão (`atr_series` levanta em buraco). Nenhuma vela posterior à
   decisão participa: `tl_scan` aplica o corte uma vez, no topo.
4. **O que as linhas significam depende da versão.** Só `trendline_breakout_v1` **lê** linha para
   decidir — nela a linha é o gatilho e a invalidação estrutural, e o `line_id` do envelope é
   destacado no gráfico junto com o pivô do stop. Em `momentum`, `mean_reversion`, `session_orb`,
   `volume_anomaly`, `breakout` e `sweep_reclaim` as linhas são **contexto calculado depois** pelo
   mesmo varredor congelado: servem para olhar a operação, nunca foram entrada dela. Tratar as duas
   coisas como a mesma é a forma mais barata de inventar uma explicação retrospectiva.
5. **Idempotência.** `render` pula o PNG que já existe (`--force` redesenha) e `--max` limita o lote,
   então uma versão de 213 operações se completa em duas invocações sem redesenhar as 200 primeiras.
   `note` reescreve a nota inteira a partir do JSONL: a nota é derivada, nunca editada à mão.
6. **Nome do arquivo:** `<YYYYMMDD-HHMM>Z-<mercado>-<resultado>.png`, com o instante em UTC — o
   título e as tabelas mostram Brasília (UTC−3) com o UTC ao lado, mas o nome do arquivo é ordenável
   e não muda com horário de verão.
7. **Teto de 120 KB por PNG** (`figsize 12,8x6,6`, dpi 96). Medido nas 681 imagens da primeira
   corrida (sete versões, 2026-09-08): entre 47 e 99 KB, 44 MB no total.

## 10. Streams e consumidores

| Stream | Produtor | Consumidores | MAXLEN |
|---|---|---|---|
| `market.ticks` | market | scanner, execution | 100k |
| `market.candles.closed` | market | scanner, strategy | 50k |
| `market.derivatives` | market | scanner | 20k |
| `market.liquidations` | market | scanner | 20k |
| `market.universe.changed` | market (durável, via outbox) | scanner, strategy, api | 1k |
| `market.backfill.requested` | scanner | market (§1b; um grupo por shard, `market-worker.backfill.{exchange}.{i}of{N}`) | 5k |
| `market.candles.backfilled` | market (durável, via outbox) | nenhum ainda (§1b item 9, §10b; requisito registrado para o scanner, T2.5d/T2.5e) | 5k |
| `features.updated` | scanner | scanner (anomaly, opportunity) | 100k |
| `anomalies.detected` | scanner | scanner (opportunity), api (rt), analytics | 20k |
| `regime.changed` | scanner | strategy, execution, api | 1k |
| `opportunities.updated` | scanner | strategy, api (rt), analytics | 50k |
| `signals.emitted` | strategy | strategy (proposals), scanner (consenso), analytics (outcomes), api | 20k |
| `shadow.signals.emitted` | strategy (Shadow Lab, §6b) | api (`/lab/shadow`), analytics (futuro) — **nunca** o proposal builder | 20k |
| `proposals.decided` | strategy | execution, api (rt), analytics | 20k |
| `executions.completed` | execution | analytics, api (rt) | 20k |
| `positions.updated` | execution | api (rt), analytics | 50k |
| `risk.events` | strategy, execution, api | api (rt), analytics (alerts) | 10k |
| `kill_switch.changed` | execution (§8 item 6; automático e retomadas de usuário) | strategy, execution | 1k |
| `audit` | api, workers | (persistido pelo produtor; stream só para rt) | 10k |

## 10b. Outbox transacional (T2.9)

**Durável vs efêmero.** Um evento é **durável** quando alguém persiste um efeito a partir dele — se ele se perder, some trabalho que ninguém reconstrói do Redis. É **efêmero** quando descreve o presente e a próxima mensagem o substitui em segundos.

| Evento | Classe | Por quê |
|---|---|---|
| `market.candles.closed` | durável | vira linha em `candles`; o strategy-worker decide a partir dela |
| `market.candles.backfilled` | durável | notifica um lote de linhas já persistidas em `candles` pelo estrato histórico do recovery (T2.9c, §1b item 9); não é a fonte da verdade — quem consumir relê a cobertura em Postgres, o evento só evita esperar a releitura periódica |
| `market.derivatives` (OI) | durável | vira linha em `open_interest_history` |
| `market.derivatives` (funding **realizado**) | durável | vira linha em `funding_rates` |
| `market.liquidations` | durável | vira linha em `liquidations` |
| `market.universe.changed` | durável | o scanner faz warm-up dos mercados novos e encerra os que saíram; perder o evento deixa a coleta e o universo elegível em desacordo até o próximo *ciclo em que algo mudar* — que pode não vir. Enfileirado na mesma transação que grava `is_monitored`/`monitor_rank` (T2.9b) |
| `market.derivatives` (funding **estimado**, WS mark price) | efêmero | ninguém persiste; o próximo markPrice o substitui |
| `market.ticks`, `rt:*` | efêmero | visão coalescida do agora |

Todo evento de `market.derivatives` carrega `funding_kind` (`realized` / `estimated` / `null` quando é só OI) e `bucket_ts` (o slot de 5 min persistido, `null` no caminho efêmero), para que o consumidor saiba o que tem em mãos sem inferir pelos campos preenchidos.

**Como funciona.** `hunter_core.events.outbox`:

1. **Enfileirar** (`enqueue`) na **mesma transação** da linha de negócio. Acontece dentro dos `upsert_*` de `persist_rows.py` — o caminho único por onde passam tanto o ingest WS quanto o backfill REST do `recovery.py`, para que nenhum produtor novo esqueça. O `event_id` é determinístico (uuid5 da chave natural da linha), com `ON CONFLICT (event_id) DO NOTHING`: transação repetida enfileira uma vez, redelivery é no-op.
2. **Despachar** (`dispatch_pending`): `SELECT ... FOR UPDATE SKIP LOCKED` em ordem de `(created_at, id)` — servida pelo índice parcial homônimo desde a `0004` —, `XADD`, marca `dispatched_at`/`attempts`/`last_error`. O `SKIP LOCKED` é o que torna N shards seguros sem eleição de líder. Cada micro-lote é uma transação curta com orçamento de tempo: o `XADD` nunca fica pendurado segurando locks.
3. **Reconciliar** (`reconcile`) na partida: publica tudo com `dispatched_at IS NULL`, na ordem de criação, antes de qualquer evento novo. Com `since=`, republica também o que já foi despachado — a recuperação para um stream **perdido** (`XTRIM`/flush), que o predicado de pendência jamais alcançaria.

A linha guarda o **envelope inteiro** em `payload`, então o evento fica determinado no enfileiramento (identidade, `ts`, produtor, chave) e uma republicação é byte a byte a mesma mensagem. O payload de negócio fica um nível abaixo: `payload -> 'payload' ->> 'symbol'`.

**Garantia.** Entrega **pelo menos uma vez** — o Redis 7 não tem `XADD` idempotente, então duplicata física existe e não é escondida. O **efeito** é uma vez só: `event_id` determinístico + a guarda de `hunter_core.events.consume` (`hunter:processed:{group}`) + a chave única do próprio efeito em Postgres. O ACK só vem depois do efeito idempotente.

| Falha injetada | Resultado |
|---|---|
| morre antes do commit | nada persistido, nada publicado; a mensagem de origem é reentregue |
| morre entre o commit e o `XADD` | linha pendente; a próxima varredura (ou a reconciliação da partida) publica **uma vez** |
| morre depois do `XADD`, antes da marca | publicado duas vezes, mesmos bytes; o consumidor entrega uma |
| consumidor cai depois do efeito, antes do ACK | redelivery é no-op (efeito com chave única) |
| stream perdido (`XTRIM`/flush) | `reconcile(since=...)` reenche a partir do Postgres |

**Ordem de `created_at` é ordem de enfileiramento, *best-effort*, e nenhum consumidor pode depender dela.** Não é ordem de commit: `created_at` cai no `now()` do Postgres, que é o início da **transação**, então uma transação longa pode carimbar mais cedo um evento que só ficou visível depois de outro; as linhas só aparecem no commit, então uma varredura pode publicar B e só na passada seguinte publicar o A que ficou atrás dele; N shards varrem em paralelo sob `SKIP LOCKED` e a intercalação dos `XADD` é a que a rede der; e uma linha que falhou é pulada pelo resto da varredura e sai depois de linhas criadas mais tarde. A ordenação existe para **limitar a idade** do acúmulo — que é o que a prontidão mede —, não para dar sequência a ninguém. Quem precisa de ordem usa os carimbos de negócio dentro do payload (`open_time` da vela, `ts` do funding) e deduplica por `event_id`.

**Prontidão.** `/ready` fica vermelho quando a fila passa de `MAX_PENDING` (500) **ou** o evento mais antigo passa de `MAX_LAG_S` (30 s) — profundidade e idade são falhas diferentes. **Linhas inpublicáveis ficam fora do veredito**: uma linha cujo `payload` não é envelope nunca vai sair por mais saudável que o processo esteja, e contá-la como acúmulo prenderia o `/ready` em vermelho até alguém editar um JSONB à mão — vermelho que, no segundo dia, ninguém mais lê como incidente. Ela continua na tabela, continua logada (`outbox_row_unreadable`, `warning`, uma linha por varredura — não mais um traceback por segundo) e é contada em `hunter_outbox_unpublishable`. A classificação exige que o **despachante** tenha declarado o defeito como permanente, não só `attempts >= N`: uma queda de Redis falha a mesma linha em toda varredura, e a regra ingênua daria o acúmulo inteiro como defeituoso exatamente quando ele mais importa — o **check `outbox`** ficaria verde *porque* o Redis caiu. (Numa queda **total** o `/ready` fica vermelho de qualquer jeito, pelo check `redis`; o que se perderia é justamente a informação de quanto o despachante ficou para trás, que é o que se olha na volta.) Métricas: `hunter_outbox_pending`, `hunter_outbox_oldest_pending_seconds`, `hunter_outbox_unpublishable`, `hunter_outbox_dispatched_total`, `hunter_outbox_dispatch_failures_total`, `hunter_outbox_replayed_total`.

**Retenção.** Linhas despachadas há mais de 7 dias são apagadas por um DELETE diário em lotes (`prune_dispatched`); pendentes nunca. O prazo é o **teto** da janela de `reconcile(since=...)` — ver DATABASE.md §1.3. O job é do analytics-worker (M5).

**Latência.** O `drain_loop` não publica: ao committar, ele só acorda o despachante (`asyncio.Event`). Assim um Redis lento não atrasa o flush seguinte, e a vela fechada não espera o intervalo de polling.

## 11. Latências alvo (MVP)

| Trecho | Alvo |
|---|---|
| Exchange → hot state Redis | < 300 ms |
| Tick → features → opportunity atualizado | < 2 s |
| Candle fechado → sinal de agente | < 3 s |
| Sinal → decisão de risco | < 500 ms |
| Proposta aprovada → fill paper | < 1 s |
| Fill → browser (WS) | < 1 s |

Medidas por métricas de lag por stream; alvo violado por 5 min gera `system_event warning`.
