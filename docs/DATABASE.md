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

### 1.2a Timeouts de sessão (`SET LOCAL statement_timeout`)

O servidor roda com `statement_timeout = 0` / `lock_timeout = 0` (sem prazo) — Neon/RDS não fixam um limite por padrão, e depender só disso deixaria qualquer transação livre para rodar indefinidamente. `hunter_core.db.session._apply_context` fecha essa lacuna: toda transação aberta por `role_session` (e portanto por `tenant_session`, `user_session`, `bootstrap_session`) recebe um `SET LOCAL statement_timeout` logo após o `SET LOCAL ROLE`, **antes** de qualquer query da aplicação.

| Role | Timeout padrão | Setting |
|---|---|---|
| `hunter_app` (API) | 10 s | `Settings.db_statement_timeout_app_s` / env `DB_STATEMENT_TIMEOUT_APP_S` |
| `hunter_worker` | 15 s | `Settings.db_statement_timeout_worker_s` / env `DB_STATEMENT_TIMEOUT_WORKER_S` |

- **Achado que motivou isto (security-reviewer, S3a, MEDIUM):** antes desta seção, só `hunter_worker` recebia um `statement_timeout`; toda transação da API (`hunter_app`) rodava sem prazo nenhum. Um chamador autenticado batendo repetidamente numa rota cara — o exemplo usado foi `GET /api/v1/lab/shadow/summary?window=all`, uma varredura sem índice por versão — não tinha nada que cortasse uma única query, podendo saturar o Postgres mesmo estando corretamente autenticado e dentro do rate limit por requisição.
- `hunter_app` tem um valor menor que `hunter_worker` de propósito: trabalho de request/response é esperado ser curto; um job de worker (ex.: consumo de stream, agregações) legitimamente precisa de mais espaço. Nenhuma chamada de `hunter_app` no `apps/api` de hoje é uma operação de longa duração — as únicas que fariam sentido levar mais tempo (webhooks do Clerk que reconciliam várias linhas, buscas de membership) já rodam como `hunter_worker`.
- **Não vaza entre transações da mesma conexão.** `SET LOCAL` é escopado à transação corrente; o Postgres o reseta em todo `COMMIT`/`ROLLBACK`, mesmo quando o pooler (Neon/PgBouncer em modo transação) entrega a mesma conexão física para a próxima transação, de outro chamador. Coberto por teste de integração com um engine de `pool_size=1` (`packages/core/tests/integration/test_db_integration.py`), forçando a segunda transação a reusar a conexão da primeira.
- `role_session` aceita um `settings: Settings | None` opcional para sobrescrever os dois valores; sem ele, cai no `hunter_core.settings.get_settings()` cacheado (o mesmo singleton que os `__main__` dos workers já usam), então nenhum call site precisou mudar para herdar um override por env var.
- `command_timeout=30` (D3, `connect_args` do `create_engine`) continua sendo um teto do driver asyncpg, à parte — vale para as duas roles e não substitui o `statement_timeout` do servidor: é o que impede um `await` do driver de travar para sempre num socket morto, não o que corta uma query lenta ainda viva.
- `lock_timeout` não tem um valor padrão hoje (nem tinha antes desta seção); só o `statement_timeout` foi endurecido aqui. Ver `hunter_core/db/session.py` se/quando isso mudar.

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

## 16. Shadow Lab (`0002_shadow_lab`)

Primeira revisão depois do schema inicial. Entrega a metade **durável** do
`docs/plans/SHADOW-LAB.md` (tarefa S0): o que precisa ser verdade *antes* de
qualquer `strategy_version` ser ativada, porque um experimento sombra cujos
parâmetros, estado de acompanhamento ou entrega de eventos podem mudar depois
produz números em que ninguém pode acreditar. Nenhuma tabela nova é de tenant:
como `agent_signals` e `signal_outcomes`, a pesquisa sombra é global (§1.1), sem
`organization_id` e sem RLS; `hunter_app` só lê, `hunter_worker` escreve.

**Numeração.** Esta é a `0002` que o `docs/plans/M2.md` (T2.1) dizia que ia
escrever. T2.1 passa a **depender** desta revisão em vez de recriar os seus
objetos e entra como `0003`.

### 16.1 `strategy_versions`: congelada pela primeira ativação

```
strategy_versions  (+) params_format INT NOT NULL DEFAULT 1
```

`params_format` é a versão do formato canônico com que o `params_hash` foi
calculado (`hunter_core.strategies.canonical`, formato 1: chaves ordenadas,
número como string decimal normalizada sem zeros à direita nem expoente,
timestamps ISO-8601 UTC com `Z`, ausentes como `null`, listas na ordem dada).

A trigger `strategy_versions_freeze_update` (`BEFORE UPDATE ... WHEN (OLD.activated_at
IS NOT NULL)`) rejeita qualquer alteração de `strategy_id`, `version`,
`code_ref`, `parameters_schema`, `default_parameters`, `params_format` e
`activated_at` — **inclusive `SET activated_at = NULL`**, que de outro modo
descongelaria a linha — em qualquer `status` (ativa, deprecated, reativada).
`status`, `changelog` e `deprecated_at` continuam mutáveis: descrevem o ciclo de
vida da versão, não o seu conteúdo. A comparação é `IS DISTINCT FROM` sobre o
valor, então reescrever o mesmo JSONB com outra ordem de chaves não é alteração.
A **primeira** ativação (`activated_at NULL` para um valor) passa, uma única vez.

**Consequência para `infra/scripts/seed.py`.** O seed **insere a v1 ausente e
nunca toca linha ativada**: o `ON CONFLICT (strategy_id, version) DO UPDATE SET
code_ref = excluded.code_ref` leva um `WHERE strategy_versions.activated_at IS
NULL`, então na linha congelada nenhum `UPDATE` chega a rodar e a trigger nem
dispara. Enquanto a versão está `draft` o upsert continua atualizando o `code_ref`
que o registry publica — e o mesmo valeria para `parameters_schema` e
`default_parameters` se o seed passasse a semeá-los: nada aponta para a linha
ainda, e até a primeira ativação o registry é a única verdade que existe.

