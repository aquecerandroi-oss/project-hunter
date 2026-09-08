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
| `outbox_events` | — | despachadas há mais de **7 d** (`dispatched_at IS NOT NULL AND dispatched_at < now() - interval '7 days'`); pendentes **nunca** são apagadas | `analytics-worker` diário, DELETE em lotes (M5) |
| `shadow_outbox` | — | idem, enquanto a fila existir (§17.5 a absorve) | idem |

**As duas filas de outbox não são particionadas — são podadas.** Elas são fila,
não histórico: o volume é alto (o market-worker sozinho enfileira da ordem de
**700 mil linhas/dia**, medido no stack local com 200 mercados) mas a vida útil
de cada linha é curta, e o predicado de poda (`dispatched_at`) não é o mesmo por
onde se lê (`dispatched_at IS NULL`), então um `DROP` de partição não expressa a
retenção. O job diário chama
`hunter_core.events.outbox_store.prune_dispatched(session, older_than, batch)`
em laço até ele devolver menos do que pediu — `DELETE` em lotes de 5 mil, **em
ordem de `id`**, para não segurar lock nem gerar WAL de um dia inteiro numa
transação só, numa tabela em que o despachante está escrevendo ao mesmo tempo.

**Ordem de `id`, não de `dispatched_at`** (revisão T2.9b da Astra; esta seção
dizia "ordenados pelos mais antigos"). `dispatched_at` não tem índice e não vai
ter: ele seria mantido em todo `mark_dispatched`, isto é, no caminho quente do
despachante, e cobriria toda linha despachada que a retenção de 7 dias ainda
guarda (~5 milhões a 700 mil/dia) para servir um job que roda uma vez por dia.
Ordenar por ele fazia de cada lote um **Seq Scan da tabela inteira mais um
sort**. `id` é `BIGSERIAL`, portanto ordem de inserção, e o lote é uma *fatia
limitada* do conjunto podável, nunca um ranking: toda linha que ele devolve já
satisfaz o predicado de retenção, então qual sai primeiro não muda nada. O
índice da PK já existe e a varredura para em `batch` linhas — provado por
`EXPLAIN` em
`test_outbox_integration.py::test_prune_takes_its_batch_from_an_index_and_never_a_seq_scan`.
O custo declarado: linhas pendentes na cabeça da PK são revarridas por todo
lote, sem nunca qualificar — conjunto limitado pelo alarme de prontidão (500).

Duas regras que o `WHERE` carrega e não são negociáveis:

- **linha pendente nunca é podada, com qualquer idade.** `dispatched_at IS NULL`
  é uma publicação que o sistema deve; apagá-la é exatamente a perda silenciosa
  que a outbox existe para tornar impossível (é a mesma razão pela qual o
  downgrade da `0003` recusa, §17.7);
- **os 7 dias são o teto da janela de replay.** `reconcile(since=...)` só
  alcança linha que ainda esteja na tabela, então essa retenção é o que faz
  "sabemos reencher um stream perdido de até uma semana atrás" ser verdade e
  "de um mês atrás" ser mentira. Aumentar a janela de replay é aumentar este
  prazo, nunca o contrário.

O job em si é do analytics-worker e chega no **M5**; até lá a função pura existe,
tem teste e não é chamada por ninguém em produção — registrado aqui para que a
lacuna seja um item de plano e não uma descoberta.

**Duas formas de partição.** Seis tabelas são RANGE mensal simples (`audit_logs_2026_09`). `candles` e `portfolio_equity_snapshots` são particionadas primeiro por LIST (`timeframe` / `resolution`) e cada nível desses por RANGE mensal, produzindo folhas como `candles_1m_2026_09`. O motivo é a própria coluna "Retenção": as retenções diferem por timeframe, e com uma única RANGE mensal expirar 1m aos 90 dias exigiria `DELETE` linha a linha dentro de partições que também guardam o 1h que se mantém para sempre — reescrevendo e inchando exatamente os dados que queremos preservar. Com o nível LIST, expirar é `DROP TABLE candles_1m_2026_05`.

O nível LIST é criado para **todos** os rótulos de `candle_timeframe`, não só os que a ingestão escreve hoje: uma linha sem partição é recusada, e uma escrita recusada é indisponibilidade, não aviso.

Partições são criadas com 3 meses de antecedência por `infra/scripts/create_partitions.py`, agendado no analytics-worker. Uma partição faltante gera `system_event` de severidade `critical`. A contrapartida é `infra/scripts/prune_partitions.py`, que faz `DETACH` + `DROP` de cada partição cuja **borda superior** já passou da janela de retenção — nunca de uma que ainda possa conter linha retida — e é idempotente porque lê as partições existentes em `pg_inherits` em vez de gerá-las pelo calendário.

**E com 2 meses de atraso (`--months-behind`, T2.5f).** O job só olhava para a frente, e histórico entra pelo passado: um pedido de backfill de 7 dias feito em 06/09 nomeia minutos de agosto, nenhuma partição os aceitava, e o consumidor do market-worker recusou **3 300 de 8 547 minutos** com `market_backfill_refused reason=no_partition` (`.claude/state/notes-T2.5.md` §31). O padrão é **2** porque a janela mais larga que alguém pede é de 30 dias (replay/β; o bootstrap de baselines pede 7), e **um mês para trás não basta sempre**: 30 dias contados a partir de 1º de março caem em **30 de janeiro** — fevereiro é curto —, então um único mês para trás recusaria os dois dias mais velhos desse pedido, que é exatamente o `no_partition` que esta política existe para eliminar. Dois cobrem no mínimo 59 dias de passado (rodando no dia 1º) e ~92 no melhor caso: 30 dias em qualquer mês do calendário, mais margem para um pedido cuja janela termina alguns dias no passado — uma lacuna detectada tarde, um replay de um trecho mais antigo, um dia em que o job não rodou.

**Criar e podar não podem brigar: a janela de retenção do pai tem de ser ≥ meses para trás + 1.** Um mês para trás é criado **somente enquanto a retenção ainda o mantém** — a decisão é a mesma função (`is_expired`, sobre a **borda superior**) que o podador usa, agora em `infra/scripts/partition_retention.py` e lida pelos dois jobs, em vez de duas cópias da tabela de retenção. Sem essa trava, `market_snapshots` (30 d) ganharia uma partição às 04:07 e a perderia às 04:12, todo dia, cada lado tomando `ACCESS EXCLUSIVE` na pai por nada. A regra vale **por pai**, não globalmente, porque as janelas diferem: `candles_1m` (90 d) recebe os dois meses para trás em **qualquer** dia do ano — a borda superior do mês retrasado é o dia 1º do mês anterior, no máximo ~62 dias atrás, sempre dentro de 90 (não é "90 d ≥ 3 meses", que seria falso em jan–mar) — e é o pai que o backfill de fato escreve; já `market_snapshots`/`liquidations` (30 d) recebem o mês anterior só enquanto ele estiver dentro da retenção, e `feature_snapshots` (14 d) deixa de receber passado a partir do dia 15. Nada disso apaga o que o backfill acabou de encher: o mês que o podador derrubaria é justamente o que o criador não cria.

**A promessa vale no mesmo instante**, e é assim que ela é verdadeira (revisão da Astra deste diff). A retenção é contada em dias inteiros, então a expiração de um mês vira à meia-noite UTC: 04:07 → 04:12 não cruza a borda, 23:59 → 00:01 cruza. Um plano montado antes da virada e podado depois pode criar um mês que a poda seguinte derruba — **uma vez**, e o próprio plano do dia seguinte já não o contém. Não é perda de dado: o que é derrubado nesse caso é justamente um mês cuja última linha retida acabou de expirar.

`funding_rates` e `open_interest_history` **não são particionadas** (§4), então backfill de funding e de open interest nunca depende deste job — não há nada a provisionar para elas.

Tudo continua idempotente e sem trava longa: só `CREATE TABLE IF NOT EXISTS ... PARTITION OF` de partições **vazias** (nunca `ATTACH` sobre dados), uma transação por pai, `lock_timeout = 3s`. Os meses para trás são criados no nível que de fato os possui — o nível LIST (`candles_1m`, `candles_5m`, …, `portfolio_equity_snapshots_1m`, …), nunca na raiz —, que é a mesma estrutura LIST-depois-RANGE descrita acima; **não há sub-partição por hash em lugar nenhum do schema**. O planejamento mora em `infra/scripts/partition_plan.py` — `create_partitions.py` passou de 341 para além do orçamento de 350 linhas com esta mudança e o *plano* saiu do *executor*; o script reexporta `planned_groups`/`planned_statements`, que são o que os testes carregam por caminho.

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
- **Migração não tem `lock_timeout`.** `env.py` roda cada revisão numa
  transação sem prazo de espera por trava (o `statement_timeout` do §1.2a é da
  aplicação, não do migrador), então uma revisão que precise de `ACCESS
  EXCLUSIVE` numa tabela quente pode enfileirar todo escritor atrás de um
  leitor longo. Nenhuma revisão até a `0005` depende disso: a `0001` cria o
  schema, a `0002`/`0003` mexem em tabelas ainda frias, a `0004` reconstrói os
  índices com `CONCURRENTLY`, sem tomar trava sobre uma construção (§17.5), e a
  `0005` é um `GRANT`, que **não trava a relação** (medido: dentro da transação
  do `GRANT`, `pg_locks` não tem nenhuma linha para `feature_baselines`; o que é
  travado é o catálogo). A
  primeira revisão que precisar de uma trava longa numa tabela quente é que
  traz o `SET LOCAL lock_timeout` — e traz junto a decisão de que uma janela de
  manutenção é aceitável ali.
  **`0006`–`0009` seguem o mesmo padrão** (colunas/triggers/grants sobre
  tabelas que na VPS têm poucas linhas — `strategy_versions`,
  `trade_proposals`, `positions` — ou `GRANT`s puros). **A `0010` é a primeira
  a tomar `ACCESS EXCLUSIVE` de fato**: `ADD COLUMN` + `ADD CONSTRAINT CHECK` +
  `DROP`/`CREATE TRIGGER` sobre `strategy_versions`, tudo numa única transação,
  rodando na VPS com `api`/`market-worker`/`strategy-worker` de pé
  (`docker compose run --rm migrate`, `docs/DEPLOYMENT.md`); o pior caso
  medido é a `statement_timeout` de 15 s do §1.2a cortando um leitor que ficou
  na fila atrás do `ALTER TABLE` — aceito porque `strategy_versions` tem uma
  linha por estratégia semeada (dezenas), não porque a trava é curta. **A
  `0011` volta a ser só `GRANT`/`REVOKE`** (nenhum DDL sobre a relação), então
  não abre essa janela.
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
`code_ref`, `parameters_schema`, `default_parameters`, `params_format`,
`activated_at` e, desde a `0010`, `purpose` (§22.2) — **inclusive
`SET activated_at = NULL`**, que de outro modo descongelaria a linha — em
qualquer `status` (ativa, deprecated, reativada). A lista viva desta trigger
mora em `ddl/strategy_purpose.py:_FROZEN_COLUMNS_0010`, não mais em
`ddl/shadow.py` (que continua congelada como a `0002` a deixou, §17.1).
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
  INDEX (created_at, id) WHERE dispatched_at IS NULL         -- fila do despachante (0004)
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
serve (achado da revisão da Astra) — desde a `0004` com a chave
`(created_at, id)`, a ordem em que o despachante drena, e não mais só `(id)`
(§17.5); (b) por consequência, é a
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
os papéis, inclusive o dono — e desde a `0005` (adiante) a imutabilidade é
**dele sozinho**, não mais do trigger *mais* a ausência de grant. Não é perda:
nenhum `REVOKE` alcança o dono da tabela, então o trigger sempre foi a fechadura
mais forte das duas, e é a única que continua valendo para todo papel.
`DELETE` **não** é proibido — retenção precisa
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

**O lock exige o privilégio de `UPDATE`, e é a `0005_baseline_lock_grant` que o
concede (BUG-1 da T2.5).** O protocolo acima esteve **inexecutável** entre a
`0003` e a `0005`: o PostgreSQL exige `UPDATE` para tomar qualquer lock de linha
(`ACL_SELECT_FOR_UPDATE` *é* `ACL_UPDATE`), e a `0003` negava `UPDATE` a
`hunter_worker` de propósito.

**Correção de fato (T3.1b, medida):** esta seção afirmava também que "um grant
por coluna não serve — um row mark não tem coluna atualizada, então a verificação
cai no `pg_class_aclcheck` de tabela". **É falso.** Em Postgres 16.15,
`GRANT SELECT, UPDATE (uma_coluna)` é suficiente para `SELECT ... FOR UPDATE` e
continua recusando qualquer `UPDATE` que escreva valor:

```sql
GRANT SELECT, UPDATE (updated_at) ON t TO r;
SET ROLE r; SELECT v FROM t WHERE id = 1 FOR UPDATE;   -- 1 linha
SET ROLE r; UPDATE t SET v = 99 WHERE id = 1;          -- permission denied
```

A `0005` **não muda**: o grant de tabela em `feature_baselines` é inofensivo
porque a imutabilidade ali mora inteira num trigger que vale até para o dono, e
mexer numa revisão aplicada é outra conversa. O que muda é a justificativa — e a
§18.7 usa a forma estreita (`UPDATE (updated_at)`) onde ela de fato importa, numa
tabela cujo conteúdo o papel da aplicação não pode escrever. Contra um banco corretamente migrado, o passo 2 falhava com
*permission denied for table feature_baselines* — e uma falha de privilégio
**aborta a transação inteira**, então o scanner sonda uma vez na partida
(`hunter_scanner_worker.writers.probe_baseline_lock`), loga em `error` e degrada
para uma leitura de existência: a amostra cuja baseline sumiu continua não sendo
gravada, mas a serialização contra o `DELETE` da retenção se perde.

A correção é o grant, e **conceder `UPDATE` não torna uma revisão editável**: o
trigger `feature_baselines_immutable` recusa todo `UPDATE` para todo papel,
dono incluído. O que faltava era exatamente a parte do protocolo que o trigger
não sabe expressar — o lock. A lista fica congelada por revisão como todas as
outras (`ddl/baseline_lock.py`, `BASELINE_LOCK_TABLES_0005`); a `0003` continua
descrevendo o schema que ela construiu. O `downgrade` da `0005` revoga só esse
privilégio (nunca `REVOKE ALL`), então um banco revertido para a `0004` volta a
poder criar e expirar baselines — e volta a degradar, dizendo isso no log.
Provado como o papel, não perguntado ao catálogo:
`test_schema_privileges.py::test_the_worker_can_actually_take_for_share_on_a_baseline_row`
e `test_schema_analysis.py::test_the_worker_can_lock_a_baseline_row_and_still_cannot_rewrite_it`
(o `FOR SHARE` passa, o `UPDATE` ainda levanta pelo trigger).

**Pendência do lado do scanner (T2.5), declarada e não corrigida aqui.** A sonda
continua no código e agora devolve `True`, então
`services/scanner-worker/tests/test_persistence.py::test_the_row_lock_is_probed_once_and_its_absence_is_reported`
— que afirma `allowed is False` e cujo comentário pede "atualize a nota em
`probe_baseline_lock`" quando o grant chegar — **falha por passar** contra o
head. É o sinal desejado (mesmo padrão do `xfail(strict=True)` da T2.5 §7) e o
conserto é do dono de `services/**`: inverter a asserção e reescrever o
docstring de `writers.probe_baseline_lock`. A sonda em si vale a pena manter —
ela é o que distingue um banco na `0004` de um banco no head sem custar uma
transação de escrita.

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
  INDEX (created_at, id) WHERE dispatched_at IS NULL   -- ix_outbox_events_pending (0004)
  CHECK attempts >= 0, CHECK char_length(stream) > 0
```

**O índice parcial é `(created_at, id)`, não `(id)` (`0004_outbox_pending_index`).**
O predicado nunca esteve errado; a chave estava. `claim_pending` ordena por
`(created_at, id)` — a sequence tem lacunas e a ordem dela não é a de commit,
então `id` sozinho não é ordem de nada — e um índice chaveado só em `id` até
*encontra* as pendentes, mas não as entrega ordenadas; com a ordenação
inevitável, o planner deixa de usar o índice. Medido com `EXPLAIN ANALYZE` do
claim real (Postgres 16, 30 mil pendentes): com `(id)` é **Seq Scan nas 30 mil
linhas + quicksort de 3,5 MB, 15,255 ms**; com `(created_at, id)` é **Index
Scan que para nas 20 linhas pedidas, 0,237 ms**. No teto de
prontidão (500 pendentes) a diferença é ruído; ela importa exatamente quando
dói, no acúmulo que uma queda de Redis deixa para trás, que é também quando a
varredura precisa drenar mais rápido. A `shadow_outbox` muda junto pelo mesmo
motivo pelo qual as duas formas são idênticas (§16.4): deixar os índices
divergirem tornaria uma das filas silenciosamente mais lenta sem que ninguém
depois conseguisse reconstruir por quê. `ddl/outbox_index.py` é dono das duas.

**A `0004` não roda em transação: o índice é reconstruído com
`CONCURRENTLY`.** `outbox_events` é caminho de escrita quente — toda transação
de negócio do market-worker insere nela (ordem de 700 mil linhas/dia, §1.3) e o
despachante escreve a cada varredura. Um `DROP INDEX` + `CREATE INDEX` comum
toma `ACCESS EXCLUSIVE` na tabela e constrói o substituto segurando essa trava,
bloqueando **todo** produtor pelo tempo da construção; e o teto de prontidão de
500 pendentes não limita esse trabalho, porque é alarme e não limite físico e
conta só as pendentes, enquanto a construção varre a tabela inteira, histórico
despachado incluído (revisão T2.9b da Astra). A sequência, nos dois sentidos, é:

1. `CREATE INDEX CONCURRENTLY <índice>_rebuilding` — leitores e escritores
   seguem, e o índice antigo continua servindo o claim;
2. `DROP INDEX CONCURRENTLY <índice>` — a fila nunca fica sem índice utilizável;
3. `ALTER INDEX <índice>_rebuilding RENAME TO <índice>` — trava só de catálogo.

**Preço declarado: a revisão perde a atomicidade.** Nenhum dos três comandos
pode rodar dentro de bloco de transação, então `rebuild_pending_indexes` abre um
`op.get_context().autocommit_block()`, que commita o que veio antes dele. Uma
queda no meio deixa um índice `_rebuilding` para trás, possivelmente
`indisvalid = false` — por isso cada passo começa derrubando o nome de staging
com `IF EXISTS`: **reexecutar a revisão é a recuperação**, e é idempotente
inclusive por cima de uma execução que deu certo.
`test_migrations.py::test_0004_leaves_no_invalid_or_staging_index_behind` lê
`pg_index.indisvalid`, porque "o índice está lá" não prova nada sozinho depois
de uma construção concorrente. Isto substitui a nota anterior de aplicar a
revisão "numa janela de manutenção com `lock_timeout`": não há mais janela a
respeitar, e por isso nada de `lock_timeout` entrou em `env.py` (ver
"Restrições operacionais conhecidas", §15.6).

**Listas congeladas por revisão, como em §16.5.** `ddl/outbox_index.py` exporta
`PENDING_INDEXES_0004`, `DRAIN_ORDER_0004` e `LEGACY_ORDER_0004` — tuplas
congeladas que só a `0004` lê, no mesmo padrão de `ddl/tables.py`,
`ddl/shadow.py` e `ddl/analysis.py`. Enquanto eram uma lista *viva* lida em
tempo de migração, uma `0005` que acrescentasse uma fila `execution_outbox` e a
anexasse ali faria a `0004` — que tinha dois índices para reconstruir no dia em
que foi escrita — tentar reconstruir um terceiro que ainda não existe no ponto
dela na história, e falhar em **todo banco limpo** (reproduzido: `relation
"execution_outbox" does not exist`). Uma fila nova traz a sua própria tupla; a
da `0004` nunca cresce. Dois testes seguram isso:
`test_every_pending_outbox_index_belongs_to_exactly_one_revision` (as tuplas
congeladas particionam os índices parciais vivos, descobertos pelo predicado) e
`test_0004_rebuilds_exactly_the_indexes_that_existed_when_it_was_written` (em
`0003`, o banco contém exatamente o que a `0004` congelou). `PENDING_PREDICATE`
continua compartilhado e não congelado: não é lista que cresce, é a definição da
dívida (§1.3, §16.4).

**Forma idêntica à de `shadow_outbox` (§16.4), de propósito.** O Shadow Lab
entregou a sua fila na `0002` antes desta existir e o item 6 de `SHADOW-LAB.md`
exige que a absorção não perca pendências, então as colunas batem uma a uma e a
absorção é um `INSERT ... SELECT` com **lista explícita de colunas** que preserva
`event_id`, `stream`, `created_at`, `dispatched_at`, `attempts` e `last_error` e
deixa `id` ser reemitido pela sequence local. Copiar `id` entre duas filas
populadas colidiria — e não significaria nada se não colidisse: `id` é ordem de
drenagem, nunca identidade. O predicado de pendência é `dispatched_at IS NULL`,
nunca uma marca d'água sobre `id` (§16.4). A troca dos escritores (a fila antiga
continua recebendo enquanto a cópia roda) é coordenação da T2.9, não DDL.

**`payload` é a exceção: ele é embrulhado, não copiado.** As duas colunas se
chamam igual e guardam coisas diferentes. A `shadow_outbox` guarda só o payload
de negócio e a S2 monta o envelope na hora do dispatch; a `outbox_events` guarda
o **envelope inteiro**, que é o que torna a linha uma mensagem pronta e uma
republicação byte a byte a mesma coisa. Uma cópia crua produziria linhas que o
despachante genérico recusa com *payload is not an envelope* — pendentes para
sempre, contadas como inpublicáveis, nunca entregues. O statement, portanto:

```sql
INSERT INTO outbox_events
    (event_id, stream, payload, created_at, dispatched_at, attempts, last_error)
