# Modelo de banco — PROJECT HUNTER

PostgreSQL 16 (Neon em produção). Convenções e schema inicial. As migrações Alembic em `infra/migrations/` são a fonte de verdade; este documento descreve a intenção e as regras que as migrações precisam respeitar.

## 1. Convenções

| Regra | Valor |
|---|---|
| Chaves primárias | `id UUID` (UUID v7, gerado na aplicação) |
| Tempo | `TIMESTAMPTZ`, sempre UTC. Colunas `created_at`, `updated_at` em tabelas mutáveis |
| Valores financeiros | `NUMERIC(28,10)`. Nunca `FLOAT` para preço, quantidade, PnL, fee |
| Percentuais | `NUMERIC(9,6)` em fração (0.012 = 1,2%) |
| Scores | `NUMERIC(5,2)` 0–100; confidence `NUMERIC(5,4)` 0–1 |
| Enums | tipos `ENUM` do Postgres, um por conceito; adição de valor via migração |
| JSONB | apenas para dados de forma variável (decomposições, snapshots, metadata). Nunca para campos que serão filtrados com frequência |
| Soft delete | `deleted_at` só em `organizations`, `workspaces`, `portfolios`, `agents`, `alert_rules`. O resto é imutável ou hard delete por retenção |
| Nomes | snake_case, plural para tabelas, singular para enums (`kill_switch_state`) |
| Índices | todo FK indexado; índices compostos começando por `organization_id` em tabelas de tenant |

### 1.1 Duas classes de tabela

**Globais (sem `organization_id`).** Market data, features, anomalias, regime, oportunidades, sinais, outcomes, catálogo de estratégias, intelligence. Tenants têm acesso somente leitura via API.

**De tenant (com `organization_id NOT NULL`).** Tudo que envolve dinheiro, configuração ou pessoas. Todas têm Row Level Security.

### 1.2 Row Level Security

```sql
ALTER TABLE portfolios ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolios FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON portfolios
  USING      (organization_id = NULLIF(current_setting('app.current_org', true), '')::uuid)
  WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), '')::uuid);
```

- A aplicação abre transação e executa `SET LOCAL app.current_org = '<uuid>'` antes de qualquer query de tenant. Sem o setting, a política retorna zero linhas. O `NULLIF` é o que mantém isso verdadeiro na *segunda* transação de uma conexão do pooler, onde o GUC volta como string vazia em vez de ausente (§15.4).
- A API define também `app.current_user` (o `users.id` do chamador), de que dependem as políticas de `users` (§15.4).
- Workers de sistema usam um role `hunter_worker` com `BYPASSRLS` apenas nos processos que precisam varrer todas as organizações (strategy, execution, analytics). O `api` usa `hunter_app` sem bypass.
- `audit_logs`, `risk_events`, `kill_switch_transitions` e `system_events` são append-only: `hunter_app` tem `INSERT` e `SELECT`, nunca `UPDATE`/`DELETE` — e isso vale também para cada partição delas (§15.6).
- Partições não herdam privilégios nem políticas da tabela-pai: cada filha é criada com `REVOKE ALL` para os dois papéis e, quando a pai é de tenant, com RLS forçada e política própria (§1.3, §15.4).

### 1.3 Particionamento e retenção

| Tabela | Partição | Retenção padrão | Job |
|---|---|---|---|
| `candles` | LIST por `timeframe`, depois RANGE por `open_time`, mensal | 1m: 90 d · 5m: 1 a · 15m/1h/4h/1d: sem limite | `analytics-worker` diário |
| `market_snapshots` | mensal | 30 d | idem |
| `feature_snapshots` | mensal | 14 d (snapshots ligados a anomalias/oportunidades/trades vivem na própria linha dessas tabelas) | idem |
| `liquidations` | mensal | 30 d | idem |
| `opportunity_history` | mensal | 90 d | idem |
| `portfolio_equity_snapshots` | LIST por `resolution`, depois RANGE por `ts`, mensal | 1m: 30 d · demais: sem limite | idem |
| `audit_logs` | mensal | sem limite | — |
| `system_events` | mensal | 30 d | idem |

**Duas formas de partição.** Seis tabelas são RANGE mensal simples (`audit_logs_2026_09`). `candles` e `portfolio_equity_snapshots` são particionadas primeiro por LIST (`timeframe` / `resolution`) e cada nível desses por RANGE mensal, produzindo folhas como `candles_1m_2026_09`. O motivo é a própria coluna "Retenção": as retenções diferem por timeframe, e com uma única RANGE mensal expirar 1m aos 90 dias exigiria `DELETE` linha a linha dentro de partições que também guardam o 1h que se mantém para sempre — reescrevendo e inchando exatamente os dados que queremos preservar. Com o nível LIST, expirar é `DROP TABLE candles_1m_2026_05`.

O nível LIST é criado para **todos** os rótulos de `candle_timeframe`, não só os que a ingestão escreve hoje: uma linha sem partição é recusada, e uma escrita recusada é indisponibilidade, não aviso.

Partições são criadas com 3 meses de antecedência por `infra/scripts/create_partitions.py`, agendado no analytics-worker. Uma partição faltante gera `system_event` de severidade `critical`. A contrapartida é `infra/scripts/prune_partitions.py`, que faz `DETACH` + `DROP` de cada partição cuja **borda superior** já passou da janela de retenção — nunca de uma que ainda possa conter linha retida — e é idempotente porque lê as partições existentes em `pg_inherits` em vez de gerá-las pelo calendário.

Toda partição, intermediária ou folha, é criada já endurecida: `REVOKE ALL` para `hunter_app`/`hunter_worker` (todo acesso passa pela tabela-pai) e, quando a pai é tabela de tenant, RLS habilitada, forçada e com política **na própria filha**. O Postgres não herda nem privilégios nem políticas de uma pai particionada.

## 2. Identidade e tenancy