**Correção de 2026-09-06 (HIGH reproduzido na VPS).** Esta seção dizia o
contrário — que um `code_ref` divergente devia fazer o seed *falhar alto*, "o
comportamento correto". Não é: como o seed roda numa transação só, a exceção da
trigger revertia as **oito** tabelas de referência, e o ambiente ficava sem
`exchanges`, `plan_entitlements`, `feature_flags`, `risk_profiles`,
`feature_definitions` e `opportunity_weights` — não "sem `strategy_versions`", sem
nada — em todo deploy posterior à primeira ativação. E o divergente é o caso
**normal**, não o excepcional: o seed grava o placeholder do registry
(`hunter_indicators.strategies.<key>_v1`) e a ativação grava o digest por versão
(`hunter_core.strategies.<módulo>@sha256:…`, de
`hunter_strategy_worker.code_ref.version_code_ref`), de modo que **toda** linha
ativada diverge do registry por construção.

Divergência em linha ativada **não é erro do seed**: a versão congelada é a
verdade — é ela que todo sinal sombra nomeia — e o registry evolui publicando
sucessora (`infra/scripts/activate_strategy_version.py --supersede`), nunca por um
`UPDATE` vindo daqui. O seed apenas **relata** na saída
(`note: <key> v1 is activated and frozen at <code_ref>; …`) e segue semeando o
resto. A contagem de `strategy_versions` continua vindo do banco e não do tamanho
da tupla de entrada (§15.6): a linha que o seed deliberadamente não escreveu
continua sendo uma linha que está lá. Quem ativa continua devendo gravar o
`code_ref` definitivo **antes** da ativação — só que agora não é um seed
reexecutado, e o ambiente inteiro sem dado de referência, que descobre isso.

`strategy_versions_freeze_delete` (`BEFORE DELETE`, mesma condição) é o outro
lado: uma linha ativada que pudesse ser apagada poderia ser reinserida com o
mesmo `id` e outros parâmetros, e todo sinal que já aponta para ela mudaria de
significado em silêncio. **Consequência aceita:** apagar uma `strategy` cuja
versão já foi ativada também falha, porque o `ON DELETE CASCADE` bate na trigger.
Encerrar uma versão é `status = 'deprecated'`, não `DELETE`.

### 16.2 `signal_outcomes`: o terceiro eixo

```
signal_outcomes  (+) tracking_state shadow_tracking_state NOT NULL DEFAULT 'pending_entry'
                 (+) no_entry_reason TEXT, censored_reason TEXT
                 (+) meta JSONB NOT NULL DEFAULT '{}'
```

`shadow_tracking_state` = `pending_entry | active | terminal | no_entry | censored`.
São três eixos distintos: `signal_status` (validade do sinal), `outcome_result`
(como o trade hipotético terminou) e `tracking_state` (onde o acompanhamento
está). `terminal`, `no_entry` e `censored` não reabrem. `meta` guarda as
excursões honestas do item 5 do plano (`{unit, method, coverage,
mfe_complete_bars, mae_complete_bars, bounds, bar_windows, ambiguous,
initial_risk, reference_price}`); `mfe`/`mae` canônicos continuam nulos quando o
extremo é indeterminado.

Dois CHECKs:

- `ck_signal_outcomes_no_entry_and_censored_reasons` — `no_entry` se e somente se
  `no_entry_reason` não nulo, `censored` se e somente se `censored_reason` não
  nulo, cada motivo com 1 a 64 caracteres (um `NOT NULL` sozinho aceitaria a
  string vazia, que não registra nada) e nulo quando não se aplica;
- `ck_signal_outcomes_tracking_state_matches_result` —
  `(result = 'open') = (tracking_state <> 'terminal')`.

**Backfill antes do CHECK.** A migração roda um `UPDATE` derivado das colunas que
já existem (`result <> 'open'` → `terminal`; `result = 'open'` com `entry_ts` →
`active`; o resto → `pending_entry`) *antes* de instalar a bicondicional. Sem
ele, um banco que já tivesse um outcome encerrado receberia o default
`pending_entry`, violaria o CHECK e abortaria o upgrade — a migração funcionaria
só em banco vazio (achado da revisão da Astra; há teste com `0001` populada).

Uma linha **contraditória** — `result = 'open'` **com** `exit_ts` preenchido — não
tem `tracking_state` derivável, e chamá-la de `pending_entry` devolveria ao worker
um acompanhamento já encerrado como se esperasse entrada. A migração **recusa o
upgrade** com a contagem e a instrução (dar a ela o resultado real e reexecutar),
em vez de adivinhar; em banco consistente é um no-op.

**Desvio deliberado do brief da S0**, registrado aqui porque muda o contrato: o
brief propunha `result <> 'open'` implicando `tracking_state IN ('terminal','censored')`.
`outcome_result` (§6) não tem membro para "desconhecido", e o plano proíbe
transformar censura em `expired`; forçar uma linha `censored` a carregar um dos
quatro resultados financeiros seria exatamente essa mentira. Então `censored` e
`no_entry` mantêm `result = 'open'` e o CHECK vira a bicondicional acima:
**`terminal` se e somente se o resultado resolveu**. A consequência vale para a
API e para as métricas (S3): *quem decide se um acompanhamento está aberto é
`tracking_state`, nunca `result`* — `no_entry` e `censored` não contam como
abertos, e censura não conta como `expired`.

### 16.3 `shadow_episodes` (sistema)

