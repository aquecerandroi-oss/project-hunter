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
  USING (organization_id = current_setting('app.current_org', true)::uuid);
```

- A aplicação abre transação e executa `SET LOCAL app.current_org = '<uuid>'` antes de qualquer query de tenant. Sem o setting, a política retorna zero linhas.
- Workers de sistema usam um role `hunter_worker` com `BYPASSRLS` apenas nos processos que precisam varrer todas as organizações (strategy, execution, analytics). O `api` usa `hunter_app` sem bypass.
- `audit_logs` e `risk_events` são append-only: `hunter_app` tem `INSERT` e `SELECT`, nunca `UPDATE`/`DELETE`.

### 1.3 Particionamento e retenção

| Tabela | Partição | Retenção padrão | Job |
|---|---|---|---|
| `candles` | RANGE por `open_time`, mensal | 1m: 90 d · 5m: 1 a · 1h/1d: sem limite | `analytics-worker` diário |
| `market_snapshots` | mensal | 30 d | idem |
| `feature_snapshots` | mensal | 14 d (snapshots ligados a anomalias/oportunidades/trades vivem na própria linha dessas tabelas) | idem |
| `liquidations` | mensal | 30 d | idem |
| `opportunity_history` | mensal | 90 d | idem |
| `portfolio_equity_snapshots` | mensal | 1m: 30 d · 1h: sem limite | idem |
| `audit_logs` | mensal | sem limite | — |
| `system_events` | mensal | 30 d | idem |

Partições são criadas com 3 meses de antecedência por `infra/scripts/create_partitions.py`, agendado no analytics-worker. Uma partição faltante gera `system_event` de severidade `critical`.

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

agent_stats                                 (materializado pelo analytics-worker)
  agent_id, window stats_window (all|7d|30d|90d), computed_at,
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

portfolio_equity_snapshots                  PARTITION BY RANGE (ts)
  portfolio_id, ts, resolution (1m|1h|1d), cash, equity, exposure_notional, exposure_pct,
  unrealized_pnl, realized_pnl_cum, peak_equity, drawdown_pct, open_positions INT
  PK (portfolio_id, resolution, ts)

trade_proposals                             (o "PROPOSAL" do pipeline)
  id, organization_id, portfolio_id, agent_id, signal_id, market_id, direction,
  requested_risk_pct, status proposal_status (pending|approved|rejected|expired|executed|failed),
  risk_decision JSONB,          -- {approved, sized_qty, sized_notional, risk_pct, checks:[{name, passed, value, limit, message}]}
  rejection_reason, kill_switch_snapshot JSONB, regime_id, opportunity_score, confidence,
  idempotency_key (unique), created_at, decided_at, expires_at
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
  id, scope ks_scope (system|organization|portfolio), scope_id (null para system),
  from_state, to_state, reason, actor_type (user|system), actor_id, created_at
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
  id, backtest_id, segment (full|train|validation|oos|wf_1..n), metrics JSONB,
  equity_curve JSONB, warnings JSONB [{code: overfitting|leakage|lookahead, detail}], trades_count INT
  UNIQUE (backtest_id, segment)

backtest_trades
  id, backtest_id, segment, market_id, direction, entry_ts, exit_ts, entry_price, exit_price,
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
  consumer, event_id, processed_at
  PK (consumer, event_id)                   -- limpeza diária > 7 d
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
mostrava só `id`, a PK passa a incluir a coluna de partição:
`liquidations (id, ts)`, `audit_logs (id, created_at)`,
`system_events (id, created_at)`.

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

### 15.4 RLS

- Além de `tenant_isolation`, `risk_profiles` recebe a política
  `system_presets_readable` (`FOR SELECT USING (organization_id IS NULL)`).
  Sem ela `hunter_app` não enxergaria os presets de sistema que o onboarding
  precisa copiar. É somente leitura: o `WITH CHECK` de `tenant_isolation`
  continua estritamente por organização, então o app nunca cria nem edita um
  preset de sistema.
- `agent_stats`, `backtest_results`, `backtest_trades`,
  `portfolio_equity_snapshots` e `kill_switch_transitions` **não** têm
  `organization_id` (conforme §6, §7 e §9) e portanto não têm RLS. O isolamento
  delas depende do join com a tabela pai (`agents`, `backtests`, `portfolios`)
  no repositório — os repositórios tenant-scoped precisam garantir isso.
- `hunter_worker` recebe `BYPASSRLS` (§1.2) por um `ALTER ROLE` dentro de um
  bloco `DO` que tolera falta de privilégio: em Postgres gerenciado o papel que
  migra pode não poder concedê-lo, e nesse caso a migração emite um `NOTICE`
  pedindo a concessão manual.
- Toda tabela de tenant ganhou `FOREIGN KEY (organization_id) REFERENCES
  organizations(id) ON DELETE CASCADE`, que o `TenantMixin` sozinho não declara.

### 15.5 Partições

`0001_initial_schema` cria 2026-09 a 2026-12 com limites fixos — uma migração
reaplicada no futuro precisa produzir o mesmo schema, então não pode depender do
relógio. Tudo depois disso é de `infra/scripts/create_partitions.py`
(`--months-ahead`, padrão 3). As listas de tabelas particionadas e de tabelas com
RLS estão **congeladas** em `infra/migrations/ddl/`, e testes de integração
garantem que continuam iguais às derivadas dos modelos.

### 15.6 Convenção de nomes em Python

`metadata` é atributo reservado pelo SQLAlchemy declarativo; as colunas JSONB
chamadas `metadata` são mapeadas para o atributo Python `meta`
(`Anomaly.meta`, `Order.meta`, ...). A classe do modelo de `market_regimes` é
`MarketRegimeRow` para não colidir com o enum `MarketRegime`.
