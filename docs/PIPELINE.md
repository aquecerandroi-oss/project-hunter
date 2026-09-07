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
7. **Prioridade: a coleta ao vivo nunca espera o bootstrap.** O recovery divide as lacunas `open` em dois estratos pela **idade da janela** (`gap_end` dentro dos 1 499 min da detecção = coleta ao vivo; mais antigo = histórico), ordena os dois por `gap_end DESC` (o minuto ausente mais novo primeiro) e só gasta com histórico o que sobrar do orçamento do ciclo (`MAX_GAPS_PER_CYCLE = 50`), com teto próprio (`MAX_HISTORY_GAPS_PER_CYCLE = 6`) e **prazo em relógio**: `min(30 s, o que falta do ciclo de 60 s menos 5 s de margem)`, aplicado à **unidade inteira** de recuperação (leituras, lock de linha e escrita, não só o fetch). Uma unidade cancelada pelo prazo faz rollback e **não gasta tentativa** do gap — ficar sem orçamento não é falha da lacuna.
8. **Criação de lacuna é serializada.** São **três** os escritores de `ingestion_gaps` com o mesmo protocolo (ler cobertura → inserir o que falta): a detecção periódica, este consumidor e `persist.report_losses` (a vela final que a fila descartou). A tabela não tem unicidade por intervalo, então os três tomam o mesmo `pg_advisory_xact_lock` por exchange **antes** de ler, e nenhuma chamada REST acontece com o lock na mão. `report_losses` usa a variante **não bloqueante** (`pg_try_advisory_xact_lock`): ela roda uma vez por iteração do `drain_loop` e esperar ali atrasa o flush das velas vivas — quem não pega o lock não escreve nada e tenta na iteração seguinte.
9. **A resposta é a que o pipeline já tem — mas o anúncio não é mais um por minuto para histórico (T2.9c).** No estrato **vivo** (item 7), cada minuto preenchido continua virando `market.candles.closed` pela outbox, na mesma transação que gravou a vela (`upsert_candles`), exatamente como um minuto ao vivo — nenhum consumidor existente muda de comportamento. No estrato **histórico**, a mesma transação enfileira **um** `market.candles.backfilled` agregado para o lote que aquela chamada realmente inseriu (`{exchange, symbol, timeframe, start, end, count, source="rest", reason="historical_recovery"}`), em vez de até 240 eventos por pedaço. Motivo: anunciar cada minuto de histórico é o gargalo de vazão do bootstrap (~1 dia de histórico por minuto de relógio, notes-T2.5.md §28) e ainda deixava minutos antigos na frente de velas ao vivo na ordem `(created_at, id)` do despachante (§10b). O `reason` é **descritivo, não causal**: `ingestion_gaps` não guarda quem pediu uma janela, e uma lacuna que a própria coleta ao vivo criou pode *envelhecer* para o estrato histórico sem que ninguém tenha publicado `market.backfill.requested` (REST ou o worker parados por mais que a janela de detecção) — por isso o motivo é sempre "a janela envelheceu", nunca "alguém pediu". Identidade do evento agregado: uuid5 sobre mercado + timeframe + `source` + o intervalo **realmente inserido** por aquela chamada (não os limites nominais do gap) — dois lotes commitados para a mesma chave `(mercado, timeframe)` nunca compartilham mínimo, porque o `ON CONFLICT DO NOTHING` do candle nunca deixa o mesmo minuto ser inserido duas vezes, então a identidade nunca colide entre passadas sucessivas sobre o mesmo gap parcial. **Ainda não implementado:** um consumidor de `market.candles.backfilled` no scanner-worker para invalidar/reagendar o bootstrap afetado em vez de esperar a releitura periódica de cobertura — registrado como requisito para a T2.5d/T2.5e (notes-T2.9.md T2.9c). Observabilidade: `market_backfill_requests_total{outcome}` (`accepted`, `partial`, `truncated`, `empty`, `refused`, `ignored`, `duplicate`, `malformed`, `failed`), `market_backfill_minutes_total` e o log `market_backfill_planned` com mercado, shard, intervalo pedido/efetivo, minutos, pedaços, adiados e sem partição.

**Limite conhecido:** `infra/scripts/create_partitions.py` provisiona o mês corrente e os seguintes, então um pedido de 7 dias no começo do mês nomeia minutos sem partição — eles são recusados com motivo em vez de abortar a transação, e o pedido volta a ser avaliado na republicação seguinte. Provisionar meses **para trás** é trabalho do job de partições. E o teto de 7 dias por pedido é política: a referência de 30 dias do regime precisa pedir o restante em outras janelas, o que ainda não está combinado.