```
shadow_episodes
  id, strategy_version_id -> strategy_versions, market_id -> markets,
  cohort TEXT, episode_id UUID, last_bar_close TIMESTAMPTZ,
  armed BOOLEAN NOT NULL DEFAULT true, open_outcome_signal_id -> agent_signals (SET NULL),
  created_at, updated_at
  UNIQUE (strategy_version_id, market_id, cohort)            -- uq_shadow_episodes_slot
  UNIQUE (open_outcome_signal_id) WHERE open_outcome_signal_id IS NOT NULL
  INDEX  (market_id)             WHERE open_outcome_signal_id IS NOT NULL   -- tracking_hold
  CHECK  (cohort ~ prospective|replay:<uuid>)                -- ck_shadow_episodes_cohort_format
  FK (open_outcome_signal_id) -> signal_outcomes (signal_id)
  FK (open_outcome_signal_id, strategy_version_id, market_id)
     -> agent_signals (id, strategy_version_id, market_id)   -- exige UNIQUE novo em agent_signals
```

**Integridade episódio ↔ outcome (achado da revisão da Astra).** Uma FK de uma
coluna só garantia "o sinal existe" e mais nada: um sinal de BTC podia ocupar o
slot de ETH — a FK ficava satisfeita, o `tracking_hold` segurava as velas de ETH
e BTC, o mercado de que o outcome precisa, ficava livre para sair do universo e
perder o histórico. Duas FKs fecham isso: uma aponta para `signal_outcomes`
(o outcome tem de existir; um slot não segura uma decisão que ninguém acompanha)
e a composta amarra o sinal à versão **e** ao mercado do próprio slot, no mesmo
padrão do §15.4 — por isso `agent_signals` ganhou
`UNIQUE (id, strategy_version_id, market_id)` (`uq_agent_signals_id_slot`).

O que o DDL ainda **não** garante, e portanto continua sendo invariante da S2
(transação única + consulta de reconciliação), está declarado aqui de propósito:
que o outcome apontado esteja aberto (`pending_entry`/`active`) e que a coorte
dele seja a do slot — a coorte vive no envelope da decisão, não numa coluna. O
item do aceite S0 "sem acompanhamentos `pending_entry|active` órfãos" está,
portanto, **parcialmente** coberto por DDL.

Um acompanhamento por (versão, mercado, coorte); replay nunca ocupa o bloqueio
do prospectivo. `cohort` é texto e não `ENUM` porque um replay carrega o seu
`run_id` — o conjunto é aberto em valor e fechado em forma, e a mesma regex vive
em `hunter_core.domain.enums.SHADOW_COHORT_PATTERN` e no CHECK. `armed` nasce
`true` e é durável: rearme depende de uma barra elegível com a condição falsa
*após* o término do acompanhamento anterior, e dado ausente não rearma — não é
algo que um worker possa recalcular de memória depois de um restart. O índice
parcial por `market_id` é a consulta do `tracking_hold` (§8 do plano): um mercado
sai do universo monitorado, mas não enquanto um acompanhamento sombra ainda
precisa das velas dele.

### 16.4 `shadow_outbox` (sistema)

```
shadow_outbox
  id BIGSERIAL PK, event_id UUID UNIQUE, stream TEXT, payload JSONB NOT NULL DEFAULT '{}',
  created_at, dispatched_at (null = pendente), attempts INT NOT NULL DEFAULT 0, last_error TEXT
  INDEX (id) WHERE dispatched_at IS NULL                     -- fila do despachante
  CHECK attempts >= 0, CHECK char_length(stream) > 0
```

Escrita na **mesma transação** do sinal, do outcome e do episódio; o despachante,
a reconciliação e a entrega idempotente são a S2. `event_id` único é o que faz
uma reentrega enfileirar uma vez só (`event_id = signal_id` para
`shadow.signals.emitted`). T2.9 a absorve depois preservando pendências e
identidades.

**Dois desvios registrados:** (a) a PK é `BIGSERIAL`, não UUID v7 (§1) — dá ao
despachante uma ordem estável e barata para drenar a fila; nada aqui é dinheiro
nem dado de tenant. **Não é marca d'água:** a sequence tem lacunas (rollback) e a
ordem dela não é a ordem de commit — a transação A pode pegar 10, a B pegar 11 e
commitar primeiro, e um cursor em 11 passaria por cima da A. O predicado de
pendência é `dispatched_at IS NULL`, que é exatamente o que o índice parcial
serve (achado da revisão da Astra); (b) por consequência, é a
**primeira sequence do schema**, e
`hunter_worker` precisa de `GRANT USAGE ON SEQUENCE shadow_outbox_id_seq` — um
grant de tabela sozinho passaria em `has_table_privilege` e falharia em todo
`INSERT` com *permission denied for sequence*. Há teste que insere como o papel,
em vez de perguntar.

### 16.5 Tipos por revisão (`ddl/enums.py`)

`create_enum_types()` iterava `ALL_ENUMS` em tempo de execução, o que era
inofensivo com uma revisão só e virou armadilha com duas: acrescentar
`shadow_tracking_state` a `ALL_ENUMS` fazia a `0001` criá-lo retroativamente e a
`0002` falhar com *type already exists*. Cada revisão passa a nomear a sua tupla
congelada (`INITIAL_ENUMS`, 44 tipos; `SHADOW_ENUMS`), como as listas de grant do
§15.6, e `test_migrations.py::test_every_enum_type_belongs_to_exactly_one_revision`
prova que as tuplas continuam particionando `ALL_ENUMS`.

**Limitação conhecida — resolvida na `0003` (§17.1).** Nesta revisão só os *nomes*
dos tipos estavam congelados por revisão; os **rótulos** ainda eram lidos de
`ALL_ENUMS` em tempo de execução, então acrescentar um membro a um enum existente
alteraria retroativamente o que a `0001` cria. A `0003_analysis` (M2 · T2.1) — a
primeira migração a acrescentar valores a enums existentes — congelou os rótulos
por revisão (`INITIAL_ENUMS`, `SHADOW_ENUMS`, `ANALYSIS_ENUMS` passam a ser mapas
`tipo -> rótulos` e nada em `ddl/enums.py` lê `ALL_ENUMS`), com teste que para em
`0001` e em `0002` e compara rótulos e ordem.