SELECT
    event_id,
    stream,
    jsonb_build_object(
        'event_id', event_id,
        'type',     stream,
        'ts',       to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US') || 'Z',
        'producer', 'strategy-worker.shadow',
        'key',      coalesce(nullif(payload ->> 'symbol', ''), event_id::text),
        'payload',  payload
    ),
    created_at, dispatched_at, attempts, last_error
FROM shadow_outbox;
```

| Campo do envelope | De onde vem | Por quê |
|---|---|---|
| `event_id` | a própria coluna | a identidade **se preserva**; é o ponto inteiro de não perder pendência |
| `type` | `stream` da linha | é o mesmo conceito com outro nome |
| `ts` | `created_at` | o `ts` histórico **não existe**: a S2 o gerava no dispatch, então para uma linha que nunca despachou não há o que recuperar. `created_at` é o substituto honesto e estável — mas é o `now()` do Postgres, ou seja o **início da transação**, não o instante do commit (Astra, revisão T2.9b). Fica registrado como substituto em vez de passado por original |
| `producer` | `PRODUCER` da S2 (`strategy-worker.shadow`) | foi quem produziu |
| `key` | `payload->>'symbol'`, senão o `event_id` | repete a heurística de roteamento da S2 (`payload.get("symbol") or event_id`), para que o roteamento depois da absorção seja idêntico ao de antes. A equivalência vale para símbolo textual, string vazia e ausência; **não** para um `symbol` que seja `false`/`0` em JSON, que o Python trataria como falso e o `->>` devolve como texto — nenhum produtor da S2 escreve isso, e está registrado aqui em vez de suposto |
| `payload` | o payload legado, um nível abaixo | `payload -> 'payload' ->> 'symbol'`, como em qualquer linha nativa |

`test_schema_analysis.py` executa **este** statement e depois passa a linha
resultante por `hunter_core.events.outbox_event.envelope_from_row` — a mesma
função que `dispatch_pending` chama antes do `XADD` —, conferindo campo a campo.
Provar só que as colunas batem não provaria nada: o que a absorção precisa
garantir é que a linha absorvida é *despachável*.

**Duas condições operacionais que o statement sozinho não dá** (Astra, revisão
T2.9b), e sem as quais a absorção perde pendência:

1. **Parar os escritores, não só o despachante.** Drenar a fila com o
   `dispatch_once` da S2 e depois copiar deixa uma janela: uma transação da S2
   que commita *depois* do snapshot da cópia insere uma linha que a cópia não
   viu e que o `DROP TABLE` seguinte apaga. O corte é: trocar o `enqueue` da S2
   pelo genérico (ou parar o worker), **esperar as transações em voo**, só então
   rodar a cópia final, e só então derrubar a tabela.
2. **O statement não é reexecutável depois de um sucesso parcial.**
   `outbox_events.event_id` é `UNIQUE`, então uma segunda passada aborta em
   colisão. Isso é a proteção funcionando, e a saída **não** é acrescentar um
   `ON CONFLICT DO NOTHING` genérico, que esconderia tanto a linha já copiada
   quanto uma colisão real de identidade: rode a cópia uma vez, dentro de uma
   transação, e reconcilie por contagem antes de derrubar a fila antiga.

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
`SELECT`/`INSERT`/`DELETE` para `hunter_worker` e, **na `0003`**, `UPDATE` para
ninguém. Não é a classe append-only do §15.6 (que também proíbe `DELETE`, porque
trilha de auditoria não é podada) — baselines *são* podadas, no mesmo prazo das
amostras que dependem delas.

**Correção da `0005_baseline_lock_grant` (BUG-1 da T2.5).** Esta seção dizia que
negar `UPDATE` no grant eram "duas fechaduras independentes na mesma porta", ao
lado do trigger. Eram uma fechadura na porta e outra no batente: o trigger já
recusava todo `UPDATE` para todo papel — inclusive o dono, que nenhum `REVOKE`
alcança —, enquanto a ausência do grant não protegia a escrita e **impedia o
lock de linha** que o próprio §17.2 manda o escritor tomar (o PostgreSQL exige
`UPDATE` para `FOR SHARE`/`FOR UPDATE`). A `0005` concede `UPDATE` em
`feature_baselines` a `hunter_worker` **para travar linha, não para escrever**;
a imutabilidade fica inteira no trigger. Nada muda para `hunter_app`, que segue
só com `SELECT`.

| Classe | Revisão | Papel | Privilégios |
|---|---|---|---|
| `APP_WRITE_TABLES` | `0001` | `hunter_app` | `SELECT`/`INSERT`/`UPDATE`/`DELETE` |
| `APP_NO_DELETE_TABLES` | `0001` | `hunter_app` | `SELECT`/`INSERT`/`UPDATE` |
| `APP_READ_ONLY_TABLES` (+ `SHADOW_*`, `ANALYSIS_APP_READ_ONLY_TABLES`) | `0001`–`0003` | `hunter_app` | `SELECT` |
| `APPEND_ONLY_TABLES` | `0001` | ambos | `SELECT`/`INSERT` |
| `WORKER_DELETE_TABLES` | `0001` | `hunter_worker` | `DELETE` (só `organizations`/`users`) |
| `WORKER_WRITE_TABLES`, `SHADOW_WORKER_WRITE_TABLES`, `ANALYSIS_WORKER_WRITE_TABLES` | `0001`–`0003` | `hunter_worker` | `SELECT`/`INSERT`/`UPDATE`/`DELETE` — **exceto `strategy_versions`** desde a `0010`/`0011` (nota abaixo) |
| `ANALYSIS_WORKER_APPEND_TABLES` | `0003` | `hunter_worker` | `SELECT`/`INSERT`/`DELETE` |
| `BASELINE_LOCK_TABLES_0005` | `0005` | `hunter_worker` | `+ UPDATE` **só como lock** (`ddl/baseline_lock.py`) |

A última linha não é uma classe nova de tabela: é um privilégio acrescentado a
uma tabela que a `0003` já classificou, e
`test_migrations.py::test_0005_touches_no_table_0003_had_not_already_classified`
é o que impede que ela vire a porta de entrada de uma tabela sem classificação —
o teste de partição de §15.6 é sobre as classes do `hunter_app` e não veria um
grant só do worker. A partição continua exata.

**Nota sobre `strategy_versions` (desde a `0010`, estreitada pela `0011`,
§22.3/§23).** A linha de `WORKER_WRITE_TABLES` acima descreve o que `0001`
concedeu — a tabela continua nessa classe para fins de classificação, e
`test_the_grant_lists_cover_every_table_exactly_once` continua vendo-a lá —,
mas o privilégio efetivo de `hunter_worker` não é mais o de tabela: a `0010`
revogou `INSERT`/`UPDATE` de tabela e regrantou por coluna, exceto `purpose`; a
`0011` foi além e revogou também `INSERT` por completo, `DELETE` de tabela e
`UPDATE` nas colunas do ciclo de ativação (`status`, `activated_at`,
`deprecated_at`, `code_ref`, `parameters_schema`, `default_parameters`,
`params_format`). O que sobra é `UPDATE` em `id`, `strategy_id`, `version`,
`changelog`, `created_at` — nenhuma delas escrita por código de produção como
`hunter_worker` hoje. **Nunca reconceder no nível de tabela**: um `GRANT INSERT,
UPDATE, DELETE ON strategy_versions TO hunter_worker` "consertando" uma
divergência aparente contra esta tabela reabre tudo que a `0010`/`0011`
fecharam, porque a ACL de coluna é a **união** com a de tabela.

**Orçamento de nome de revisão: 32 caracteres.** `alembic_version.version_num` é
`VARCHAR(32)`; o id `0005_feature_baselines_lock_grant` (33) rodou a revisão
inteira e só então falhou no `UPDATE alembic_version` com *value too long*. Daí
o nome curto `0005_baseline_lock_grant`.

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

## 18. Carteira virtual e Risk Engine — M3 (`0006_paper_wallet`)

Sexta revisão. Entrega o estado durável do Milestone 3 (tarefa T3.1) conforme a
**"Decisão conjunta Claude ⇄ Astra (2026-09-06)"** de `docs/plans/M3.md`, que
prevalece sobre o resto daquele plano, e o contrato `docs/RISK_ENGINE.md` **v2**.
Seis tabelas novas: duas globais e imutáveis (`fx_observations`, `market_betas`)
e quatro de tenant (`portfolio_currency_anchor`, `portfolio_risk_state`,
`portfolio_exit_intents`, `participation_consumptions`).

A regra que organiza tudo o que vem abaixo: **a diretiva do Everton proíbe aporte
e reset**, e uma proibição que só existe em prosa é uma proibição que o primeiro
`DELETE` derrota. Cada seção diz qual frase da diretiva virou constraint, índice
ou trigger — e, quando não deu para virar, diz isso também em vez de deixar o
leitor supor.

**A `0006` foi corrigida no lugar, antes de qualquer aplicação persistente
(T3.1b).** A revisão de segurança de `11faba8`
(`.claude/state/review-T3.1-security.md`) achou dois bloqueantes, cinco "deve
corrigir" e cinco sugestões, cada um reproduzido como `hunter_app`/`hunter_worker`
reais. Como a `0006` **nunca** tinha sido aplicada a banco persistente nenhum — a
VPS e o stack local estavam os dois em `0005_baseline_lock_grant`, verificado
antes da edição —, a correção foi na própria revisão e não numa `0007`, pelo
mesmo motivo e com o mesmo limite que a §15 registra para a
`0001_initial_schema`: uma revisão que nunca rodou em lugar nenhum **descreve** um
schema, e o schema tem de ser o certo para quem o ler a seguir. A partir do
primeiro deploy real dela essa liberdade acaba. O que mudou está espalhado pelas
seções abaixo, cada uma marcada com o achado que a moveu:

| Achado | Onde | O que passou a ser verdade |
|---|---|---|
| bloqueante 1 | §18.7 | a transição que autoriza um movimento do kill switch tem de ser a **mais recente** do escopo **e** ter sido escrita **nesta transação** |
| bloqueante 2 | §18.5, §18.8 | a carteira principal é única por **organização**, não por `(organização, workspace)` |
| deve 3 | §18.7 | a mesma constraint trigger em `organizations`, com `scope = 'organization'` |
| deve 4 | §18.3 | `orders.position_id`, `trades.position_id` e `trades.proposal_id` compostos, e `orders.exit_intent_id` amarrado ao `position_id` da intenção |
| deve 5 | §18.7, §18.9 | `portfolio_risk_state` recusa todo `UPDATE` do `hunter_app`; dia crescente, referência do dia uma vez por dia, pico ≤ equity observado |
| deve 6 | §18.2 | a âncora confere o **par** da observação de FX |
| deve 7 | §18.8 | `paper_v1` tem **uma** fonte: `hunter_risk.limits.PAPER_V1` |
| sugestão 8 | §18.5 | `released ≤ reserved_notional` da própria proposta |
| sugestão 9 | §18.7 | transição automática sem `evidence` é irrepresentável |
| sugestão 10 | §18.7 | `kill_switch_transitions` sem FK em cascata: a trilha sobrevive ao tenant |
| sugestões 11 e 12 | §18.3, §18.9 | declarações, registradas onde já moram |

E três escapes que a **revisão da Astra sobre esta própria correção** reproduziu,
fechados antes de ela ficar de pé: uma CTE que escrevia o filho antes do pai
pulava o teto do pico; `equity_day_start` participava do teto que ele mesmo
deveria respeitar; e `current_user = 'hunter_app'` é nome, não privilégio — um
papel que apenas herda a role atravessava o trigger. As três estão na §18.7, com
o experimento que mede cada uma. A terceira corrige de quebra uma afirmação
errada da §17.2 sobre grant por coluna.

### 18.1 Enums (`ddl/enums.py`)

Tipos novos, congelados em `PAPER_ENUMS`: `proposal_source` (`manual|agent`),
`reservation_state` (`none|held|consumed|released|expired`), `exit_intent_state`
(`open|blocked_residual|fulfilled|superseded|voided`) e
`participation_entry_kind` (`reserved|executed|released`). `exit_reason` é
**reusado** para o motivo de uma intenção de saída em vez de duplicado: ele já
soletra stop/alvo/invalidação/manual/kill switch/risk event, que é exatamente
esse vocabulário (§1, "um ENUM por conceito").

`proposal_source` nasce com dois membros e **sem** `shadow_bridge`: a decisão
conjunta deixa a ponte sinal → proposta para o M4 (item 9), e um rótulo é uma
promessa de que algo existe. `manual` é a única origem viva no M3; `agent` entra
congelado como a interface que a T3.12/M4 vai usar, para a ponte não precisar de
migração só para isso. **Origem não é ator**: quem pediu continua sendo
`agent_id` mais o ator da auditoria.

Valores acrescentados a tipos da `0001` (`PAPER_ADDED_VALUES`):

| Tipo | Rótulo novo | Posição |
|---|---|---|
| `risk_preset` | `paper_v1` | `BEFORE 'custom'` (todo preset nomeado precede o coringa) |
| `risk_event_type` | `proposal_unavailable_input` | `BEFORE 'daily_loss_warning'` |
| `risk_event_type` | `participation_capped` | `BEFORE 'data_degraded_in_position'` |
| `risk_event_type` | `beta_missing` | `BEFORE 'data_degraded_in_position'` |

Os três eventos são os que o contrato v2 (§8) nomeia e o v1 não tinha, e cada um
é uma distinção que o motor precisa **publicar**, não só calcular: "reprovado por
não caber" e "não avaliado por falta de dado" são fatos diferentes (§7 do
contrato); o teto de participação é o limitante que a diretiva espera que mais
morda e que a D2 promete medir; e "sem beta validado, manter o ativo apenas em shadow" é uma
regra dele cujo disparo tem de ser visível. A ordem é parte do contrato (§17.1) e
`test_each_revision_creates_exactly_the_labels_it_froze` compara `enumsortorder`.

Mesma restrição do Postgres da `0003`: um valor acrescentado por `ALTER TYPE ...
ADD VALUE` não pode ser **usado** na mesma transação. A `0006` acrescenta os
quatro e não escreve nenhum; `paper_v1` chega ao banco por
`infra/scripts/seed.py`, depois do commit da migração.

### 18.2 O ledger: `fx_observations` e `portfolio_currency_anchor`

```
fx_observations                              (global, imutável)
  id, pair, rate NUMERIC(28,10), source, observed_at, available_at, raw JSONB, created_at
  UNIQUE (pair, source, observed_at)          -- uq_fx_observations_observation
  INDEX  (pair, available_at)                 -- ix_fx_observations_lookup
  CHECKs: rate > 0; observed_at <= available_at; pair e source não vazios

portfolio_currency_anchor                    (tenant, imutável, 1 linha por carteira)
  id, organization_id, portfolio_id (UNIQUE), origin_currency (BRL), origin_amount,
  operating_currency (USDT), credited_amount, fx_observation_id -> fx_observations (RESTRICT),
  rate, conversion_residual, rounding_policy, anchored_at
  CHECKs: origin_amount > 0; credited_amount > 0; rate > 0; conversion_residual >= 0;
          round(credited_amount * rate + conversion_residual, 10) = round(origin_amount, 10)
```

**Dois carimbos, não um.** `observed_at` é quando a corretora diz que a taxa
valia; `available_at` é quando **nós** poderíamos ter agido sobre ela. Uma
decisão das 10:00 não pode ser explicada por uma cotação que chegou às 10:02 — o
mesmo corte causal das baselines (§17.2).

**A identidade do dinheiro é um CHECK.** `origin = credited × rate + residual`,
arredondado à escala armazenada porque `credited × rate` é um produto de 20 casas
e as colunas guardam dez. Para isso a taxa é **copiada** para a âncora: um CHECK
não alcança outra tabela. E uma cópia que possa discordar da fonte é pior que
nenhuma cópia, então a trigger `portfolio_currency_anchor_matches_observation`
recusa a inserção cuja `rate` não seja a da observação nomeada.

O **resíduo** é gravado, não absorvido: absorvê-lo faria a carteira começar num
número que ninguém escolheu, e a política que o produziu (`rounding_policy`) fica
ao lado dele.

**A âncora também tem de concordar com a carteira que ela abre.** A mesma
trigger recusa (a) uma âncora para carteira sem `portfolio_risk_state` — a linha
de trava tem de existir antes, porque `SELECT ... FOR UPDATE` numa linha que não
existe não serializa nada — e (b) `credited_amount` diferente de
`portfolios.initial_capital`, ou `operating_currency` diferente de
`base_currency`. O segundo é achado da revisão de diff da Astra: sem ele duas
fontes persistidas discordavam sobre o capital de abertura, e uma reconstrução
que lesse `initial_capital` enquanto a atribuição lê `credited_amount` parte de
um número que ninguém creditou.

**E tem de ser uma cotação *deste par* (T3.1b, deve corrigir 6).** A trigger
confere `fx_observations.pair = operating_currency || origin_currency` —
`'USDT' || 'BRL' = 'USDTBRL'`, quantas unidades da moeda de origem custa uma
unidade da moeda operacional — e que a observação tem `available_at`. O que
faltava era exatamente isto: `conversion_is_exact` prova que a aritmética fecha
*consigo mesma*, não que a taxa precifica as duas moedas certas. Uma âncora
nomeando uma observação `BTCUSDT` a 60000 e copiando essa taxa passa em todos os
CHECKs e abre a carteira com "R$1,2 bilhão" — e, como a âncora é imutável, o erro
seria **permanente**. `available_at` é `NOT NULL` hoje; a condição está na trigger
mesmo assim, porque a garantia que interessa é "a abertura foi explicada por uma
cotação que dava para alcançar", e ela não pode depender de a coluna continuar
`NOT NULL` para sempre. A convenção do par é declarada aqui: **`operating ||
origin`**, e é a mesma que `hunter_core.portfolio.attribution.FX_PAIR` publica.

**O que isso *não* prova**, e a frase honesta é esta: que carteira, crédito,
âncora e auditoria nasceram no mesmo commit. A trigger exige que a linha de trava
exista, não que ela tenha sido criada na mesma transação. A atomicidade da
abertura é invariante do caminho único de escrita (T3.3), com teste.

`portfolio_equity_snapshots` ganha `fx_observation_id` **anulável**, com FK
`RESTRICT`. Anulável de propósito: FX indisponível depois da abertura deixa o
USDT apurável e o BRL **indisponível com motivo**, nunca extrapolado. `RESTRICT`
porque a observação é a explicação de um número guardado.

`fx_observations` é imutável por trigger para **todo papel, inclusive o dono** —
que é mais do que qualquer `REVOKE` promete. Consequência aceita e declarada: uma
observação nunca é apagada, nem em limpeza de tenant; são poucas linhas por
minuto e são a evidência de toda a curva em BRL.

### 18.3 A reserva, o FIFO e a identidade composta (`trade_proposals`, `orders`, `fills`)

```
trade_proposals  (+) source proposal_source NOT NULL DEFAULT 'manual'
                 (+) admission_seq BIGINT
                 (+) reservation_state reservation_state NOT NULL DEFAULT 'none'
                 (+) reserved_notional, reserved_cash, reserved_risk NUMERIC(28,10)
                 (+) reserved_slot BOOLEAN NOT NULL DEFAULT false
                 (+) reserved_until TIMESTAMPTZ
  UNIQUE (id, organization_id, portfolio_id)                 -- uq_trade_proposals_id_scope
  UNIQUE (organization_id, portfolio_id, admission_seq)      -- uq_trade_proposals_admission_seq
  INDEX  (organization_id, portfolio_id, reserved_until) WHERE reservation_state = 'held'