```
users
  id, external_auth_id (unique, Clerk), email (unique), display_name, avatar_url,
  onboarding_state JSONB, created_at, updated_at, last_seen_at

organizations
  id, slug (unique), name, plan plan_tier, kill_switch_state, kill_switch_reason,
  settings JSONB, created_by → users, created_at, updated_at, deleted_at

organization_members                        (PK organization_id, user_id)
  organization_id, user_id, role org_role, status member_status (invited|active|suspended),
  invited_by → users, joined_at, created_at

organization_invitations
  id, organization_id, email, role, token_hash, expires_at, accepted_at, created_by, created_at

workspaces
  id, organization_id, name, objective workspace_objective (explore|paper_trading|research|automated_trading),
  default_risk_profile_id → risk_profiles, settings JSONB (monitored_exchanges, base_currency, timezone),
  created_at, updated_at, deleted_at

api_keys                                    (acesso programático; schema no M0, uso em Fase 2)
  id, organization_id, created_by, name, key_prefix, key_hash, scopes TEXT[],
  last_used_at, expires_at, revoked_at, created_at

subscriptions
  id, organization_id (unique), plan plan_tier, status subscription_status,
  provider (null|stripe), provider_customer_id, provider_subscription_id,
  current_period_start, current_period_end, created_at, updated_at

plan_entitlements                           (seed; PK plan, key)
  plan plan_tier, key, value JSONB
  -- max_agents, max_exchanges, max_portfolios, market_history_days, backtesting,
  -- advanced_intelligence, live_trading, api_access, custom_agent_params

feature_flags                               (sistema)
  key (PK), enabled BOOLEAN, description, updated_by, updated_at

organization_feature_overrides              (PK organization_id, key)
  organization_id, key → feature_flags, enabled, reason, updated_by, updated_at
```

Enums: `org_role` = OWNER, ADMIN, TRADER, ANALYST, VIEWER. `plan_tier` = FREE, PRO, QUANT, ENTERPRISE. `kill_switch_state` = ACTIVE, WARNING, TRADING_DISABLED, EMERGENCY.

## 3. Referência de mercado (global)

```
exchanges
  id, code (unique: binance|bybit|okx|coinbase|hyperliquid|kraken), name, status exchange_status,
  capabilities JSONB (spot, perpetual, funding, open_interest, liquidations, ws_depth),
  created_at

assets
  id, symbol (unique: BTC), name, coingecko_id, metadata JSONB, created_at

markets
  id, exchange_id, symbol (BTCUSDT), market_type market_type (spot|perpetual),
  base_asset_id → assets, quote_asset_id → assets, status market_status,
  tick_size NUMERIC, step_size NUMERIC, min_notional NUMERIC, contract_size NUMERIC,
  max_leverage INT, is_monitored BOOLEAN, monitor_rank INT, volume_24h_usd NUMERIC,
  metadata JSONB, first_seen_at, last_seen_at, delisted_at
  UNIQUE (exchange_id, symbol, market_type)
  INDEX (is_monitored, monitor_rank)
```

## 4. Market data (global, particionado)

```
candles                                     PARTITION BY RANGE (open_time)
  market_id, timeframe candle_timeframe (1m|5m|15m|1h|4h|1d), open_time,
  open, high, low, close, volume, quote_volume, trade_count, taker_buy_volume,
  is_final BOOLEAN, source (ws|rest), received_at
  PK (market_id, timeframe, open_time)

market_snapshots                            PARTITION BY RANGE (ts)   -- 1 por minuto por mercado
  market_id, ts, price, bid, ask, spread_pct, volume_24h, quote_volume_24h,
  open_interest, open_interest_value, funding_rate, next_funding_time, mark_price, index_price,
  liq_long_notional_1h, liq_short_notional_1h
  PK (market_id, ts)

funding_rates
  market_id, funding_time, rate, mark_price
  PK (market_id, funding_time)

open_interest_history
  market_id, ts, open_interest, open_interest_value
  PK (market_id, ts)                        -- 5 min

liquidations                                PARTITION BY RANGE (ts)
  id, market_id, ts, side order_side, qty, price, notional, source
  INDEX (market_id, ts)

ingestion_gaps                              -- lacunas detectadas e seu status de recovery
  id, market_id, timeframe, gap_start, gap_end, detected_at, recovered_at, status, attempts
```

Duas convenções que o M1 (T1.3) fixou e que valem para todo consumidor destas tabelas:

- **`market_snapshots`: ausência de linha significa "não observado".** O market-worker pula o
  mercado quando não há nenhum hot state para ele naquele minuto, em vez de gravar uma linha com
  todos os campos nulos — como o insert é `ON CONFLICT (market_id, ts) DO NOTHING`, uma linha vazia
  seria permanente e a observação real que chegasse segundos depois nunca a substituiria. Campos
  individuais continuam podendo ser `NULL`: cada um é anulado quando o seu próprio timestamp em
  Redis está mais velho que `MARKET_STALE_AFTER_S` (nunca se republica um valor velho como fresco).
- **`liquidations.id` é UUID v5, não v7** — a exceção à convenção do §1.3. É um hash determinístico
  (namespace fixo) de exchange, símbolo, lado, preço, quantidade e do timestamp **truncado ao
  milissegundo**; é isso que torna a redelivery do WebSocket idempotente sob
  `ON CONFLICT (id, ts) DO NOTHING`. Por isso o `ts` gravado também é truncado ao milissegundo: a
  chave persistida tem de ser exatamente a chave de que o `id` foi derivado, senão dois microssegundos
  de diferença criam duas linhas para a mesma liquidação.

Trades brutos e order book **não** são persistidos no Postgres (ver `SPEC_REVIEW.md` B3).

## 5. Análise (global)