Pelo mesmo motivo as quatro classes de grant do §15.6 continuam congeladas em
`0001`: as tabelas desta revisão estão em `ddl/shadow.py`
(`SHADOW_APP_READ_ONLY_TABLES`, `SHADOW_WORKER_WRITE_TABLES`, `SHADOW_SEQUENCES`)
e `test_schema_privileges.py` une as listas — toda tabela continua classificada
exatamente uma vez.

Nada nesta revisão depende de estado de sessão: sem prepared statement de sessão,
sem `LISTEN/NOTIFY`, sem advisory lock de sessão. O bloqueio de um episódio é a
própria linha, dentro da transação.

## 17. Análise — M2 (`0003_analysis`)

Segunda revisão depois do schema inicial e a primeira que **acrescenta valor a um
enum existente**. Entrega o estado durável do Milestone 2 (tarefa T2.1) conforme
a **"Decisão conjunta Claude ⇄ Astra (2026-09-05)"** de `docs/plans/M2.md`, que
prevalece sobre as "Decisões deste plano" do mesmo documento. Nenhuma tabela nova
é de tenant: análise é global (§1.1), sem `organization_id` e sem RLS;
`hunter_app` só lê, `hunter_worker` escreve.

### 17.1 Rótulos de enum congelados por revisão (`ddl/enums.py`)

O follow-up que a §16.5 deixou aberto está fechado aqui. A `0002` congelou os
**nomes** dos tipos por revisão, mas os **rótulos** continuavam vindo de
`ALL_ENUMS` em tempo de execução — então esta revisão, a primeira a acrescentar
um membro a um enum que já existia, teria alterado retroativamente o que a `0001`
cria: um `upgrade 0001` em banco limpo passaria a criar um `opportunity_status`
que já contém `EXTENDED`, e o `ALTER TYPE ... ADD VALUE` da `0003` encontraria o
rótulo já lá.

Cada revisão passa a nomear o seu próprio mapa congelado `tipo -> rótulos`
(`INITIAL_ENUMS`, 44 tipos; `SHADOW_ENUMS`; `ANALYSIS_ENUMS`) e nada em
`ddl/enums.py` lê `ALL_ENUMS`.
`test_migrations.py::test_each_revision_creates_exactly_the_labels_it_froze` para
em `0001` e em `0002` e compara os rótulos **e a ordem** (`enumsortorder`) com o
que aquela revisão congelou;
`test_every_enum_type_belongs_to_exactly_one_revision` continua provando a
partição por nome.

**A ordem faz parte do contrato.** `ANALYSIS_ADDED_VALUES` diz onde cada rótulo
entra e as classes de `hunter_core.domain.enums` os declaram nas mesmas posições:

| Tipo | Rótulo novo | Posição |
|---|---|---|
| `opportunity_status` | `EXTENDED` | `BEFORE 'EXPIRED'` (EXPIRED é terminal) |
| `anomaly_type` | `TRADE_VELOCITY_SPIKE`, `MOMENTUM_SHIFT` | `BEFORE 'SOCIAL_SPIKE'` (são MVP v1) |
| `market_regime` | `UNKNOWN` | no fim |

Tipos novos: `opportunity_stage`, `anomaly_evaluation_state`, `baseline_source`,
`baseline_sampling`.

**Caixa de `opportunity_stage`: `EARLY | DEVELOPING | EXTENDED | NONE`, em
maiúsculas.** É um desvio consciente do rascunho `(early | developing | extended
| none)` das "Decisões deste plano" (superadas) e da regra de caixa do §15.1: a
coluna irmã na mesma tabela é `opportunity_status`, que é MAIÚSCULA, os dois
aparecem juntos na mesma lista de precedência e no mesmo chip do Radar, e a
decisão conjunta escreve os três estágios em maiúsculas em toda a prosa. `NONE` é
membro e não `NULL` de propósito: durante o warm-up do ATR não há estágio, e uma
coluna anulável deixaria cada consumidor ler a ausência como `EARLY`.

`baseline_sampling` tem **um** membro (`per_minute`). Não é defeito: uma segunda
política de amostragem passa a exigir migração, e toda linha já grava qual
política a produziu, então duas populações não podem ser somadas em silêncio.

**Postgres 12+ permite `ALTER TYPE ... ADD VALUE` dentro de transação, mas proíbe
*usar* o valor novo na mesma transação** — inclusive em `DEFAULT` e em predicado
de índice. A `0003` acrescenta os quatro e não usa nenhum; o único rótulo que ela
escreve em DDL (`'EXPIRED'`, no CHECK de expiração) já existia na `0001`.

**Downgrade.** Postgres não tem `ALTER TYPE ... DROP VALUE`, então o downgrade
renomeia o tipo, recria-o com os rótulos congelados da `0001`, converte cada
coluna (`opportunities.status`, `opportunity_history.status`, `anomalies.type`,
`market_regimes.regime`) com `USING x::text::tipo` e derruba o tipo antigo.
`opportunity_history` é particionada: `ALTER TABLE ... ALTER COLUMN TYPE` sem
`ONLY` recursa para as partições, e por isso o índice parcial e o CHECK novos são
removidos **antes** — nenhuma expressão armazenada pode continuar ligada ao tipo
que vai ser substituído. Antes de tudo isso há uma guarda que conta as linhas que
ainda usam um rótulo prestes a desaparecer (inclusive uma amostra `EXTENDED` sob
um episódio já `EXPIRED`) e **recusa** o downgrade nomeando-as.

### 17.2 `feature_baselines` — revisões imutáveis