orders  (+) exit_intent_id UUID
  UNIQUE (id, organization_id, portfolio_id)                 -- uq_orders_id_scope
  UNIQUE (id, organization_id, portfolio_id, market_id)      -- uq_orders_id_market_scope
  FK (proposal_id, organization_id, portfolio_id, market_id) -> trade_proposals, ON DELETE SET NULL (proposal_id)
  FK (position_id, organization_id, portfolio_id, market_id) -> positions, ON DELETE SET NULL (position_id)
  FK (exit_intent_id, organization_id, portfolio_id, market_id) -> portfolio_exit_intents
  FK (exit_intent_id, position_id) -> portfolio_exit_intents (id, position_id)  -- fk_orders_exit_intent_matches_position
  CHECK purpose <> 'entry' OR exit_intent_id IS NULL
  CHECK exit_intent_id IS NULL OR position_id IS NOT NULL

trades  FK (position_id, organization_id, portfolio_id, market_id) -> positions, ON DELETE SET NULL (position_id)
        FK (proposal_id, organization_id, portfolio_id, market_id) -> trade_proposals, ON DELETE SET NULL (proposal_id)

fills  (+) execution_key TEXT NOT NULL
  UNIQUE (organization_id, execution_key)                    -- uq_fills_execution_key
  FK (order_id, organization_id, portfolio_id) -> orders, ON DELETE CASCADE

positions  UNIQUE (id, organization_id, portfolio_id, market_id)  -- uq_positions_id_scope
```

**Vigência separada do rótulo.** `status` é o que o Risk Engine **decidiu** e não
para de ser verdade; `reservation_state` é se o compromisso ainda está de pé. Uma
proposta pode ser `approved` para sempre e ter a reserva já consumida por um
fill, liberada por um cancelamento ou expirada sob a trava do portfolio. Juntar
os dois eixos é como um rótulo velho acaba segurando uma vaga que ninguém tem.

**Três dinheiros, não um.** `reserved_notional` é o que a entrada compromete de
exposição e de participação; `reserved_cash` é o que ela compromete de **caixa,
taxas incluídas**; `reserved_risk` é a perda planejada no stop, com custos.
Separar caixa de notional é a correção da Astra, com o cenário: caixa 100,
reserva de notional 100, taxa estimada 0,10 — todos os CHECKs passam e a compra
precisa de 100,10. Embutir a taxa no notional resolveria o caixa distorcendo
exposição e participação.

`reserved_risk` é **dinheiro na moeda operacional, não fração**: o teto agregado
é um percentual de um patrimônio que se move, enquanto o compromisso já assumido
é um valor. E o agregado é a soma de riscos por posição, **nunca**
`max(0, Σ assinado)` — riscos de −80 e +100 não podem virar um compromisso de 20.
Isso é invariante do motor (T3.2), não DDL, e está escrito aqui para não ser
descoberto depois.

Um eixo só **não** impede um escritor de reabrir um ciclo por `UPDATE`
(`consumed` de volta para `held`); o que o schema garante é que existe **um** eixo
por proposta, e é isso que torna `proposal_id` identidade suficiente da reserva
no ledger de participação (§18.5). Manter o ciclo único é regra do serviço de
admissão (T3.12), com teste — **e é a sugestão 11 da revisão de segurança da
T3.1b, registrada aqui como invariante da T3.12 em vez de virar DDL**: um CHECK
sobre `reservation_state` não enxerga a transição, só o valor final, e uma trigger
que proibisse `consumed -> held` proibiria junto a correção legítima de um ciclo
escrito errado dentro da mesma transação.

Os CHECKs são duas implicações e não uma bicondicional, de propósito: quantificada
se e somente se `reservation_state <> 'none'`, o que deixa `consumed`, `released`
e `expired` **guardarem os valores originais** como histórico. O que conta contra
um limite é decidido pelo estado, nunca pelas colunas irem a nulo. E
`NOT reserved_slot OR reservation_state = 'held'`: o fill **converte** a vaga
reservada na vaga da posição, e uma reserva convertida que continuasse contando
seriam duas vagas para a mesma entrada.

**`fifo_v1` é um contador de linha, não uma `SEQUENCE`.** `admission_seq` é
atribuído sob a trava de `portfolio_risk_state`, então é ordem de commit por
construção. Uma sequence do Postgres tem lacunas no rollback e a ordem dela não é
a de commit — a transação A pode pegar 10, a B pegar 11 e commitar primeiro (o
mesmo argumento que a §16.4 faz sobre `outbox_events.id`) —, e ordem de admissão
é uma promessa ao operador. O `UNIQUE` por carteira é o que faz um retry que
recupera a proposta existente **manter o lugar** em vez de tomar um segundo.

**Identidade composta descendo a cadeia.** Com FK de uma coluna só, uma ordem
podia declarar-se da organização A apontando para a proposta da B: a FK ficava
satisfeita e a RLS só olha o `organization_id` da própria linha (§15.4). Agora
proposta → ordem é pelo **quádruplo** `(id, organization_id, portfolio_id,
market_id)` — uma ordem colocada num mercado que a decisão nunca avaliou é uma
entrada sem preço vestindo uma aprovação — e ordem → fill pelo **trio**
`(id, organization_id, portfolio_id)`, porque `fills` não tem mercado próprio.
As ações de `ON DELETE` que a `0001` tinha são preservadas —
`SET NULL (proposal_id)` nomeando a coluna, porque um `SET NULL` simples também
anularia `organization_id` e `portfolio_id`, ambos `NOT NULL`.

**E descendo também pela posição (T3.1b, deve corrigir 4).** A primeira redação
parou na proposta: `orders.position_id`, `trades.position_id` e
`trades.proposal_id` continuavam FKs de uma coluna só, e o mesmo argumento vale
inteiro para elas — uma ordem da organização A apontando para a posição da B
satisfazia a FK, e a RLS só olha o `organization_id` da própria linha. Em
`trades` isso é pior que em `orders`: é a tabela que o analytics trata como a
verdade, então uma linha que atribui a posição de outro tenant a esta carteira é
um número que ninguém desfaz depois. As três passam ao **quádruplo**
`(id, organization_id, portfolio_id, market_id)`.

**A quarta amarração é entre duas colunas da mesma linha.** `exit_intent_id`
carregava o quádruplo e `position_id` não carregava nada, então as duas podiam
nomear posições **diferentes** da mesma carteira e do mesmo mercado: o fill
reduziria uma posição enquanto o `filled_qty` da intenção creditaria a proteção
da outra — as unidades desprotegidas em silêncio que a §10 do contrato existe
para impedir. Fecham duas coisas juntas: a FK
`(exit_intent_id, position_id) -> portfolio_exit_intents (id, position_id)`
(o alvo `uq_portfolio_exit_intents_id_position` já existia, §18.4) e o
`CHECK exit_intent_id IS NULL OR position_id IS NOT NULL`. **O CHECK não é
enfeite:** uma FK composta é `MATCH SIMPLE`, isto é, não é verificada quando
qualquer coluna dela é nula, então sem ele bastaria deixar `position_id` nulo
para a amarração não valer. A implicação "toda tentativa contra uma proteção
durável sabe qual posição está protegendo" é o que o CHECK declara.

**O que continua não sendo DDL, e por quê.** "Nenhuma ordem de entrada sem
proposta aprovada" (§8 do contrato) **não** virou CHECK. Um
`purpose <> 'entry' OR proposal_id IS NOT NULL` seria derrotado pela própria FK:
uma remoção de tenant faz `SET NULL (proposal_id)` e a ordem de entrada
sobrevivente violaria o CHECK, travando a remoção. Fica como invariante do
caminho único de escrita da T3.12, com teste — e registrado aqui em vez de
suposto.

`fills.execution_key` é a chave de idempotência da **execução**, escopada por
tenant pela mesma razão da chave da proposta (§15.3): ela é cunhada pelo
adaptador de um tenant, e um único global faria a reentrega do tenant A ser
engolida como duplicata do fill do B. A coluna nasce anulável, recebe
`execution_key = id::text` nas linhas preexistentes e só então vira `NOT NULL` —
backfill do que as colunas existentes **implicam**, a fronteira da `0002`. Isso é
uma **identidade legada**, não uma alegação de que aquelas linhas já tiveram
proteção contra duplicata, e a guarda de downgrade distingue as duas exatamente
por essa igualdade.

### 18.4 Intenção não é tentativa (`portfolio_exit_intents`)

```
portfolio_exit_intents                       (tenant)
  id, organization_id, portfolio_id, position_id, market_id,
  reason exit_reason, protection_key TEXT, state exit_intent_state,
  intended_qty, filled_qty, trigger_price, degraded_since, degraded_reason,
  superseded_by_id -> self (RESTRICT), closed_reason, closed_at, created_at, updated_at
  FK (position_id, organization_id, portfolio_id, market_id) -> positions (CASCADE)
  UNIQUE (id, organization_id, portfolio_id, market_id)   -- alvo da FK de orders
  UNIQUE (id, position_id)                                -- alvo da FK do sucessor
  UNIQUE (position_id, protection_key) WHERE state IN ('open','blocked_residual')
  CHECKs: intended_qty > 0; 0 <= filled_qty <= intended_qty;
          (state='fulfilled') = (filled_qty = intended_qty);
          (state='superseded') = (superseded_by_id IS NOT NULL);
          state='voided' -> closed_reason NOT NULL;
          (state IN ('fulfilled','superseded','voided')) = (closed_at IS NOT NULL);
          id <> superseded_by_id; (degraded_since IS NULL) = (degraded_reason IS NULL)
```

O cenário que a tabela existe para impedir (§10 do contrato): um stop de 10
unidades encontra 4 vendáveis; se o cancelamento do restante encerrasse a
intenção, 6 unidades ficariam abertas sem proteção, inclusive depois de um
restart. A **tentativa** continua sendo a linha de `orders` — que agora carrega
`exit_intent_id`, com identidade própria por tentativa — e a **intenção** é a
linha daqui.

**A unicidade é por proteção, não por motivo.** O primeiro rascunho usava
`(position_id, reason)`, e a Astra derrubou com um contraexemplo: uma posição de
10 com alvo A para 4 e alvo B para 6 são duas intenções `target` a preços
diferentes, e a §10 nunca pede alvo único — ela pede que a mesma unidade não seja
vendida duas vezes, o que a trava compartilhada faz. Daí `protection_key`
(`stop`, `target:1`, `target:2`, `manual`), com o preço **fora** da identidade:
mover um stop é revisão da mesma proteção, não uma proteção nova.

**`blocked_residual` é estado, não eixo separado.** É o resíduo abaixo do mínimo
negociável, contabilizado e visível, sem quitação fictícia — e não é terminal:
volta a `open` quando preço e filtros voltarem a permitir. **`voided`** é o
terminal honesto para uma intenção cuja quantidade foi liquidada por uma proteção
**concorrente** (um stop que levou a posição inteira deixa o alvo sem nada para
vender): ele existe para que nenhuma intenção precise receber um fill fictício
para chegar a `fulfilled`, que é o que a bicondicional `fulfilled = (filled_qty =
intended_qty)` impede.

`degraded_since`/`degraded_reason` andam juntos: sem livro utilizável **não se
fabrica fill** — a saída fica pendente e *marcada* degradada, com alerta, e vela
nunca fornece fill retroativo.

A FK para `positions` é pelo **quádruplo** `(id, organization_id, portfolio_id,
market_id)`. Com FK de uma coluna só, o contraexemplo da Astra: a intenção aponta
a posição certa mas declara a carteira B e o mercado ETH da mesma organização;
todas as constraints passam, o worker trava a carteira errada e segura o mercado
errado na coleta.

**A FK do sucessor é `DEFERRABLE INITIALLY DEFERRED`, e é isso que torna uma
substituição escrevível.** Trocar A por B sob a mesma `protection_key` não tem
ordem legal com a FK imediata: inserir B primeiro esbarra no único parcial (A
ainda está viva) e aposentar A primeiro aponta para um B que ainda não existe. Com
a verificação adiada para o COMMIT o protocolo é (1) aposentar A nomeando o id de
B — UUIDs são gerados pela aplicação, então o id é conhecido antes — e (2)
inserir B. A Astra levantou isso na revisão de diff; é melhor fechado aqui do que
descoberto pela T3.4.

O que o DDL **não** garante e por isso é invariante da T3.4/T3.5: que ciclos de
substituição com mais de um passo não existam (`id <> superseded_by_id` só fecha
o auto-ciclo), e que a reconciliação de intenções concorrentes aconteça na mesma
transação que a liquidação.

### 18.5 O orçamento de participação (`participation_consumptions`)

```
participation_consumptions                   (tenant, log de eventos imutável)
  id, organization_id, portfolio_id, market_id, proposal_id,
  order_id, fill_id, kind participation_entry_kind, notional, occurred_at, created_at
  FK (proposal_id, organization_id, portfolio_id, market_id) -> trade_proposals  -- NO ACTION
  FK (order_id, organization_id, portfolio_id, market_id)    -> orders           -- NO ACTION
  FK (fill_id, order_id)                                     -> fills            -- NO ACTION
  UNIQUE (proposal_id) WHERE kind = 'reserved'
  UNIQUE (proposal_id) WHERE kind = 'released'
  UNIQUE (fill_id)     WHERE kind = 'executed'
  INDEX  (organization_id, portfolio_id, market_id, occurred_at)
  CHECKs: notional > 0; (kind='executed') = (fill_id NOT NULL AND order_id NOT NULL)
```

A fórmula do contrato (§4), sobre este log:

```
disponivel = max(0, max_participation_pct × referencia
                    − Σ(executed com occurred_at > as_of − 60s)
                    − Σ(reserved − executed − released das reservas ainda 'held'))
```

A Astra percorreu a álgebra com teto de 100 e todos os efeitos dentro dos 60 s
(reserva de 80 → fill parcial de 30 → cancelamento terminal de 50 → nova reserva
de 70) e **não encontrou excesso**, com uma condição: o saldo é calculado **por
reserva**, com o histórico inteiro dela; só o executado recebe o corte móvel, e
uma reserva executável não desaparece por ter mais de 60 segundos.

**A identidade do lançamento é fechada, e o motivo é um cenário.** Na primeira
redação `fill_id` referenciava só `fills.id` e `market_id` era livre: uma execução
de 80 USDT em BTC podia ser lançada no orçamento de ETH — os 80 continuavam
disponíveis para a próxima entrada em BTC, e unicidade por fill não corrige
atribuição errada (Astra, revisão de diff). As três FKs agora prendem o
lançamento ao mercado da proposta, ao mercado da ordem e ao fill **daquela**
ordem.

**Idempotência por efeito lógico, não por UUID novo a cada tentativa.** Um
`INSERT` com id novo não deduplica evento nenhum. Os três índices parciais únicos
são a chave: uma reserva e uma liberação por proposta, uma execução por fill.
Assim um fill reentregue não gasta o minuto duas vezes, e um retry não renova
`occurred_at` para empurrar a janela de 60 s para a frente. `proposal_id` basta
como identidade da reserva **porque uma proposta tem exatamente um ciclo de
reserva** — `reservation_state` é um eixo só, numa linha só; se um dia houver
mais de um, isto passa a exigir um `reservation_id`.

**`occurred_at` acompanha o efeito durável** (o `ts` do fill para uma execução),
não a hora em que a linha foi escrita: a janela é chaveada nele, então a virada
do minuto não perdoa nada dentro dos 60 s.

`ON DELETE NO ACTION` nas três FKs é escolha, não descuido: um `DELETE FROM
orders` avulso é recusado, porque apagar um consumo executado devolve em silêncio
o orçamento daquele mercado; já uma cascata de organização passa, porque as
linhas do log vão junto no mesmo comando.

**Uma liberação devolve o que foi reservado, nunca mais (T3.1b, sugestão 8).**
`notional > 0` era o único limite de um lançamento `released`, então uma
liberação de 900 contra uma reserva de 80 era aceita e a fórmula acima devolvia
820 USDT de um minuto que aquele mercado nunca teve. Um CHECK não alcança
`trade_proposals`, então é a trigger
`participation_consumptions_release_within_reservation`, `BEFORE INSERT`:
`notional ≤ trade_proposals.reserved_notional` da **própria** proposta, e uma
liberação contra proposta que nunca quantificou reserva é recusada de saída —
não há o que devolver. Só `released` é checado: `reserved` *é* a quantificação, e
`executed` é amarrado ao fill pelas três FKs acima.

O que **não** é DDL: que a soma por reserva nunca fique negativa e que o saldo
negativo de uma reserva não compense o positivo de outra. São invariantes da
T3.12, com teste.

**Escopo de capital.** A chave do orçamento é `(market_id, escopo)` e o escopo é
a carteira principal (§11 do contrato). Com uma principal por **organização**
(§18.8), a trava dessa carteira serializa o orçamento; **mais de uma carteira no
mesmo escopo exige trava própria antes de ser habilitada** — condição escrita,
não suposição. Esta frase dizia `(organization_id, workspace_id)` até a T3.1b, e
o bloqueante 2 é exatamente o motivo de não dizer mais: com o workspace na chave,
"o escopo de capital" era algo que um botão de criar workspace redefinia.

### 18.6 `market_betas` — revisões imutáveis e qual delas vale

```
market_betas                                 (global, imutável)
  id, market_id -> markets (CASCADE), reference_market_id -> markets (RESTRICT),
  as_of, window_start, window_end, input_start, last_pair_end, valid_until,
  computed_at, available_at, beta_version, estimator,
  beta NUMERIC(18,8), alpha NUMERIC(18,8), r_squared NUMERIC(9,6),
  n, contiguous_bars, valid, reason, input_digest, estimate JSONB, params JSONB, superseded_at
  UNIQUE (market_id, as_of, beta_version, input_digest)              -- uq_market_betas_revision
  UNIQUE (market_id, as_of, beta_version) WHERE superseded_at IS NULL -- uq_market_betas_current
  INDEX  (market_id, beta_version, available_at, as_of)              -- ix_market_betas_asof
  CHECKs: input_start < window_start < window_end <= as_of; window_end <= available_at;
          valid_until > window_end; valid = (reason IS NULL); valid -> beta NOT NULL;
          n >= 0; contiguous_bars entre 0 e n; superseded_at >= computed_at
```

Segue o §6 das notas da T3.7 (`.claude/state/notes-T3.7-beta.md`) com **três
desvios declarados**, os três acordados com a Astra:

1. **Sem `organization_id`.** β é dado global de mercado, calculado pelo
   scanner-worker a partir de velas globais, como `feature_baselines` (§1.1). O
   rascunho da T3.7 previa a coluna "como o resto do schema"; carregá-la
   significaria uma cópia por tenant ou uma coluna que é a mesma mentira para
   todo mundo.
2. **`input_digest` na chave de idempotência, no lugar de `computed_at`.** É a
   doutrina do `input_fingerprint` da §17.2: uma **retentativa** byte a byte
   colide e é no-op, uma **recomputação** real entra como revisão nova.
   `computed_at` na chave faria de todo retry uma revisão. O digest tem de cobrir
   a identidade da referência, os insumos efetivos e as evidências de qualidade
   que mudam o resultado — hashear só os coeficientes faria uma reexecução
   corrigida por lacuna parecer idêntica à execução que ela corrige.
3. **A vigência é decidida pelo banco.** `uq_market_betas_current` é único em
   `(market_id, as_of, beta_version) WHERE superseded_at IS NULL`: gravar uma
   revisão nova sem aposentar a anterior na mesma transação é **recusado**. Um
   índice parcial `WHERE valid` não daria isso — o cenário da Astra é uma revisão
   posterior que registra *invalidez*, onde filtrar por `valid` ressuscita a
   anterior.

**A consulta vigente, definida:**

```sql
SELECT * FROM market_betas
 WHERE market_id = :market
   AND beta_version = :version            -- o leitor escolhe a versão compatível
   AND available_at <= :t
   AND (superseded_at IS NULL OR superseded_at > :t)
 ORDER BY as_of DESC, available_at DESC, id DESC
 LIMIT 1;