```
feature_definitions
  id, name, version INT, category feature_category, parameters JSONB, description,
  inputs TEXT[], created_at
  UNIQUE (name, version)

feature_snapshots                           PARTITION BY RANGE (ts)   -- 1 por minuto
  market_id, ts, feature_set_version, features JSONB
  PK (market_id, ts)

anomalies
  id, market_id, type anomaly_type, severity NUMERIC(5,2), confidence NUMERIC(5,4),
  detected_at, resolved_at, status anomaly_status (active|resolved|expired),
  baseline NUMERIC, current_value NUMERIC, deviation NUMERIC, unit,
  feature_snapshot JSONB, metadata JSONB, detector_version
  INDEX (market_id, detected_at DESC), INDEX (status, detected_at DESC), INDEX (type, detected_at DESC)

market_regimes
  id, scope regime_scope (global|btc), regime market_regime, confidence,
  start_time, end_time (null = vigente), supporting_features JSONB, classifier_version
  INDEX (scope, start_time DESC); índice parcial único em (scope) WHERE end_time IS NULL

opportunity_weights
  id, version (unique), weights JSONB, is_active BOOLEAN, description, created_by, created_at

opportunities
  id, market_id, direction trade_direction (long|short|neutral),
  score, confidence, peak_score, status opportunity_status,
  decomposition JSONB,          -- {component: {raw, normalized, weight, contribution}}
  weights_version, regime_id → market_regimes, anomaly_ids UUID[],
  supporting_signal_ids UUID[], feature_snapshot JSONB,
  first_seen_at, last_updated_at, expired_at
  INDEX (status, score DESC), INDEX (market_id, first_seen_at DESC)
  -- índice parcial único (market_id) WHERE status IN ('watching','hot','entry_candidate')

opportunity_history                         PARTITION BY RANGE (ts)
  opportunity_id, ts, score, confidence, status, decomposition JSONB
  PK (opportunity_id, ts)
```

`opportunity_status` = NORMAL, WATCHING, ANOMALY, HOT, ENTRY_CANDIDATE, EXPIRED. Os status `IN_POSITION` e `BLOCKED_BY_RISK` do Radar são **derivados por organização** na leitura (junção com posições e propostas da org), porque uma oportunidade global pode estar em posição numa org e bloqueada em outra.

## 6. Estratégias e agentes

```
strategies                                  (catálogo global)
  id, key (unique: momentum|breakout|volume_anomaly|order_flow|mean_reversion|derivatives|narrative|ensemble),
  name, description, category, created_at

strategy_versions
  id, strategy_id, version (v1, v2), status strategy_version_status (draft|active|deprecated),
  parameters_schema JSONB, default_parameters JSONB, code_ref (módulo Python),
  changelog, created_at, activated_at, deprecated_at
  UNIQUE (strategy_id, version)

agent_signals                               (global; gerados uma vez por strategy_version)
  id, strategy_version_id, market_id, params_hash, direction, confidence,
  entry_zone JSONB {low, high}, stop NUMERIC, targets JSONB [{price, pct_of_position}],
  invalidations JSONB, expected_holding_s INT, reason TEXT, supporting_features JSONB,
  opportunity_id, regime_id, emitted_at, expires_at, status signal_status (active|expired|invalidated)
  INDEX (market_id, emitted_at DESC), INDEX (strategy_version_id, emitted_at DESC), INDEX (status, expires_at)

signal_outcomes                             (shadow de sistema; 1:1 com agent_signals)
  signal_id (PK), virtual_entry, virtual_stop, virtual_targets JSONB, entry_ts,
  mfe NUMERIC, mae NUMERIC, mfe_ts, mae_ts, result outcome_result (target|stop|expired|invalidated|open),
  exit_price, exit_ts, r_multiple NUMERIC, tracked_until, updated_at

agents                                      (tenant; instância de estratégia num portfolio)
  id, organization_id, workspace_id, portfolio_id, name, strategy_version_id,
  parameters JSONB (null = defaults), uses_custom_params BOOLEAN,
  status agent_status (enabled|paused|disabled), capital_allocation_pct, max_open_positions INT,
  allowed_directions trade_direction[], market_filter JSONB, min_opportunity_score, min_confidence,
  created_by, created_at, updated_at, deleted_at
  INDEX (organization_id, portfolio_id, status)

agent_stats                                 (tenant; materializado pelo analytics-worker)
  agent_id, organization_id, window stats_window (all|7d|30d|90d), computed_at,
  trades INT, wins INT, losses INT, win_rate, profit_factor, expectancy, avg_win, avg_loss,
  sharpe, sortino, max_drawdown_pct, pnl, pnl_pct, by_regime JSONB, by_market JSONB,
  by_hour JSONB, by_volatility JSONB
  PK (agent_id, window)
```

## 7. Portfolios, risco e execução (tenant)