```
feature_baselines
  id (uuid7), market_id -> markets (CASCADE), feature, feature_version, algo_version,
  hour_of_day SMALLINT 0-23, window_start, window_end, available_at,
  median NUMERIC(28,10), mad NUMERIC(28,10),
  sample_size, expected_size, distinct_days, coverage NUMERIC(9,6),
  source baseline_source (live|bootstrap), sampling baseline_sampling (per_minute),
  input_fingerprint, computed_at
  UNIQUE (market_id, feature, hour_of_day, feature_version, algo_version,
          window_end, source, input_fingerprint)      -- uq_feature_baselines_revision
  INDEX  (market_id, feature, hour_of_day, available_at)  -- ix_feature_baselines_lookup
  CHECKs: hour_of_day 0-23; window_start < window_end <= available_at;
          0 <= sample_size <= expected_size, expected_size > 0, distinct_days >= 0;
          0 <= coverage <= 1; mad >= 0
```

**Arquivo de revisões, não projeção atual.** Uma linha por (mercado, feature,
hora UTC) bastaria para pontuar *agora* e seria inútil para explicar *então*. O
critério de aceite da decisão conjunta é "recalcular baselines amanhã reproduz o
score de hoje", o que só é verdade se uma revisão é escrita uma vez e nunca
editada: recomputar cria linha nova com `available_at` posterior, e o envelope do
score guarda o `id` que usou. O bucket é a **hora UTC** com observações **por
minuto** — 420 esperadas em sete dias.

**Corte causal — duas condições, não uma:** `available_at <= as_of` **E**
`window_end < observation_ts`. O cenário que exige as duas: uma feature de 10:00
processada às 10:02 passaria por um teste só de `available_at <= 10:02` contra
uma baseline publicada às 10:01 que já inclui a observação de 10:00. O leitor
também escolhe versões compatíveis de feature e algoritmo — uma mediana calculada
por outro algoritmo é outra população, não um valor mais novo da mesma.

**`input_fingerprint` separa retentativa de recomputação.** Digest canônico do
conjunto de entrada e do corte. Sem ele, um backfill que chegue depois de a
janela ter sido calculada produziria (mercado, feature, hora, versões,
`window_end`, `source`) idênticos com amostra/mediana/MAD diferentes: a revisão
corrigida não poderia ser gravada — `DO NOTHING` manteria a incompleta e `UPDATE`
é proibido. Com ele, reexecutar o mesmo job colide (idempotente) e uma
recomputação real entra como revisão nova.

**Maturidade não é armazenada.** `sample_size`, `expected_size`, `distinct_days`
e `coverage` ficam crus e o gate (>= 3 dias distintos **E** >= 120 observações
válidas) é aplicado pelo leitor com os seus limiares versionados
(`opportunity_weights.weights["baseline_gate"]`). Um booleano gravado congelaria
um limiar feito para ser versionado. Baseline abaixo do gate existe — "em
construção" é estado que o Radar mostra, não linha ausente.

**Imutabilidade.** Trigger `feature_baselines_immutable`
(`BEFORE UPDATE OR DELETE ... FOR EACH ROW`) recusa **todo** `UPDATE`, para todos
os papéis, inclusive o dono. `DELETE` **não** é proibido — retenção precisa
expirar revisões —, mas é recusado a menos que o chamador se declare com
`SET LOCAL app.baseline_retention = 'on'`. O marcador é de transação, o que o
torna seguro atrás do pooler (mesmo mecanismo de `app.current_org`, §15.4), e
significa que um bug no scanner não apaga a evidência que os próprios scores dele
apontam: apagar é um ato, não um acidente.

**Protocolo de retenção (contrato para T2.8, não implementado aqui).** Não há FK
entre `opportunities`/`opportunity_history` e `feature_baselines` — os
`baseline_ids` vivem dentro do envelope JSONB —, então **nada no DDL impede**
apagar uma baseline ainda referenciada. O contrato que fecha isso, e que a T2.8
tem de implementar, é **exclusão mútua por linha**, não uma regra de idade:

1. **Idade não prova ausência de dependência.** Uma amostra gravada hoje pode
   referenciar uma revisão de duas semanas atrás (uma baseline permanece
   utilizável até ser recomputada). Qualquer critério do tipo "apague o que for
   mais velho que X" apaga evidência viva. A única condição válida é *nenhuma
   amostra preservada referencia esta revisão*, avaliada sobre
   **`opportunities.feature_snapshot` e `opportunity_history.envelope`** — a
   projeção atual conta tanto quanto o histórico.
2. **O escritor toma o lock antes de referenciar.** Antes de gravar um envelope,
   o scorer faz `SELECT ... FROM feature_baselines WHERE id = ANY(...) FOR SHARE`
   na mesma transação e **revalida que as linhas ainda existem** — uma baseline
   em cache pode ter sido apagada desde que ele a leu. Se sumiu, o componente
   fica indisponível com motivo; nunca se grava um `baseline_id` que não está
   mais lá.
3. **A retenção toma o mesmo lock antes de apagar.** `SELECT ... FOR UPDATE` na
   revisão candidata, e só então a consulta de referências e o `DELETE`, tudo na
   mesma transação e com `SET LOCAL app.baseline_retention = 'on'`. Os dois locks
   sobre a mesma linha são o que serializa as duas operações: a corrida "o job
   verifica que ninguém referencia B, um scorer com B em cache grava o envelope,
   o job apaga B" deixa de ser possível porque um dos dois espera pelo outro.
   Locks de linha, nunca advisory lock de sessão (§1.2 / pooler).

Se a consulta de referências vier a pesar, o caminho é um índice GIN sobre a
expressão JSONB dos ids, **não** uma segunda coluna `UUID[]` a sincronizar à mão:
ela não daria FK de qualquer forma, e duas representações divergem.

O **downgrade** da `0003` (§17.7) recusa enquanto houver amostra preservada
referenciando uma baseline, pelo mesmo motivo.