## 1c. Câmbio USDTBRL — `fx_observations` (T3.11a)

**Onde:** `market-worker` (`hunter_market_worker/fx.py`). **Gatilho:** contínuo, independente do pipeline de mercado acima — não consome nem publica em nenhum stream de `market.*`.

A carteira paper (M3) opera em USDT mas a diretiva parte de R$100.000; a abertura (`hunter_core.portfolio.opening.open_paper_wallet`, T3.3b) e a curva de equity (`record_equity_point`) precisam de uma cotação `USDTBRL` sempre disponível e nunca fabricada, sob a mesma política de frescor (`FxPolicy`, `docs/DATABASE.md` §18.2): `available_at` ≤ 300 s e `observed_at` ≤ 600 s no instante do ato.

1. **Coleta.** A cada ~60 s (± 5 s de jitter), `GET /api/v3/ticker/24hr?symbol=USDTBRL` (peso 2) no bucket de peso do spot (`rl:binance:spot_request_weight`, token bucket Redis, pesos oficiais — `packages/exchange-adapters/hunter_exchanges/binance_spot/http.py`). `429`/`418` vira `RateLimited` e um `system_event` (`warning`), nunca um laço de retentativa silenciosa; falha de transporte após as retentativas internas do `SpotHttp` também não fabrica cotação — o ciclo seguinte tenta de novo, com backoff (5 s → 60 s, com jitter) entre tentativas mal sucedidas.
2. **Persistência.** `fx_observations` recebe `pair="USDTBRL"`, `source="binance.spot.ticker"` (a mesma constante que `PAPER_FX_POLICY.source`, T3.3 — uma fonte com outra grafia nunca abre carteira), `rate` = `lastPrice`, `observed_at` = `closeTime` (relógio da Binance), `available_at` = `utcnow()` no instante do INSERT, `raw` = corpo cru da resposta. Idempotente por `(pair, source, observed_at)` (`uq_fx_observations_observation`) via `ON CONFLICT DO NOTHING`: uma repetição do mesmo segundo fechado nunca duplica.
3. **Banda de plausibilidade.** Uma cotação fora de `[1, 100]` (a banda declarada em `FxPolicy`, revisão adversarial de `8a6a69f`, bloqueante 3) é **gravada do mesmo jeito** — o coletor registra o que a exchange imprimiu, sem editar — mas loga em `warning` e incrementa `hunter_fx_implausible_total`. Quem recusa uma cotação implausível é o **consumo** (`validate_fx_observation`), no instante do ato, nunca o coletor.
4. **Sharding: um coletor por venue, nunca N.** Só o shard 0 do market-worker cujo `exchange_code == "binance"` coleta câmbio (`MARKET_SHARD=i/N`, `hunter_core.settings.Settings.shard_index`); todo outro shard — e qualquer market-worker de outra exchange — idla essa tarefa para sempre. A fonte é fixa em Binance spot independentemente de qual perpétuo o processo ingere.
5. **Observabilidade.** `hunter_fx_observations_total{outcome}` (`ok`, `duplicate`, `malformed`, `rate_limited`, `network_error`, `error`), `hunter_fx_implausible_total`, `hunter_fx_age_seconds` (idade da última coleta bem-sucedida). A idade também aparece como *status detail* — nunca um readiness check — em `WorkerRuntime.status_details["fx"]` (`"ok"`/`"stale"`/`"unknown"`, limiar igual a `FxPolicy.availability_max_age_s`, 300 s): uma cotação velha pode impedir a abertura da carteira ou a valorização em BRL da curva, mas o resto da coleta de mercado continua, então `/ready` nunca fica vermelho por isso.

**Falha:** Redis fora do ar suspende o bucket de peso do spot como qualquer outro REST do worker (§1 item 7); Postgres fora do ar propaga da inserção (nunca silenciada) e o ciclo seguinte tenta de novo. Nunca há aporte, fabricação de cotação nem escrita sob o lock de `portfolio_risk_state` — a transação do coletor é só o INSERT em `fx_observations`, fora de qualquer unidade de trabalho da carteira.

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

## 3. Anomaly Engine

**Onde:** `scanner-worker`. **Gatilho:** `features.updated`.