```

`superseded_at IS NULL` **sozinho não serve** para replay histórico, e o cenário
é da Astra: revisão A disponível às 10:00, decisão às 10:05, revisão B chega às
10:10 e supersede A. Perguntar depois por `t = 10:05` com `IS NULL` devolve
**nada** — A falha no `IS NULL` e B falha no `available_at <= t`. Daí o `OR
superseded_at > :t`, e daí o índice não ser parcial. `beta_version` é fixado pelo
chamador porque duas versões podem estar vigentes no mesmo corte; sem isso o
`ORDER BY` escolheria arbitrariamente. E a ordem é: **primeiro a revisão
aplicável, depois `valid`/`valid_until`** — nunca procurar uma revisão antiga
válida para esconder uma nova inválida.

**A exceção à imutabilidade, declarada.** O §6 do contrato diz "só INSERT"; aqui
o `UPDATE` de `superseded_at` (`NULL` → valor, uma vez) é permitido, e
`market_betas_immutable` recusa qualquer outra alteração, `DELETE` inclusive,
para todo papel. É metadado de ciclo de vida com payload imutável — o precedente
é o freeze de `strategy_versions` (§16.1), que também deixa `status` mutável — e
é registrado aqui em vez de alegado como conformidade literal. `hunter_worker`
precisa de `UPDATE` só por causa disso, no mesmo espírito da `0005`.

`beta`/`alpha` são `NUMERIC(18,8)` — nem dinheiro (`NUMERIC(28,10)`) nem fração de
apresentação (`NUMERIC(9,6)`): coeficiente de regressão. A largura é a correção da
Astra ao rascunho `NUMERIC(12,8)`, que deixava quatro dígitos inteiros; uma
referência quase constante produz inclinação maior, e o carregador deve recusar em
vez de truncar em silêncio. `n` conta **retornos pareados**, não fechamentos.
`valid` significa *elegível pelo protocolo* e **nunca** precisão — o Risk Engine
não pode ler `valid = true` como exatidão (T3.7 §7).

### 18.7 Kill switch: a linha de trava e a retomada autenticada

```
portfolio_risk_state                         (tenant, PK portfolio_id)
  organization_id, portfolio_id (PK), last_admission_seq BIGINT,
  trading_day DATE, trading_day_timezone TEXT, trading_day_start_utc,
  equity_day_start, day_reference_observed_at,
  peak_equity, peak_equity_at, peak_sampling_interval_s, created_at, updated_at

kill_switch_transitions  (+) evidence JSONB NOT NULL DEFAULT '{}'
  CHECK from_state <> to_state
  CHECK actor_type IN ('user','system')
  CHECK NOT (from_state IN ('TRADING_DISABLED','EMERGENCY') AND to_state IN ('ACTIVE','WARNING'))
        OR (actor_type = 'user' AND actor_id IS NOT NULL)
  CHECK actor_type <> 'system' OR evidence <> '{}'::jsonb
  -- e **nenhuma** FK para organizations (§15.4, o precedente de audit_logs)
```

**Uma linha que é quatro coisas, de propósito.** `portfolio_risk_state` é ao
mesmo tempo (a) a linha de trava da carteira, na ordem sistema → organização →
portfolio, (b) o contador FIFO, (c) a referência diária e (d) o pico durável.
Quatro tabelas seriam quatro travas disputando a mesma carteira sem ganho nenhum,
e a decisão conjunta manda serializar os quatro sob a mesma trava. É trava de
**linha**, nunca advisory lock de sessão (§1.2, pooler). A PK é `portfolio_id`,
então "uma linha por carteira" é chave e não convenção.

**O pico só sobe e a sequência só avança**, garantido por
`portfolio_risk_state_guard` — e o mesmo trigger recusa `DELETE`, porque um
`DELETE` seguido de `INSERT` é exatamente como um pico de 110 vira 100 sem que
nenhum `UPDATE` aconteça para uma trigger de `UPDATE` ver (Astra). O pico é
**amostrado**, com `peak_sampling_interval_s` declarando a cadência: não é o
máximo intratick, e o schema diz isso em vez de fingir precisão.

**A linha de trava é do motor, e o `hunter_app` não escreve nela (T3.1b, deve
corrigir 5).** "Só sobe" e "só avança" eram os dois únicos limites, e o papel da
aplicação tinha `UPDATE`: de dentro de um request handler dava para reescrever
`trading_day` e `equity_day_start` — que é zerar a perda do dia, um reset
contábil sem `DELETE` nenhum — ou gravar `peak_equity = 999999` e travar a
carteira num drawdown de 98 % que **nada desfaz**, porque o pico nunca volta a
descer. Quatro regras novas:

1. **só o motor faz `UPDATE`.** O teste é de **pertencimento de papel**
   (`pg_has_role(current_user, 'hunter_worker', 'USAGE')`), não
   `current_user = 'hunter_app'` — ver "nome não é privilégio" abaixo.
2. **`trading_day` é estritamente crescente** e nunca volta a ser desconhecido:
   rebobiná-lo reabre um dia cuja perda já foi contada.
3. **`equity_day_start` (com `day_reference_observed_at`) é definível uma vez por
   `trading_day`.** Desconhecido → conhecido continua permitido — é a referência
   ficando disponível, e a §18.7 exige que "desconhecida" seja representável;
   conhecido → qualquer outra coisa é rebasear a perda de hoje num número
   escolhido *depois* da perda.
4. **nem `peak_equity` nem `equity_day_start` passam do equity observado.**
   "Observado" é definido e não implícito: o **maior `equity` já registrado em
   `portfolio_equity_snapshots`** para a carteira, ou o
   `portfolios.initial_capital` que a âncora prova ter sido creditado, mais — no
   `UPDATE` — o pico que a linha já carrega. Só é avaliado quando um dos dois
   **sobe**; a queda do pico já é recusada e a igualdade é todo heartbeat comum.

**`equity_day_start` é *limitado* pelo teto, não *parte* dele** (revisão de diff
da Astra sobre este mesmo diff). A primeira redação punha `NEW.equity_day_start`
dentro do `greatest`, e então um único statement declarava o próprio teto: um
`INSERT` com `peak_equity = 999999` **e** `equity_day_start = 999999` passava como
`hunter_app`, sem snapshot nenhum, e a carteira nascia num drawdown fictício de
98 % que a monotonicidade torna permanente. Os dois são equity da mesma carteira:
os dois são limitados pelo que ela mostrou, e nenhum atesta o outro.

**A metade do `INSERT` é um segundo trigger, adiado, e isso não é estilo.** Com a
verificação em `BEFORE INSERT`, a Astra escapou com uma CTE que escrevia o
**filho antes do pai** num único statement: a carteira ainda não existia, o
trigger não tinha com o que comparar, e a FK — verificada no *fim* do statement,
quando o pai já existia — ficava satisfeita. Resultado: capital 20.000, pico
999.999, como `hunter_app`. `portfolio_risk_state_opens_honestly` é
`AFTER INSERT ... DEFERRABLE INITIALLY DEFERRED`, então roda quando o quadro
inteiro existe — e por isso pode **recusar** uma carteira invisível em vez de
pular: no COMMIT a RLS já opinou sobre o próprio `INSERT`, então uma linha que
chegou até ali pertence a uma carteira que a sessão enxerga.

**Nome não é privilégio: por que a trava é um grant por coluna.** A decisão é
"`UPDATE` só para `hunter_worker`". A primeira implementação manteve o grant de
tabela e recusou no trigger comparando `current_user = 'hunter_app'` — e a Astra
atravessou isso com um papel que apenas **herda** `hunter_app`: ele mantém todos
os privilégios da role e reporta o próprio nome, então o trigger não o
reconhecia e o pico foi a 999999. A correção tem duas metades, e a primeira é a
que importa:

- **privilégio:** `hunter_app` recebe `SELECT`, `INSERT` e
  `UPDATE (updated_at)` — e nada mais. Privilégio **é** herdado, então a
  restrição viaja com a herança;
- **trigger:** `pg_has_role(current_user, 'hunter_worker', 'USAGE')`, que é a
  pergunta que o guarda de fato quer fazer, como defesa em profundidade.

Por que uma coluna e não `REVOKE UPDATE`: o PostgreSQL cobra `ACL_UPDATE` por
`SELECT ... FOR UPDATE`, e essa trava é a serialização da carteira que a T3.6
toma na entrada da retomada (`hunter_core.risk.scopes.load_locked_state`);
revogar tudo reintroduziria o BUG-1 da T2.5 com outro nome. **Um grant por coluna
satisfaz o row mark e recusa toda escrita de valor — medido, não suposto**
(Postgres 16.15):

```sql
GRANT SELECT, UPDATE (updated_at) ON t TO r;
SET ROLE r; SELECT v FROM t WHERE id = 1 FOR UPDATE;   -- 1 linha
SET ROLE r; UPDATE t SET v = 99 WHERE id = 1;          -- permission denied
```

Isso **contradiz** a frase da §17.2 ("um grant por coluna não serve — um row mark
não tem coluna atualizada"), que fica corrigida lá. A `0005` continua com o grant
de tabela em `feature_baselines` porque ali a imutabilidade mora inteira num
trigger que vale até para o dono; o que muda é a justificativa, não o DDL.
Provado como o papel, não perguntado ao catálogo, em
`test_the_app_role_can_lock_the_wallet_row_and_never_write_it` (o `FOR UPDATE`
passa, três `UPDATE` batem no privilégio e o de `updated_at` bate no trigger) e
em `test_a_role_that_merely_inherits_the_app_cannot_write_the_lock_row_either`.

**Custo declarado.** O teto lê `max(equity)` da curva por `portfolio_id`, uma
tabela LIST→RANGE. O índice `ix_portfolio_equity_snapshots_peak_lookup`
(`(portfolio_id, equity)`, criado na pai e propagado a toda partição, presente e
futura) transforma isso num index scan; sem ele seria uma agregação sobre todos os
pontos da carteira, a cada subida do pico — uma por intervalo de amostragem por
carteira, o que hoje é ruído e amanhã não precisa ser.

**Divisão de trabalho, e é contrato para a T3.6.** A retomada pela API
(`hunter_app`) escreve `kill_switch_transitions` **e**
`portfolios.kill_switch_state`, nas duas na mesma transação; a **referência
diária e o pico são do worker** (`hunter_worker`), e nenhum caminho da API os
toca. É a leitura literal de "a retomada não redefine pico nem perdas"
(RISK_ENGINE.md §5) transformada em privilégio, e `hunter_core/risk/resume.py` já
a documenta do lado do código ("this module writes to `portfolio_risk_state`
never at all").

**A referência diária pode ser desconhecida.** `equity_day_start` e
`day_reference_observed_at` são anuláveis, juntos (CHECK): não conseguir
reconstruí-la é um estado que o motor precisa representar, porque ele bloqueia
entradas e preserva proteções em vez de inventar um patrimônio de meia-noite a
partir do primeiro preço visto depois de um restart.
`day_reference_observed_at` é o instante **real** da avaliação — avaliar às 03:17
não faz do equity de 03:17 o equity da meia-noite.

**Não há CHECK provando o fuso, e o motivo está aqui.** A intenção era provar que
`trading_day_start_utc` é a meia-noite de `trading_day` em `America/Sao_Paulo`.
`timezone(text, timestamp)` é catalogada `IMMUTABLE`, mas a base de fusos por
trás dela **não** é congelada entre instalações e atualizações: uma correção de
tzdata poderia fazer uma linha existente falhar num `UPDATE` sem relação ou num
restore (Astra). A conversão é validada uma vez, na virada do dia, o instante
resolvido é o que fica gravado, e o fuso é gravado **por linha**
(`trading_day_timezone`) em vez de assumido.

**Sair de um bloqueio é ato registrado e atribuído — e o CHECK sozinho não dava
isso.** O contrato (§5) diz que não há volta automática de
`TRADING_DISABLED`/`EMERGENCY`, e o CHECK torna uma retomada não auditada
irrepresentável **no histórico**. Sobre a coluna que os workers de fato leem
(`portfolios.kill_switch_state`) ele não dizia nada: `UPDATE portfolios SET
kill_switch_state = 'ACTIVE'` era um desbloqueio completo e silencioso — sem
linha, sem ator, sem evidência (Astra, revisão de diff; reproduzido).

O que fecha é uma **constraint trigger adiada**,
`portfolios_kill_switch_is_audited`: no COMMIT, toda mudança de
`kill_switch_state` precisa ter uma transição correspondente escrita na mesma
transação. Adiada porque isso não dita ordem de statement — a T3.6 escreve os
dois na ordem que quiser. Com ela o CHECK passa a valer transitivamente: sair de
um bloqueio exige uma pessoa nomeada também na coluna efetiva.

**"Correspondente" era fraco demais, e a T3.1b (bloqueante 1) mostrou como.** A
primeira redação da trigger perguntava `EXISTS` sobre
`(scope, scope_id, organization_id, from_state, to_state)` — qualquer linha,
de qualquer época. Consequência: a **primeira** retomada legítima cunhava o par
`(TRADING_DISABLED, ACTIVE)` e, a partir dali, `UPDATE portfolios SET
kill_switch_state = 'ACTIVE'` passava para sempre — desbloqueio completo, sem
linha, sem ator, sem evidência (reproduzido: **3 transições para 4 movimentos**).
A variante é pior porque não precisa nem de um ciclo: `actor_id` não tem FK de
propósito, então gravar **uma** linha `EMERGENCY → ACTIVE` atribuída a um UUID
que nunca foi usuário autorizava todo destravamento futuro.

Duas condições substituem o `EXISTS`, e **são necessárias as duas**:

1. **coerência com a última transição do escopo** — a mais recente de
   `(scope, scope_id)` por `ORDER BY created_at DESC, id DESC` tem de ser
   exatamente `from = OLD.kill_switch_state`, `to = NEW.kill_switch_state`;
2. **prova de mesma transação** — `t.xmin = pg_current_xact_id()::xid`.

Sozinha, (1) é derrotada por uma linha *plantada antes*: escrever a transição
numa transação e mover a coluna na seguinte a torna "a mais recente" e passa —
que é literalmente a variante do ator inexistente. Sozinha, (2) é derrotada por
uma transação que escreve uma linha casando com um movimento que ela não está
fazendo. Juntas, "um movimento, uma linha, uma transação".

**Por que `xmin` e não `portfolios.current_transition_id` com FK.** As duas
opções estavam na mesa. `xmin` não custa coluna nova em tabela quente, não custa
FK de uma tabela de tenant para uma append-only, e não obriga nenhum escritor a
mudar: o caminho único (`hunter_core.risk.transitions.record_transition`) já
escreve os dois na mesma transação. E `current_transition_id` **não prova mesma
transação sozinho** — nada impede apontá-lo para uma linha escrita antes —, então
ele exigiria a mesma condição (2) por cima, com o custo a mais. Barata e provável,
como o brief pedia; registrada aqui a escolha.

**O preço declarado, e é uma recusa falsa, nunca uma aprovação falsa.** Uma linha
inserida **dentro de um `SAVEPOINT`** carrega o xid da subtransação, não o do topo
(`pg_current_xact_id()` devolve sempre o do topo — medido). A regra para
T3.4/T3.6/T3.12 é, portanto: **escreva a transição e o `UPDATE` na mesma
transação, sem `SAVEPOINT`/`begin_nested` entre eles.** Nenhum caminho de escrita
de hoje usa um.

**Segunda consequência declarada: um movimento por transação e por escopo.** Se
uma transação mover o kill switch da mesma carteira duas vezes (`ACTIVE →
WARNING → TRADING_DISABLED` em dois `UPDATE`), a trigger adiada dispara duas
vezes no COMMIT e as duas leem a *mesma* "última transição" — a segunda casa, a
primeira não, e a transação é recusada. É o comportamento certo (a coluna se moveu
de `ACTIVE` para `TRADING_DISABLED` e não há transição que diga isso) e o motor
avalia um degrau por vez de qualquer forma, mas fica escrito em vez de descoberto.

**A mesma trigger em `organizations` (T3.1b, deve corrigir 3).**
`organizations.kill_switch_state` é lida como bloqueante pela API
(`apps/api/.../radar_org_derivation.py`) e não tinha guarda nenhuma: um bloqueio
de organização inteira era levantado com um `UPDATE` e zero histórico.
`organizations_kill_switch_is_audited` é a mesma função, instanciada com
`scope = 'organization'` e `organization_id = NEW.id`. O escopo `system` não tem
linha (é configuração de processo, `hunter_core.risk.scopes`), então não tem
trigger — e a §18.9 registra isso em vez de deixar a ausência parecer descuido.

**Uma transição automática publica os números (T3.1b, sugestão 9).**
`CHECK (actor_type <> 'system' OR evidence <> '{}'::jsonb)`. Numa linha `system`,
`actor_id` é nulo por definição e `reason` é prosa: `evidence` é a única coisa
que diz *por quê*. Vazia, a linha registra que algo aconteceu e nada sobre o quê.
Uma pessoa continua podendo mover sem números — ela é a evidência. A guarda de
upgrade correspondente conta linhas `actor_type = 'system'` preexistentes e
**recusa**, porque a evidência de um movimento passado não é derivável.

**A trilha sobrevive ao tenant (T3.1b, sugestão 10).**
`kill_switch_transitions.organization_id` perdeu a FK
`ON DELETE CASCADE` para `organizations` — pelo mesmo motivo, e com o mesmo
precedente, de `audit_logs` (§15.4). O teardown é declarado com
`app.portfolio_teardown`, um `SET LOCAL` que qualquer papel escreve, e com a
cascata `DELETE FROM organizations` levava junto exatamente o registro de que o
kill switch daquela organização foi travado: travar a carteira e depois remover o
tenant era um jeito de o travamento nunca ter acontecido. **A órfã é
intencional** — a linha continua com `organization_id` apontando para nada.

**E a frase honesta sobre quem a lê** (correção da Astra na revisão deste diff,
que reproduziu o contrário do que esta seção dizia antes): `tenant_isolation`
filtra pela **coluna**, não pela linha referenciada, então a órfã é ilegível por
**todo outro tenant** — mas continua legível por uma sessão que apresente
`app.current_org` igual ao id da organização removida, que é exatamente o dono da
trilha. Não é buraco: é a mesma propriedade que `audit_logs` tem desde a `0001`
(§15.4) e é o ponto de a trilha sobreviver. O `CHECK
(scope = 'system') = (organization_id IS NULL)` não é afetado — apagar a
organização não mexe em `scope` nem em `organization_id`.

Há guarda de downgrade para a órfã: restaurar a FK não a representa, então o
downgrade recusa nomeando-as em vez de apagá-las.

**O que continua não sendo prova, e o schema não finge que é:** *qual* pessoa.
`actor_id` não tem FK para `users` de propósito — um usuário removido depois não
pode invalidar a trilha —, então um UUID preenchido prova que alguém foi nomeado,
não que alguém se autenticou. Autenticar a identidade autorizada é da API, na
T3.6. `evidence` guarda os números que justificaram o movimento (perda do dia,
drawdown, equity, pico, o dia de negociação e os limiares vigentes): `reason` é
prosa, e é `evidence` que torna a transição auditável em vez de apenas
registrada.

### 18.8 Permanência: o buraco do `DELETE`, e o que fecha

O índice único parcial da §11 do contrato está em `portfolios`:

```sql
CREATE UNIQUE INDEX uq_portfolios_principal_paper ON portfolios (organization_id)
  WHERE type = 'paper' AND NOT is_arena;