**Consequência aceita:** o `ON DELETE CASCADE` de `market_id` também passa pelo
trigger — apagar um `market` que tenha baselines exige o mesmo marcador. Um
mercado é aposentado com `delisted_at` e nunca apagado de verdade pela aplicação
(§3), então na prática isso só aparece em limpeza operacional, e é o
comportamento certo: uma cascata continua sendo uma exclusão.

**Volume e cadência (a fechar em T2.3).** Um recomputo completo de 200 mercados ×
20 features × 24 buckets são **96 mil linhas**. Recomputar *todos* os buckets a
cada hora seriam 2,3 milhões de linhas/dia; recomputar apenas o bucket da hora que
fechou são 4 mil linhas/hora, ~96 mil/dia. A tabela **não** é particionada, e essa
decisão assume a segunda cadência. T2.3 fixa a cadência; se escolher a primeira, o
particionamento mensal por `available_at` volta à mesa antes do ensaio de 24 h.

### 17.3 Identidade do episódio de oportunidade

```
opportunities  (+) stage opportunity_stage NOT NULL DEFAULT 'NONE'
               (+) explanation JSONB NOT NULL DEFAULT '{}'
               (+) below_40_since TIMESTAMPTZ
  uq_opportunities_open_per_market: UNIQUE (market_id) WHERE expired_at IS NULL
  CHECK ((status = 'EXPIRED') = (expired_at IS NOT NULL))

opportunity_history  (+) stage opportunity_stage NOT NULL DEFAULT 'NONE'
                     (+) envelope JSONB NOT NULL DEFAULT '{}'
```

O índice parcial único **deixa de ser por lista de status** (`'WATCHING'`,
`'HOT'`, `'ENTRY_CANDIDATE'`, §15.3) e passa a ser `WHERE expired_at IS NULL`. O
cenário decisivo da decisão conjunta é o motivo: `HOT(id=A, 80)` que cai para
`NORMAL(35)` por um minuto e volta a `WATCHING(45)` tem de continuar sendo o
**mesmo** episódio; sob o predicado antigo a linha saía do índice ao virar NORMAL
e um segundo episódio podia ocupar a vaga — o Radar mostraria uma oportunidade
"nova" que é o mesmo movimento. `NORMAL` não *abre* episódio, mas é estado
temporário válido de um já aberto.

O CHECK bicondicional é o que impede os dois lados de discordarem: o índice
chaveia identidade em `expired_at` e todo consumidor lê `status`. Sem ele um
episódio ficaria aberto para o índice e encerrado para o Radar, ou o contrário.

`below_40_since` é durável porque a expiração de 15 minutos tem de sobreviver a um
restart e não é recomputável de mais nada: perda de qualidade interrompe a
continuidade (o intervalo desconhecido nunca conta como "abaixo de 40"), e só o
processo que viu as observações sabe disso.

`opportunities.feature_snapshot` e `opportunity_history.envelope` carregam o
envelope completo por amostra: vetor exato, `ts`/qualidade/disponibilidade por
entrada, `as_of`, `baseline_ids`, `regime_id`, versões e `state_in`/`state_out` da
histerese e dos confirmadores. Duas garantias, declaradas: recomputar um score
gravado a partir do envelope, **sim**; refazer a trajetória intraminuto, **não**
(perfil de backtest "bar-only" identificado). `stage` entra no history porque uma
mudança de estágio é um dos gatilhos que gravam uma amostra — sem a coluna, a
amostra apareceria na série sem motivo visível.

**`alembic check` não vê troca de predicado de índice.** O Alembic compara as
*colunas* de um índice, não o `WHERE`. Um índice deixado com o predicado antigo
não acusaria drift e estaria fazendo cumprir o invariante errado, então a troca é
escrita à mão na revisão e
`test_schema_analysis.py::test_episode_identity_is_keyed_on_expired_at_and_not_on_a_status_list`
lê `pg_indexes.indexdef` para provar.

### 17.4 `anomalies.evaluation_state`

```
anomalies  (+) evaluation_state anomaly_evaluation_state NOT NULL DEFAULT 'ok'
  uq_anomalies_active_per_market_type: UNIQUE (market_id, type) WHERE status = 'active'
```

Eixo separado do ciclo de vida: `status` diz onde a anomalia está
(`active → resolved/expired`), `evaluation_state` diz se o dado por trás dela
ainda pode ser acreditado (`ok | stale | unknown`). O par que importa é
`active + unknown` — a anomalia cujo feed sumiu continua **ativa** e fica
inelegível, e nunca é resolvida por ausência: "paramos de olhar" não é "parou de
acontecer".

**Backfill deliberado.** `ADD COLUMN ... DEFAULT 'ok'` escreveria `ok` em toda
linha preexistente, atribuindo uma qualidade que ninguém verificou. A migração
grava `unknown` em todas elas logo depois: são anteriores aos detectores do M2 e
`active + unknown` é exatamente o estado previsto para elas. Em tabela vazia é
no-op.

### 17.5 `outbox_events` (T2.9)

```
outbox_events
  id BIGSERIAL PK, event_id UUID UNIQUE, stream TEXT, payload JSONB NOT NULL DEFAULT '{}',
  created_at, dispatched_at (null = pendente), attempts INT NOT NULL DEFAULT 0, last_error TEXT
  INDEX (id) WHERE dispatched_at IS NULL       -- ix_outbox_events_pending
  CHECK attempts >= 0, CHECK char_length(stream) > 0
```