```
risk_profiles
  id, organization_id (null = preset de sistema), name, preset risk_preset (conservative|balanced|aggressive|custom),
  limits JSONB, created_by, created_at, updated_at
  -- limits: max_position_pct, max_total_exposure_pct, max_daily_loss_pct, max_drawdown_pct,
  --         max_concurrent_positions, max_asset_exposure_pct, max_exchange_exposure_pct,
  --         min_liquidity_usd_24h, max_spread_pct, max_slippage_pct, max_leverage,
  --         max_correlated_positions, auto_close_on_emergency

portfolios
  id, organization_id, workspace_id, name, type portfolio_type (paper|shadow|live),
  base_currency (USDT), initial_capital, risk_profile_id, exchange_connection_id (null),
  execution_config JSONB (fee_model, slippage_model, latency_model),
  status portfolio_status (active|paused|archived), kill_switch_state, kill_switch_reason,
  is_arena BOOLEAN DEFAULT false, created_by, created_at, updated_at, deleted_at
  INDEX (organization_id, type, status)

portfolio_equity_snapshots                  PARTITION BY LIST (resolution) -> RANGE (ts)
  organization_id, portfolio_id, ts, resolution (1m|1h|1d), cash, equity, exposure_notional,
  exposure_pct, unrealized_pnl, realized_pnl_cum, peak_equity, drawdown_pct, open_positions INT
  PK (portfolio_id, resolution, ts)
  FOREIGN KEY (portfolio_id, organization_id) REFERENCES portfolios (id, organization_id)

trade_proposals                             (o "PROPOSAL" do pipeline)
  id, organization_id, portfolio_id, agent_id, signal_id, market_id, direction,
  requested_risk_pct, status proposal_status (pending|approved|rejected|expired|executed|failed),
  risk_decision JSONB,          -- {approved, sized_qty, sized_notional, risk_pct, checks:[{name, passed, value, limit, message}]}
  rejection_reason, kill_switch_snapshot JSONB, regime_id, opportunity_score, confidence,
  idempotency_key, created_at, decided_at, expires_at
  UNIQUE (organization_id, idempotency_key)   -- por tenant, nunca global
  INDEX (organization_id, portfolio_id, created_at DESC), INDEX (status, expires_at)

orders
  id, organization_id, portfolio_id, proposal_id, agent_id, market_id, position_id (null até abrir),
  client_order_id (unique per portfolio), exchange_order_id,
  side order_side (buy|sell), type order_type (market|limit|stop_market|stop_limit|take_profit),
  purpose order_purpose (entry|stop|target|exit|reduce), qty, price, stop_price,
  time_in_force, reduce_only BOOLEAN, execution_mode execution_mode (paper|shadow|live),
  status order_status (pending|submitted|partially_filled|filled|cancelled|rejected|expired),
  filled_qty, avg_fill_price, fees_paid, submitted_at, completed_at, reason, metadata JSONB, created_at
  UNIQUE (portfolio_id, client_order_id)
  INDEX (organization_id, portfolio_id, created_at DESC), INDEX (status)

fills
  id, order_id, organization_id, portfolio_id, ts, qty, price, fee, fee_asset,
  liquidity (maker|taker), slippage_bps NUMERIC, simulated BOOLEAN, book_snapshot JSONB, metadata JSONB
  INDEX (order_id), INDEX (organization_id, portfolio_id, ts DESC)

positions
  id, organization_id, portfolio_id, agent_id, market_id, direction,
  qty, avg_entry_price, mark_price, notional, leverage,
  unrealized_pnl, realized_pnl, fees_paid, stop_price, targets JSONB, trailing JSONB,
  mfe NUMERIC, mae NUMERIC, status position_status (open|closing|closed),
  opened_at, closed_at, updated_at, metadata JSONB
  INDEX (organization_id, portfolio_id, status), INDEX (market_id, status)

trades                                      (uma linha por posição fechada; a "verdade" para analytics)
  id, organization_id, portfolio_id, agent_id, strategy_version_id, market_id, position_id (unique),
  signal_id, proposal_id, opportunity_id, execution_mode, direction,
  entry_price, exit_price, qty, notional, fees, slippage_cost, pnl, pnl_pct, r_multiple,
  duration_s INT, mfe, mae, regime_id, opportunity_score, confidence,
  entry_reason TEXT, exit_reason exit_reason (target|stop|invalidation|manual|kill_switch|expired|risk_event),
  entry_snapshot JSONB, exit_snapshot JSONB, opened_at, closed_at
  INDEX (organization_id, portfolio_id, closed_at DESC), INDEX (agent_id, closed_at DESC), INDEX (market_id, closed_at DESC)

risk_events
  id, organization_id, portfolio_id (null = org), type risk_event_type, severity event_severity,
  message, data JSONB, triggered_by (system|user_id), acknowledged_by, acknowledged_at, created_at
  INDEX (organization_id, created_at DESC)

kill_switch_transitions
  id, organization_id (null ⟺ scope = system), scope ks_scope (system|organization|portfolio),
  scope_id (null para system), from_state, to_state, reason, actor_type (user|system),
  actor_id, created_at
  CHECK ((scope = 'system') = (organization_id IS NULL))
```

## 8. Exchanges conectadas (tenant; pós-MVP, schema no M0)

```
exchange_connections
  id, organization_id, exchange_id, label, api_key_encrypted BYTEA, api_secret_encrypted BYTEA,
  encryption_key_version INT, key_fingerprint (últimos 4 chars), permissions JSONB {read, trade, withdraw},
  withdraw_enabled BOOLEAN NOT NULL DEFAULT false CHECK (withdraw_enabled = false),
  status connection_status (pending|valid|invalid|revoked), last_validated_at, validation_error,
  created_by, created_at, updated_at
  UNIQUE (organization_id, exchange_id, label)
```

O `CHECK (withdraw_enabled = false)` é deliberado: uma chave com permissão de saque nunca é persistida como válida.

## 9. Backtests (tenant; M6)

```
backtests
  id, organization_id, workspace_id, created_by, name, strategy_version_id, parameters JSONB,
  market_ids UUID[], timeframe, start_at, end_at, initial_capital, risk_profile_id,
  fee_model JSONB, slippage_model JSONB,
  validation JSONB {train_pct, validation_pct, oos_pct, walk_forward_windows},
  status backtest_status (queued|running|completed|failed|cancelled), progress_pct,
  started_at, finished_at, error, created_at

backtest_results
  id, backtest_id, organization_id, segment (full|train|validation|oos|wf_1..n), metrics JSONB,
  equity_curve JSONB, warnings JSONB [{code: overfitting|leakage|lookahead, detail}], trades_count INT
  UNIQUE (backtest_id, segment)

backtest_trades
  id, backtest_id, organization_id, segment, market_id, direction, entry_ts, exit_ts, entry_price, exit_price,
  qty, pnl, r_multiple, mfe, mae, exit_reason
  INDEX (backtest_id, segment)
```

## 10. Intelligence (global; Fase 2/3, schema previsto)

```
intelligence_sources
  id, key (unique: news|reddit|x|google_trends|onchain|whales|listings|unlocks|announcements),
  kind, status, config JSONB, last_polled_at

intelligence_events
  id, source_id, external_id, dedupe_hash (unique), occurred_at, ingested_at,
  title, excerpt, url, asset_ids UUID[], classification JSONB {sentiment, narrative, importance, model, version},
  raw JSONB
  INDEX (occurred_at DESC), GIN (asset_ids)
```