```

Sem `status` e sem excluir `deleted_at` preenchido, exatamente como a decisão
conjunta manda — arquivar ou apagar logicamente a carteira e abrir outra
preservaria as linhas antigas e ainda assim reiniciaria patrimônio e pico, e
destravaria um kill switch bloqueado que ninguém autorizou. Como o Alembic não
compara predicado de índice (§17.3), **a chave e o predicado** são lidos de
`pg_indexes` por `test_schema_paper.py`.

**A chave é a organização, e não `(organização, workspace)` (T3.1b, bloqueante
2).** Por par, o índice não impedia nada que um usuário não desfizesse: workspace
é agrupamento de produto e `hunter_app` tem `INSERT` nele, então a sequência
reproduzida foi *criar workspace novo → inserir portfolio + `portfolio_risk_state`
+ âncora com R$100.000 novos*, **sem `DELETE`, sem auditoria, sem tocar em nada
que uma trigger visse**. Permanência chaveada em algo que um botão da UI cria não
é permanência. A D7 do Everton é "uma carteira principal" e é isso que o índice
passa a dizer; se um dia houver várias, é ato auditado de OWNER e revisão nova,
nunca efeito colateral.

**O que a T3.3 tem de ajustar** (declarado, não corrigido aqui — `hunter_core/
portfolio/**` é dela): `open_paper_wallet` pré-checa
`PortfolioRepository.principal_paper_id(workspace_id)` e a mensagem de
`WalletAlreadyOpen` fala em workspace. O comportamento continua **seguro** —
abrir a segunda carteira em outro workspace da mesma organização agora perde no
índice, a `IntegrityError` nomeia `uq_portfolios_principal_paper` e o
`except` existente a converte em `WalletAlreadyOpen` —, mas a pré-checagem passa a
ser inútil e a mensagem, errada: ela diz "concurrent opening" para o que é uma
carteira já aberta noutro workspace. O ajuste é escopar a pré-checagem pela
organização e reescrever as duas frases.

**O índice impede uma segunda carteira e não impede nada sobre a primeira.** E
`portfolios` está em `APP_WRITE_TABLES` (§15.6), então `hunter_app` tem `DELETE`:
um comando apaga a carteira, a âncora e o pico, e a requisição seguinte abre uma
R$100.000 nova. Isso é o reset que a diretiva proíbe, alcançável de dentro de um
request handler. A trigger `portfolios_permanence` fecha por dois lados:

- **`DELETE` de uma carteira ancorada é recusado para o papel da aplicação
  *mesmo com o marcador*.** Um `SET LOCAL` que qualquer um pode escrever não
  autentica ninguém (Astra): ele é escopado à transação, o que o torna seguro
  atrás do pooler, mas isso é isolamento, não autorização. Para os demais papéis
  a remoção exige `SET LOCAL app.portfolio_teardown = 'on'` — remover um tenant
  continua possível para o operador, e passa a ser um ato e não um acidente. O
  mesmo vale para `portfolio_currency_anchor` e `portfolio_risk_state`.
- **Os campos de identidade ficam congelados** enquanto houver âncora:
  `organization_id`, `workspace_id`, `type`, `is_arena`, `base_currency` e
  `initial_capital`. Virar `is_arena = true` tira a linha do índice, libera uma
  principal nova com R$100.000 e **nenhum `DELETE` acontece** para uma trigger de
  `DELETE` ver. `base_currency` e `initial_capital` entram pela razão vizinha: a
  âncora declara o que foi creditado, e uma carteira que reescreve o próprio
  capital de abertura não precisa de reset para ter um.

**A cascata do workspace era a porta dos fundos, e ela foi reproduzida.**
`hunter_app` também tem `DELETE` em `workspaces`, e `workspaces → portfolios` é
`ON DELETE CASCADE`. Com o marcador ligado, `DELETE FROM workspaces` respondia
`DELETE 1` e levava a carteira aberta junto. O motivo: **uma ação referencial roda
o delete em cascata como o *dono* da tabela referenciante**, então quando
`portfolios_permanence` disparava, `current_user` já não era `hunter_app` e a
metade de papel do teste não mordia — a prova é que, sem o marcador, o mesmo
comando falhava com *"may not be deleted by hunter"*, o dono, não o chamador
(Astra, revisão de diff). `workspaces_permanence` guarda a **origem** da cascata,
onde o chamador ainda é o chamador. É a mesma regra, uma tabela antes.

**Consequência aceita e declarada:** remover uma organização ou um workspace com
carteira aberta (cascata) passa a exigir o marcador, como apagar uma
`feature_baselines` exige o dela (§17.2). A
alternativa considerada e descartada foi revogar o `DELETE` de `portfolios` do
`hunter_app` — não porque a `0001` seja intocável (uma revisão posterior pode
mudar grants; a `0005` já acrescenta um), mas porque sozinha ela bloquearia
também a exclusão legítima de carteiras de experimento e não fecharia nem a
cascata nem a alteração de identidade.

**Seed: uma fonte para o `paper_v1` (T3.1b, deve corrigir 7).**
`seed_reference.PAPER_V1_LIMITS` era um **segundo literal** ao lado de
`hunter_risk.limits.PAPER_V1`, e os dois já tinham divergido:
`RiskLimits.model_validate(profile.limits)` falhava com **dez** erros sobre a
linha que o seed grava. Seis chaves que o motor exige faltavam —
`max_entry_deviation_pct`, `max_price_age_s`, `max_book_age_s`,
`max_volume_age_s`, `max_beta_age_s` e `day_timezone` —, ou seja, os tetos que a
v2.1 do contrato acrescentou existiam no código e **em nenhum perfil que uma
organização copia no onboarding**; e quatro chaves para as quais o motor não tem
campo estavam presentes, o que `extra="forbid"` rejeita.

A correção é a doutrina do §17.8 aplicada de novo: o seed passa a gravar
exatamente `hunter_risk.limits.PAPER_V1.model_dump(mode="json")`.
`hunter-core` já declara `hunter-risk` como dependência de distribuição
(`packages/core/pyproject.toml`) e a imagem já copia `packages/risk-core`, então
não foi preciso gerar JSON por script. `model_dump(mode="json")` é o que mantém a
regra do §17.8 sobre fração: pydantic renderiza todo `Decimal` como **string**
JSON, que é como o motor os lê de volta. **Nenhum valor da diretiva muda** — a
prova é `test_the_seeded_paper_profile_has_exactly_one_source`, que carrega os
dois e compara `json.dumps(..., sort_keys=True)` byte a byte, mais as asserções
por número em `test_schema_seed_and_partitions.py`.

**Quatro chaves saem do JSON, e cada uma tem destino declarado** — o mesmo padrão
de `max_exchange_exposure_pct`/`max_position_pct` logo abaixo, e não um
desaparecimento silencioso:

| Chave removida | Onde a informação passa a viver |
|---|---|
| `participation_reference` | é **fórmula**, não limite: `hunter_risk` a calcula de `MarketLiquidity` (`inputs.participation_reference`) e nunca a leu daqui |
| `market_types: ["spot"]` | é o que `max_leverage = 1` já significa, e o validador de `RiskLimits` recusa qualquer outro valor ("directive §6 is spot only") |
| `auto_close_on_emergency: false` | é a **ausência** de caminho de liquidação automática em `hunter_risk.kill_switch`, não um interruptor que alguém lê |
| `regime_size_multiplier` | nomeia a gramática do v1 (RISK_ENGINE.md §2.1) que o motor do M3 **não implementa** — `RiskLimits` não tem o campo. Carregá-la no perfil fazia um controle não implementado parecer configurado |

As duas últimas linhas são **desvio em relação à tabela de RISK_ENGINE.md §2**,
que ainda lista `participation_reference` e `regime_size_multiplier` como chaves
do perfil. Fica registrado aqui como a diferença entre *o que o contrato descreve*
e *o que o motor da T3.2 lê*; fechá-la é decisão do dono de
`docs/RISK_ENGINE.md` e de `packages/risk-core` (acrescentar os campos ao
`RiskLimits` ou remover as linhas da tabela), não deste diff, que não pode tocar
em `packages/risk-core/**`.

`paper_v1` continua sendo a quarta coisa congelada do seed: inserido quando falta,
**verificado** quando presente, com divergência parando o seed. Os três presets genéricos continuam
sendo reescritos no lugar porque são padrões em que ninguém apostou dinheiro;
`paper_v1` é o perfil da carteira, todo número nele é do Everton, e o contrato
(§2) faz de qualquer mudança de valor uma pergunta a ele, não um deploy. O custo
operacional é zero: o preset de sistema é **modelo**, as organizações copiam no
onboarding (§15.4) e uma edição auditada de limite (§2.1) acontece na cópia.

`max_exchange_exposure_pct` e `max_position_pct` estão deliberadamente **ausentes**
do JSON: a §9.1 do contrato declara o primeiro inaplicável enquanto houver uma
exchange de execução (volta no M1b) e substitui o segundo por
`max_asset_exposure_pct` mais o teto de participação. Gravá-los como `null` se
leria como "sem limite" em vez de "não se aplica aqui".

### 18.9 Grants, RLS e guardas

**Classes congeladas em `ddl/paper.py`**, no padrão de §15.6/§16.5/§17.6:

| Classe | Papel | Privilégios | Tabelas |
|---|---|---|---|
| `PAPER_APP_READ_ONLY_TABLES` | `hunter_app` | `SELECT` | `fx_observations`, `market_betas` |
| `PAPER_APPEND_TABLES` | ambos | `SELECT`/`INSERT` | `portfolio_currency_anchor`, `participation_consumptions` |
| `PAPER_NO_DELETE_TABLES` | ambos | `SELECT`/`INSERT`/`UPDATE` | `portfolio_exit_intents` |
| `PAPER_LOCK_ONLY_TABLES` | `hunter_app` | `SELECT`/`INSERT` + `UPDATE (updated_at)` | `portfolio_risk_state` |
| `PAPER_LOCK_ONLY_TABLES` | `hunter_worker` | `SELECT`/`INSERT`/`UPDATE` | `portfolio_risk_state` |
| `PAPER_WORKER_APPEND_TABLES` | `hunter_worker` | `SELECT`/`INSERT` | `fx_observations` |
| `PAPER_WORKER_SUPERSEDE_TABLES` | `hunter_worker` | `SELECT`/`INSERT`/`UPDATE` | `market_betas` |

**`PAPER_LOCK_ONLY_TABLES` é a sexta classe, e a primeira com grant por coluna.**
`portfolio_risk_state` saiu de `PAPER_NO_DELETE_TABLES` na T3.1b: o `UPDATE` do
`hunter_app` ali é **trava, não escrita**, e a forma estreita
(`UPDATE (updated_at)`) é a que sobrevive a herança de papel, porque privilégio é
herdado e nome não é. Mesmo formato de argumento que `BASELINE_LOCK_TABLES_0005`
(§17.6) — o privilégio nomeia a capacidade, não a permissão —, só que aqui a
permissão é de fato negada pelo próprio grant e não só pelo trigger. O motivo
completo, com o bug que um `REVOKE` inteiro reintroduziria e o experimento que
mede o grant por coluna, está na §18.7 (e a correção da §17.2, lá).

`test_schema_privileges.py` une estas listas às das revisões anteriores — toda
tabela continua classificada exatamente uma vez.

**A `0007_paper_roles` muda o que estas classes concedem, não a classificação
delas (§19).** `hunter_app` perde a escrita em `portfolio_equity_snapshots` e
fica só com `SELECT`/`INSERT` em `trade_proposals`; `hunter_worker` ganha
`UPDATE` de coluna em `portfolios` e em `organizations`. As tuplas desta seção
continuam descrevendo o que a `0006` fez — é o que "congelada por revisão"
significa —, e a tabela papel × tabela × privilégio **vigente** é a da §19.1.

**E a `0008_paper_roles_2` faz a única *reclassificação* do schema até aqui
(§20.1):** `orders`, `fills`, `positions` e `trades` saem de `APP_WRITE_TABLES`
(`0001`) para a leitura, em `APP_READ_ONLY_TABLES_0008`. A tupla da `0001` também
não muda; quem mantém a partição exata é o teste, que subtrai a lista da `0008`
da classe de escrita antes de contar.

`PAPER_TENANT_TABLES` são as quatro de tenant, com RLS habilitada, **forçada** e
`tenant_isolation` própria. `fx_observations` e `market_betas` ficam fora por
serem globais (§1.1).

**Triggers desta revisão, por tabela** (todas em `ddl/paper.py`):

| Tabela | Trigger | Momento |
|---|---|---|
| `fx_observations` | `fx_observations_immutable` | `BEFORE UPDATE OR DELETE` |
| `market_betas` | `market_betas_immutable` | `BEFORE UPDATE OR DELETE` |
| `portfolio_currency_anchor` | `portfolio_currency_anchor_matches_observation` | `BEFORE INSERT` |
| `portfolio_currency_anchor` | `portfolio_currency_anchor_immutable` | `BEFORE UPDATE OR DELETE` |
| `portfolio_risk_state` | `portfolio_risk_state_guard` | `BEFORE INSERT OR UPDATE OR DELETE` |
| `portfolio_risk_state` | `portfolio_risk_state_opens_honestly` | constraint trigger `AFTER INSERT`, `DEFERRABLE INITIALLY DEFERRED` |
| `portfolios` | `portfolios_permanence` | `BEFORE UPDATE OR DELETE` |
| `workspaces` | `workspaces_permanence` | `BEFORE DELETE` |
| `portfolios` | `portfolios_kill_switch_is_audited` | constraint trigger `AFTER UPDATE`, `DEFERRABLE INITIALLY DEFERRED` |
| `organizations` | `organizations_kill_switch_is_audited` | idem |
| `participation_consumptions` | `participation_consumptions_release_within_reservation` | `BEFORE INSERT` |

**Não há trigger para o escopo `system` do kill switch, e a ausência é
deliberada:** ele não tem linha — é configuração de processo lida por
`hunter_core.risk.scopes` —, então não há coluna efetiva a amarrar a uma
transição. Uma transição de escopo `system` continua sendo escrita e lida
normalmente (§15.4, `system_scope_readable`).

**Guardas de upgrade** (a migração conta os infratores e recusa com instruções —
o precedente da `0002`; em todo banco de hoje cada uma conta zero):

| Guarda | Por que não há backfill honesto |
|---|---|
| mais de uma carteira principal paper por **organização** | escolher qual delas é a permanente é decisão de operador sobre qual história é a real |
| `kill_switch_transitions.actor_type` fora de (`user`,`system`) | o ator verdadeiro é conhecimento de quem moveu o switch |
| transição `actor_type = 'system'` preexistente (T3.1b) | ela receberia o default `evidence = '{}'` e violaria o CHECK novo; os números que justificaram um movimento passado não são deriváveis de coluna nenhuma |
| `from_state = to_state` | uma transição que não moveu não é transição |
| saída de bloqueio sem `actor_type='user'` e `actor_id` | a migração não inventa a identidade que autorizou |
| ordem cujo `(organization_id, portfolio_id)` diverge do da proposta | nenhuma inferência diz qual dos dois escopos era o verdadeiro |
| fill divergente da ordem | idem |

**Guardas de downgrade** — reverter é permitido, perder obrigação ou evidência
não é, e "a migração reverteu sem erro" seria o único relatório da perda:
`risk_profiles` com `paper_v1`; `risk_events` com um dos três rótulos novos;
qualquer `portfolio_currency_anchor`; qualquer `portfolio_risk_state`; intenção
de saída em `open`/`blocked_residual`; proposta com `reservation_state = 'held'`;
consumo `executed` dentro dos últimos 60 s; consumo cuja reserva ainda está
`held`; transição de kill switch com `evidence` não vazia (o caso independente de
carteira: uma transição de escopo `system` não dispara nenhuma das guardas de
carteira e mesmo assim perderia a razão do movimento — Astra); ponto de equity
com `fx_observation_id`; decisão preservada citando uma
revisão de β em `risk_decision -> 'beta' ->> 'revision_id'` (o caminho é o
contrato que esta revisão fixa para a T3.2); fill com `execution_key <> id::text`
(chave real, não a identidade legada do backfill); proposta com `admission_seq`;
ordem com `exit_intent_id`.

e, desde a T3.1b, **transição de kill switch órfã** (com `organization_id` que
não nomeia organização nenhuma): ela só existe porque a FK em cascata foi
removida, e restaurar a FK no downgrade não a representa — recusar nomeando-as é
o oposto de apagá-las em silêncio.

O que **não** é guardado, declarado em vez de descoberto: revisões de β que
nenhuma decisão preservada nomeia e observações de FX que nenhuma âncora ou
snapshot nomeia — ambas recomputáveis ou recoletáveis, e recusar por causa delas
tornaria o downgrade impossível em qualquer banco que os coletores já tenham
tocado. É a mesma fronteira da §17.7. **E, completando a sugestão 12 da revisão
de segurança:** também não são guardadas as **intenções de saída em estado
terminal** (`fulfilled`, `superseded`, `voided`) nem os **consumos de participação
com mais de 60 s**. Os dois são deliberados e pela mesma razão: a guarda existe
para não perder *obrigação viva* nem *evidência de um número que sobrevive*, e
nenhum dos dois é. Uma intenção terminal já não deve nada — o que sobrevive dela é
a ordem, o fill e o `trade`; um consumo fora da janela móvel já não conta contra
nenhum teto, porque a fórmula da §18.5 só soma `executed` dentro dos 60 s. O que
se perde é **histórico de auditoria**, não obrigação, e as instruções da guarda
mandam exportar antes (abaixo) exatamente por isso.

**As instruções das guardas dizem "exporte antes", e exportar não muda
predicado nenhum.** É deliberado, e a frase completa é esta: o downgrade de um
banco com carteira aberta **não** é uma operação de rotina. Ele exige uma decisão
operacional — exportar a evidência *e* remover as linhas que a guarda nomeia,
sabendo o que isso significa (a carteira deixa de ter abertura, pico e referência
diária, e a diretiva proíbe reabri-la). Nenhuma guarda apaga nada sozinha, e é
por isso que a instrução não é um comando pronto.

**Consequência declarada:** depois de o seed rodar, a guarda de `paper_v1`
impede o downgrade mesmo num banco sem carteira aberta. Isso é a política
funcionando, não algo a resolver apagando o preset automaticamente.

### 18.10 Pooler e orçamento de nome

Nada nesta revisão depende de estado de sessão: sem prepared statement de sessão,
sem `LISTEN`/`NOTIFY`, sem advisory lock de sessão — a serialização é a linha de
`portfolio_risk_state`, dentro da transação. O único GUC envolvido,
`app.portfolio_teardown`, é escrito com `SET LOCAL` e lido com
`NULLIF(current_setting(..., true), '')`, exatamente como `app.current_org`
(§15.4) e `app.baseline_retention` (§17.2).

`0006_paper_wallet` tem 17 caracteres; o teto de `alembic_version.version_num`
continua sendo 32 (§17.6).

**`execution.py` foi dividido em quatro, e o caminho público continua o mesmo.**
`Fill`, `Position` e `Trade` moraram nele até esta revisão; a reserva, a sequência
FIFO e as identidades compostas empurraram o módulo para além das 350 linhas
(`infra/scripts/check_file_size.py`), então eles passaram para
`execution_fills.py` e `execution_trades.py` — e as duas FKs compostas mais o
CHECK que a T3.1b acrescentou a `orders` o empurraram de novo (359 linhas,
medido), levando `Order` para `execution_orders.py`. `execution.py` **reexporta os
quatro**: `from hunter_core.db.models.execution import Position` é caminho público
com chamador fora deste pacote (`apps/api`), e uma divisão de módulo que quebra um
import é uma refatoração que quebrou alguma coisa (Astra reproduziu o
`ImportError` na revisão de diff). Sobra em `execution.py` só `TradeProposal`.

Dois nomes de constraint tiveram de encolher porque a convenção de nomes gerava
mais de 63 caracteres e o Postgres trunca identificadores: a bicondicional da
retomada é `ck_kill_switch_transitions_resuming_a_block_is_authenticated` e a FK
do sucessor de uma intenção é nomeada à mão
(`fk_portfolio_exit_intents_superseded_by_id`). O sintoma, se alguém repetir o
erro: `alembic check` acusa drift permanente, comparando o nome truncado que o
banco tem com o nome inteiro que o modelo declara.

Um terceiro nome é à mão por **colisão**, não por tamanho:
`fk_orders_exit_intent_matches_position` (§18.3). A convenção
`fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s` produziria
`fk_orders_exit_intent_id_portfolio_exit_intents` para as **duas** FKs que
`orders` tem para `portfolio_exit_intents` — a do quádruplo e a do par
`(exit_intent_id, position_id)` — e a segunda derrubaria a primeira.

## 19. Modelo de papéis da carteira paper — M3 (`0007_paper_roles`)

Sétima revisão, e a primeira que muda **quem** escreve a carteira em vez de o que
ela é. A `0006` desenhou as tabelas e deixou uma pergunta aberta em seis lugares
diferentes; três tarefas bateram nela pelo mesmo motivo e nenhuma podia fechá-la
sozinha:

| De onde veio | O que estava impossível |
|---|---|
| T3.6, achado 1 | **nenhum papel implantado escrevia uma avaliação inteira do kill switch**: `portfolio_risk_state` é do `hunter_worker` e `portfolios` era do `hunter_app`, e o contrato exige as duas metades na mesma transação |
| T3.6, achado 2 | `kill_switch.changed` não era publicável por papel nenhum: quem movia a trava não tinha `INSERT` na outbox |
| T3.6, achado 3 | `docs/SECURITY.md` §2 (TRADER+) contradizia a diretiva ("retomar somente com a minha autorização") |
| T3.12, bloqueantes A–D | `hunter_worker` não tinha `ACL_UPDATE` em `organizations`, então `effective_state(lock=True)` morria em *permission denied* antes de decidir; e a escalada automática não tinha portador |
| Revisão de segurança da `0006`, achado 5 | `hunter_app` tinha DML completo em `portfolio_equity_snapshots` — a curva é a **evidência** que a retomada lê |
| T3.3b, dívida | um ponto da curva sem BRL não tinha onde dizer *por quê* |

**Por que uma revisão nova e não outra emenda na `0006`.** A liberdade que a §15
registra — uma revisão que nunca rodou em lugar nenhum pode ser corrigida no
lugar — acabou para a `0006`: ela está sendo aplicada à VPS enquanto isto é
escrito. Daqui em diante toda mudança é revisão própria, e `0007_paper_roles` tem
16 caracteres (o teto de `alembic_version.version_num` continua sendo 32, §17.6).

A decisão que organiza tudo abaixo: **o worker decide e grava estado de risco; a
API pede, lê e autoriza pessoas.**

### 19.1 Papel × tabela × privilégio (a superfície da carteira)

O que vale **depois** da `0007` — e, nas duas linhas marcadas **`0008`**, depois
da `0008_paper_roles_2` (§20), que é a única revisão posterior a mexer nesta
tabela — a `0009_paper_geometry` acrescenta colunas às tabelas abaixo e **nenhum
privilégio** (§21.5), então esta tabela continua vigente como está. Ela é mantida **vigente** aqui, no lugar de ser congelada e reescrita numa
seção nova: quem pergunta "quem pode escrever isto?" tem uma tabela para ler, não
uma cadeia de revisões para somar. O que cada revisão *fez* continua nas listas
congeladas de `ddl/`.

"coluna" quer dizer `GRANT UPDATE (col, …)`, que é o formato que a §18.7 mediu:
satisfaz o row mark (`FOR SHARE`/`FOR UPDATE`) e recusa toda escrita de valor —
e, ao contrário de um teste por `current_user`, viaja com a herança de papel.

| Tabela | `hunter_app` (API) | `hunter_worker` (motor) | Fixado em |
|---|---|---|---|
| `portfolios` | `SELECT`/`INSERT`/`UPDATE`/`DELETE` | `SELECT` + **`INSERT`** (só carteira `paper` não-arena, e auditada na mesma transação — §20.2) + **`UPDATE (kill_switch_state, kill_switch_reason, updated_at)`** | `0001` · `0007` · **`0008`** |
| `organizations` | `SELECT`/`INSERT`/`UPDATE` | `SELECT`/`DELETE` + **`UPDATE (updated_at)`** | `0001` · **`0007`** |
| `workspaces` | `SELECT`/`INSERT`/`UPDATE`/`DELETE` | `SELECT` | `0001` |
| `portfolio_risk_state` | `SELECT`/`INSERT` + `UPDATE (updated_at)` | `SELECT`/`INSERT`/`UPDATE` | `0006` |
| `portfolio_equity_snapshots` | **`SELECT`** | `SELECT`/`INSERT`/`UPDATE`/`DELETE` | `0001` · **`0007`** |
| `trade_proposals` | **`SELECT`/`INSERT`** (só pedido; trigger de forma) | `SELECT`/`INSERT`/`UPDATE`/`DELETE` | `0001` · **`0007`** |
| `orders`, `fills`, `positions`, `trades` | **`SELECT`** | `SELECT`/`INSERT`/`UPDATE`/`DELETE` | `0001` · **`0008`** |
| `portfolio_exit_intents` | `SELECT`/`INSERT`/`UPDATE` | `SELECT`/`INSERT`/`UPDATE` | `0006` |
| `participation_consumptions` | `SELECT`/`INSERT` | `SELECT`/`INSERT` | `0006` |
| `portfolio_currency_anchor` | `SELECT`/`INSERT` | `SELECT`/`INSERT` | `0006` |
| `fx_observations` | `SELECT` | `SELECT`/`INSERT` | `0006` |
| `market_betas` | `SELECT` | `SELECT`/`INSERT`/`UPDATE` (só `superseded_at`, §18.6) | `0006` |
| `kill_switch_transitions`, `risk_events`, `audit_logs` | `SELECT`/`INSERT` | `SELECT`/`INSERT` | `0001` |
| `outbox_events` | `SELECT` | `SELECT`/`INSERT`/`UPDATE`/`DELETE` | `0003` |
| `risk_profiles` | `SELECT`/`INSERT`/`UPDATE`/`DELETE` (+ presets de sistema só leitura) | `SELECT` | `0001` |
| `markets`, `candles`, `market_snapshots`, análise | `SELECT` | escrita | `0001`–`0003` |

E a mesma coisa por **ato**, que é como um leitor humano pergunta:

| Ato | Papel | Escreve |
|---|---|---|
| Abrir a carteira (uma vez, operador) | `hunter_worker` | `portfolios`, `portfolio_risk_state`, `portfolio_currency_anchor`, o primeiro ponto da curva, `audit_logs` |
| Gravar um ponto da curva | `hunter_worker` | `portfolio_equity_snapshots` |
| Avaliar o kill switch (automático) | `hunter_worker` | `portfolio_risk_state` (dia, referência, pico), `portfolios.kill_switch_state`, `kill_switch_transitions`, `risk_events`, `outbox_events` |
| Retomar um bloqueio | `hunter_app`, **OWNER** | `kill_switch_transitions`, `portfolios.kill_switch_state`, `risk_events` |
| Pedir uma entrada manual | `hunter_app` | `trade_proposals` (só o pedido) |
| Admitir (decidir, reservar, FIFO) | `hunter_worker` | `trade_proposals`, `portfolio_risk_state.last_admission_seq`, `participation_consumptions`, `audit_logs`, `outbox_events` |
| Ler a carteira (lista, resumo, âncora, curva, posições, ordens, trades) | `hunter_app`, VIEWER | nada — são as sete rotas `GET` da T3.8a (§20.1) |
| Executar (ordens, fills, posições, saídas) | `hunter_worker` | `orders`, `fills`, `positions`, `trades`, `portfolio_exit_intents`, `participation_consumptions` |
| Travar a organização inteira — **intenção, não rota** | `hunter_app`, ADMIN+ | `organizations.kill_switch_state` + a transição |

**A última linha é intenção, e a distinção importa** (revisão de segurança da
`0007`, S6/S7). Esta tabela a listava ao lado das outras, como se existisse; **não
há rota**. `organizations.kill_switch_state` é *lida* como bloqueante
(`apps/api/.../radar_org_derivation.py`, `routers/me.py`) e o schema já está
pronto para o ato — `hunter_app` tem `UPDATE` na tabela, a constraint trigger
`organizations_kill_switch_is_audited` (§18.7) exige a transição, e
`docs/SECURITY.md` §2 já reserva o ato a OWNER/ADMIN. O que falta é o handler.
Enquanto faltar, quem quiser travar uma organização inteira faz isso por operação
manual no banco, escrevendo a transição na mesma transação como qualquer outro
movimento. As demais linhas desta tabela descrevem caminhos que existem e têm
teste.

### 19.2 As frases, uma por decisão

**1. Quem decide e grava estado de risco é o worker.** Uma avaliação do kill
switch é uma coisa só: a referência do dia e o pico (`portfolio_risk_state`), a
trava que os workers leem (`portfolios.kill_switch_state`), a transição que a
explica e o evento que a publica. Antes da `0007` essas quatro escritas moravam
em dois papéis que não se combinam numa transação, e o custo era o cenário da
T3.6: vira o dia em São Paulo com a carteira em AVISO e os gatilhos limpos — como
`hunter_app`, a referência nova é recusada e a perda do dia passa a ser medida
contra o patrimônio de ontem; como `hunter_worker`, a limpeza do AVISO é recusada
e a carteira segue pela metade num dia em que não perdeu nada. Em duas transações
existe a janela em que a referência é de hoje e a trava é de ontem. O grant é de
**coluna** (`kill_switch_state`, `kill_switch_reason`, `updated_at`): o motor move
a trava e nada mais — não renomeia a carteira, não arquiva, não vira `is_arena`
(que liberaria uma segunda principal, §18.8). `updated_at` está lá porque o
`onupdate` do `TimestampMixin` escreve a coluna no mesmo `UPDATE`; `kill_switch_reason`
porque `record_transition` a escreve junto, e uma trava sem motivo é pior que a
trava.

**1b. E `INSERT` em `portfolios`, porque abrir a carteira é uma transação só.**
`open_paper_wallet` grava a carteira, a linha de trava, a âncora, **o primeiro
ponto da curva** e a auditoria num commit — a §18.2 diz que essa atomicidade é a
única prova de que nasceram juntos. No instante em que a curva virou do motor
(item 3 abaixo), a linha da carteira teve de ir junto: `hunter_app` não escreve
mais a curva e `hunter_worker` não escrevia `portfolios`, então a abertura ficou
**sem papel nenhum capaz de executá-la** — a mesma parede da T3.6, uma tabela ao
lado. Medido, não suposto: *permission denied for table portfolios*, na primeira
execução da suíte da admissão depois da revogação. É `INSERT` e nada mais: o
motor cria a carteira e move a trava, e continua sem poder renomear, arquivar,
virar `is_arena` ou reescrever o capital de abertura (§18.8 congela esses campos
depois da âncora, e o grant não os alcança). Segunda carteira principal continua
impossível para todo mundo — `uq_portfolios_principal_paper` é índice, não
privilégio.

**2. `organizations` ganha `UPDATE (updated_at)` para o worker, e só isso.** O
PostgreSQL cobra `ACL_UPDATE` por `SELECT ... FOR SHARE`, e a ordem de travas do
contrato é sistema → organização → carteira. Sem essa coluna a admissão inteira
morria em *permission denied for table organizations* antes de decidir qualquer
coisa (T3.12, bloqueante A). É estritamente mais estreito que o `DELETE` que o
papel tem nessa tabela desde a `0001` (§15.4) e **não** alcança
`organizations.kill_switch_state`: travar uma organização continua sendo ato de
pessoa pela API, auditado pela constraint trigger da §18.7 — medido: `UPDATE
organizations SET kill_switch_state = 'EMERGENCY'` como `hunter_worker` responde
*permission denied for table organizations*.

**3. A API pede, lê e autoriza pessoas.** `hunter_app` perde
`INSERT`/`UPDATE`/`DELETE` em `portfolio_equity_snapshots` e `UPDATE`/`DELETE` em
`trade_proposals`.

- A curva é a **evidência** de que a carteira se recuperou (`hunter_core.risk.curve`)
  e o **teto** contra o qual todo pico que sobe é medido (§18.7). A RLS não protege
  a integridade dos números de um tenant contra o próprio request handler daquele
  tenant: um ponto fabricado de 20.000 no carimbo certo é uma recuperação que a
  retomada seguinte aceita. A API lê; o worker escreve.
- Em `trade_proposals` sobram `SELECT` e `INSERT`, porque registrar um pedido
  manual *é* trabalho da API. `UPDATE` e `DELETE` saem porque decidir é da
  admissão, e a admissão roda como o motor (o contador `fifo_v1` mora em
  `portfolio_risk_state`, §18.3). Sem isso um handler podia virar uma proposta
  recusada em `approved` ou alargar uma reserva depois da decisão que a
  dimensionou.

**4. Retomar é de OWNER.** A rota `POST …/risk/kill-switch/resume` declarava
`require_org(TRADER)`, o piso que `docs/SECURITY.md` §2 documentava numa linha só
para "kill switch de portfolio". Travar e destravar não são o mesmo ato: travar é
proteção (o motor faz sozinho); sair de um bloqueio é o que a diretiva reserva
para a autorização do dono. Com o piso antigo, um TRADER convidado destravava uma
carteira que o motor bloqueou. `SECURITY.md` §2 passa a ter **duas linhas** e a
rota exige OWNER. Não há allowlist nomeando uma pessoa — seria um segundo sistema
de identidade ao lado do Clerk; OWNER é o papel que o modelo já tem para "de quem
é este dinheiro". Quem retoma continua nomeado na trilha, na mesma transação do
movimento.

### 19.3 Três colunas — e uma que **não** entrou

```
trade_proposals             (+) request_digest TEXT
  CHECK request_digest IS NULL OR char_length(request_digest) BETWEEN 1 AND 128

portfolio_equity_snapshots  (+) brl_unavailable_reason TEXT
                            (+) marks_stale BOOLEAN NOT NULL DEFAULT false
  CHECK brl_unavailable_reason IS NULL
     OR (fx_observation_id IS NULL AND char_length(brl_unavailable_reason) BETWEEN 1 AND 64)
```

**`request_digest` é parte da identidade do pedido, não um segundo `idempotency_key`.**
A chave diz "é o mesmo pedido"; o digest é o que **prova**. Sem ele, o replay de
uma proposta **recusada** só podia ser comparado com as quatro colunas que estão
gravadas (carteira, mercado, direção, origem), então um segundo pedido diferente
que reusasse a chave voltava como a recusa do primeiro (T3.12, pendência 1). É
anulável porque uma proposta escrita antes desta revisão genuinamente não tem
digest, e string vazia alegaria um. **Desde a `0009_paper_geometry` (§21.2) ele é
nulo em toda linha que a API arquiva**, e por trigger: a API calcula o digest e o
devolve ao chamador, o motor recomputa e grava o dele quando decide, e o que some
é a persistência de uma prova escolhida por quem ela vincula.

**`brl_unavailable_reason` e `marks_stale` são a dívida da T3.3b.** A §18.2 já
dizia que FX indisponível deixa "o USDT apurável e o BRL indisponível **com
motivo**, nunca extrapolado" — e não havia coluna para o motivo. O CHECK é a
frase inteira: um ponto que **nomeia** uma observação foi convertido, então não
pode também declarar a conversão indisponível, e um motivo vazio não declara nada
(o argumento do §16.2 sobre `no_entry_reason`). `marks_stale` é o outro eixo: o
ponto é gravado mesmo com marcações velhas — recusar deixaria um buraco na curva
exatamente quando a carteira está degradada —, mas gravado **como estimativa**,
para que a evidência da retomada e o gráfico saibam distinguir sem inferir por
carimbo. As duas colunas são escritas pelo worker; a API só as lê.

**`applied_attempts` não entrou, e isso é decisão.** A T3.4b derivou a
idempotência da execução de `fills.execution_key` (único por
`(organization_id, execution_key)`, §18.3) e de `orders.client_order_id` (único
por carteira, §7) — as duas já existem e já são chave. Um contador de tentativas
seria uma **segunda resposta** para a pergunta que o schema já responde, e a
primeira vez que as duas discordassem ninguém saberia qual vale. Fica registrada
aqui como dívida fechada por não existir, e não como esquecimento.

### 19.4 Um `INSERT` da API é um **pedido**, e o schema diz isso

O grant impede a API de **editar** uma decisão; não impede a API de **escrever**
uma, porque `INSERT` carrega todas as colunas. Nada impediria um handler de gravar
uma linha já com `status = 'approved'`, um `risk_decision` de autoria própria e
uma reserva anexada — uma decisão que o Risk Engine nunca tomou, indistinguível
depois de uma que ele tomou, e segurando capital no orçamento de participação
(§18.5).

`trade_proposals_the_app_only_files_requests` (`BEFORE INSERT`) fecha isso: quando
o chamador tem os privilégios da aplicação **e nada além deles**
(`pg_has_role(current_user, 'hunter_app', 'USAGE') AND NOT pg_has_role(…, 'hunter_worker', …)`
— nome não é privilégio, §18.7), a linha tem de ser um pedido: `source = 'manual'`,
`status = 'pending'`, sem `risk_decision`, sem `rejection_reason`, sem
`decided_at`, sem `admission_seq` e sem reserva (`reservation_state = 'none'`,
`reserved_slot = false`). O motor e o operador inserem à vontade.

**A `0009_paper_geometry` amplia esta trigger (§21.2), e a tabela vigente é a de
lá.** Ela mantém a cláusula acima palavra por palavra e acrescenta duas: o pedido
tem de **carregar** `request_payload` e não pode carregar `request_digest` nem
`kill_switch_snapshot`. O motivo é a S1 da revisão de segurança desta revisão — a
prova de identidade de um pedido não pode ser escolhida por quem ela vincula.

**`pending`, não `requested`.** O brief desta tarefa pedia `status='requested'`;
`proposal_status` (§7) não tem esse rótulo e ganhar um exigiria `ALTER TYPE ...
ADD VALUE` — um rótulo novo é uma promessa de que existe um estado novo, e não
existe: `pending` já é exatamente "pedida, ainda não decidida". Desvio declarado
em vez de silencioso.

### 19.5 Guardas

**Não há guarda de upgrade, e isso é afirmação.** Esta revisão acrescenta duas
colunas anuláveis e uma com default, e **estreita** privilégios: nada que já
esteja gravado passa a ser irrepresentável, então não há nada que um backfill
honesto não produza. A `0002`/`0003`/`0006` param quando param porque criam
invariantes sobre dado existente; esta não cria nenhum.

**O downgrade recusa duas coisas** (§17.7: reverter é permitido, perder obrigação
ou evidência não é):

| Guarda | O que se perderia |
|---|---|
| proposta com `request_digest` | a identidade canônica do pedido que aquela decisão respondeu — não derivável das colunas que sobram, e é contra ela que um replay de recusa é comparado |
| ponto de equity com `brl_unavailable_reason` ou `marks_stale` | cada um volta a parecer um ponto plenamente precificado e recém-marcado: exatamente a extrapolação que a §18.2 proíbe |

Os **grants** não têm guarda: o downgrade os alarga de volta ao que a `0001`
concedeu, o que é declaração de privilégio, não fato sobre dado. E ele devolve
exatamente aquilo — `INSERT`/`UPDATE`/`DELETE` na curva e `UPDATE`/`DELETE` na
proposta para `hunter_app`, e retira as duas colunas do worker —, nunca um
`GRANT ALL`.

### 19.6 Consequências operacionais, declaradas

- **A abertura da carteira passa a rodar como `hunter_worker`.**
  `open_paper_wallet` grava o primeiro ponto da curva na mesma transação da
  carteira, da linha de trava e da âncora (§18.2), e a API não escreve mais a
  curva. `infra/scripts/open_paper_wallet.py` abre a transação com
  `tenant_session(..., db_role="hunter_worker")`. É a mesma classe de ato que
  remover um tenant (§15.4): operação de operador, não de request handler. O
  preço é que essa transação atravessa a RLS (o papel tem `BYPASSRLS`), e o que
  a segura é o caminho único de escrita com o índice `uq_portfolios_principal_paper`
  do outro lado.
- **A T3.6, achado 2, fecha pelo lado do worker e continua aberto pelo lado da
  API.** `hunter_worker` agora move a trava **e** enfileira `kill_switch.changed`
  na mesma transação, então `record_transition(publish=True)` é possível no
  caminho automático. A **retomada pela API** continua sem `INSERT` em
  `outbox_events` — deliberado: o worker publica, e dar à API a capacidade de
  enfileirar era o que a T3.12 (bloqueante C) pedia e o que esta decisão recusa.
  O que sobra é a releitura de 10 s, que é a garantia em que o contrato §5 se
  apoia.
- **A T3.12 deixa de precisar do grant experimental.** `ORG_ROW_LOCK_GRANT` e
  `apply_pending_grants` saíram dos testes da admissão: `admit()` roda inteiro
  como `hunter_worker` no schema íntegro.
- **O que continuou largo aqui, e foi fechado na `0008` (§20.1):** `hunter_app`
  manteve DML completo em `orders`, `fills`, `positions` e `trades` (`0001`,
  `APP_WRITE_TABLES`). Nenhuma rota escrevia essas tabelas — quem executa é o
  worker —, então o mesmo argumento da curva se aplicava a elas, e fechá-las
  ficou para uma revisão própria com a T3.5/T3.8 na mão para dizer o que a API
  ainda precisa poder escrever. **A resposta veio e é "nada":** a T3.8a entregou
  sete `GET` (`routers/portfolio.py`) e nenhuma escrita, e a `0008_paper_roles_2`
  revoga `INSERT`/`UPDATE`/`DELETE` nas quatro. Foi declarado aqui em vez de
  descoberto por uma revisão de segurança depois — e a revisão de segurança
  seguinte o achou mesmo assim, reproduzido como o papel (§20.1): declarar uma
  lacuna não é fechá-la, e o intervalo entre as duas revisões foi tempo real em
  que a API podia forjar um fill.
- **`portfolio_exit_intents` e `participation_consumptions` continuam sem
  `DELETE` para os dois papéis**, como a §18.9 os classificou. O brief desta
  tarefa dizia "DML completo" para o worker nas duas; conceder `DELETE` desfaria
  exatamente o que aquela seção argumenta — apagar um consumo executado devolve
  em silêncio o orçamento do mercado, e uma intenção é a prova de que uma posição
  esteve protegida. O worker escreve tudo o que o código dele de fato escreve
  (`INSERT`/`UPDATE` na intenção, `INSERT` no consumo). Desvio declarado.

### 19.7 Pooler e travas

Nada aqui depende de estado de sessão: os grants são fato de catálogo e a trigger
lê só `NEW` e `pg_has_role`. Sem prepared statement de sessão, sem
`LISTEN`/`NOTIFY`, sem advisory lock de sessão — a serialização continua sendo a
linha de `portfolio_risk_state` e, um nível acima, o `FOR SHARE` na linha da
organização que esta revisão finalmente torna possível para o motor.

## 20. A API para de escrever execução, e a carteira nasce auditada — M3 (`0008_paper_roles_2`)

Oitava revisão, e a segunda seguida a mudar **quem** escreve em vez de **o quê**.
Não traz tabela nem coluna: fecha os três achados de DDL da revisão de segurança
da `0007` (`.claude/state/review-T3.1c-security.md`, "deve corrigir" D1, D3 e
D4), cada um reproduzido contra um Postgres real, como o papel real. O quarto
achado (D2) é uma guarda de cobertura na suíte da API e não tem DDL — está na
§20.4.

`0008_paper_roles_2` tem 18 caracteres; o teto de `alembic_version.version_num`
continua sendo 32 (§17.6). As listas desta revisão estão congeladas em
`ddl/paper_roles_2.py`, no padrão de §15.6/§16.5/§17.6/§18.9/§19.

**A frase que organiza as três correções:** um privilégio que ninguém usa não é
folga, é superfície. As três nascem do mesmo padrão — a `0006` e a `0007`
fecharam a porta certa e deixaram aberta a janela ao lado.

### 20.1 D1 — a API lê execução e não escreve nenhuma parte dela

```
REVOKE INSERT, UPDATE, DELETE ON orders, fills, positions, trades FROM hunter_app;
```

`SELECT` fica. `trade_proposals` **não muda** (`SELECT`/`INSERT`, §19.2 item 3):
registrar um pedido manual é a única escrita que a API de fato possui no caminho
de execução, e `trade_proposals_the_app_only_files_requests` (§19.4) já limita a
forma dela.

**O que estava aberto, reproduzido como `hunter_app`, na organização certa, onde
a RLS diz sim:** um fill fabricado, `positions.qty × 1000`, `DELETE FROM trades`,
`UPDATE orders` — os quatro aceitos. A RLS mantém um tenant fora das linhas de
outro e não diz absolutamente nada sobre o request handler *daquele* tenant
reescrevendo a própria história de execução.

**E é a mesma correção da curva, um nível abaixo.** A `0007` fechou
`portfolio_equity_snapshots` porque a curva é a evidência que a retomada lê
(§19.2, item 3). Mas a curva é **derivada** destas quatro tabelas: com a `0007`
sozinha, forjar deixou de ser "escrever o ponto" e passou a ser "escrever o fill",
e o resultado é pior — o ponto forjado passa a ser calculado, assinado e gravado
pelo `hunter_worker`, o papel em que todo leitor a jusante confia. Fechar a saída
e deixar a entrada aberta é mover a assinatura da fraude para a testemunha.

**Por que agora, e não na `0007`.** A §19.6 declarou esta lacuna e a adiou "para
uma revisão própria com a T3.5/T3.8 na mão para dizer o que a API ainda precisa
poder escrever". A resposta chegou e é **nada**: a T3.8a entregou sete rotas em
`apps/api/hunter_api/routers/portfolio.py` — lista, resumo, âncora, curva de
equity, posições, ordens e trades — e as sete são `GET`. A T3.5 escreve execução
como o motor. Fica registrado o custo do adiamento: entre a `0007` e a `0008`
houve tempo real em que a API podia forjar um fill, e **declarar uma lacuna não é
fechá-la**.

**A classificação é um *movimento*, não uma classe nova.**
`APP_READ_ONLY_TABLES_0008` = (`orders`, `fills`, `positions`, `trades`). As
quatro saem de `APP_WRITE_TABLES` (congelada na `0001`, que precisa continuar
descrevendo o que a `0001` fez) e entram na leitura. A partição exata do schema
sobre as classes do `hunter_app` — a garantia de §15.6 — continua valendo porque
`test_schema_privileges.py::test_the_grant_lists_cover_every_table_exactly_once`
**subtrai** esta tupla da classe de escrita antes de contar, e
`test_migrations.py::test_0008_reclassifies_only_tables_0001_had_already_classified`
prova que ela é subconjunto do que a `0001` já classificou — sem isso, a
subtração seria a porta de entrada de uma tabela sem classificação, no mesmo
papel que `test_0005_touches_no_table_0003_had_not_already_classified` cumpre do
lado do worker.

Provado como o papel e não perguntado ao catálogo, no padrão de §18.7:
`test_schema_privileges.py::test_the_app_role_reads_execution_and_writes_none_of_it`
roda os cinco statements da revisão e
`test_the_engine_still_writes_every_execution_table` guarda o outro lado — uma
revogação escrita no papel errado deixaria a T3.5 sem ninguém capaz de registrar
um fill, que é exatamente a parede que a `0007` levou em `portfolios` (§19.2,
item 1b).

### 20.2 D3 — `portfolios_are_born_audited`

```sql
CREATE CONSTRAINT TRIGGER portfolios_are_born_audited
  AFTER INSERT ON portfolios DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
  EXECUTE FUNCTION portfolios_are_born_audited();
```

Quando o autor tem os privilégios do motor **e nada além deles**
(`pg_has_role(current_user, 'hunter_worker', 'USAGE') AND NOT pg_has_role(…,
'hunter_app', …)` — nome não é privilégio, §18.7), a linha tem de satisfazer duas
condições:

1. **`type = 'paper' AND NOT is_arena`**;
2. **uma linha de `audit_logs` da mesma organização escrita nesta transação**,
   `a.organization_id = NEW.organization_id AND a.xmin = pg_current_xact_id()::xid`
   — exatamente o formato de prova da §18.7.

**O que a `0007` abriu sem querer.** O item 1b da §19.2 deu `INSERT` em
`portfolios` ao `hunter_worker` porque abrir a carteira é uma transação só, e
disse "é `INSERT` e nada mais: o motor cria a carteira e move a trava". `INSERT`
carrega **todas as colunas**, e o papel tem `BYPASSRLS`. Três linhas que ninguém
pretendeu, as três reproduzidas:

| Linha | Por que é pior do que parece |
|---|---|
| `is_arena = true` | `uq_portfolios_principal_paper` é `WHERE type = 'paper' AND NOT is_arena` (§18.8), então a arena fica **fora** do índice: é uma segunda carteira que a própria trava da permanência não enxerga |
| `type = 'live'` | um portfolio *live* num milestone cuja diretiva é paper-only; todo leitor a jusante o trata como dinheiro real |
| carteira em **outra organização** | a RLS não filtra quem a atravessa, e nenhuma outra constraint olha para quem pediu |

As três chegavam sem âncora, sem `portfolio_risk_state` e sem auditoria — e é
essa a parte mais profunda: **uma carteira cujo nascimento ninguém registrou não
tem começo a reconstruir**, e a proibição de reset da diretiva é feita cumprir
justamente por essa história.

**A condição de auditoria é `xmin`, não `EXISTS`, e pela mesma razão do
bloqueante 1 da §18.7:** estar auditado *em algum momento* não é estar auditado
*por este ato*. Com `EXISTS`, uma única linha de `audit_logs` da organização
autorizaria toda abertura futura dela, para sempre. `xmin` não custa coluna nova
em tabela quente, não custa FK de uma tabela de tenant para uma append-only e não
obriga nenhum escritor a mudar — `open_paper_wallet` já grava a auditoria no
mesmo commit (§18.2). `audit_logs` é particionada e `xmin` lê corretamente pela
pai particionada no Postgres 16 (medido); o motor tem `BYPASSRLS`, então enxerga a
linha que acabou de escrever.

**É constraint trigger adiada, e isso não é estilo.** A auditoria é a **última**
coisa que `open_paper_wallet` escreve, então um `BEFORE INSERT` recusaria
exatamente o caminho que a trigger existe para abençoar. Adiada para o COMMIT o
quadro inteiro existe e a guarda não dita ordem de statement — mesmo desenho e
mesmo motivo de `portfolio_risk_state_opens_honestly` (§18.7).

**O preço declarado é o mesmo da §18.7, e é uma recusa falsa, nunca uma aprovação
falsa:** uma linha inserida dentro de um `SAVEPOINT` carrega o xid da
subtransação. Nenhum caminho de escrita usa um; a regra fica escrita em vez de
descoberta.

**Quem a guarda deliberadamente não alcança.** O operador, o dono do banco e um
superusuário têm os **dois** papéis, então não são "só o motor" e continuam
escrevendo um portfolio `shadow` ou uma arena à mão; `hunter_app` está intacta e
continua criando os portfolios não-principais que o produto oferece. Estreitar
isso por `current_user` seria o erro de "nome não é privilégio" ao contrário.

A abertura real continua passando, e isso é provado através da função real e como
o papel real, sem nada acrescentado à ela em nome da guarda
(`test_portfolio_opening.py::TestTheBirthGuardBoundsTheEngineGrantWithoutBreakingTheOpening`).
As recusas cruas estão em `test_schema_paper.py`, uma por linha da tabela acima,
mais a auditoria de outra organização e a auditoria bancada antes.

### 20.3 D4 — o motivo viaja com a trava

O `WHEN` das duas constraint triggers da §18.7 passa a ser:

```sql
WHEN (OLD.kill_switch_state IS DISTINCT FROM NEW.kill_switch_state
   OR OLD.kill_switch_reason IS DISTINCT FROM NEW.kill_switch_reason)
```

`kill_switch_reason` era reescrevível **sem transição nenhuma**: a guarda não
disparava, `kill_switch_transitions` continuava dizendo uma coisa e a coluna que
a tela do OWNER lê (`routers/risk.py`, `services/portfolio_queries.py`,
`services/radar_org_derivation.py`) dizia outra — permanentemente, e sem ator.
Uma trava com o motivo errado é pior que uma trava sem motivo: ela explica.

**Consequência declarada: reescrever só o motivo passa a ser impossível para todo
papel.** `kill_switch_transitions` carrega `CHECK (from_state <> to_state)`, então
uma parada não é representável como transição — e a leitura pretendida do achado
é exatamente essa: um motivo que ninguém consegue atribuir a um movimento é
legenda, não registro. Não custa nada ao caminho real:
`hunter_core.risk.transitions.record_transition` é o escritor único e move
`kill_switch_state` e `kill_switch_reason` no **mesmo `UPDATE`**, que é também a
razão pela qual o grant de coluna da `0007` nomeia os dois juntos.

O corpo das duas funções ganha um ramo, para a recusa dizer o que aconteceu em
vez de *"moved its kill switch from WARNING to WARNING"* — a mensagem é o valor
inteiro de uma guarda que alguém encontra no COMMIT. Como o `WHEN` de uma trigger
não pode ser alterado, as duas são derrubadas e recriadas em volta de um
`CREATE OR REPLACE FUNCTION`.

**O corpo é congelado na `0008`, em cópia, e isso é deliberado.** Ler
`ddl.paper._audited_move_body` em tempo de migração deixaria uma edição futura na
`0006` redefinir em silêncio o que a `0008` instala — a armadilha retroativa que
§16.5 e §17.1 congelaram todas as outras listas para evitar. As duas não divergem
sem aviso: `test_schema_paper.py::test_the_audited_move_guard_still_proves_the_same_transition`
refaz as recusas que a `0006` mediu (sem transição; transição bancada por outra
transação) contra o corpo novo. O **downgrade** vai no sentido oposto e chama a
`create_kill_switch_audit_guard()` da própria `0006`: reverter para a `0006` é ter
a guarda que a `0006` descreve, e `ddl/paper.py` é essa descrição.

Não há trigger para o escopo `system` — ele não tem linha (§18.9), e a ausência
continua deliberada.

### 20.4 D2 — as duas guardas de cobertura de rota voltaram a verde

Sem DDL, e registrado aqui porque é a mesma classe de falha: uma verificação que
não verifica.

`apps/api/tests/integration/test_rbac_matrix.py` e `test_isolation.py` afirmam,
cada uma, que a sua tabela de rotas cobre **toda** operação servida sob
`/api/v1/orgs/{org_id}`. As sete rotas da T3.8a entraram no app e não entraram
nas listas: **16 declaradas contra 23 servidas**. Em `test_isolation.py` o número
aparecia duas vezes como literal — `range(16)` na parametrização e
`assert len(operations) == 16` — e o primeiro é o que tornava a falha *silenciosa*
em vez de vermelha: a parametrização simplesmente parava na décima sexta entrada.
As sete entram como **VIEWER** nas duas listas (é o piso que `routers/portfolio.py`
declara: são leituras de painel) e os literais viram `len(ROUTE_COUNT)`/`len(ROUTES)`,
derivados da própria lista, para que os dois números não possam mais discordar.

E a sugestão 5 da mesma revisão vira teste
(`test_risk_api.py::test_an_owner_of_another_organization_cannot_resume_this_wallet`):
OWNER da organização A fazendo `POST …/risk/kill-switch/resume` na carteira de B
recebe **404** nas duas grafias do pedido — com o id de A no caminho, quem recusa
é `_owned`; com o id de B, é `require_org`, antes de qualquer leitura — e nada é
escrito: a carteira segue travada e a última transição continua sendo a automática.
Ser dono *em algum lugar* não é ser dono *aqui*.

### 20.5 Guardas: não há, e as duas ausências são afirmação

**Nenhuma guarda de upgrade.** Esta revisão estreita privilégios e acrescenta uma
trigger de `INSERT`. Nada que já esteja gravado passa a ser irrepresentável — as
linhas que a trigger nova recusaria não podem existir retroativamente, porque ela
só dispara em `INSERT`. A `0002`/`0003`/`0006` param quando param porque criam
invariantes sobre dado existente; esta não cria nenhum, como a `0007` (§19.5).

**Nenhuma guarda de downgrade, e pelo mesmo motivo que os grants da `0007` não
têm** (§19.5: reverter é permitido, perder obrigação ou evidência não é). O que o
downgrade desfaz é declaração de privilégio e comportamento de trigger, nunca fato
sobre dado:

| O que o downgrade devolve | O que se perde de dado |
|---|---|
| `INSERT`/`UPDATE`/`DELETE` em `orders`, `fills`, `positions`, `trades` para `hunter_app` — nomeados, nunca `GRANT ALL` | nada; o `SELECT` que a `0008` preservou continua lá |
| `portfolios_are_born_audited` é derrubada | nada; as carteiras abertas sob ela continuam auditadas, e a auditoria delas é linha de `audit_logs`, que ninguém apaga |
| o `WHEN` das duas guardas volta a `kill_switch_state` sozinho | nada; um `kill_switch_reason` já gravado sobrevive intacto. O que volta é a *capacidade* de reescrever um sem transição |

Um banco revertido para a `0007` é utilizável pelo código que rodava contra a
`0007` — que é o critério que a §17.7 fixa para todo downgrade — e o round trip
`downgrade -1` / `upgrade head` é verificado por
`test_migrations.py::test_0008_reverses_to_the_execution_privileges_0001_shipped`,
que confere os privilégios, a ausência da trigger e o `WHEN` estreito no meio do
caminho, e o `alembic check` no fim.

### 20.6 Pooler

Nada aqui depende de estado de sessão: os grants são fato de catálogo e as duas
triggers leem só `NEW`/`OLD`, `pg_has_role` e `pg_current_xact_id()`. Sem prepared
statement de sessão, sem `LISTEN`/`NOTIFY`, sem advisory lock de sessão — a
serialização continua sendo a linha de `portfolio_risk_state` (§18.10, §19.7).

## 21. A geometria do pedido e o pó que não é posição — M3 (`0009_paper_geometry`)

Nona revisão. Duas colunas, um CHECK cada, um índice parcial e três recusas na
trigger do pedido. Ela fecha uma lacuna **bloqueante** e um "deve corrigir" que
três tarefas alcançaram por três caminhos diferentes:

| De onde veio | O que estava impossível |
|---|---|
| T3.5, `.claude/state/notes-T3.5.md` §5.1 (bloqueante) | um pedido arquivado pela API **não podia ser decidido**: `trade_proposals` guarda carteira, mercado, direção, origem, chave e digest, e nenhuma coluna para `entry_ref`, `stop`, `requested_notional` ou `assumed_costs`. O execution-worker só podia registrar `pending_request_without_geometry` — uma vez por segundo, por pedido, para sempre |
| `.claude/state/review-T3.5.md` item 3 (deve corrigir) | o **pó** do spot contava como posição viva: `closing` com `qty > 0` segura vaga, exposição e duplicidade. Reproduzido 4 h depois do stop, com a segunda ordem na moeda recusada |
| S1 da `.claude/state/review-T3.1c-security.md` | `_REQUEST_SHAPE` (§19.4) não cobria `request_digest` nem `kill_switch_snapshot`, e o motor lia o digest de volta com `coalesce(request_digest, :digest)` — isto é, **confiava na prova escrita por quem ela existe para vincular** |

`0009_paper_geometry` tem 19 caracteres; o teto de `alembic_version.version_num`
continua sendo 32 (§17.6). As listas desta revisão estão congeladas em
`ddl/paper_geometry.py`, no padrão de §15.6/§16.5/§17.6/§18.9/§19/§20.

A frase que organiza as duas colunas: **uma coluna a menos não é simplicidade
quando o que falta é o que a decisão precisa ler.** As duas nasceram do mesmo
sintoma — um worker que sabe que há trabalho e não consegue fazê-lo — e as duas
são estado durável, não cache.

### 21.1 As duas colunas

```
trade_proposals  (+) request_payload JSONB NULL
  CHECK request_payload IS NULL OR (
        jsonb_typeof(request_payload) = 'object'
    AND coalesce(jsonb_typeof(request_payload -> 'client_key'),         'absent') IN ('string')
    AND coalesce(jsonb_typeof(request_payload -> 'market_id'),          'absent') IN ('string')
    AND coalesce(jsonb_typeof(request_payload -> 'direction'),          'absent') IN ('string')
    AND coalesce(jsonb_typeof(request_payload -> 'entry_ref'),          'absent') IN ('string')
    AND coalesce(jsonb_typeof(request_payload -> 'stop'),               'absent') IN ('string')
    AND coalesce(jsonb_typeof(request_payload -> 'target'),             'absent') IN ('string','null')
    AND coalesce(jsonb_typeof(request_payload -> 'requested_notional'), 'absent') IN ('string','null')
    AND coalesce(jsonb_typeof(request_payload -> 'assumed_costs'),      'absent') IN ('object'))
  -- ck_trade_proposals_request_payload_is_a_geometry

positions        (+) is_residual BOOLEAN NOT NULL DEFAULT false
  CHECK NOT is_residual OR status = 'closing'   -- ck_positions_residual_is_a_closing_position
  INDEX (organization_id, portfolio_id) WHERE status <> 'closed' AND NOT is_residual
  -- ix_positions_org_portfolio_live
```

**Oito chaves, e todas presentes.** "Ausente" é escrito como `null` de JSON,
nunca por omissão — a mesma escolha que `opportunity_stage` fez com `NONE` em vez
de coluna anulável (§17.1). Um leitor não pode ter de decidir se um `target` que
falta quer dizer "sem alvo" ou "quem escreveu esqueceu", e uma chave obrigatória
é uma chave que a rota da T3.8 e a ponte da T3.14 preenchem **sem migração
nova**.

**Dinheiro é string de JSON**, como em todo lugar onde o projeto canonicaliza um
número (§17.8, `model_dump(mode="json")`): um número de JSON volta como float na
maioria dos parsers, e um preço que retorna como `0.30000000000000004` é
exatamente o bug que a disciplina do `Decimal` existe para impedir. O CHECK
recusa `entry_ref: 100` (número) e aceita `entry_ref: "100"`.

**O `coalesce` do CHECK não é enfeite — ele é a correção de um erro medido.**
`jsonb_typeof(payload -> 'k')` é SQL `NULL` para chave **ausente** e a string
`'null'` para chave presente com valor JSON nulo, o que parece ser exatamente a
distinção desejada. Não basta: **um CHECK é satisfeito quando a expressão dele
avalia para `NULL`** ("desconhecido não é violação"), então
`jsonb_typeof(payload -> 'target') IN ('string','null')` **aceitava um payload
sem `target` nenhum** — reproduzido num Postgres 16 real, na primeira versão
desta constraint, antes do teste existir. `coalesce(…, 'absent')` transforma o
desconhecido num valor que nenhuma lista permite, e presença e tipo voltam a ser
uma comparação só. O operador `?&` faria a metade da presença e não é usado:
ele põe um `?` literal em DDL que vários paramstyles de DBAPI leem como
placeholder, e ainda exigiria a metade do tipo. **Desvio declarado** em relação
ao brief da tarefa, que pedia `jsonb_typeof`/`?&`.

**O que deliberadamente não está no payload:** `organization_id`,
`portfolio_id`, `agent_id` e `signal_id`. São **colunas**, e um payload que as
repetisse seria uma segunda resposta para uma pergunta que a linha já responde —
o argumento que a §19.3 faz sobre `applied_attempts`. `market_id` e `direction`
*são* repetidos, e essa é a exceção de propósito: são o que torna o payload
legível sozinho, e as FKs compostas da §18.3 já tornam irrepresentável um
desacordo entre os dois.

**`request_payload` é anulável, e a nulidade tem dono.** O `INSERT` do motor
(`hunter_core.admission.record.insert_proposal`) passa a escrevê-lo também — o
que torna "recomputar o digest a partir do payload" verdade de **toda** linha e
não só das que uma pessoa arquivou (era a pendência §5.2 de
`.claude/state/notes-T3.14.md`) —, mas a coluna continua anulável porque
propostas escritas antes desta revisão genuinamente não têm geometria, e um
objeto vazio alegaria uma. O que **não** é opcional é o pedido da API: essa é a
trigger, não a coluna (§21.2).

**`is_residual` é o pó, e o pó não é posição.** Uma compra spot paga a taxa em
moeda, então a quantidade vendável quase nunca é múltiplo do `step_size` e
sobram alguns décimos de milésimo abaixo do `min_qty`, invendáveis a qualquer
preço. A decisão registrada em `review-T3.5.md` item 3 é: o resíduo **não conta
vaga, nem exposição, nem duplicidade**, e continua **visível e valorizado** pela
marca. O CHECK prende a marcação ao único estado que pode segurar pó: uma
posição `open` que se declarasse resíduo seria uma posição que a carteira acha
que tem e nenhum leitor conta — o pior dos dois lados —, e uma `closed` não
segura nada, então não tem resíduo a declarar. O assentamento (vender o pó junto
da próxima saída quando o acumulado da moeda alcançar `min_qty`) é do worker,
não do schema.

**O índice parcial é a pergunta que os leitores passam a fazer.**
`(organization_id, portfolio_id) WHERE status <> 'closed' AND NOT is_residual` —
começando por `organization_id` porque a §1 exige isso de todo índice composto de
tabela de tenant. Como o Alembic **não compara predicado de índice** (§17.3),
a chave e o predicado são lidos de `pg_indexes.indexdef` por
`test_schema_paper.py`.

### 21.2 Um pedido carrega a sua geometria e nunca a sua própria prova

A trigger `trade_proposals_the_app_only_files_requests` (§19.4) ganha dois ramos
e continua com o primeiro. Quando o chamador tem os privilégios da aplicação **e
nada além deles**, a linha tem de ser um pedido:

1. **sem decisão** — `source = 'manual'`, `status = 'pending'`, sem
   `risk_decision`, `rejection_reason`, `decided_at`, `admission_seq` nem
   reserva (a cláusula da `0007`, copiada sem mudança);
2. **sem prova própria** — `request_digest IS NULL` e
   `kill_switch_snapshot = '{}'`;
3. **com geometria** — `request_payload IS NOT NULL`.

**Por que a prova é do motor (S1).** O digest é o que *prova* que dois pedidos
são o mesmo; um digest escolhido pelo chamador não vincula ninguém. O motor lia
`coalesce(request_digest, :digest)`, então um handler — ou uma injeção dentro de
um, na organização certa, onde a RLS diz sim — podia fazer um segundo pedido
**diferente** voltar como a decisão do primeiro, que é exatamente o buraco que a
§19.3 criou o digest para fechar. Agora não há o que "coalescer": a coluna chega
nula por construção e o motor recomputa o digest a partir de `request_payload`,
da linha e da referência de mercado, no instante em que decide.
`kill_switch_snapshot` é a mesma mentira um nível acima — ele registra *os três
escopos sob os quais a decisão foi tomada*, e um pedido arquivado horas antes não
foi decidido sob nada; um snapshot fornecido pela API seria um álibi anexado a
uma decisão que ninguém tinha tomado.

**Consequência para a API, e ela não é perda.** `apps/api/.../services/admission.py`
deixa de persistir `request_digest`. Ele continua sendo **calculado** e devolvido
ao chamador como a identidade do que foi pedido; o que some é a persistência dele
como prova. E o replay de uma linha **pendente** passa a ser comparado pelo
`request_payload` arquivado (`hunter_core.admission.dedupe._payload_pair`) — a
mesma informação um passo antes. Sem essa troca, comparar contra um digest sempre
nulo teria transformado toda chave reutilizada num replay silencioso do primeiro
pedido, que é o oposto do que a S1 pediu.

**A trigger é derrubada e recriada, com o corpo congelado em cópia.** Ler
`ddl.paper_roles._REQUEST_SHAPE` em tempo de migração deixaria uma edição futura
na `0007` redefinir em silêncio o que a `0009` instala — a armadilha retroativa
que §16.5 e §17.1 congelaram todas as outras listas para evitar. O **downgrade**
vai no sentido oposto e chama a `create_request_guard()` da própria `0007`:
reverter para a `0008` é ter a guarda que a `0007` descreve. Ele roda **antes** de
a coluna cair, porque o corpo da `0009` a nomeia e o da `0007` não.

### 21.3 `signal_id` já existia, e por isso não entra aqui

O brief desta tarefa previa acrescentar `trade_proposals.signal_id UUID NULL
REFERENCES agent_signals(id)` com índice, caso a T3.14 pedisse.
**A coluna existe desde a `0001_initial_schema`** (§7), anulável, com
`ON DELETE SET NULL` e índice próprio, e a ponte da T3.14 já a lê e escreve
(`bridge_repo.pending_signals` usa `NOT EXISTS … trade_proposals.signal_id = s.id`
como fila durável, e `hunter_core.admission.record.insert_proposal` a grava).
Não há nada a migrar, e acrescentar uma segunda coluna com o mesmo nome seria
impossível — acrescentar uma com outro nome seria a segunda verdade que o §17.8
descreve. **Desvio declarado em relação ao brief**, e a consequência: o
downgrade da `0009` **não tem guarda para `signal_id`**, porque esta revisão não
o remove.

### 21.4 Guardas

**Não há guarda de upgrade, e isso é afirmação.** `request_payload` é anulável e
toda linha guardada é honestamente nula; `is_residual` tem default `false` e toda
posição guardada honestamente não é pó; o CHECK do payload só fala de valores não
nulos e a trigger ampliada dispara só em `INSERT`. Nada que já esteja gravado
passa a ser irrepresentável, então não há nada que um backfill honesto não
produza. A `0002`/`0003`/`0006` param quando param porque criam invariantes sobre
dado existente; esta não cria nenhum — a mesma afirmação da `0007` (§19.5) e da
`0008` (§20.5).

**O downgrade recusa duas coisas** (§17.7: reverter é permitido, perder obrigação
ou distinção não é):

| Guarda | O que se perderia |
|---|---|
| proposta com `request_payload` | a geometria que uma pessoa de fato pediu — referência de entrada, stop, teto e hipótese de custo. Não é derivável de nenhuma coluna que sobra, e **todo pedido ainda pendente vira indecidível para sempre**, que é o estado que a `notes-T3.5.md` §5.1 mediu e esta revisão encerrou |
| posição com `is_residual` | cada pó volta a ser posição viva: segura vaga, conta como exposição e recusa a próxima ordem naquela moeda como duplicata — exatamente o que a `review-T3.5.md` item 3 reproduziu 4 h depois de um stop |

Nenhuma das duas apaga nada: elas contam os infratores e recusam nomeando-os,
com a instrução de exportar antes (o mesmo padrão e o mesmo limite da §18.9 —
exportar não muda predicado nenhum; o downgrade de um banco com carteira viva
não é operação de rotina).

**O que não é guardado, declarado em vez de descoberto:** propostas sem payload,
posições que não são pó, e o próprio `signal_id` (§21.3). E a trigger não tem
guarda: reverter o corpo dela é declaração de comportamento, não fato sobre dado
— o que volta é a *capacidade* de a API arquivar um pedido sem geometria, que é
o estado da `0008`.

### 21.5 Grants, RLS e pooler

**Nenhuma classe de grant muda, e nenhuma tabela é reclassificada.** As duas
colunas moram em tabelas que a `0001` já classificou e a `0007`/`0008` já
estreitaram: `trade_proposals` continua `SELECT`/`INSERT` para `hunter_app` e DML
completo para `hunter_worker`; `positions` continua **só leitura** para
`hunter_app` desde a `0008` (§20.1) e DML completo para o motor. Um privilégio de
tabela alcança as colunas novas por construção, então não há `GRANT` nesta
revisão — a tabela vigente da §19.1 continua correta como está.

**Nenhuma política de RLS muda**: as duas tabelas já são de tenant, com
`organization_id NOT NULL`, RLS habilitada e forçada e `tenant_isolation` própria
desde a `0001`. Que isso continue verdade das colunas novas é provado e não
suposto — `test_schema_paper.py::test_org_a_cannot_read_org_bs_geometry_or_its_dust`
lê o `request_payload` e o pó da organização A com o `app.current_org` de A e
conta zero linhas de B.

**Nada aqui depende de estado de sessão:** duas colunas, duas constraints, um
índice parcial e uma trigger que lê só `NEW` e `pg_has_role`. Sem prepared
statement de sessão, sem `LISTEN`/`NOTIFY`, sem advisory lock de sessão — a
serialização continua sendo a linha de `portfolio_risk_state` (§18.10, §19.7,
§20.6).

### 21.6 O que as tarefas vizinhas têm de ajustar

Declarado aqui porque nenhuma delas é deste diff (`services/**` é da T3.5b/T3.14
e não foi tocado):

| Onde | Ajuste |
|---|---|
| `packages/core/hunter_core/db/repositories/ledger.py` | `PositionRow.is_residual` é hoje uma **propriedade derivada** (`status == 'closing'`) com a nota "a durable `positions.is_residual` is filed for T3.1e"; passa a ler a coluna (`p.is_residual` no `SELECT`), e `open_positions` passa a filtrar `AND NOT p.is_residual` para usar `ix_positions_org_portfolio_live` |
| `services/execution-worker/.../positions.py` | `reduce_position(dust=True)` grava `is_residual = true` junto de `status = 'closing'` |
| `services/execution-worker/.../entry.py`, `bridge_repo.py` | as consultas de "moeda já comprometida" e de vagas acrescentam `AND NOT p.is_residual` |
| `services/execution-worker/.../admission_cycle.py` | `pending_requests` passa a ler `request_payload`, reconstrói o `ProposalRequest` (linha + payload + `markets`) e chama `decide_pending`; `report_unreadable`/`pending_request_without_geometry` deixa de existir para a linha que tem payload |
| `packages/core/hunter_core/admission/decide.py` | `coalesce(request_digest, :digest)` vira `:digest`: o motor recomputa e grava o seu, nunca herda o do chamador (S1) |
| `packages/core/hunter_core/admission/sources.py` (T3.8) | `target: Decimal \| None = None` em `ProposalRequest`, incluído em `request_digest` e em `request_payload` — a chave já está reservada (§21.1) e é o pedido da `notes-T3.14.md` §5.1 |

## 22. O propósito na versão, e o rótulo `paper` — M3 (`0010_strategy_purpose`)

Décima revisão. Uma coluna, um CHECK, a trigger de congelamento da `0002`
alargada e um estreitamento de grant. Ela fecha o achado da D10
(`.claude/state/decisions-delegated-2026-09-07.md`): o produtor só escrevia
`research_only` (literal cravado em `record.py`), os dois consumidores só
aceitavam `live`, e **o rótulo que a carteira paper precisa não existia em
lugar nenhum** — não era um valor de linha que faltava, era uma coluna.

`0010_strategy_purpose` tem 21 caracteres; o teto de `alembic_version.version_num`
continua sendo 32 (§17.6). As listas desta revisão estão congeladas em
`ddl/strategy_purpose.py`, no padrão de §15.6/§16.5/§17.6/§18.9/§19/§20/§21.

### 22.1 A coluna

```
strategy_versions  (+) purpose text NOT NULL DEFAULT 'research_only'
  CHECK purpose IN ('research_only', 'paper', 'live')   -- ck_strategy_versions_purpose_is_a_known_label
```

Sem guarda de upgrade, e isso é uma afirmação: toda linha existente é, e só
foi, `research_only` — o default preenche o que já era verdade (mesmo
raciocínio da §21.4). Os três rótulos:

| Rótulo | Quem escreve | Quem aceita |
|---|---|---|
| `research_only` | default da coluna; toda versão do Lab nasce assim | ninguém admite: evidência de sombra nunca vira ordem (decisão conjunta, item 9) |
| `paper` | **só** o script de ativação (`--paper-line`), na conexão de migração | a admissão (`hunter_core.admission.sources`) e, pela T3.15b, o portão da ponte |
| `live` | ninguém hoje | ninguém: recusado **por nome** no catálogo do worker (a versão nem é avaliada), na admissão e no script (`live é Fase 4; ENABLE_LIVE_TRADING=false`) |

### 22.2 Congelada depois da ativação

A trigger `shadow_freeze_strategy_version` da `0002` (§16.1) é **substituída, não
duplicada**: `ddl/strategy_purpose.py` copia a lista congelada de `ddl/shadow.py`,
acrescenta `purpose`, e recria a função e as duas triggers com o mesmo nome — o
mesmo desenho que a `0009` usou para o corpo da guarda do pedido (§21.2). O
downgrade chama o criador da própria `ddl/shadow.py`: voltar à `0009` é ter a
trigger que a `0002` descreve.

Consequência prática: a linha `paper` nasce **antes** da ativação (`draft`,
`activated_at IS NULL`) já com o rótulo, e a ativação a congela junto com
`code_ref`. Não existe "mudar uma versão de pesquisa para paper": é uma linha
nova, derivada (§22.4).

### 22.3 Grants — medido, não suposto

`REVOKE` de coluna **não estreita** um `GRANT` de tabela: o Postgres checa o
acesso à coluna como a **união** da ACL da tabela e da ACL da coluna (foi
exatamente isso que a `0007` usou ao contrário, §19.1). `hunter_worker` tinha
`INSERT, UPDATE` de tabela em `strategy_versions` desde a `0001`, então a
revisão faz o que de fato estreita: revoga os dois de tabela e os reconcede
**por coluna**, para todas as colunas exceto `purpose`. Omitir `purpose` na
lista de um `INSERT` continua usando o `DEFAULT` sem precisar do privilégio.

| Papel | `strategy_versions.purpose` | Demais colunas |
|---|---|---|
| `hunter_app` | SELECT | SELECT (só leitura desde a `0001`; nada a estreitar) |
| `hunter_worker` | SELECT | SELECT, INSERT, UPDATE por coluna — como a `0001` deu, menos esta |
| dono / `DATABASE_URL_MIGRATIONS` | tudo — é por aí que `infra/scripts/activate_strategy_version.py` escreve | tudo |

Provado em `packages/core/tests/integration/test_schema_privileges.py` (os dois
papéis leem; o worker não nomeia `purpose` num INSERT nem num UPDATE, e continua
inserindo uma versão que confia no default) e em `test_migrations.py` (CHECK
recusa um quarto rótulo; trigger alargada lida do `pg_proc`; `purpose`
congelado depois da ativação; round trip; downgrade recusado enquanto houver
linha com propósito diferente de `research_only`).

### 22.4 A linha `paper` é derivada, nunca convertida

`activate_strategy_version.py momentum v1 --paper-line --changelog "..."` cria a
linha `v<n+1>` (próximo `v<n>` livre da estratégia, para não colidir com um
`--supersede`) copiando `parameters_schema`, `default_parameters` e
`params_format` **da linha congelada**, com `code_ref` recalculado do módulo que
o digest congelado nomeia (recusa se o build atual divergir), `status = 'draft'`,
`activated_at = NULL`, `purpose = 'paper'`, e uma linha em `system_events`. A
fonte não é tocada; a coorte `research_only` continua rodando ao lado. Uma
linha `paper` não deprecada por estratégia. **Nada é ativado**: ativar a linha
derivada é um `activate` separado, auditado, que resolve o código pelo
`code_ref` congelado (o `v2` não tem entrada no registro) — e as sete condições
da D10 vêm antes dele.

### 22.5 O que as tarefas vizinhas ajustam

- `services/strategy-worker`: o catálogo lê `purpose` e recusa `live` na origem
  (`purpose_live_forbidden`); `record.py` carimba `envelope["purpose"] =
  version.purpose` — o `SignalEnvelope` das estratégias continua nascendo
  `research_only` porque o código não sabe para que coorte roda.
- `hunter_core.admission.sources`: `ProposalRequest.purpose` default `paper`;
  `origin()` recusa `live` por nome e `research_only` como antes.
- `apps/api` (ordem manual): nasce `purpose = paper`.
- T3.15b (`services/execution-worker/bridge_screen.py`): importa
  `PURPOSE_PAPER` de `hunter_core.strategies.envelope` e admite `paper`.

### 22.6 Correção de 2026-09-08 (HIGH da revisão de segurança): a ponte decide
pela coluna, não pelo envelope

A T3.15b (§22.5) fazia o portão ler `purpose` de
`agent_signals.supporting_features`/`signal_outcomes.meta` — o envelope que
`hunter_worker` escreve com INSERT/UPDATE de tabela cheios — e nunca chegava a
olhar a coluna que esta seção protege. Uma escrita indevida no envelope (bug em
`record.py`, ou qualquer caminho futuro com o papel do worker) carimbando
`purpose: "paper"` num sinal de uma versão `research_only` chegaria à carteira
sem nunca ter passado pelo script auditado.

`bridge_repo._SIGNAL_SELECT` agora lê `v.purpose` (a query já fazia `JOIN
strategy_versions v`) e `ShadowSignal.purpose` é **essa** coluna —
`ShadowSignal.envelope_purpose` guarda o rótulo do envelope só como
contraprova. `bridge_screen.screen_signal` compara os dois **antes** de
qualquer outra triagem: divergência é recusada `purpose_mismatch` e logada em
`warning` (não `info`, como toda outra recusa) — um sinal com coluna e
envelope discordando é evidência de uma escrita que não deveria ter
acontecido, não ruído de operação. Os dois rótulos vão no log
(`column_purpose`, `envelope_purpose`).

## 23. Nada além de SELECT: fechando o buraco da ativação — M3 (`0011_strategy_activation_owner`)

Décima primeira revisão. A `0010` protegeu o *rótulo*; a revisão de segurança
(MEDIUM 4) e a de database-architect (A4) mediram o mesmo buraco de lados
opostos: a trigger de congelamento só dispara `WHEN (OLD.activated_at IS NOT
NULL)`, então uma linha `draft` — exatamente a forma que
`--paper-line` deriva, esperando as sete condições da D10 — podia ser
**ativada** (`UPDATE strategy_versions SET status='active', activated_at=now()`)
ou **apagada** pelo papel `hunter_worker`, sem linha em `system_events`, sem
`--changelog` e sem decisão do Everton. Isso é pré-existente desde a `0001`,
não foi introduzido pela `0010` — mas é a revisão que promete "escrita só pelo
script auditado", e a promessa era mais estreita do que soava.

### 23.1 O que é revogado

Toda consulta de produção contra `strategy_versions` como `hunter_worker` é
`SELECT` (`catalogue.py`, `replay/load.py`, `metrics.py`, `bridge_repo.py`); os
únicos escritores são a conexão de dono (`activate_strategy_version.py`,
`seed.py`) e `paper_line.py`, que também roda como dono. A `0011` revoga:

| Privilégio | Colunas/escopo |
|---|---|
| `UPDATE` | `status`, `activated_at`, `deprecated_at`, `code_ref`, `parameters_schema`, `default_parameters`, `params_format` |
| `DELETE` | tabela inteira |
| `INSERT` | tabela inteira (todas as colunas do grant da `0010`) |

`INSERT` sai por completo porque nada insere como `hunter_worker` — o mesmo
motivo que já tirava `DELETE` de discussão para `hunter_app` desde a `0001`.

### 23.2 O que sobra

`UPDATE` em `id`, `strategy_id`, `version`, `changelog`, `created_at` — as
cinco colunas de `ddl.strategy_purpose.WORKER_COLUMNS_EXCEPT_PURPOSE` (doze)
que ficam de fora de `REVOKED_LIFECYCLE_COLUMNS` (sete). Nenhuma delas é
escrita por código de produção como `hunter_worker` hoje — a lista não nasceu
de um caso de uso, nasceu de deixar intocado o que nenhuma das duas revisões
apontou como problema, com a mesma barra de evidência que um `GRANT` exigiria.
`REMAINING_WORKER_UPDATE_COLUMNS` é calculada por subtração das duas listas
congeladas, não escrita duas vezes, para as duas nunca divergirem em silêncio.

| Papel | `strategy_versions` |
|---|---|
| `hunter_app` | `SELECT` (inalterado desde a `0001`) |
| `hunter_worker` | `SELECT`; `UPDATE` só em `id`/`strategy_id`/`version`/`changelog`/`created_at` |
| dono / `DATABASE_URL_MIGRATIONS` | tudo — ativação, derivação `--paper-line` e seed |

### 23.3 Sem trava longa, sem guarda de downgrade

Ao contrário da `0010`, esta revisão não faz `ALTER TABLE`: é só
`GRANT`/`REVOKE`, que não toma `ACCESS EXCLUSIVE` na relação (mesma medição da
`0005`, §15.6) — não reabre a janela de ~15 s que a `0010` abriu. E reverter
não perde dado nenhum: o downgrade apenas regrante o que `0001`/`0010` já
davam, então não há guarda como a da `0010` (§17.7) — não há nada que uma
linha existente possa "já ter violado".

### 23.4 Provado em

`packages/core/tests/integration/test_schema_privileges.py`: o worker não
consegue ativar (`UPDATE status/activated_at`) nem apagar uma linha `draft`,
e continua lendo (`SELECT`) e escrevendo `changelog`/`id`/`strategy_id`/
`version`/`created_at`. `test_migrations.py`: round trip da `0011` e
`alembic check` sem drift.