**Forma idêntica à de `shadow_outbox` (§16.4), de propósito.** O Shadow Lab
entregou a sua fila na `0002` antes desta existir e o item 6 de `SHADOW-LAB.md`
exige que a absorção não perca pendências, então as colunas batem uma a uma e a
absorção é um `INSERT ... SELECT` com **lista explícita de colunas** que preserva
`event_id`, `stream`, `payload`, `created_at`, `dispatched_at`, `attempts` e
`last_error` e deixa `id` ser reemitido pela sequence local. Copiar `id` entre
duas filas populadas colidiria — e não significaria nada se não colidisse: `id` é
ordem de drenagem, nunca identidade. O predicado de pendência é
`dispatched_at IS NULL`, nunca uma marca d'água sobre `id` (§16.4). Há teste que
executa exatamente esse `INSERT ... SELECT`, para que as duas formas não possam
divergir sem alguém ficar vermelho. A troca dos escritores (a fila antiga
continua recebendo enquanto a cópia roda) é coordenação da T2.9, não DDL.

Mesmos dois desvios registrados na §16.4: PK `BIGSERIAL` em vez de UUID v7 (§1) e
a sequence `outbox_events_id_seq`, que exige
`GRANT USAGE ON SEQUENCE ... TO hunter_worker` — um grant de tabela sozinho passa
em `has_table_privilege` e falha no `INSERT` com *permission denied for sequence*,
então o teste insere como o papel em vez de perguntar.

### 17.6 Grants — a quinta classe

`ddl/tables.py` está congelada na `0001` e `ddl/shadow.py` na `0002`; as listas
desta revisão estão em `ddl/analysis.py` (`ANALYSIS_APP_READ_ONLY_TABLES`,
`ANALYSIS_WORKER_WRITE_TABLES`, `ANALYSIS_WORKER_APPEND_TABLES`,
`ANALYSIS_SEQUENCES`) e `test_schema_privileges.py` une as três — toda tabela
continua classificada exatamente uma vez.

A novidade é `ANALYSIS_WORKER_APPEND_TABLES` = (`feature_baselines`):
`SELECT`/`INSERT`/`DELETE` para `hunter_worker` e **`UPDATE` para ninguém**. Não é
a classe append-only do §15.6 (que também proíbe `DELETE`, porque trilha de
auditoria não é podada) — baselines *são* podadas, no mesmo prazo das amostras que
dependem delas. `UPDATE` é negado no grant, antes de o trigger ser consultado:
duas fechaduras independentes na mesma porta.

### 17.7 Guardas em banco populado

Três invariantes novos não podem ser derivados para linhas que já os violam. A
migração conta os infratores e **recusa** com instruções, seguindo o precedente da
`0002` (fazer backfill do que as colunas existentes *implicam*, recusar o que elas
apenas sugerem). Em todo banco onde o scanner do M2 nunca rodou — que é todo banco
hoje — cada uma conta zero.

| Guarda | Por que não há backfill honesto |
|---|---|
| `(status = 'EXPIRED') <> (expired_at IS NOT NULL)` | inventar `expired_at` fabricaria justamente o carimbo em que o modelo de episódio é chaveado |
| mais de uma oportunidade aberta por mercado | a migração não pode escolher qual das duas é o episódio |
| mais de uma anomalia `active` por (mercado, tipo) | idem: qual delas o detector está mantendo é conhecimento do detector |

**E guardas no downgrade.** Reverter um schema é permitido; perder dado não é — e
"a migração reverteu sem erro" é exatamente como essa perda seria reportada. Além
da guarda de rótulos (§17.1), o downgrade recusa quando:

| Guarda | Cenário concreto |
|---|---|
| `outbox_events` com `dispatched_at IS NULL` | é uma publicação que o sistema deve; derrubar a tabela conclui com sucesso e o evento simplesmente nunca sai — a perda exata que a outbox existe para tornar impossível |
| amostra preservada com `baseline_ids` não vazio no envelope | a oportunidade sobrevive e a evidência não: a linha continua dizendo "é por isso" apontando para nada |

Baselines que **nenhuma** amostra preservada referencia não são protegidas: são
recomputáveis a partir dos `feature_snapshots`, e recusar por causa delas tornaria
o downgrade impossível em qualquer banco que o scanner já tenha tocado. É perda
aceita e recuperável, registrada aqui em vez de descoberta depois.

### 17.8 Seeds

**`feature_definitions` é derivado do registry da T2.2, nunca redigitado.** O seed
chama `hunter_indicators.features.default_definitions_rows()`, cujo `as_row()`
devolve exatamente as colunas da tabela (`name`, `version`, `category`,
`parameters`, `description`, `inputs`); `seed_reference.feature_definition_rows()`
só repassa e `seed.py` acrescenta o `id` (UUID v7 da aplicação). **v1: 28
features.**

O motivo de não haver segunda cópia: `feature_snapshots.feature_set_version` é o
hash das próprias identidades que essas linhas guardam (chave, `version`,
`category`, `inputs`, `parameters`). Uma lista escrita à mão ao lado do registry
não é documentação, é uma segunda verdade — e as duas já tinham divergido: **20
das 28 chaves ficaram órfãs de um lado ou do outro** (o seed dizia `volatility` e
`volume_relative`, o registry publica `atr_14_pct` e `relative_volume_5m`; o seed
falava o vocabulário `candles_1m`/`book_20`, o registry fala `candles:1m`/`book:20`).
Uma tabela assim descreve um motor que ninguém rodou.

`parameters` **deixa de ficar no default `{}`**: as janelas, períodos e limiares
vêm canonicalizados do registry (números como *string* JSON, como em todo o resto
do seed), que é onde foram de fato calculados — a razão para deixá-los vazios era
não inventar número, e derivar não inventa nada. `inputs` continua nomeando as
fontes que cada calculadora pode ler (o que permite revisar look-ahead), agora no
vocabulário real do build (`candles:1m`, `candles:1m:forming`, `book:20`,
`trades`, `deriv:funding`, `deriv:oi`, `deriv:history`, `state:atr_15m`).

