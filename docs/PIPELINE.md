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
5. **Persistência.** Candle 1m fechado → `candles` (`is_final=true`) e `market.candles.closed`. Snapshot por minuto → `market_snapshots`. Open interest via REST a cada 5 min → `open_interest_history`. Funding realizado → `funding_rates`. Liquidações → `liquidations`.
6. **Recovery.** Ao reconectar ou detectar gap (`open_time` esperado ausente), busca candles via REST, grava com `source=rest`, registra `ingestion_gaps`. Enquanto há gap aberto para um mercado, seu `data_quality` no hot state é `degraded`.

**Eventos publicados:** `market.ticks` (coalescido 250 ms; payload: preço, bid, ask, volume incremental, trades_count, book_imbalance top 5), `market.candles.closed`, `market.derivatives` (OI, funding, mark), `market.liquidations`, `market.universe.changed`.

**Falha:** WS caiu → reconnect com backoff (1 s → 60 s), REST recovery; Redis caiu → buffer em memória por 60 s, depois descarta ticks (candles são recuperáveis); Postgres lento → escrita em lote com fila em memória limitada, alerta se > 10 s de atraso.

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

**Onde:** `execution-worker`. **Gatilho:** `proposals.decided` (approved), `market.ticks` (gestão de posições, throttle 1 s), `kill_switch.changed`.

1. **Entrada.** `ExecutionAdapter(mode=portfolio.type).submit(OrderIntent)`. Paper v1: ordem a mercado contra o book top 25 do Redis; fill com walk do book (partial fills se o book não cobre), slippage real do book + `slippage_model` (bps adicionais configuráveis), fee taker (Binance 0,05 %, Bybit 0,055 %, configurável), latência simulada 50–300 ms (o preço usado é o book **após** a latência, o que penaliza mercados rápidos). Se `spread_pct > max_spread_pct` no momento, a ordem é rejeitada com `reason=spread_guard`.
2. Cria `orders` (`client_order_id = proposal_id`), `fills`, `positions`; ordens filhas `stop` e `target` viram registros `pending` gerenciados pelo worker (não existe exchange para segurá-las em paper).
3. **Gestão.** A cada 1 s: marca a mercado com mark price; atualiza `unrealized_pnl`, MFE, MAE; verifica stop (toque no mark), alvos parciais, invalidações do sinal e `expected_holding` × 3 como expiração; verifica limites de portfolio (perda diária, drawdown) → `risk_events` e, se o risk profile permitir `auto_close_on_emergency`, fecha.
4. **Saída.** Fecha posição → `trades` com `exit_reason`, snapshots de features de entrada e saída, `r_multiple`. Publica `executions.completed`, `positions.updated`.
5. **Equity.** A cada 1 min por portfolio com posição ou movimento: `portfolio_equity_snapshots` (1m). analytics-worker agrega em 1h/1d.
6. **Shadow.** `mode=shadow` grava ordens e fills com `simulated=true` e `execution_mode=shadow`, sem alterar cash. Idêntico ao paper em tudo o mais.
7. **Live.** `LiveExecutionAdapter` existe como interface e levanta `LiveTradingDisabled` enquanto `ENABLE_LIVE_TRADING=false` ou entitlement ausente. Sem implementação até a Fase 4.

**Falha:** worker reinicia → relê posições `open` do Postgres, reconstrói estado, retoma; propostas `approved` sem ordem após 30 s expiram (`status=expired`), nunca são executadas tarde; market data `degraded` para o mercado → não abre, mas continua gerenciando saídas com o último preço válido e gera `risk_event` se ficar sem preço por > 60 s.

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
| `market.universe.changed` | market | scanner, strategy, api | 1k |
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