Conteúdo externo é **dado**. Nunca é interpolado em prompts como instrução.

## 11. Alertas (tenant)

```
alert_rules
  id, organization_id, workspace_id, created_by, name, condition JSONB, channels JSONB,
  enabled, cooldown_s INT, last_triggered_at, created_at, updated_at, deleted_at

notifications
  id, organization_id, user_id (null = todos da org), rule_id, type, title, body, data JSONB,
  channel (in_app|email|telegram|discord|push), status (pending|sent|failed|read),
  sent_at, read_at, created_at
  INDEX (organization_id, user_id, status, created_at DESC)
```

## 12. Sistema

```
audit_logs                                  PARTITION BY RANGE (created_at); append-only
  id, organization_id (null = sistema), actor_type (user|system|agent|api_key), actor_id,
  action (ex: risk_profile.updated, agent.enabled, kill_switch.changed, order.created),
  entity_type, entity_id, before JSONB, after JSONB, ip INET, user_agent, request_id, metadata JSONB, created_at
  INDEX (organization_id, created_at DESC), INDEX (entity_type, entity_id)

system_events                               PARTITION BY RANGE (created_at)
  id, level event_severity (debug|info|warning|error|critical), component, event, message, data JSONB, created_at

worker_heartbeats
  worker_role, instance_id, version, started_at, last_heartbeat_at, last_success_at,
  error_count INT, status (healthy|degraded|stale|down), metadata JSONB
  PK (worker_role, instance_id)

processed_events                            -- idempotência durável para consumidores críticos
  consumer, event_id, claimed_at, completed_at
  PK (consumer, event_id)                   -- claim em duas fases: a linha é inserida antes do
                                            -- efeito (completed_at NULL) e completada depois; só
                                            -- linha completa conta como duplicata, e um claim
                                            -- inacabado mais velho que a janela de staleness pode
                                            -- ser retomado pela redelivery.
                                            -- limpeza de linhas completas > 7 d
                                            -- (infra/scripts/prune_processed_events.py)
```

## 13. Relação com a lista da especificação (§42)

| Tabela sugerida | Destino |
|---|---|
| `features` | `feature_definitions` |
| `feature_values` | `feature_snapshots` (linha larga JSONB por minuto) |
| `agent_versions` | removida; `strategy_versions` + audit |
| `trade_snapshots` | `trades.entry_snapshot` / `exit_snapshot` |
| `paper_executions`, `shadow_executions` | `orders` + `fills` com `execution_mode` e `fills.simulated`; shadow de sistema em `signal_outcomes` |
| `alerts` | `alert_rules` + `notifications` |
| `portfolio_balances` | `portfolio_equity_snapshots` |
| novas | `trade_proposals`, `signal_outcomes`, `kill_switch_transitions`, `ingestion_gaps`, `processed_events`, `plan_entitlements`, `organization_feature_overrides`, `agent_stats`, `opportunity_weights`, `opportunity_history` |

## 14. Diagrama de relações (núcleo)

```
users ──< organization_members >── organizations ──< workspaces ──< portfolios ──< agents
                                        │                              │            │
                                        ├──< risk_profiles             │            └── strategy_versions ── strategies
                                        ├──< exchange_connections      ├──< trade_proposals ── agent_signals ── opportunities ── markets ── exchanges
                                        ├──< audit_logs                ├──< orders ──< fills
                                        └──< risk_events               ├──< positions ── trades
                                                                       └──< portfolio_equity_snapshots
markets ──< candles / market_snapshots / feature_snapshots / anomalies / liquidations
agent_signals ── signal_outcomes
market_regimes ◄── opportunities, trade_proposals, trades
```

## 15. Notas de implementação do schema inicial (M0 · T04)

Decisões tomadas ao escrever `packages/core/hunter_core/db/models/**` e
`infra/migrations/versions/0001_initial_schema.py` que **acrescentam** ou
**precisam** o que está acima. Nada aqui contradiz as seções 1–14.

**`0001_initial_schema` é emendada no lugar, não sucedida por uma `0002`.** As
correções do cross-review de `154ecea` (grants por tabela, RLS nas partições e
em `organizations`/`users`, `organization_id` em mais cinco tabelas, FKs
compostas, re-particionamento de `candles` e `portfolio_equity_snapshots`)
mudam a *forma* do schema inicial, não o evoluem. O schema nunca foi aplicado em
lugar nenhum além de CI e testcontainers: não há banco no mundo em `0001`, então
não há nada a migrar. Uma `0002` que reparticionasse `candles` teria de mover
dados que não existem e deixaria o schema inicial permanentemente errado para
quem o lesse — a revisão precisa descrever o schema, e o schema correto é este.
A partir do primeiro deploy real, essa liberdade acaba e toda mudança vira
revisão nova. Vale igualmente para a re-revisão de `c28c1bc` (políticas por
comando em `organizations`/`users`, classe de grant sem `DELETE`, verificação de
existência dos papéis): mesma revisão, emendada de novo, pelo mesmo motivo.

### 15.1 Enums

- Novo tipo `liquidity_role` (`maker|taker`) para `fills.liquidity`: a seção 7
  dá os valores em linha mas não nomeia o tipo, e §1 exige um `ENUM` por
  conceito fechado.
- Enums que a doc tipa mas não enumera foram fixados assim:
  `subscription_status` = `trialing|active|past_due|canceled`;
  `exchange_status` = `active|inactive`;
  `market_status` = `active|suspended|delisted`;
  `feature_category` = `price|volume|volatility|microstructure|momentum|derivatives|cross`
  (grupos de `PIPELINE.md` §2).
- `portfolio_equity_snapshots.resolution` reusa `candle_timeframe`;
  `intelligence_sources.kind` usa `intelligence_source_kind`.