**Uma `(name, version)` publicada é congelada, como um vetor de pesos.** O seed
insere o que falta, **verifica** o que existe e **para** quando a identidade
armazenada difere da que este build publica — mudança de fórmula é `version` nova
no registry, que entra como linha nova ao lado da antiga, e sobrescrever faria a
tabela mentir sobre todo snapshot que citou aquela identidade. Fora da comparação
fica só `description`: é prosa, o próprio hash do conjunto a exclui de propósito
(reescrever texto não pode invalidar snapshot), então ela é atualizada no lugar.
Rodar o seed duas vezes não reescreve nenhuma linha — o teste de integração
compara `xmin`, não contagem de linhas.

Este documento **não lista as 28 chaves**: listá-las aqui recriaria a divergência
que a derivação acabou de fechar. A lista viva é
`hunter_indicators.features.DEFAULT_REGISTRY`. As features `Cross` de
`PIPELINE.md` §2 (`btc_correlation_1h`, `market_beta_1h`,
`relative_strength_vs_btc_1h`) **continuam fora**: não estão na entrega da T2.2 e
portanto não estão no registry.

O seed passa a depender de `hunter-indicators`, e depende onde roda: é membro do
workspace `uv` (`pyproject.toml` raiz), `uv sync --all-packages` o instala no venv
da imagem e `Dockerfile.api-workers` copia `packages/indicators` — a mesma imagem
serve `HUNTER_COMMAND=migrate` e `HUNTER_COMMAND=seed` (`infra/docker/entrypoint.sh`).

**`opportunity_weights` v2 ativo, v1 inativo.** A v1 continua com a sua forma
plana; a v2 é aninhada (`components`, `early_movement`, `normalization`, `stage`,
`status`, `expiry`, `baseline_gate`, `precision`) porque a decisão conjunta manda
os limiares de estágio morarem em `weights["stage"]`, "versionados, nunca
hardcoded", e um mapa plano não distinguiria um peso de componente de um limiar. A
forma é lida por versão, nunca adivinhada.

**Conteúdo de uma versão publicada é congelado, como em `strategy_versions`
(§16.1).** Toda `opportunities.weights_version` nomeia um vetor; se o seed
reescrevesse os números sob o mesmo nome, todo score já explicado por ele mudaria
de significado em silêncio. Então `infra/scripts/seed_weights.py` **insere** uma
versão ausente e **verifica** uma existente, e uma divergência para o seed com a
instrução de publicar versão nova. Regressão concreta que isso fecha: a T2.4
ratifica a v2 e grava `components_frozen: true`, e o deploy seguinte devolveria
`false` sem que ninguém visse.

A troca de versão ativa fica no **seed**, não na migração, e acontece **uma vez**:
a decisão vem do `INSERT ... ON CONFLICT DO NOTHING ... RETURNING`, isto é, só
promove quem de fato *criou* a linha. Basear isso num `SELECT` anterior seria
sujeito a corrida — entre a leitura e a escrita, um operador pode ter criado a
versão inativa de propósito, e o seed a promoveria por cima da escolha dele. Com
`DO NOTHING`, quem criou primeiro ganha e esta execução não promove nada. A
aposentadoria da anterior e a ativação da nova são duas instruções nessa ordem na
mesma transação (o índice parcial único obriga). Uma versão ativa fora de
`seed_reference.PROMOTED_FROM` nunca é rebaixada: tirar o perfil vivo de um scorer
em operação não é decisão de script de deploy.

`infra/scripts/seed.py` passou a ter dois módulos irmãos por causa do orçamento de
350 linhas: `seed_reference.py` (conteúdo, sem IO — literais mais o catálogo de
features derivado do registry) e `seed_weights.py` (a parte do seed que não é
upsert simples; `feature_definitions` segue a mesma regra dentro de `seed.py`).

**Desvio registrado, a ratificar pela T2.4.** A decisão conjunta fixa a aritmética
(`Σ pesos_i = 0,90`, Agent Consensus 0, Early-Movement assinado ±10 fora da soma,
`score = clip(Σ w_i·c_i + 10·e, 0, 100)`) mas deixa explicitamente os **pesos
individuais** para congelar antes de implementar a T2.4. O brief da T2.1 exige v2
ativa. A v2 semeada resolve o conflito assim: tudo que a decisão fixa vai como
está; o vetor de componentes é o da v1 com `agent_consensus` zerado e os 0,05
restantes retirados de `anomalies` — o componente cujo sinal já é contado duas
vezes no M2 (dirige o status `ANOMALY` e as confirmações de EARLY) — e a linha
carrega `components_frozen: false`. **T2.4 ratifica esse vetor ou publica uma v3**;
enquanto isso não acontece, nenhum score foi produzido por ele (o scorer é a
própria T2.4).

**`strategy_versions` é a terceira coisa congelada do seed**, ao lado de
`feature_definitions` e `opportunity_weights` — e a única das três em que uma
divergência **não** para o seed. A regra e o motivo estão em §16.1; o que fica
aqui é a consequência para o seed como um todo: ele é idempotente também em banco
que já ativou versão. O teste que fixa isso é
`packages/core/tests/integration/test_schema_seed_and_partitions.py::test_the_seed_never_touches_an_activated_strategy_version`,
que ativa uma versão do jeito que o script de ops ativa (`status`, `activated_at` e
um `code_ref` novo), roda o seed **duas vezes** e compara `xmin` — contagem de
linha não enxerga reescrita — da linha congelada, de `feature_definitions` e de
`opportunity_weights`, enquanto verifica que as oito tabelas continuam com as
mesmas linhas de antes da ativação e que o seed relatou o que o banco de fato
guarda.

### 17.9 Pooler

Nada nesta revisão depende de estado de sessão: sem prepared statement de sessão,
sem `LISTEN/NOTIFY`, sem advisory lock de sessão. O único GUC envolvido,
`app.baseline_retention`, é lido com `NULLIF(current_setting(..., true), '')` e
escrito com `SET LOCAL`, exatamente como `app.current_org` (§15.4).