- Cada `AnomalyDetector` compara valor atual com baseline (mediana + MAD sobre janela de 7 d, mesma hora do dia) e emite `Anomaly {type, severity 0–100, confidence, baseline, current_value, deviation (em MADs), metadata}`.
- MVP (v1): `VOLUME_SPIKE`, `PRICE_ACCELERATION`, `VOLATILITY_EXPANSION`, `ORDERBOOK_IMBALANCE`, `OPEN_INTEREST_SPIKE`, `FUNDING_ANOMALY`, `LIQUIDATION_CLUSTER`, `CROSS_EXCHANGE_DIVERGENCE` (mesmo símbolo Binance vs Bybit).
- Fase 2/3: `SOCIAL_SPIKE`, `WHALE_ACTIVITY`.
- Deduplicação: uma anomalia `active` por (market, type); atualiza severidade enquanto persistir; `resolved` quando o desvio cai abaixo do limiar por 5 min; `expired` após 4 h.
- Persiste em `anomalies` com `feature_snapshot`. Publica `anomalies.detected` (novas ou severidade +20).

## 4. Market Regime Engine

**Onde:** `scanner-worker`. **Gatilho:** a cada 1 min (fechamento de candle do BTC). **Escopo:** global.

- v0 (M2): entrada = BTC features (retornos 1h/4h/1d, volatilidade 1h vs 30 d, EMA ratio) + breadth (fração de mercados monitorados com retorno 4h > 0, com `relative_volume_1h` > 1,5).
- Regras determinísticas com histerese (não muda de regime sem 3 leituras consecutivas). Regimes v0: `BTC_BULL`, `BTC_BEAR`, `SIDEWAYS`, `HIGH_VOLATILITY`, `LOW_VOLATILITY` (volatilidade é uma dimensão separada; o estado é `{trend, volatility}` e o `regime` principal é o mais relevante para o Risk Engine).
- Persiste `market_regimes` (fecha o anterior com `end_time`). Publica `regime.changed` só em transição.
- v1 (Fase 2) adiciona `RISK_ON/RISK_OFF`, `ALT_EXPANSION`, `PANIC`, `LIQUIDITY_CONTRACTION` com breadth, funding agregado e liquidações agregadas.

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
- `agent_signals.supporting_features` é escrito uma vez e nunca reescrito, com `purpose = research_only`, coorte, `decision_at` e proveniência;
- todo evento sai em `shadow.signals.emitted` — **nunca** em `signals.emitted`. O proposal builder do §7 não vê sinais de pesquisa, e quando vier a vê-los deve recusar `purpose = research_only` (item 10 da decisão conjunta).

**Escritor único de outcomes.** No §6 quem abre e acompanha `signal_outcomes` é o `analytics-worker`. Enquanto o Shadow Lab existir, **quem escreve os outcomes de sombra é o `strategy-worker`, e só ele** (`hunter_strategy_worker/outcomes.py` + `tracking_repo.py`): a decisão, a entrada, a saída e a liberação do slot precisam acontecer sob o mesmo lock de `shadow_episodes`, e dois escritores produziriam dois acompanhamentos do mesmo episódio. A transferência para o `analytics-worker` é prevista e fica registrada aqui como pendência explícita: quando acontecer, `advance_tracking`, `settle` e a liberação do slot mudam de processo (não são duplicados), e o `strategy-worker` deixa de escrever `signal_outcomes` no mesmo commit em que o analytics passa a escrever.

**`tracking_hold`.** O `market-worker` mantém a coleta de um mercado que saiu do top N enquanto houver `shadow_episodes.open_outcome_signal_id IS NOT NULL` apontando para ele (`universe.with_tracking_holds`). O hold amplia a *coleta*, nunca a *elegibilidade*: `markets.is_monitored` continua sendo o conjunto elegível e é o que o `strategy-worker` lê. A blocklist explícita do operador prevalece sobre o hold; os acompanhamentos afetados terminam como `censored`.

**Backfill.** O `strategy-worker` nunca chama REST: quando falta uma vela, ele espera a recuperação do `market-worker` (dono único do REST) e, esgotado o prazo, encerra o acompanhamento como `censored` com o minuto que faltou — nunca como `expired`.

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
   transação.
7. **Live.** `LiveExecutionAdapter` levanta `LiveTradingDisabled` sempre, e o processo **recusa
   subir** com `ENABLE_LIVE_TRADING=true`: um worker de papel que subisse assim seria um que o
   operador acredita estar operando de verdade.

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
| `kill_switch.changed` | api | strategy, execution | 1k |
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