- `backtest_warning_code` é criado como tipo, mas hoje só é espelhado dentro de
  `backtest_results.warnings` (JSONB); existe para o espelhamento 1:1 com
  Pydantic e TS.
- Todos os tipos são criados **explicitamente** pela migração
  (`infra/migrations/ddl/enums.py`); os modelos declaram `create_type=False`.

### 15.2 Chaves primárias de tabelas particionadas

O Postgres exige que a chave de partição faça parte de qualquer PK. Onde a doc
mostrava só `id`, a PK passa a incluir a coluna de partição, **e a coluna de
partição vem primeiro** (é a ordem que os modelos produzem e a que está no banco):
`liquidations (ts, id)`, `audit_logs (created_at, id)`,
`system_events (created_at, id)`. A ordem importa: o índice da PK serve
`WHERE created_at BETWEEN ...` como coluna líder, que é a varredura real dessas
tabelas; `(id, created_at)` não serviria.

### 15.3 Índices

- Índices compostos são declarados **ascendentes** mesmo onde a doc escreve
  `DESC`: o Postgres varre um btree para trás com o mesmo custo, e um índice
  ascendente compara sem ruído no `alembic check`.
- O índice parcial único de `opportunities` usa os rótulos em maiúsculas
  (`'WATCHING','HOT','ENTRY_CANDIDATE'`), que são os valores reais de
  `opportunity_status` (§5 os escreve em minúsculas por descuido).
- Novo índice parcial único `uq_risk_profiles_system_preset` em `(preset)`
  `WHERE organization_id IS NULL`: garante um preset de sistema por nome e dá a
  `infra/scripts/seed.py` uma chave natural para o upsert.
- Novo índice parcial único `uq_opportunity_weights_active` em `(is_active)`
  `WHERE is_active`: no máximo uma versão de pesos ativa. Sem ele o scorer teria
  de escolher arbitrariamente entre duas linhas de `WHERE is_active`.
- FKs "quentes" indexadas explicitamente (`agents.portfolio_id`,
  `positions.portfolio_id`, `trade_proposals.portfolio_id`,
  `trades.portfolio_id`, `fills.portfolio_id`, `notifications.user_id`): os
  índices compostos que começam por `organization_id` não as cobrem, e sem elas
  um `DELETE` em `portfolios` faz seq scan em cada tabela filha.
- `UNIQUE (organization_id, idempotency_key)` em `trade_proposals`, no lugar de
  um único global. A chave é cunhada pelo cliente de um tenant; global, a
  retentativa do tenant A colidiria com — e seria engolida como duplicata de —
  a proposta do tenant B.

### 15.4 RLS

**Correções do cross-review de `154ecea`.** A revisão provou, com SQL, quatro
buracos no desenho original; todos estão fechados aqui e cada um tem teste de
integração que falhava antes da correção.

- `agent_stats`, `backtest_results`, `backtest_trades` e
  `portfolio_equity_snapshots` **passaram a ter `organization_id NOT NULL`** e
  `tenant_isolation`. Deixar o isolamento delas para um join com a tabela pai no
  repositório punha a curva de equity e as estatísticas de agente de um tenant a
  um `JOIN` esquecido de distância de qualquer outro. `kill_switch_transitions`
  ganhou `organization_id` **anulável** (`NULL` exatamente quando
  `scope = 'system'`, garantido por CHECK), `tenant_isolation` e
  `system_scope_readable` (`FOR SELECT USING (scope = 'system')`): o kill switch
  da plataforma afeta todo mundo, então todo mundo pode ver que ele se moveu.
- **Partições de uma pai de tenant** (hoje `audit_logs_*` e
  `portfolio_equity_snapshots_*`) recebem RLS habilitada, forçada e **política
  própria**, no momento da criação, tanto na migração quanto em
  `create_partitions.py`. O Postgres não consulta as políticas da pai para uma
  consulta que nomeia a filha; sem isso, `SELECT ... FROM audit_logs_2026_09`
  devolvia as linhas de todos os tenants.
- `organizations` e `users` também têm RLS, embora não tenham `organization_id`:
  `organizations` é filtrada pelo próprio `id`; `users` por co-participação
  (`EXISTS` em `organization_members` na organização corrente) mais uma política
  que deixa a pessoa ler a própria linha. Antes, qualquer tenant lia e editava a
  linha de qualquer outro e enumerava seus membros.

**Correções da re-revisão de `c28c1bc`: uma política por comando.** As duas
políticas acima nasceram `FOR ALL`, e `FOR ALL` sobre "toda linha que o chamador
enxerga" transforma uma listagem em superfície de escrita. Ambas foram abertas em
políticas por comando, e o comando que falta em cada uma é o ponto:

- `user_visible_to_co_members` passou a ser **`FOR SELECT`**. Como `FOR ALL`, ela
  deixava qualquer membro de uma organização rodar
  `UPDATE users SET external_auth_id = '<o Clerk id dele>' WHERE id = <colega>` —
  tomada de conta — ou apagar a linha do colega. Uma lista de membros é leitura;
  a única porta de escrita em `users` para a API é `user_reads_own_row`, chaveada
  em `app.current_user`, isto é, a pessoa editando a si mesma.
- `organizations` deixou de ter `tenant_isolation FOR ALL` e passou a ter três
  políticas: `tenant_isolation` (`FOR SELECT`), `organization_updatable`
  (`FOR UPDATE`, `USING`/`WITH CHECK` em `id = app.current_org`, para renomear,
  trocar plano e mover o kill switch) e `organization_bootstrap`
  (`FOR INSERT WITH CHECK (id = app.current_org)`, porque o sign-up precisa criar
  a linha). **Não há política de `DELETE`** — para ninguém: com
  `FORCE ROW LEVEL SECURITY` isso fecha inclusive para o dono da tabela. Um
  `DELETE` ali cascateia por `ON DELETE CASCADE` em toda tabela de tenant e
  apagaria portfolios, ordens, posições e fills num único comando.

**Remover uma organização (ou uma pessoa) é operação de `hunter_worker` /
operador.** O papel da API perdeu `DELETE` em `organizations` e `users` também na
camada de grants (§15.6), e `hunter_worker` — que já tem `BYPASSRLS`, portanto
atravessa a ausência de política — é quem recebeu esse `DELETE`, e nada mais
nessas duas tabelas. Encerramento de conta é decisão operacional com política de
retenção junto, não algo que um request handler (ou uma injeção dentro de um)
deva alcançar. `audit_logs` continua sem FK para `organizations` de propósito, de
modo que a trilha sobrevive à remoção do tenant.
- `audit_logs` ganhou `audit_system_scope`
  (`FOR INSERT WITH CHECK (organization_id IS NULL)`). O `WITH CHECK` de
  `tenant_isolation` recusa `organization_id NULL`, então a trilha de auditoria
  perdia em silêncio exatamente os eventos sem organização em contexto (sign-up,
  webhook, cron) — que são os que ninguém está olhando.

**Dois settings, não um.** As políticas leem
`NULLIF(current_setting('app.current_org', true), '')::uuid` e
`NULLIF(current_setting('app.current_user', true), '')::uuid`. O `NULLIF` é
obrigatório atrás do pooler: `current_setting(nome, true)` só devolve `NULL`
enquanto a sessão *nunca* viu o setting; depois de um `SET LOCAL`, o GUC
sobrevive ao commit como **string vazia**, e `''::uuid` levanta erro em vez de
devolver zero linhas. `app.current_user` é o `users.id` do chamador (nunca o id
do Clerk); `hunter_core.db.session.tenant_session` continua definindo só
`app.current_org` — quem define os dois é a API, no T06.

**Consequência operacional do `FORCE` em `organizations` e `users`.** Criar uma
organização ou um usuário exige que o setting correspondente já aponte para o id
que está sendo inserido (a API gera o UUID v7 antes de inserir), ou que a
operação corra como `hunter_worker`, que tem `BYPASSRLS`. Vale para onboarding e
para o webhook do Clerk.

- Além de `tenant_isolation`, `risk_profiles` recebe `system_presets_readable`
  (`FOR SELECT USING (organization_id IS NULL)`): sem ela `hunter_app` não
  enxergaria os presets de sistema que o onboarding precisa copiar. É somente
  leitura — o `WITH CHECK` de `tenant_isolation` continua estritamente por
  organização, então o app nunca cria nem edita um preset de sistema.
- E `system_presets_manageable`, concedida **apenas ao papel que migra**
  (`TO CURRENT_USER`, `USING`/`WITH CHECK (organization_id IS NULL)`). Com
  `FORCE ROW LEVEL SECURITY` o dono da tabela também é filtrado, então sob um
  dono `NOSUPERUSER` — que é o que um Postgres gerenciado entrega —
  `infra/scripts/seed.py` não gravava preset nenhum e mesmo assim relatava três
  linhas semeadas.
- `hunter_worker` recebe `BYPASSRLS` (§1.2) por um `ALTER ROLE` dentro de um
  bloco `DO` que tolera falta de privilégio: em Postgres gerenciado o papel que
  migra pode não poder concedê-lo, e nesse caso a migração emite um `NOTICE`
  pedindo a concessão manual. **Esse é o único passo que degrada para `NOTICE`.**
  A criação dos dois papéis também tolera `insufficient_privilege`, mas logo
  depois `create_roles()` consulta `pg_roles` e, se algum deles de fato não
  existir, levanta `RAISE EXCEPTION` nomeando o passo manual
  (`CREATE ROLE hunter_app NOLOGIN; CREATE ROLE hunter_worker NOLOGIN BYPASSRLS;`).
  Tolerar em silêncio era pior que falhar: todo `GRANT` e toda política daqui
  para a frente nomeiam esses papéis, então ou a migração morria cem comandos
  adiante com `role "hunter_app" does not exist`, ou alguém lia o `NOTICE` como
  aviso e subia o schema sem papel de aplicação nenhum — com a API conectando
  como dono e passando por cima de todos os grants.
- Toda tabela de tenant ganhou `FOREIGN KEY (organization_id) REFERENCES
  organizations(id) ON DELETE CASCADE`, que o `TenantMixin` sozinho não declara —
  **com uma exceção deliberada: `audit_logs`.** A trilha de auditoria é
  append-only e nunca é podada (§1.3); um `CASCADE` apagaria justamente o
  registro de que a organização existiu e foi removida, e um `RESTRICT` impediria
  a remoção. A coluna fica sem FK de propósito, e a política de RLS é o que
  garante que ninguém lê a de outro tenant.
- **FKs compostas.** `portfolios`, `agents` e `backtests` carregam
  `UNIQUE (id, organization_id)`, e `orders`, `fills`, `positions`, `trades`,
  `trade_proposals`, `portfolio_equity_snapshots`, `agent_stats`,
  `backtest_results` e `backtest_trades` referenciam o **par**
  `(<pai>_id, organization_id)`. Com FK de uma coluna só, uma linha podia
  declarar-se da organização A apontando para o portfolio da B: a FK ficava
  satisfeita e a RLS só olha o `organization_id` da própria linha. Onde a coluna
  filha é anulável o `ON DELETE` nomeia a coluna
  (`SET NULL (agent_id)`, Postgres 15+), porque um `SET NULL` simples também
  anularia `organization_id`, que é `NOT NULL`.

### 15.5 Partições

`0001_initial_schema` cria 2026-09 a 2026-12 com limites fixos — uma migração
reaplicada no futuro precisa produzir o mesmo schema, então não pode depender do
relógio. Tudo depois disso é de `infra/scripts/create_partitions.py`
(`--months-ahead`, padrão 3) e `infra/scripts/prune_partitions.py` (`--dry-run`).
As listas de tabelas particionadas e de tabelas com RLS estão **congeladas** em
`infra/migrations/ddl/`, e testes de integração garantem que continuam iguais às
derivadas dos modelos.

`candles` e `portfolio_equity_snapshots` são LIST-depois-RANGE (§1.3); o nível
intermediário (`candles_1m`) é ele próprio uma partição e é ocultado do
autogenerate por `env.py`, junto com as folhas mensais, senão `alembic check`
acusaria cada um como drift.

### 15.6 Grants

Os `GRANT` são **nomeados tabela a tabela**, nunca
`GRANT ... ON ALL TABLES IN SCHEMA public`, e os papéis são criados *antes* das
partições. As duas coisas vêm do cross-review:

- `ON ALL TABLES` é avaliado uma vez, sobre as tabelas que existem naquele
  instante. As partições já existiam, então cada `audit_logs_YYYY_MM` recebeu
  `UPDATE`/`DELETE`, e o `REVOKE` na tabela-pai não as alcançava — Postgres
  confere uma consulta que nomeia a filha contra os privilégios da filha.
  `DELETE FROM audit_logs_2026_09` era permitido para o papel da API.
- e ele dava DML completo em tudo: `hunter_app` podia reescrever o catálogo de
  estratégias, os `plan_entitlements` e os `feature_flags`.

Agora há **quatro** classes, congeladas em `infra/migrations/ddl/tables.py` e que
formam uma partição exata do schema: `APP_WRITE_TABLES` (DML completo, todas
atrás de RLS), `APP_NO_DELETE_TABLES` (`SELECT`/`INSERT`/`UPDATE` e nunca
`DELETE` — só `organizations` e `users`; ver §15.4),
`APP_READ_ONLY_TABLES` (só `SELECT`: catálogo global, market data, análise,
`plan_entitlements`, `feature_flags`, `strategies`, `strategy_versions`,
`opportunity_weights` — a lista de exceções para escrita da API é
deliberadamente **vazia** no M0; quem escreve é `hunter_worker`) e
`APPEND_ONLY_TABLES` (`SELECT` + `INSERT`). Do lado do worker há ainda
`WORKER_DELETE_TABLES` (`DELETE` em `organizations` e `users`, e nada além
disso nessas duas), que é o outro lado de `APP_NO_DELETE_TABLES`.

**O que impede uma tabela futura de nascer sem classificação é um teste, não
DDL.** A primeira correção escrevia também
`ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM hunter_app,
hunter_worker`, que *parece* uma garantia permanente e é um no-op: os privilégios
padrão de um papel que não é o criador já começam vazios, revogar de um conjunto
vazio não remove nada, e a declaração não sobrevive como regra que um `GRANT`
futuro tivesse de derrotar. Foi removida. A garantia real é
`test_schema_privileges.py::test_the_grant_lists_cover_every_table_exactly_once`,
que compara as quatro classes congeladas com o `pg_class` vivo e falha para
qualquer tabela que esteja em nenhuma delas ou em duas.

**Restrições operacionais conhecidas.**

- `system_presets_manageable` é concedida `TO CURRENT_USER`, ou seja, ao papel
  que rodou a migração. **Migre e semeie com o mesmo papel.** Rodar
  `infra/scripts/seed.py` como um papel diferente faz `FORCE ROW LEVEL SECURITY`
  filtrar os presets de sistema de novo. O acoplamento não some — o que some é o
  silêncio: `seed.py` passou a contar as linhas do `RETURNING` de cada `INSERT
  ... ON CONFLICT`, em vez de devolver o tamanho da tupla de entrada, então uma
  gravação filtrada por política aparece como `seeded 0 row(s)` em vez de mentir
  três. Um teste de integração fixa isso (`reported == stored`).
- Remoção de organização/usuário exige `hunter_worker` ou um superusuário
  (§15.4): não há política de `DELETE` em `organizations` nem grant de `DELETE`
  para `hunter_app` em nenhuma das duas.
- `infra/scripts/create_partitions.py` roda **uma transação por tabela-pai
  particionada**, não uma para todas. `CREATE TABLE ... PARTITION OF` toma
  `ACCESS EXCLUSIVE` na pai, e uma transação única segurava as oito travas até o
  último comando — o job diário bloqueava escrita em `audit_logs` enquanto
  percorria `candles`. Como todo comando é idempotente, dividir não custa nada: a
  execução seguinte termina o que a anterior não terminou.

### 15.7 Precisão numérica

`market_snapshots.funding_rate` e `funding_rates.rate` são `NUMERIC(28,10)`, não
`NUMERIC(9,6)` como as demais colunas percentuais. Funding é um número de
dinheiro, não uma fração de apresentação: `NUMERIC(9,6)` arredondava uma taxa de
0.0000125 para 0.000013 (erro de 4 % no número de que as estratégias de
derivativos dependem) e zerava qualquer coisa abaixo de 5e-7, que é a maioria
delas.

### 15.8 CHECKs de domínio

`qty > 0` (`orders`, `fills`, `trades`, `backtest_trades`), `price > 0` /
`entry_price > 0` / `exit_price > 0` / `avg_entry_price > 0` onde a coluna é
obrigatória e `IS NULL OR > 0` onde é opcional, `filled_qty` entre 0 e `qty`,
`positions.qty >= 0` (uma posição em fechamento chega a zero antes de virar
`trade`), `initial_capital >= 0` em `portfolios` e `backtests`, e o invariante
de escopo do kill switch. As tabelas de market data ficaram **de fora** de
propósito: um feed de exchange emite ocasionalmente um zero, e um CHECK ali
transformaria um dado estranho em falha de ingestão.

### 15.9 Convenção de nomes em Python

`metadata` é atributo reservado pelo SQLAlchemy declarativo; as colunas JSONB
chamadas `metadata` são mapeadas para o atributo Python `meta`
(`Anomaly.meta`, `Order.meta`, ...). A classe do modelo de `market_regimes` é
`MarketRegimeRow` para não colidir com o enum `MarketRegime`.
