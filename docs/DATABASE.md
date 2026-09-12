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
| `meme_curve_snapshots` | mensal | `MEME_RETENTION_DAYS` (90 d) | idem |
| `meme_features_1m` | mensal | idem | idem |
| `meme_trades` | mensal | idem | idem |
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

**Duas formas de partição.** Nove tabelas são RANGE mensal simples (`audit_logs_2026_09`) — as seis da `0001` mais as três da `0021` (§33). `candles` e `portfolio_equity_snapshots` são particionadas primeiro por LIST (`timeframe` / `resolution`) e cada nível desses por RANGE mensal, produzindo folhas como `candles_1m_2026_09`. O motivo é a própria coluna "Retenção": as retenções diferem por timeframe, e com uma única RANGE mensal expirar 1m aos 90 dias exigiria `DELETE` linha a linha dentro de partições que também guardam o 1h que se mantém para sempre — reescrevendo e inchando exatamente os dados que queremos preservar. Com o nível LIST, expirar é `DROP TABLE candles_1m_2026_05`.

O nível LIST é criado para **todos** os rótulos de `candle_timeframe`, não só os que a ingestão escreve hoje: uma linha sem partição é recusada, e uma escrita recusada é indisponibilidade, não aviso.

Partições são criadas com 3 meses de antecedência por `infra/scripts/create_partitions.py`, agendado no analytics-worker. Uma partição faltante gera `system_event` de severidade `critical`. A contrapartida é `infra/scripts/prune_partitions.py`, que faz `DETACH` + `DROP` de cada partição cuja **borda superior** já passou da janela de retenção — nunca de uma que ainda possa conter linha retida — e é idempotente porque lê as partições existentes em `pg_inherits` em vez de gerá-las pelo calendário.

**E com 2 meses de atraso (`--months-behind`, T2.5f).** O job só olhava para a frente, e histórico entra pelo passado: um pedido de backfill de 7 dias feito em 06/09 nomeia minutos de agosto, nenhuma partição os aceitava, e o consumidor do market-worker recusou **3 300 de 8 547 minutos** com `market_backfill_refused reason=no_partition` (`.claude/state/notes-T2.5.md` §31). O padrão é **2** porque a janela mais larga que alguém pede é de 30 dias (replay/β; o bootstrap de baselines pede 7), e **um mês para trás não basta sempre**: 30 dias contados a partir de 1º de março caem em **30 de janeiro** — fevereiro é curto —, então um único mês para trás recusaria os dois dias mais velhos desse pedido, que é exatamente o `no_partition` que esta política existe para eliminar. Dois cobrem no mínimo 59 dias de passado (rodando no dia 1º) e ~92 no melhor caso: 30 dias em qualquer mês do calendário, mais margem para um pedido cuja janela termina alguns dias no passado — uma lacuna detectada tarde, um replay de um trecho mais antigo, um dia em que o job não rodou.

**Criar e podar não podem brigar: a janela de retenção do pai tem de ser ≥ meses para trás + 1.** Um mês para trás é criado **somente enquanto a retenção ainda o mantém** — a decisão é a mesma função (`is_expired`, sobre a **borda superior**) que o podador usa, agora em `infra/scripts/partition_retention.py` e lida pelos dois jobs, em vez de duas cópias da tabela de retenção. Sem essa trava, `market_snapshots` (30 d) ganharia uma partição às 04:07 e a perderia às 04:12, todo dia, cada lado tomando `ACCESS EXCLUSIVE` na pai por nada. A regra vale **por pai**, não globalmente, porque as janelas diferem: `candles_1m` (90 d) recebe os dois meses para trás em **qualquer** dia do ano — a borda superior do mês retrasado é o dia 1º do mês anterior, no máximo ~62 dias atrás, sempre dentro de 90 (não é "90 d ≥ 3 meses", que seria falso em jan–mar) — e é o pai que o backfill de fato escreve; já `market_snapshots`/`liquidations` (30 d) recebem o mês anterior só enquanto ele estiver dentro da retenção, e `feature_snapshots` (14 d) deixa de receber passado a partir do dia 15. Nada disso apaga o que o backfill acabou de encher: o mês que o podador derrubaria é justamente o que o criador não cria.

**A promessa vale no mesmo instante**, e é assim que ela é verdadeira (revisão da Astra deste diff). A retenção é contada em dias inteiros, então a expiração de um mês vira à meia-noite UTC: 04:07 → 04:12 não cruza a borda, 23:59 → 00:01 cruza. Um plano montado antes da virada e podado depois pode criar um mês que a poda seguinte derruba — **uma vez**, e o próprio plano do dia seguinte já não o contém. Não é perda de dado: o que é derrubado nesse caso é justamente um mês cuja última linha retida acabou de expirar.

`funding_rates` e `open_interest_history` **não são particionadas** (§4), então backfill de funding e de open interest nunca depende deste job — não há nada a provisionar para elas. `replay_runs` (`0013`, §25) também não é particionada **e não tem retenção**: é o registro de pesquisa, algumas dezenas de linhas por dia no pior caso, e apagá-la por idade seria apagar exatamente a contagem de tentativas que o protocolo de replicação existe para manter. `meme_tokens` e `meme_ingest_gaps` (`0021`, §33) também não são: a chave da primeira é o **mint**, não um instante — ela não tem mês a derrubar e por isso é podada linha a linha pelo meme-worker, atrás de `app.meme_retention` —, e a segunda é uma linha por buraco, dezenas por dia no pior caso.
`market_breadth` (`0019`, §31) também não é particionada, por outro motivo: a conta cabe (525 600 linhas/ano **por série**, isto é, por `(exchange, breadth_version, window_minutes)`), e o dia em que não couber é uma revisão que reconstrói a tabela, porque a PK é `id` sozinha (§15.2).

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
  id, code (unique: binance|bybit|okx|coinbase|hyperliquid|kraken), name,
  status exchange_status (planned|active|inactive; `planned` desde a 0016, §28),
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
  `exchange_status` = `active|inactive` (a `0016` acrescenta `planned` **antes**
  de `active`, e o desvio em relação a esta linha está declarado na §28);
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
         (a `0012_replication` acrescenta `replication:<pai>:<k>`, k 1..99 — §24.1)
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
do prospectivo, e desde a `0012_replication` (§24.1) uma irmã de replicação
também não. `cohort` é texto e não `ENUM` porque um replay carrega o seu
`run_id` e uma irmã carrega o id do pai — o conjunto é aberto em valor e fechado
em forma, e a mesma regex vive em `hunter_core.domain.enums.SHADOW_COHORT_PATTERN`
e no CHECK. `armed` nasce
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
| `REPLAY_APP_READ_ONLY_TABLES` | `0013` | `hunter_app` | `SELECT` (`ddl/replay_runs.py`, §25.4) |
| `REPLAY_WORKER_APPEND_TABLES` | `0013` | `hunter_worker` | `SELECT`/`INSERT` — nunca `UPDATE`/`DELETE` (idem) |

A última linha não é uma classe nova de tabela: é um privilégio acrescentado a
uma tabela que a `0003` já classificou, e
`test_migrations.py::test_0005_touches_no_table_0003_had_not_already_classified`
é o que impede que ela vire a porta de entrada de uma tabela sem classificação —
o teste de partição de §15.6 é sobre as classes do `hunter_app` e não veria um
grant só do worker. A partição continua exata.

**Nota sobre `strategy_versions` (desde a `0010`, estreitada pela `0011`,
§22.3/§23; a `0012` acrescenta quatro colunas e **nenhum** grant, §24.5).** A linha de `WORKER_WRITE_TABLES` acima descreve o que `0001`
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
**A T3.44c acrescenta um terceiro pelo mesmo motivo** — `seed_risk_reference.py`,
o conteúdo de `risk_profiles` — e a linha acima fica anotada em vez de reescrita,
como toda descrição congelada por revisão (§28.7).

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

Esta tabela descreve o grant **por papel**; o raio de alcance da própria DSN
de dono (que processos a têm no ambiente) é assunto separado — §23.5.

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

### 23.5 O raio de alcance da própria DSN de dono — T3.15d, e o que faltava (T3.15f)

Esta seção e a §22.3 protegem quem pode escrever `strategy_versions` **por
papel de banco** (`hunter_worker` vs. dono); nenhuma das duas protegia a
conexão de dono **em si** de vazar para um processo que não deveria tê-la.
`.claude/state/review-T3.15-security.md` HIGH 1 (confirmado por
`astra-review-lab-pronto-2026-09-08.md` §2: "o compose ainda entrega
`DATABASE_URL_MIGRATIONS` aos serviços de runtime") mediu exatamente isso:
até `.claude/state/notes-T3.15d.md`, `api` e todo worker (`market`, `scanner`,
`strategy`, `execution`) recebiam `DATABASE_URL_MIGRATIONS` no próprio
ambiente — a `0011` deixa de importar se um desses processos, comprometido,
simplesmente abre a conexão de dono e ignora o grant por completo.

`infra/docker/docker-compose.yml` e `infra/vps/docker-compose.prod.yml`
separaram a âncora de ambiente em duas (`x-api-env`/`x-prod-db-env`, sem a
DSN de dono, para `api` e todo worker; `x-owner-env`/`x-prod-owner-env`, só a
DSN de dono, para `migrate` e o novo serviço `ops`, `profiles: ["ops"]`,
nunca `up`d). O raio de alcance da DSN de dono passa a ser exatamente os dois
serviços desta seção nomeia (§23.1: "os únicos escritores são a conexão de
dono... e `paper_line.py`") — nunca mais um container de vida longa.
Detalhe operacional e comandos novos: `docs/DEPLOYMENT.md` §3.4.

**E isso estreitou o HIGH 1 sem fechá-lo.** O que a T3.15d tirou do ambiente
foi a *segunda* cópia da credencial de dono. A que ficou — `DATABASE_URL` —
**era a mesma credencial**: `hunter`, `rolsuper = true`, `rolbypassrls = true`.
`hunter_app` e `hunter_worker` são papéis `NOLOGIN` concedidos a ela
(`infra/migrations/ddl/security.py`), então o `SET LOCAL ROLE` de
`hunter_core.db.session` sempre foi uma **redução voluntária**, que um
`RESET ROLE` desfaz. Todo `REVOKE` das §22.3/§23.1/§24.5 vale contra o papel;
nenhum deles vale contra um processo que pode deixar de ser esse papel. Um RCE
em `api` ou em qualquer worker continuava alcançando
`ALTER TABLE … DISABLE ROW LEVEL SECURITY` e
`UPDATE strategy_versions SET purpose = 'paper'`.

A `0015_runtime_login_role` (§27) fecha o caminho **silencioso** desse achado:
um login `hunter_runtime` sem superusuário, sem `BYPASSRLS` e **sem herança**,
membro de `hunter_app` e `hunter_worker` e de mais nada. O login dono continua
existindo e continua sendo o de `migrate`/`ops`.

**"Silencioso", e não "fechado", é a palavra — a §27.1 declara o resíduo.** A
frase que estava aqui até 2026-09-08 dizia "o HIGH 1 está fechado depois de
(a)–(e)", e a revisão de segurança desta tarefa (ALTA 1) mostrou que ela promete
mais do que um login único pode dar: `hunter_runtime` é membro dos **dois**
papéis, e `SET ROLE` depende só da opção `SET` da membership — nunca de
`INHERIT`. O que (a)–(e) de fato compram, e é muito, é a tabela adiante; o que
sobra, e o desenho que o fecha de verdade (**dois** logins, T3.15h), está na
§27.1, no bloco "O que um login único não fecha".

A distinção entre criar o papel e trocar a credencial continua sendo a mesma
que a §20.1 registra sobre a `0007` ("declarar uma lacuna não é fechá-la"). A
revisão cria o papel; quem troca a credencial é o deploy:

| Passo | O que é | Onde |
|---|---|---|
| (a) | `alembic upgrade head` aplica a `0015` e o papel passa a existir, **sem senha** | serviço `migrate`, em todo deploy |
| (b) | o operador define a senha (`ALTER ROLE hunter_runtime PASSWORD …`) pelo `ops` | VPS, uma vez |
| (c) | `HUNTER_RUNTIME_DB_PASSWORD` entra no `.env` | VPS, uma vez |
| (d) | `compose.sh update` sobe `api` e os workers com o `DATABASE_URL` novo | VPS |
| (e) | verificação de dentro do `api`: `current_user = 'hunter_runtime'`, `rolsuper`/`rolbypassrls` falsos | VPS |

Enquanto (d) não acontecer, `DATABASE_URL` continua nomeando o dono e **nada**
do que o achado descreve mudou — a `0015` estando aplicada não muda nada
sozinha. O runbook completo, com o caminho de rollback, é `docs/DEPLOYMENT.md`
§3.5.

**O que (a)–(e) compram, na frase mais precisa que se pode escrever hoje.**
Antes deles, `DATABASE_URL` e `DATABASE_URL_MIGRATIONS` eram **a mesma
credencial de login** (`hunter`, `rolsuper=true`, `rolbypassrls=true` —
`infra/migrations/ddl/security.py:12`), e `hunter_app`/`hunter_worker` eram
papéis `NOLOGIN` concedidos a ela: o `SET LOCAL ROLE` de
`hunter_core/db/session.py` era uma redução **voluntária**, que um `RESET ROLE`
desfazia. Depois deles, um processo de runtime comprometido:

| Alcança | Antes de (d) | Depois de (d) |
|---|---|---|
| `ALTER TABLE … DISABLE ROW LEVEL SECURITY` | **sim** (é o dono) | não — o login não é dono de nada |
| `UPDATE strategy_versions SET purpose = 'paper'` | **sim** | não — nenhum papel alcançável tem o privilégio (§22.3/§23.1) |
| `RESET ROLE` devolvendo a união dos privilégios | **sim** | não — `NOINHERIT` devolve **nada** (§27.1) |
| `SET ROLE hunter_worker` a partir do `api` | sim | **sim** — é o resíduo declarado da §27.1 |

As três primeiras linhas são o achado como ele foi escrito, e as três fecham. A
quarta é o que sobra, e é a razão de esta seção **não** dizer mais "HIGH 1
fechado": ver "O que um login único não fecha", §27.1, incluindo o desenho de
dois logins (T3.15h) que o fecharia.

## 24. A coorte da replicação, o carimbo de promissora e a linhagem da irmã — M3 (`0012_replication`)

Décima segunda revisão. Um CHECK alargado, quatro colunas, um CHECK novo por par
de colunas, uma UNIQUE, uma FK para a própria tabela e a trigger de congelamento
da `0010` alargada de novo. Ela fecha as duas pendências que a T3.19 **declarou**
(`.claude/state/notes-T3.19.md`, CONCERNS 1 e 2) e uma terceira que ninguém
tinha nomeado — as três da mesma família: uma coisa de que o protocolo depende
morava em prosa em vez de morar no schema.

| De onde veio | O que estava impossível |
|---|---|
| notes-T3.19 CONCERN 2 · REPLICATION.md §4.4 | o rótulo do braço **não podia ser coorte**: `ck_shadow_episodes_cohort_format` (`0002`) e `SHADOW_COHORT_PATTERN` aceitavam só `prospective` e `replay:<uuid>`, então a irmã emitia como `prospective` — exatamente a única coorte que a ponte de execução admite (T3.15e) |
| notes-T3.19 CONCERN 1 · REPLICATION.md §1.6 | `promising_at` morava no `changelog` das irmãs e num `system_events` com retenção de **30 dias**, para um bloco que exige **15 dias distintos depois dele**. Um marco cuja cópia durável é uma substring de texto livre não é um marco |
| achado desta tarefa | a **linhagem** da irmã (de quem, qual braço) também era só uma frase no `changelog`, recuperada por regex (`replication_stats.ARM_RE`) — uma família de dez versões que só um `LIKE` distinguia de dez experimentos independentes |

`0012_replication` tem 16 caracteres; o teto de `alembic_version.version_num`
continua sendo 32 (§17.6). As listas desta revisão estão congeladas em
`ddl/replication.py`, no padrão de §15.6/§16.5/§17.6/§18.9/§19/§20/§21/§22.

A frase que organiza as três: **o protocolo já dizia essas coisas; o schema
passa a garanti-las.** Nada aqui muda um veredito, ativa uma linha ou chega
perto da carteira — pelo contrário, acrescenta a terceira barreira que faltava
entre uma irmã de pesquisa e a ponte.

### 24.1 A coorte: um ramo novo, os dois antigos byte a byte

```
shadow_episodes  ck_shadow_episodes_cohort_format
  antes:  ^(prospective|replay:<uuid>)$
  depois: ^(prospective|replay:<uuid>|replication:<uuid>:[1-9][0-9]?)$
```

`<uuid>` é `[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}`, o
mesmo de antes. **É um superconjunto estrito:** todo episódio já gravado
continua válido com o rótulo que tem, e é isso que a revisão promete a quem já
tem população em disco.

**`[1-9][0-9]?` é 1..99 escrito como forma, não como contagem de dígitos**, e
isso não é detalhe: `replication:<pai>:01` seria uma **segunda grafia do braço
1** — duas populações sob um nome que o relatório já usa —, e `replication:<pai>:0`
não é braço nenhum. Os dois são recusados. O teto 99 vem de a rodada ter dez
braços (`hunter_indicators.replication.SIBLINGS_N`) com duas ordens de grandeza
de folga; acima disso o número de tentativas já é o problema que o protocolo
existe para contar (REPLICATION.md §7), não uma limitação de schema.

A regex vive em dois lugares e é copiada, nunca importada, pela razão de sempre
(`ddl/paper_geometry.py`): o contrato do banco não pode seguir em silêncio uma
edição posterior de uma constante Python. `hunter_core.domain.enums.SHADOW_COHORT_PATTERN`
é a outra cópia, e `test_migrations.py::test_0012_and_the_domain_constant_agree_on_the_cohort_grammar`
compara as duas string a string — além de provar que os dois ramos da `0002`
sobrevivem caractere por caractere dentro do novo.

**A coorte é dita pelo worker, não pelo processo.** `SHADOW_COHORT` continua
sendo a coorte do *processo*; `ActiveVersion.cohort(process_cohort)`
(`services/strategy-worker/hunter_strategy_worker/catalogue.py`) carimba
`replication:<pai>:<k>` quando a linha da versão tem linhagem, e a coorte do
processo quando não tem. **Um replay continua replay**, irmã ou não: coortes
separam populações *da mesma versão*, um replay nunca é a avaliação prospectiva
reservada daquela versão (SHADOW-LAB.md §1), e colapsar os dois ainda poria um
replay no slot que `uq_shadow_episodes_slot` guarda para a corrida para a
frente.

O que isso compra, em uma frase: a ponte de execução admite `prospective` e
recusa toda outra coorte com `cohort_not_live` (T3.15e, §22.5) — enquanto o
rótulo era irrepresentável, essa recusa citava nominalmente "a replication
sibling's cohort" e recusava um nome que **nada podia escrever**. O isolamento
nunca dependeu dela (as outras duas barreiras são `purpose = research_only` e a
ausência de linha em `agents`, as duas com teste); o que muda é que agora são
três barreiras de verdade em vez de duas mais uma promessa.

### 24.2 `promising_at` e `promising_by`

```
strategy_versions  (+) promising_at timestamptz NULL
                   (+) promising_by text NULL
  CHECK (promising_at IS NULL) = (promising_by IS NULL)
    AND (promising_by IS NULL OR char_length(promising_by) BETWEEN 1 AND 64)
    -- ck_strategy_versions_promising_is_attributed
```

`promising_at` é o instante em que o placar viu a versão `validada` pela
primeira vez (REPLICATION.md §1.6) e é de onde o bloco 1 (fora da amostra)
começa a contar. A bicondicional com `promising_by` é o argumento do §16.2 sobre
`no_entry_reason`, um marco adiante: **um carimbo que ninguém consegue atribuir
é uma data, não evidência**, e um `NOT NULL` sozinho aceitaria a string vazia,
que não atribui nada.

**Escrito por um lugar só.** `hunter_strategy_worker.replication.mark_promising(conn,
version_id, verdict_source)` é o único escritor, na conexão de dono, e ele é
único porque duas datas seriam a mais recente ganhando sem que ninguém visse a
outra sumir. Três propriedades, cada uma com uma razão:

- **idempotente por SQL, não por leitura anterior**: o `UPDATE ... WHERE
  promising_at IS NULL` é quem decide. Um `SELECT` seguido de um `UPDATE` seria
  a mesma corrida que o §17.8 recusa no seed. Uma segunda chamada não move o
  carimbo e **não escreve evento nenhum**;
- **conexão de dono**: a `0010`/`0011` deixaram `hunter_worker` com `SELECT` e
  nada mais de tabela aqui, então a coluna nova é ilegível para escrita por
  construção (§24.5);
- **auditada**: um `system_events` (`component = replicate_strategy_version`,
  `event = strategy_version_promising`) por marcação de fato feita, com
  `promising_at` e `promising_by` no `data`.

**`promising_at` é deliberadamente deixado *fora* do congelamento** (§24.4), e é
a única das quatro colunas novas nessa situação: ele é escrito **depois** da
ativação por definição — uma versão tem de rodar trinta dias antes de um placar
poder chamá-la de `validada` —, então congelá-lo tornaria a coluna inescrevível
em toda linha que poderia ganhá-la.

**Um pai forçado não é um pai promissor.** `replicate_strategy_version.py
--force-research "<motivo>"` continua **não** gravando o carimbo (REPLICATION.md
§4.1): ele dispensa a régua, e inventar a data em que a régua passou seria
inventar o marco do bloco 1.

### 24.3 A linhagem: `replication_parent_id` e `replication_index`

```
strategy_versions  (+) replication_parent_id uuid NULL REFERENCES strategy_versions(id)
                   (+) replication_index smallint NULL
  CHECK (replication_parent_id IS NULL) = (replication_index IS NULL)
    AND (replication_index IS NULL OR replication_index BETWEEN 1 AND 99)
    AND replication_parent_id IS DISTINCT FROM id
    -- ck_strategy_versions_replication_lineage
  UNIQUE (replication_parent_id, replication_index)  -- uq_strategy_versions_replication_arm
  FK  (replication_parent_id) -> strategy_versions (id)  -- ON DELETE NO ACTION
```

Três cláusulas no CHECK e cada uma fecha um jeito de escrever meia linhagem:

- **a bicondicional** — um braço sem pai nomeia um experimento que ninguém
  encontra de novo; um pai sem braço não se distingue das próprias irmãs;
- **a faixa 1..99** — a mesma que a gramática da coorte aceita, para que nenhuma
  linha carregue uma linhagem sem coorte representável;
- **`IS DISTINCT FROM id`** — uma versão não é irmã de si mesma (o precedente é
  `id <> superseded_by_id`, §18.4). É `IS DISTINCT FROM` e não `<>` porque `<>`
  é `NULL` para um pai nulo, e **um CHECK que avalia `NULL` está satisfeito** —
  a armadilha que a `0009` mediu (§21.1), um operador antes.

`ON DELETE NO ACTION` (o padrão), **nunca `RESTRICT`**, e a diferença é
operacional: `NO ACTION` é verificada no **fim do statement**, então
`DELETE FROM strategies` continua derrubando a família inteira num comando só
(a cascata leva pai e irmãs juntos), enquanto apagar um pai sozinho, deixando as
irmãs órfãs, é recusado. É a mesma escolha e a mesma razão de
`participation_consumptions` (§18.5).

**Nenhum índice novo para a FK.** `uq_strategy_versions_replication_arm` começa
por `replication_parent_id`, então ela *é* o índice que o §1 exige de toda chave
estrangeira. E como o Postgres trata `NULL`s como distintos numa UNIQUE, ela não
custa nada às versões que não são irmãs — que são quase todas.

O `changelog` continua carregando o rótulo ao lado (`replication:<pai>:<k> | irmã
k de v1 | promising_at=… | seed=…`): é o que uma irmã derivada **antes** desta
migração tem, e é o que um humano lê. `replication_stats.load_sibling_rows`
consulta os dois — a coluna e o `LIKE` — e prefere a coluna para o `k`; trocar
por uma das duas sozinha faria daquela irmã antiga ou uma órfã (só coluna) ou
uma linha que constraint nenhuma protege (só rótulo).

### 24.4 Congelada depois da ativação — as duas colunas certas

A trigger `shadow_freeze_strategy_version` da `0010` (§22.2) é **substituída,
não duplicada**, pela terceira vez no mesmo padrão (`0008` §20.3, `0009` §21.2,
`0010` §22.2): `ddl/replication.py` copia a lista congelada de
`ddl/strategy_purpose.py`, acrescenta `replication_parent_id` e
`replication_index`, e recria função e triggers com o mesmo nome. O downgrade
chama o criador da própria `ddl/strategy_purpose.py`: voltar à `0011` é ter a
trigger que a `0010` descreve.

| Coluna nova | Congelada depois da ativação? | Por quê |
|---|---|---|
| `replication_parent_id` | **sim** | a irmã nasce com ela no mesmo `INSERT` que a ativa, então a trigger nunca vê essa escrita; repontar a irmã depois reatribuiria em silêncio um experimento cujos sinais já estão gravados |
| `replication_index` | **sim** | idem: trocar o braço de lugar renomearia a coorte de uma população que já emitiu sob a antiga |
| `promising_at` | **não** | escrito depois da ativação por definição (§24.2). Congelá-lo tornaria a coluna inescrevível justamente em quem pode ganhá-la |
| `promising_by` | **não** | anda com `promising_at`; separá-los violaria a bicondicional no primeiro `UPDATE` |

Consequência prática, e é a mesma da §22.2: **não existe "transformar uma versão
em irmã"**. Uma irmã é uma linha nova, derivada, com a linhagem no `INSERT` —
que é exatamente como `infra/scripts/replicate_strategy_version.py` escreve.

### 24.5 Grants: nenhum, e isso é afirmação

Esta revisão **não emite um único `GRANT` ou `REVOKE`**, e a razão é aritmética
de ACL, não descuido. A `0010` revogou o `INSERT`/`UPDATE` de tabela de
`hunter_worker` em `strategy_versions` e reconcedeu doze colunas; a `0011`
revogou `INSERT` por completo, `DELETE` de tabela e `UPDATE` em sete das doze. O
que sobra para o worker é `SELECT` de tabela mais `UPDATE` em cinco colunas
nomeadas — então **uma coluna acrescentada depois é legível pelos dois papéis (o
grant de tabela a alcança) e escrevível por papel de aplicação nenhum**, sem uma
linha de DDL. É a mesma forma que `purpose` tem, alcançada por subtração em vez
de por revogação.

Escrever um `REVOKE` no-op aqui para *parecer* uma garantia seria exatamente o
erro que o §15.6 registra sobre `ALTER DEFAULT PRIVILEGES ... REVOKE ALL`. A
garantia é teste, e como o papel:
`test_schema_privileges.py::test_the_worker_cannot_write_any_of_the_replication_columns`
(quatro `UPDATE`, quatro *permission denied*) e
`test_the_owner_connection_writes_the_promising_marker` do outro lado — uma
revogação escrita no papel errado deixaria o protocolo sem ninguém capaz de
registrar que uma versão virou promissora, que é a parede que a `0007` levou em
`portfolios` (§19.2, item 1b), uma tabela ao lado.

Medido no head, contra um Postgres 16 real:

| Coluna | `hunter_app` | `hunter_worker` | dono / `DATABASE_URL_MIGRATIONS` |
|---|---|---|---|
| `purpose` | `SELECT` | `SELECT` | tudo |
| `promising_at` | `SELECT` | `SELECT` | tudo (`mark_promising`) |
| `promising_by` | `SELECT` | `SELECT` | tudo (`mark_promising`) |
| `replication_parent_id` | `SELECT` | `SELECT` | tudo (`replicate_strategy_version.py`) |
| `replication_index` | `SELECT` | `SELECT` | tudo (idem) |
| `changelog` (referência) | `SELECT` | `SELECT` + `UPDATE` | tudo |

Nenhuma classe de grant muda e nenhuma tabela é reclassificada: `strategy_versions`
continua em `APP_READ_ONLY_TABLES` (`0001`) e em `WORKER_WRITE_TABLES` para fins
de classificação, com a nota do §17.6 valendo inteira — **nunca reconceder no
nível de tabela**, porque a ACL de coluna é a *união* com a de tabela.
`shadow_episodes` continua com as classes que a `0002` lhe deu (§16.5).

**Nenhuma política de RLS muda.** As duas tabelas são globais (§1.1): pesquisa
sombra e catálogo de estratégias não têm `organization_id` e nunca tiveram RLS.
Nada nesta revisão cria dado de tenant.

### 24.6 Guardas

**Não há guarda de upgrade, e isso é afirmação.** Quatro colunas anuláveis, sem
default; um CHECK que só fala de valores não nulos; um CHECK alargado que aceita
um superconjunto estrito do que aceitava. Nada que já esteja gravado passa a ser
irrepresentável — a mesma afirmação da `0007` (§19.5), da `0008` (§20.5), da
`0009` (§21.4) e da `0010` (§22.1).

**O downgrade recusa em três frentes** (§17.7: reverter é permitido, perder
evidência não é):

| Guarda | O que se perderia |
|---|---|
| `strategy_versions` com `promising_at` | o instante de onde o bloco 1 conta. Nunca é recalculado para trás, e a cópia no `changelog` só existe em famílias **já replicadas** — um pai marcado promissor e ainda não replicado (o estado normal entre o veredito e a rodada) não tem outra cópia durável |
| `strategy_versions` com `replication_parent_id` | dez irmãs voltam a parecer dez experimentos independentes: exatamente a inflação por múltiplas tentativas que o protocolo existe para contar (REPLICATION.md §2) |
| `shadow_episodes` com coorte `replication:%` | o CHECK da `0002` não a representa. O Postgres recusaria a constraint de qualquer forma; a guarda recusa **antes**, com a contagem e a instrução, em vez de morrer no meio da revisão com uma violação que não nomeia saída |

Nenhuma delas apaga nada: contam os infratores e recusam nomeando-os, com a
instrução de exportar antes — o mesmo limite declarado do §18.9 (exportar não
muda predicado nenhum; o downgrade de um banco com replicação viva não é
operação de rotina). Para a terceira, a instrução diz mais: apagar um episódio
solta o `tracking_hold` de um mercado cujas velas um outcome aberto ainda
precisa (§16.3).

**O que não é guardado, declarado em vez de descoberto:** irmãs cuja linhagem
está só no `changelog` (nada se perde — o texto sobrevive ao downgrade) e o
`promising_by` sozinho (ele cai junto com `promising_at`, que a primeira guarda
já cobre).

### 24.7 Trava, pooler e o que muda para as tarefas vizinhas

**Trava.** A revisão faz `ALTER TABLE` em duas relações frias:
`shadow_episodes` (uma linha por versão × mercado × coorte — milhares) e
`strategy_versions` (dezenas). O `DROP`/`ADD CONSTRAINT` do CHECK da coorte é
**validante**, isto é, varre a tabela: é o preço de não instalar uma constraint
que mente, e nessa escala é a mesma ordem de grandeza da janela de ~15 s que a
`0010` abriu (§15.6), não uma nova classe de risco. `ADD COLUMN` sem default não
reescreve tabela no Postgres 11+.

**Pooler.** Nada aqui depende de estado de sessão: um CHECK, quatro colunas, uma
UNIQUE, uma FK e uma trigger que lê só `NEW`/`OLD`. Sem prepared statement de
sessão, sem `LISTEN`/`NOTIFY`, sem advisory lock de sessão.

**Vizinhos.**

| Onde | O que muda |
|---|---|
| `hunter_strategy_worker/catalogue.py` | `ActiveVersion` lê `replication_parent_id`/`replication_index` e ganha `cohort(process_cohort)`; `decide.py` calcula a coorte **uma vez** por decisão e a usa nos quatro lugares (slot, identidade do sinal, envelope, episódio) |
| `hunter_strategy_worker/replication.py` | o `INSERT` da irmã carrega a linhagem; a rodada chama `mark_promising` antes de escrever as irmãs (elas citam o carimbo) e não escreve mais o evento `strategy_version_promising` por conta própria; recusa quando a `0012` não está aplicada |
| `hunter_strategy_worker/replication_stats.py` | `load_promising_at` lê a **coluna** primeiro (depois `changelog`, depois `system_events`); `load_sibling_rows` reconhece irmã por coluna **ou** rótulo |
| T3.18 (placar) | passa a poder ler `strategy_versions.promising_at` direto para o bloco fora da amostra, em vez de `load_promising_at`. O contrato está em `.claude/state/notes-T3.19c.md`; **a API não foi ligada nesta tarefa** |
| `services/execution-worker/bridge_screen.py` | **nada a mudar** — ele já recusa toda coorte que não seja `prospective` (T3.15e). A diferença é que agora existe uma coorte de verdade para ele recusar |

## 25. O recibo de um replay vira evidência durável — M3 (`0013_replay_runs`)

Décima terceira revisão. **Uma tabela**, um índice, dois `GRANT`. Nenhuma coluna
nova em tabela existente, nenhum enum, nenhum trigger, nenhuma partição, nenhuma
política de RLS. Ela responde ao brief que a T3.19b escreveu **em vez de** uma
migração (`.claude/state/brief-T3.19b-db-replay-runs.md`), porque o brief daquela
tarefa proibia o autor de escrever a própria migração.

O motor de replay já produzia a linha de livro-razão e a gravava em dois lugares,
e nenhum dos dois responde à pergunta que o placar e o plantão fazem — *quantas
operações simuladas esta versão já acumulou, sobre que janela, e quando?*:

| Onde a linha já morava | Por que não basta |
|---|---|
| `system_events` (`component = 'replay_engine'`, `event = 'replay_run_finished'`) | **retenção de 30 dias** (§1.3), enquanto o `docs/plans/REPLICATION.md` conta 15 e 30 dias de resultados *depois* de um marco. O canal operacional expira antes da pergunta que ele deveria sustentar |
| um JSONL local (`--ledger caminho.jsonl`) | honesto e frágil: prova uma corrida só se alguém guardou o arquivo |

`0013_replay_runs` tem 17 caracteres; o teto de `alembic_version.version_num`
continua sendo 32 (§17.6). As listas desta revisão estão congeladas em
`ddl/replay_runs.py`, no padrão de §15.6/§16.5/§17.6/§18.9/§19/§20/§21/§22/§24.

A frase que organiza tudo abaixo: **um recibo que o próprio escritor pode editar
não é recibo** — e é dessa frase que a forma da tabela decorre, não o contrário.

### 25.1 Uma linha por **fatia**, não por corrida

O brief deixou a decisão para esta tarefa e recomendou (a); a decisão é (a), e a
razão vai além da recomendação.

| Opção | O que dá | O que custa |
|---|---|---|
| **(a) uma linha por fatia** — `id` é `uuid7` novo, `run_id` é coluna, `UNIQUE (run_id, window_from, window_to)` | o histórico de throughput fatia a fatia; somar reconstrói a corrida | uma linha a mais por comando |
| (b) uma linha por corrida, acumulada por `UPSERT` (`bars_evaluated = bars_evaluated + :n`) | o total | **exige `UPDATE` na própria tabela**, e perde a cadência para sempre |

Duas coisas decidem, e a segunda é a que fecha:

1. **a fatia é a unidade que de fato acontece.** A prova da T3.19b rodou 31 dias
   em **onze comandos** sob a *mesma* coorte (`.claude/state/notes-T3.19b.md`
   §4.1). Somar fatias é sempre possível; separar uma corrida de volta em fatias
   não é;
2. **(b) exigiria dar `UPDATE` ao escritor.** O único escritor é o
   strategy-worker (`replay/ledger.py`), e a regra de `audit_logs`,
   `risk_events` e `kill_switch_transitions` desde a `0001` (§1.2) é que quem
   escreve evidência não a reescreve. A forma da tabela não é uma preferência de
   modelagem: é a consequência do grant que a §25.4 fixa.

`UNIQUE (run_id, window_from, window_to)` é o que torna **repetir uma fatia
idempotente** — a mesma propriedade que a identidade `uuid5` dos sinais já
garante do outro lado. O escritor usa `ON CONFLICT DO NOTHING` (e não
`DO UPDATE`, que o grant recusaria): reexecutar uma fatia grava um recibo, não
dois, e o número de throughput não dobra.

> **Corrigido pela `0018_replay_runs_slice_markets` (§30).** Esta chave nomeia a
> **janela**, e a unidade que ela deveria nomear é a *fatia* — janela **mais** os
> mercados sobre os quais ela foi despachada. Com uma coorte por versão e quatro
> fatias de mercado dentro da mesma janela, a segunda, a terceira e a quarta
> pareciam a primeira repetida e o `DO NOTHING` as descartava em silêncio: a
> T3.62 rodou 32 fatias e guardou **8 recibos**. A chave passa a ser
> `(run_id, window_from, window_to, markets_digest)`. O parágrafo acima fica
> anotado em vez de reescrito — ele descreve o que a `0013` construiu, que é o
> que "congelado por revisão" significa (§16.5, §17.1, §28.1).

### 25.2 A tabela

```
replay_runs                                  (global, append-only, não particionada)
  id uuid PK (uuid7)
  run_id uuid NOT NULL                       -- o <uuid> de replay:<uuid>
  cohort text NOT NULL
  strategy_version_id uuid NOT NULL -> strategy_versions(id) ON DELETE CASCADE
  window_from, window_to timestamptz NOT NULL          -- [from, to), semiaberto
  markets text[] NOT NULL                    -- <exchange>:<symbol>
  started_at, finished_at timestamptz NOT NULL
  bars_evaluated, signals, outcomes_resolved, outcomes_open integer NOT NULL
  seconds numeric(12,3) NOT NULL
  decision_lag_s integer NOT NULL
  workers smallint NOT NULL
  evaluations_by_state jsonb NOT NULL DEFAULT '{}'
  errors integer NOT NULL DEFAULT 0
  created_at timestamptz NOT NULL DEFAULT now()
  UNIQUE (run_id, window_from, window_to)              -- uq_replay_runs_slice
  INDEX  (strategy_version_id, window_from)            -- ix_replay_runs_version_window
```

> **A `0018` (§30) acrescenta `markets_digest text NOT NULL`** (sha256 hex da
> lista ordenada de `markets`), leva `uq_replay_runs_slice` para
> `(run_id, window_from, window_to, markets_digest)` e mais dois CHECKs
> (`markets_digest ~ '^[0-9a-f]{64}$'`, `array_position(markets, NULL::text) IS
> NULL`). O bloco acima continua descrevendo o que a `0013` criou.

Dez CHECKs, e cada um fecha uma forma diferente de escrever um recibo que não é
um:

| CHECK | O que se tornou irrepresentável |
|---|---|
| `ck_replay_runs_cohort_is_a_replay_cohort` (`cohort ~ '^replay:<uuid>$'`) | uma corrida rotulada `prospective` ou `replication:<pai>:<k>`. As duas são populações do relógio vivo; uma linha aqui existe justamente porque uma janela do passado foi replayada |
| `ck_replay_runs_cohort_names_the_run` (`cohort = 'replay:' \|\| run_id::text`) | o rótulo e o `run_id` discordarem. A redundância é deliberada e, ao contrário de prosa, incapaz de derivar |
| `ck_replay_runs_window_is_half_open` (`window_to > window_from`) | uma janela vazia, e — com o semiaberto — duas fatias adjacentes visitando a mesma barra |
| `ck_replay_runs_finished_after_it_started` | uma corrida que terminou antes de começar |
| `ck_replay_runs_counts_are_not_negative` | barras, sinais, desfechos, erros, segundos ou lag negativos |
| `ck_replay_runs_resolved_within_the_population` (`outcomes_resolved <= signals`) | mais desfechos resolvidos do que sinais existem |
| `ck_replay_runs_a_slice_visited_a_market` (`cardinality(markets) > 0`) | um recibo de uma fatia que não visitou mercado nenhum — `run.py` recusa a corrida antes disso (`no market matched the selection`), então o CHECK só torna a recusa durável |
| `ck_replay_runs_a_slice_had_at_least_one_worker` (`workers >= 1`) | uma fatia executada por zero processos |
| `ck_replay_runs_evaluations_is_an_object` (`jsonb_typeof(...) = 'object'`) | um `evaluations_by_state` que é lista ou escalar — o precedente é o CHECK de forma de `request_payload` (§21.1) |

**`seconds` é `numeric(12,3)`, nunca `double precision`**, e isso é acréscimo às
convenções numéricas do §1, no mesmo espírito de `funding_rates.rate` (§15.7) e
de `market_betas.beta` (§18.6): não é dinheiro (`NUMERIC(28,10)`) nem fração de
apresentação (`NUMERIC(9,6)`) — é **duração**, e ela vira **taxa** num relatório
(`bars_evaluated / seconds`). Três casas é a resolução que `time.perf_counter()`
merece sobre uma corrida de minutos; doze dígitos são onze anos deles. O escritor
liga o parâmetro como **string** e converte no SQL, pela mesma razão pela qual
todo número canonicalizado do projeto é string (§17.8, §21.1).

**A coorte é a mesma gramática, escrita três vezes e comparada por teste.**
`hunter_core.domain.enums.REPLAY_COHORT_PATTERN` é a constante viva (nova nesta
tarefa), `ddl/replay_runs.py::REPLAY_COHORT_PATTERN_0013` é a **cópia congelada**
que a revisão instala — cópia e nunca import, pela razão de sempre
(`ddl/paper_geometry.py`: o contrato do banco não pode seguir em silêncio uma
edição posterior de uma constante Python) — e o modelo ORM lê a constante viva.
`test_migrations.py::test_0013_and_the_domain_constant_agree_on_the_replay_grammar`
compara as três **e** prova que o padrão é o segundo ramo de
`SHADOW_COHORT_PATTERN` caractere por caractere, de modo que um recibo nunca
carrega uma coorte que `shadow_episodes` recusaria, nem o contrário.

**Três colunas contam a corrida inteira, não a fatia — e isso está declarado
aqui em vez de ser descoberto pelo primeiro `SUM`.** `count_population`
(`replay/simulate.py`) conta as linhas *da coorte*, sem filtro de janela, porque
um número que um processo guarda na memória não é evidência sobre o que foi
escrito. Logo:

| Coluna | Escopo |
|---|---|
| `bars_evaluated`, `seconds`, `errors`, `workers`, `evaluations_by_state` | **da fatia** — somar reconstrói a corrida |
| `signals`, `outcomes_resolved`, `outcomes_open` | **da coorte inteira, no instante em que a fatia terminou** — um total corrente. O número da corrida é o da **última** fatia; somá-los multiplica a população |

Mudar isso seria mudar o que a prova da T3.19b relatou (o mesmo JSON já está em
`system_events` com esse significado), então o que muda é a documentação, não o
número.

**O que do `to_jsonable()` deliberadamente *não* virou coluna**, pela doutrina do
§17.8 (uma segunda verdade diverge): `version_label` (é
`strategies.key || ' ' || strategy_versions.version`, um join a partir de
`strategy_version_id`), `market_count` (`cardinality(markets)`) e
`bars_per_second` (`bars_evaluated / seconds`). Os três continuam no JSON do
`system_events` e do JSONL, que são documentos e não tabelas.

### 25.3 Índices

- PK (`id`);
- `uq_replay_runs_slice (run_id, window_from, window_to)` — a idempotência da
  §25.1, e o índice que serve a consulta por `run_id` (ela é a coluna líder);
- `ix_replay_runs_version_window (strategy_version_id, window_from)` — a
  pergunta do placar, e o índice que o §1 exige da chave estrangeira.
  Ascendente, como toda a §15.3 manda, embora a leitura seja decrescente.

**Sem partição**, e a razão é aritmética: uma corrida por versão por janela é da
ordem de dezenas de linhas por dia, não de milhões. **Sem retenção**, e a razão
é a regra do `Registro de Tentativas`: estas linhas são o registro de pesquisa, e
apagá-las por idade apagaria a contagem de tentativas que o protocolo de
replicação existe para manter (§1.3 registra a ausência em vez de deixá-la
parecer esquecimento).

### 25.4 Grants — papel × tabela

| Papel | `replay_runs` |
|---|---|
| `hunter_app` (API) | `SELECT` |
| `hunter_worker` (motor) | `SELECT`, `INSERT` — **nunca `UPDATE`, nunca `DELETE`** |
| dono / `DATABASE_URL_MIGRATIONS` | tudo |

É exatamente a forma que `fx_observations` já tem (§18.9): leitura para o papel
que lê o placar, acréscimo para o papel que produz o fato. O `UPDATE` ausente não
é folga sobrando — é a §25.1 inteira: com ele, a opção (b) seria possível e um
recibo passaria a ser editável pelo processo que o escreveu.

Nenhuma classe de grant nova e nenhuma tabela reclassificada:
`REPLAY_APP_READ_ONLY_TABLES` e `REPLAY_WORKER_APPEND_TABLES` (ambas
`("replay_runs",)`) entram na união que
`test_schema_privileges.py::test_the_grant_lists_cover_every_table_exactly_once`
compara com o `pg_class` vivo — a partição exata do schema do §15.6 continua
exata. Provado **como o papel**, não perguntado ao catálogo:
`test_the_worker_appends_a_replay_receipt_and_can_never_edit_it` (o `INSERT`
passa; o `UPDATE` e o `DELETE` batem em *permission denied*) e
`test_the_app_role_reads_a_replay_receipt_and_writes_none_of_it`.

### 25.5 RLS: nenhuma, e isso é afirmação

`replay_runs` é **global** (§1.1), como `agent_signals`, `signal_outcomes`,
`shadow_episodes` e `feature_baselines`: pesquisa sombra não tem
`organization_id` e nunca teve RLS. Nada nesta revisão cria dado de tenant, e um
replay não pode chegar a uma carteira — a coorte é recusada por nome na ponte
(`cohort_not_live`), a versão é `research_only`, não há linha em `agents` e,
desde a T3.19b, um replay não escreve `shadow_outbox`.

A ausência é **asserida**, não suposta:
`test_schema_privileges.py::test_replay_runs_is_global_and_carries_no_tenant_column`
lê `information_schema.columns` e `pg_policy` e exige zero em ambos — porque "não
precisa de política" e "alguém esqueceu a política" são indistinguíveis de fora,
e uma coluna de tenant aparecendo aqui depois passaria a exigir RLS.

### 25.6 Guardas

**Não há guarda de upgrade, e isso é afirmação.** A revisão cria uma tabela que
não existia; não há linha guardada que ela possa tornar irrepresentável — a mesma
afirmação da `0007` (§19.5), da `0008` (§20.5), da `0009` (§21.4), da `0010`
(§22.1) e da `0012` (§24.6).

**O downgrade recusa enquanto houver um recibo** (§17.7: reverter é permitido,
perder evidência não é):

| Guarda | O que se perderia |
|---|---|
| qualquer linha em `replay_runs` | a **única** cópia durável de quantas decisões simuladas uma versão acumulou. `system_events` guarda o mesmo JSON por 30 dias e depois o apaga; o JSONL só existe se alguém passou `--ledger` e guardou o arquivo. "A migração reverteu sem erro" seria o único relatório da perda |

Ela conta os infratores e recusa nomeando-os, com a instrução de exportar antes
(`COPY (SELECT * FROM replay_runs) TO ...`) — o mesmo limite declarado do §18.9 e
do §24.6: exportar não muda predicado nenhum, e o downgrade de um banco que já
replayou não é operação de rotina. Num banco onde nenhum replay rodou a guarda
conta zero e o downgrade segue —
`test_0013_reverses_on_a_database_that_never_replayed` é essa metade.

### 25.7 Trava, pooler e o que muda para as tarefas vizinhas

**Trava.** `CREATE TABLE` não toma trava numa relação que ainda não existe, e os
dois `GRANT` travam só o catálogo (a mesma medição da `0005`, §15.6). Esta
revisão **não abre janela de manutenção** — ao contrário da `0010` e da `0012`,
que fazem `ALTER TABLE` validante.

**Pooler.** Nada aqui depende de estado de sessão: uma tabela, um índice, dois
`GRANT`. Sem prepared statement de sessão, sem `LISTEN`/`NOTIFY`, sem advisory
lock de sessão.

**Vizinhos.**

| Onde | O que muda |
|---|---|
| `hunter_strategy_worker/replay/ledger.py` | ganha `record_slice()` — o **terceiro ramo**, não uma reescrita. `record_run()` chama-o **antes** do `INSERT` em `system_events`, na mesma transação do chamador: um evento publicado que nenhuma linha gravada explica é a discordância que a outbox existe para impedir, uma tabela ao lado. O JSONL continua sendo escrito fora da transação, como sempre |
| idem | `record_slice` **sonda** `to_regclass('public.replay_runs')` antes de escrever. Não é excesso de zelo: um statement contra relação inexistente **aborta a transação inteira**, e um banco ainda na `0012` perderia junto a metade `system_events` do recibo — meia hora de corrida relatando nada por causa de uma ordem de deploy. Faltando a tabela, o log sai em `error` nomeando a revisão a aplicar (nunca em silêncio) e os outros dois ramos gravam. É a forma que o §17.2 dá à sonda de lock do scanner, uma tabela adiante |
| `hunter_core.domain.enums` | constante nova `REPLAY_COHORT_PATTERN` (o segundo ramo de `SHADOW_COHORT_PATTERN`, sozinho) |
| `hunter_core.db.models.replay_runs` | `ReplayRunRow` — `...Row` e não `ReplayRun` pela razão que o §15.9 dá para `MarketRegimeRow`: `hunter_strategy_worker.replay.ledger.ReplayRun` é a forma em memória do mesmo recibo, e duas coisas diferentes com um nome só numa lista de import é como um teste acaba afirmando sobre a errada |
| API / placar (T3.18) | **nada foi ligado nesta tarefa.** O grant existe (`SELECT`) e a consulta do placar tem índice; escrever o handler é de quem é dono de `apps/**` |
| `services/execution-worker/**` | **nada a mudar** — nenhuma linha desta tabela é lida por caminho de execução, e nenhuma pode virar entrada |

### 25.8 Desvios em relação ao brief, declarados

O brief da T3.19b é a origem desta revisão; onde esta implementação diverge dele,
diverge por escrito:

| Brief | O que foi feito, e por quê |
|---|---|
| "`id` uuid PK = o `run_id`; **não** um uuid7 novo" | `id` é `uuid7` e `run_id` é coluna. O próprio brief oferece isso como opção (a) e a recomenda; a §25.1 diz por que ela também é a única compatível com o grant sem `UPDATE` |
| "vale o mesmo CHECK de `shadow_episodes` (`SHADOW_COHORT_PATTERN`) **mais** a exigência do prefixo `replay:`" | o CHECK é a **interseção** escrita uma vez (`^replay:<uuid>$`), não a gramática larga mais um segundo predicado. Duas expressões que precisam concordar são duas expressões que podem divergir; e a interseção é literalmente o segundo ramo da larga, provado caractere a caractere por teste |
| a tabela de colunas (uma transcrição do `to_jsonable`) | `version_label`, `market_count` e `bars_per_second` **não** viraram colunas: são join e aritmética sobre colunas que já existem (§25.2, doutrina do §17.8) |
| CHECKs pedidos: `window_to > window_from`, `finished_at >= started_at`, `bars_evaluated >= 0` | mantidos, mais seis (§25.2). Cada um fecha uma forma de recibo mentiroso que o brief não nomeou; nenhum recusa uma linha que `replay/run.py` possa produzir hoje |
| — (o brief não fala do escopo dos contadores) | `signals`/`outcomes_resolved`/`outcomes_open` são **da coorte inteira**, não da fatia, porque é assim que `count_population` já os produz. Declarado na §25.2 em vez de corrigido: mudar o número mudaria o que a prova da T3.19b relatou |
| "`record_run` ganha um terceiro ramo" | ganhou, e ganhou também uma **sonda** de existência da tabela (§25.7). O brief não a pediu; sem ela, um banco atrasado numa revisão perde o recibo inteiro em vez de perder um terço dele |

## 26. A coorte deixa de ser invisível para o planejador — M3 (`0014_lab_signals_indexes`)

Décima quarta revisão. **Dois índices em `agent_signals`, nada mais**: nenhuma
coluna, nenhuma constraint, nenhum enum, nenhum grant, nenhuma partição. Ela
responde ao pedido que a T3.37a escreveu em vez de uma migração
(`.claude/state/notes-T3.37.md` §T3.37a).

```
agent_signals
  INDEX (      (supporting_features ->> 'cohort'), emitted_at, id)   -- ix_agent_signals_cohort_emitted
  INDEX (strategy_version_id,
               (supporting_features ->> 'cohort'), emitted_at, id)   -- ix_agent_signals_version_cohort_emitted
```

### 26.1 O problema não era só a varredura: era a **estatística**

A coorte de uma decisão sombra vive dentro do envelope imutável
(`supporting_features->>'cohort'`, §16) — não é coluna. Quatro consumidores
filtram por ela: `replay/simulate.count_population`,
`replay/stress.cohort_cases`, `replication_stats` (o placar) e a listagem
`GET /lab/shadow/signals`. Uma expressão que ninguém indexou **não tem
estatística nenhuma**: o Postgres cai no palpite padrão de 0,5 % para ela.

Medido na VPS em 2026-09-08, somente `EXPLAIN`, com 5 571 linhas em
`agent_signals`:

```
 Seq Scan on agent_signals  (cost=0.00..515.57 rows=28 width=572)
   Filter: ((supporting_features ->> 'cohort'::text) = 'prospective'::text)
```

**28 linhas estimadas** onde quase todas as 5 571 casam. São dois estragos
distintos, e o segundo é o pior:

1. a varredura é sequencial e cresce com a tabela;
2. a subestimativa de ~200x sobe para todos os nós acima, e é ela que escolheu
   um `Nested Loop` de milhares de sondagens em `signal_outcomes` planejando
   para 28 — inclusive na consulta de totais, que a tela pede a **cada**
   requisição.

Um índice de expressão corrige o segundo de graça: o `ANALYZE` coleta
estatística para expressões de índice, então depois da `0014` o planejador
conhece a seletividade real da coorte **use ou não** o índice para varrer.

### 26.2 Por que a chave de ordenação é `emitted_at`, e não a cópia do envelope

`emitted_at` **é** o instante da decisão: `persist.persist_decision` grava
`emitted_at=record.decision_at`, e `record.py` carimba
`supporting_features['decision_at']` a partir da mesma variável. Não é
coincidência de dado: é um só valor escrito em dois lugares — conferido também
no banco do stack local (840 linhas, `count(*) FILTER (WHERE emitted_at IS
DISTINCT FROM (supporting_features->>'decision_at')::timestamptz) = 0`) — e o
placar (`replication_stats`) já ordena por `ORDER BY s.emitted_at, s.id`.

A coluna é indexável. **A cópia no envelope não é, e isso não é uma escolha:**

```sql
CREATE INDEX ... ON agent_signals (((supporting_features->>'decision_at')::timestamptz));
ERROR:  functions in index expression must be marked IMMUTABLE
```

`text -> timestamptz` executa `timestamptz_in`, que é `STABLE` (aceita `'now'`,
depende de `TimeZone`) — `provolatile = 's'` no `pg_proc`. Pelo mesmo motivo uma
coluna `GENERATED ALWAYS AS (...)` com essa expressão também é recusada. Os dois
índices que a T3.37a pediu **não são escrevíveis como ela os escreveu**, e
nenhuma migração pode fazer `GET /lab/shadow/signals` usar índice enquanto o
`ORDER BY` dela for esse cast: hoje a rota ordena por
`(supporting_features->>'decision_at')::timestamptz`
(`hunter_api/repositories/lab_common.py`, `DECISION_AT`).

**A correção que falta é de uma linha e não é desta revisão:**
`DECISION_AT = AgentSignal.emitted_at`. Enquanto ela não vier, a página do Lab
continua com `Seq Scan` + `top-N heapsort` — **264 ms com 50 000 linhas**,
contra **0,96 ms** da mesma página ordenada pela coluna. As duas metades estão
travadas por teste (`apps/api/tests/integration/test_lab_signals_explain.py`):
o `ERROR ... IMMUTABLE` e o `Sort` que ele causa.

**Desvio declarado da §1.** A convenção diz "JSONB … nunca para campos que serão
filtrados com frequência". `cohort` e `decision_at` são exatamente isso, e já
eram antes desta revisão — a S0 congelou o envelope antes de existir uma API que
filtrasse por ele. A `0014` torna o filtro sustentável (índice de expressão) sem
desfazer o desvio; desfazê-lo é promover `cohort` a coluna de `agent_signals`,
com backfill e mudança no `strategy-worker`, e continua sendo a forma certa se a
tabela crescer uma ordem de grandeza. `decision_at` **não** precisa dessa
promoção: a coluna já existe e se chama `emitted_at`.

### 26.3 Medido, não suposto (50 000 linhas, 6 versões, 3 coortes, PG 16)

`EXPLAIN (ANALYZE, BUFFERS)` no testcontainer, antes (índices derrubados dentro
de uma transação revertida, o que também derruba a estatística da expressão) e
depois:

| consulta | antes | depois |
|---|---|---|
| totais da aba (coorte, todas as versões) | 96,7 ms · 122 633 buffers · `Nested Loop` de 40 000 sondagens | **43,3 ms · 3 860 buffers** · `Parallel Hash Join` |
| página 1, todas as versões, `ORDER BY emitted_at` | 180,7 ms · 122 633 buffers · `Seq Scan` + `top-N heapsort` | **0,96 ms · 634 buffers** · `Index Scan Backward using ix_agent_signals_cohort_emitted` |
| página 1, uma versão, `ORDER BY emitted_at` | 33,4 ms · 22 717 buffers | **1,6 ms · 700 buffers** · `Index Scan Backward using ix_agent_signals_version_cohort_emitted`, sem `Sort` e sem `Filter` |
| `count_population(cohort='replay:<run>')` | 27,8 ms · 17 632 buffers · `Seq Scan` | **17,7 ms · 3 899 buffers** · `Bitmap Index Scan` |
| placar: população avaliável de uma versão | 32,2 ms · 22 709 buffers · estimativa **42** contra 6 667 reais | **19,7 ms · 3 871 buffers** · estimativa **6 644** |
| página 1 **como a API a escreve hoje** (cast) | 264 ms · `top-N heapsort` de 40 000 linhas | **inalterada** — nenhum índice pode servir esse `ORDER BY` (§26.2) |

O placar é o caso que prova a §26.1 sozinho: o plano continua sendo hash join
com `Sort` (ele lê a população inteira, não uma página), e ainda assim cai de
32,2 ms para 19,7 ms e de 22 709 para 3 871 buffers — **só porque a estimativa
deixou de ser ficção**.

O segundo índice foi medido contra a hipótese de não existir: com apenas
`ix_agent_signals_cohort_emitted`, a página de uma versão vira `Index Scan` no
índice antigo `(strategy_version_id, emitted_at)` com `Incremental Sort` e um
`Filter` de coorte (1,5 ms, 703 buffers — empatado hoje). O que compra o segundo
índice não é o milissegundo de hoje: é que o `Filter` cresce com a proporção de
linhas **não** prospectivas da versão, que é justamente o que uma versão
replayada várias vezes acumula (`Rows Removed by Filter` já é 50 em 252 lidas
com 10 % de replay).

### 26.4 O que **não** entrou, e por quê

- **Índice parcial `WHERE cohort = 'prospective'`** (item b do pedido): a coorte
  é a coluna **líder** dos dois índices, então a fatia prospectiva já é um
  intervalo contíguo dentro de cada um; uma cópia parcial seria uma segunda
  estrutura para manter e escrever, sem nenhuma consulta que ela sirva melhor. E
  `prospective` não é privilegiada: `count_population` e `cohort_cases`
  perguntam por uma coorte `replay:<run>`, que os mesmos índices atendem.
- **`signal_outcomes (tracking_state)`** (item c): `signal_outcomes` nunca é a
  tabela dirigente — toda consulta parte do sinal e alcança o desfecho pela
  chave primária. Um índice de cinco rótulos seria escrito em todo `UPDATE` de
  outcome e lido por ninguém. **Medido, não suposto:** o teste de `EXPLAIN` cria
  esse índice dentro de uma transação, mostra que nem os totais nem
  `state=closed` o mencionam, e o desfaz. Se um dia uma consulta o quiser, o
  teste falha e ele vira migração em vez de parágrafo.

### 26.5 Trava, downgrade e pooler

`CREATE INDEX` simples, dentro da transação da migração — não
`CONCURRENTLY`. Ele toma `SHARE` em `agent_signals`, que bloqueia os `INSERT`s
do strategy-worker durante a construção e deixa todo leitor passar; medido em
50 000 linhas, os dois índices custam 131/162 ms e 148/192 ms em duas execuções,
e uns poucos milissegundos nas 5 571 linhas que a VPS tem hoje. A `0004`
precisou de `CREATE INDEX CONCURRENTLY` em `autocommit_block` porque
`outbox_events` recebe ~700 mil linhas/dia; `agent_signals` recebe ~1 600, e
comprar uma migração não atômica — que pode deixar um índice `indisvalid = false`
e precisa da própria receita de recuperação — seria pagar esse preço por nada. Se
um dia o volume tornar a construção uma indisponibilidade visível, a receita é a
da `0004`.

`downgrade` derruba os dois e não perde nada: um índice não guarda fato que a
tabela não tenha. Não há guarda de downgrade, e a ausência é afirmação (§17.7 só
protege evidência). Nada aqui depende de estado de sessão: dois `CREATE INDEX`,
nenhum prepared statement de sessão, nenhum `LISTEN`/`NOTIFY`, nenhum advisory
lock de sessão — a revisão é transparente para o pooler.

### 26.6 Onde as declarações moram, e o que o `alembic check` de fato compara

As duas `Index(...)` são construídas por
`hunter_core.db.models._common.shadow_cohort_indexes()` e entram no
`__table_args__` de `AgentSignal` com `*shadow_cohort_indexes()`. Ficam ali, ao
lado de `org_fk()`/`tenant_scoped_fk()`, porque `models/agents.py` está no teto
de 350 linhas do projeto; a expressão da coorte é a constante
`_common.SHADOW_COHORT`, a mesma string que a `0014` instala.

`alembic check` **detecta** a ausência de qualquer um dos dois (medido: com os
índices derrubados à mão ele acusa `Detected added index
'ix_agent_signals_cohort_emitted' on ('emitted_at', 'id')`), mas repare no que
ele lista: **as colunas não-expressão**. Uma divergência apenas no texto da
expressão passaria em silêncio — e um índice cuja expressão não bate com a da
consulta é um índice que ninguém usa. Por isso a prova real é o catálogo:
`test_0014_installs_the_two_cohort_indexes_and_reverses` lê
`pg_indexes.indexdef` e exige `supporting_features ->> 'cohort'` lá dentro (a
mesma razão pela qual a §17.3 lê `indexdef` para um predicado).

### 26.7 Desvios em relação ao brief, declarados

| O brief pedia | O que foi entregue, e por quê |
|---|---|
| índice composto `(strategy_version_id, cohort, emitted_at DESC, id DESC)` | entregue, ascendente (§15.3): a leitura `DESC` percorre o mesmo índice de trás para frente |
| índice parcial `WHERE cohort = 'prospective'` | **não entrou** (§26.4): a coorte é coluna líder, a fatia já é contígua |
| índice em `signal_outcomes (tracking_state)` | **não entrou** (§26.4), com o plano que prova que ninguém o leria |
| "`CREATE INDEX CONCURRENTLY` não é possível dentro da transação do Alembic" | é possível, e a `0004` já o faz num `autocommit_block`. Ainda assim escolhi `CREATE INDEX` simples, com a trava medida (§26.5) |
| "o teste de `EXPLAIN` afirma um `Index Scan` para a visão padrão" | afirma — para a visão padrão **ordenada pela coluna**. Para a rota como ela está escrita hoje o teste afirma o contrário (`Sort` + `Seq Scan`), porque é o que o Postgres permite (§26.2) |
| (o brief não fala de estatística) | é o ganho maior, e vale mesmo onde o índice não é varrido (§26.1, §26.3) |

## 27. O runtime deixa de conectar como dono — M3 (`0015_runtime_login_role`)

Décima quinta revisão. **Nenhuma tabela, coluna, constraint, índice, enum,
trigger, política, partição ou `GRANT` sobre relação nenhuma**: um papel de
cluster, duas memberships e um `CONNECT`. Ela fecha, do lado do banco, o HIGH 1
que a §23.5 registra — o achado de que `DATABASE_URL` e
`DATABASE_URL_MIGRATIONS` eram a **mesma credencial de dono**, e que por isso
todo `REVOKE` das §22.3/§23.1/§24.5 valia contra o papel e não contra o
processo, que podia simplesmente deixar de ser o papel com um `RESET ROLE`.

`0015_runtime_login_role` tem 23 caracteres; o teto de
`alembic_version.version_num` continua sendo 32 (§17.6). As listas desta revisão
estão congeladas em `ddl/runtime_login_role.py`, no padrão de
§15.6/§16.5/§17.6/§18.9/§19/§20/§21/§22/§24/§25.

A frase que organiza tudo abaixo: **um papel que o processo pode deixar de ser
não é um limite, é uma convenção.**

### 27.1 O papel, e por que `NOINHERIT` é a decisão

```sql
CREATE ROLE hunter_runtime
  LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION NOINHERIT;
GRANT hunter_app    TO hunter_runtime WITH INHERIT FALSE, SET TRUE;
GRANT hunter_worker TO hunter_runtime WITH INHERIT FALSE, SET TRUE;
GRANT CONNECT ON DATABASE <o banco corrente> TO hunter_runtime;
```

Membro de `hunter_app` e `hunter_worker` **e de mais nada**; dono de nada. O
login dono (`hunter`) continua existindo e continua sendo o de `migrate` e do
serviço `ops` (§23.5).

**`NOINHERIT` é acréscimo ao brief da tarefa, que não fala de herança — e é o
que decide se esta revisão fecha ou reabre um buraco.** Com o `INHERIT` padrão,
o login carregaria, **sem `SET ROLE` nenhum**, a *união* das ACLs dos dois
papéis, e — o que é pior — `pg_has_role(current_user, 'hunter_app', 'USAGE')` e
`pg_has_role(current_user, 'hunter_worker', 'USAGE')` seriam **as duas
verdadeiras**. Toda guarda que o schema usa para distinguir "a aplicação e nada
além dela" de "o motor e nada além dele" está escrita exatamente nessa forma:

| Guarda | Condição | Um login que herda os dois |
|---|---|---|
| `trade_proposals_the_app_only_files_requests` (§19.4, §21.2) | `pg_has_role(app,'USAGE') AND NOT pg_has_role(worker,'USAGE')` | **não dispara** |
| `portfolios_are_born_audited` (§20.2) | `pg_has_role(worker,'USAGE') AND NOT pg_has_role(app,'USAGE')` | **não dispara** |
| `portfolio_risk_state_guard` (§18.7) | `pg_has_role(worker,'USAGE')` | é lido como o motor |

As duas primeiras são assim de propósito: **quem tem os dois papéis é o
operador** (§20.2, "quem a guarda deliberadamente não alcança"). Um login de
*runtime* com os dois herdados é lido pelo schema como o operador — e, com a
união dos privilégios na mão, isso é um `INSERT INTO trade_proposals` já
`approved`, com um `risk_decision` que o Risk Engine nunca tomou, escrito de
dentro de um request handler comprometido. Seria fechar a porta da frente
reabrindo a janela que a §19.4 existe para fechar.

Com `NOINHERIT`, e **medido** em
`test_runtime_login_role.py::test_the_guards_still_tell_the_application_and_the_engine_apart`:

| `SET LOCAL ROLE` | `pg_has_role(app,'USAGE')` | `pg_has_role(worker,'USAGE')` |
|---|---|---|
| nenhum | `false` | `false` |
| `hunter_app` | `true` | `false` |
| `hunter_worker` | `false` | `true` |

Três consequências, e nenhuma delas é estilo:

1. o privilégio efetivo do login é **nenhum**. Um caminho de código que esqueça
   o `SET LOCAL ROLE` falha alto com *permission denied* em vez de rodar em
   silêncio com a união (`test_without_set_role_the_runtime_login_reaches_no_table`);
2. depois do `SET LOCAL ROLE`, `current_user` **é** o papel, e as guardas mordem
   exatamente como hoje;
3. `RESET ROLE` — a reversão voluntária que o achado cita como o furo — passa a
   devolver **nada**.

`SET ROLE` continua permitido: ele depende da opção `SET` da membership, nunca
de `INHERIT`. E `WITH INHERIT FALSE` é escrito na própria membership, além do
atributo do papel, porque desde o Postgres 16 a opção mora na membership: um
`ALTER ROLE hunter_runtime INHERIT` posterior não deve poder ligar a união de
volta para uma concessão feita sob o padrão antigo.

#### O que um login único não fecha — o resíduo declarado (revisão de segurança da T3.15f, ALTA 1)

`SET ROLE` continuar permitido é o que faz esta revisão funcionar **e** é o que
ela não fecha. `NOINHERIT` mata o caminho *silencioso*; o caminho *deliberado*
continua aberto, e a frase honesta é esta:

> um login que é membro dos dois papéis pode `SET ROLE` para qualquer um deles.
> Um RCE no `api` executa `SET LOCAL ROLE hunter_worker` e passa a ter
> `BYPASSRLS` (§27.2 é a prova disso, do lado bom) **mais** os grants de escrita
> da execução (`orders`, `fills`, `positions`, `trades`, `trade_proposals`,
> `portfolio_equity_snapshots`, §19.1): lê e escreve **toda** organização.

E as guardas não substituem o limite, porque elas foram escritas para distinguir
papéis, não processos:

| Guarda | Contra uma sessão que virou `hunter_worker` |
|---|---|
| `trade_proposals_the_app_only_files_requests` (§19.4/§21.2) | **não morde** — a condição é `app AND NOT worker`, e essa sessão é `worker`. Um `INSERT` já `approved`, com `risk_decision` forjado, passa |
| `portfolios_are_born_audited` (§20.2) | morde (`worker AND NOT app`), mas só exige uma linha de `audit_logs` na mesma transação — que a mesma sessão escreve |
| `portfolio_risk_state_guard` (§18.7) | trata a sessão como o motor: `trading_day`, `equity_day_start` e `peak_equity` viram escrita legítima |

É **exatamente** o cenário que o bloco acima usa para justificar o `NOINHERIT`,
alcançado por outro caminho — e é por isso que a §23.5 deixou de dizer "HIGH 1
fechado depois de (a)–(e)". Três coisas ficam registradas junto, para que a
frase não seja lida como mais alarmante do que é:

1. **não é regressão.** Antes de (d) é estritamente pior: a DSN é a do dono,
   `rolsuper = true`, e nem `SET ROLE` é preciso. A `0015` é melhora estrita;
2. **não bloqueia o deploy.** (a)–(e) continuam sendo o próximo passo, e fecham
   as três primeiras linhas da tabela da §23.5;
3. **o que sobra é uma superfície de *tenant e de execução*, não de schema**: o
   login não é dono de nada, então `ALTER TABLE`, `DROP`, `TRUNCATE` e a
   promoção de `strategy_versions` a `paper` (§22.3/§23.1) continuam fora de
   alcance por **todos** os papéis que ele pode virar.

**O fechamento de verdade são dois logins, e é a T3.15h — nota de desenho, não
implementada aqui.** Um papel por processo, cada um membro de **um** papel:

```sql
-- T3.15h (desenho; nenhuma revisão o implementa hoje)
CREATE ROLE hunter_runtime_api    LOGIN NOSUPERUSER … NOINHERIT;
CREATE ROLE hunter_runtime_worker LOGIN NOSUPERUSER … NOINHERIT;
GRANT hunter_app    TO hunter_runtime_api    WITH INHERIT FALSE, SET TRUE;
GRANT hunter_worker TO hunter_runtime_worker WITH INHERIT FALSE, SET TRUE;
```

Com eles, `SET ROLE hunter_worker` a partir do `api` responde *permission denied
to set role* — a lista de papéis alcançáveis **é** a superfície do login
(§27.3), e um login que só pode virar `hunter_app` não alcança `BYPASSRLS` por
caminho nenhum. O que a T3.15h precisa resolver, e por isso ela é uma tarefa e
não uma linha:

- **duas senhas e duas DSNs no compose.** `x-api-env` deixa de ser um bloco só:
  `api` recebe a do `api`, e os quatro workers a do worker. Duas chaves novas no
  `.env`, dois passos (b) no runbook;
- **quem é quem não é óbvio em todo processo, e este é o item difícil.** O `api`
  usa `hunter_worker` em caminhos legítimos hoje: `auth/principal.py:231`
  (transformar um id do Clerk no `users.id` — em **toda** requisição
  autenticada), `services/clerk_webhook.py` e `services/invitations.py:193`
  (aceitar um convite pelo hash do token). As políticas de `users` são chaveadas
  em `app.current_user`, então essas buscas *precisam* atravessar a RLS (§1.2a,
  §15.4). Ou elas mudam — um papel novo, estreito, só para resolver identidade,
  o que é uma revisão de schema —, ou o login do `api` volta a ser membro dos
  dois e a T3.15h **não entrega nada**. **Resolver isto é o coração da tarefa**,
  não um detalhe de configuração;
- **`infra/scripts/open_paper_wallet.py` e os demais atos de operador** rodam
  como `hunter_worker` pelo `ops` (§19.6), que continua com a DSN de dono — não
  são afetados;
- **a `0015` não precisa ser revertida**: a T3.15h acrescenta dois logins ao
  lado, e `hunter_runtime` é aposentado quando as duas DSNs estiverem de pé.

Enquanto isso não acontece, o resíduo é **declarado** — que é a única coisa que
distingue uma lacuna conhecida de uma surpresa (§20.1: "declarar uma lacuna não
é fechá-la"; esta seção declara, e não finge fechar).

### 27.2 `BYPASSRLS` continua chegando aos workers

Atributo de papel **nunca** é herdado, em nenhuma direção. `hunter_runtime` é
`NOBYPASSRLS`; `SET ROLE hunter_worker` faz o papel corrente ser
`hunter_worker`, e `check_enable_rls` lê o `rolbypassrls` do papel **corrente**.
Então `strategy`/`execution`/`analytics` continuam varrendo todas as
organizações (§1.2) e `hunter_app` continua sem bypass. Era o jeito óbvio de
esta revisão quebrar o sistema em silêncio, então é medido e não argumentado:
`test_the_engine_role_still_bypasses_rls_through_the_runtime_login`.

### 27.3 A migração: idempotente, sem senha, e verificando o resultado

O padrão é o de `create_roles()` (§15.6): tenta, tolera não poder, e **verifica
o resultado no catálogo**, falhando com os comandos manuais exatos — nunca um
`NOTICE` que alguém lê como aviso.

| Passo | Tolerado | Verificado |
|---|---|---|
| `CREATE ROLE` | `duplicate_object`, `insufficient_privilege` | existe em `pg_roles` |
| `ALTER ROLE <atributos>` | `insufficient_privilege` | `rolcanlogin` e os seis "no" (`rolsuper`, `rolbypassrls`, `rolcreaterole`, `rolcreatedb`, `rolreplication`, `rolinherit`) |
| `GRANT hunter_app`/`hunter_worker` | `insufficient_privilege` | `pg_has_role(…, 'MEMBER')` verdadeiro, `…, 'USAGE'` falso, **e nenhuma terceira membership** |
| `GRANT CONNECT` | `insufficient_privilege` | `has_database_privilege(…, 'CONNECT')` |

O `ALTER ROLE` é emitido em **dois** comandos — os três atributos que só um
superusuário pode mexer (`NOSUPERUSER`, `NOBYPASSRLS`, `NOREPLICATION`), e o
resto — para que um papel migrador apenas `CREATEROLE` (a forma usual num
Postgres gerenciado) ainda consiga consertar `LOGIN`/`NOINHERIT`/`NOCREATEDB`/
`NOCREATEROLE` em vez de perder o `ALTER` inteiro. Ele é emitido
incondicionalmente, e é isso que **conserta** um `hunter_runtime` criado à mão
com a forma errada: um papel que herda, ou que carrega `BYPASSRLS`, é pior que
papel nenhum, porque a DSN pareceria correta.

**A terceira membership para a migração**, e isso é escolha: a lista de papéis
que este login pode virar **é** toda a superfície de segurança dele — ele não
tem privilégio próprio nenhum —, então uma membership que ninguém escreveu aqui
alarga essa superfície em silêncio. Alargar é revisão nova
(`RUNTIME_MEMBER_OF_0015`), nunca um `GRANT` que alguém roda uma vez e ninguém
mais lê.

**O preço, dito com precisão** (revisão de segurança da T3.15f, BAIXA 7 — a
redação anterior, aqui e em `.claude/state/notes-T3.15f.md` §10.4, dizia
"derruba o próximo deploy" e prometia um alarme que não existe): a verificação
roda **quando a `0015` roda**, e a `0015` não roda de novo num banco que já está
nela. Conceder um papel de monitoração a `hunter_runtime` à mão, hoje, não
derruba `compose.sh update` nenhum — o `alembic upgrade head` da VPS não tem o
que aplicar. O que ela de fato pega é: um **banco novo** do mesmo cluster
subindo do zero (papel é objeto de cluster, a membership extra já está lá), um
`downgrade` seguido de `upgrade`, e a CI, que migra do zero a cada execução. É
uma guarda de *provisionamento*, não um monitor contínuo — quem quiser a versão
contínua tem de escrever um teste que rode contra o banco vivo, e ele não
existe.

**Postgres 16 ou mais novo, e é requisito, não preferência (BAIXA 8).**
`GRANT … WITH INHERIT FALSE, SET TRUE` é sintaxe do PG16: a opção `INHERIT` por
membership e a opção `SET` nasceram lá. Num cluster PG15 a `0015` morre com
**erro de sintaxe** — e o `DO` só tolera `insufficient_privilege` e
`duplicate_object`, de propósito (tolerar erro de sintaxe seria seguir sem a
membership), então o serviço `migrate` falha e o deploy para. Isso não é
regressão de compatibilidade: `docs/DATABASE.md` abre declarando "PostgreSQL 16
(Neon em produção)", os dois composes fixam `postgres:16-alpine` e os testes
rodam em `postgres:16-alpine`. Fica escrito porque um cluster mais velho é
justamente o tipo de coisa que aparece num ambiente que ninguém previu — e o
sintoma, `syntax error at or near "INHERIT"` no meio do `migrate`, não sugere
sozinho "o servidor é velho demais".

**Nada de senha, e nada de afirmar sobre ela.** A migração cria o papel sem
senha; quem a define é o operador, fora de banda (§23.5, passo (b)). E ela não
finge verificar: `pg_authid.rolpassword` só é legível por superusuário, então não
há nada que ela pudesse conferir honestamente.

**Nenhum `GRANT` de tabela, e isso é afirmação.** O privilégio do runtime é
exatamente o de `hunter_app`/`hunter_worker`, alcançado por `SET ROLE`. Dar ao
login algo próprio criaria uma terceira ACL a manter em dia — o
no-op-que-parece-garantia que a §15.6 registra e a §24.5 recusa repetir.

**A tabela de papel × tabela × privilégio da §19.1 não muda.** `hunter_runtime`
não aparece nela porque não tem linha para aparecer: ele não é um papel que
recebe privilégio, é o login de onde uma sessão *parte*. Pela mesma razão ele
não entra em `hunter_core.db.session.DB_ROLES` — nada nunca faz
`SET ROLE hunter_runtime`.

### 27.4 Downgrade: derruba o papel só quando nada mais depende dele

Papel é objeto de **cluster**; migração é de **banco**. Outro banco do mesmo
cluster pode já estar na `0015` — é literalmente o caso do container de teste,
com quatro — e o `GRANT CONNECT` de cada um deixa uma linha em `pg_shdepend`. Um
`DROP ROLE` incondicional ou falharia com *dependent objects still exist*, ou
tiraria o login de um banco que ainda o usa. Então o downgrade:

1. `REVOKE CONNECT` no banco corrente;
2. `REVOKE hunter_app, hunter_worker FROM hunter_runtime`;
3. conta o que o papel possui (`pg_class`/`pg_namespace`/`pg_proc`/`pg_type`/
   `pg_database`) e as referências restantes em `pg_shdepend`. **Zero →
   `DROP ROLE`. Qualquer coisa → deixa o papel de pé**, com um `NOTICE`
   nomeando o que resta.

O que o downgrade tem de remover é o **alcance**, e o alcance é a membership —
um login sem membership e sem `CONNECT` aqui não chega a lugar nenhum. É por
isso que o teste afirma "não pode mais virar nada"
(`test_0015_reverses_by_taking_the_membership_away`) e não "o papel sumiu"; e é
o mesmo precedente da `0001`, cujo downgrade nunca derruba
`hunter_app`/`hunter_worker`.

**Declarado: membership é cluster-wide**, então reverter **num** banco a revoga
para todos os bancos daquele cluster. É inerente a papel de cluster e vale igual
para o `CREATE ROLE` do upgrade; a VPS tem um banco só.

**Não há guarda de downgrade, e a ausência é afirmação.** A §17.7 protege
*dado*; esta revisão não guarda linha nenhuma — ela declara quem pode conectar,
que é declaração de credencial e nunca fato sobre dado, exatamente como os
grants da `0007` (§19.5) e da `0008` (§20.5). O que **não** é de graça é o lado
operacional, e está escrito em `docs/DEPLOYMENT.md` §3.5: reverter esta revisão
com o `DATABASE_URL` ainda nomeando `hunter_runtime` deixa todo processo de
runtime sem alcançar tabela nenhuma. Volte a DSN **primeiro**; por isso o
caminho de rollback do runbook não precisa deste downgrade.

### 27.5 O que o runtime executava que precisava do dono — a varredura, e o único achado

Levantamento sobre `apps/api/hunter_api/**` e `services/*/hunter_*/**`:

| Procurado | Encontrado |
|---|---|
| `CREATE` / `ALTER` / `DROP` / `TRUNCATE` | **nada** |
| criação de partição | **nada** — é `infra/scripts/create_partitions.py`/`prune_partitions.py`, pelo `ops` (T3.15e) |
| `LISTEN` / `NOTIFY` | **nada** (§16.5, §17.9, §18.10, §19.7, §20.6, §21.5, §24.7, §25.7) |
| advisory lock | só `pg_advisory_xact_lock` (`market-worker/recovery_queries.py`) — **de transação**, seguro atrás do pooler, e sem privilégio especial |
| `DATABASE_URL_MIGRATIONS` | nenhum processo de runtime a lê desde a T3.15d |

**Um achado, e não é DDL: quatro conexões sem `SET ROLE`.**
`services/scanner-worker/hunter_scanner_worker/main.py` (`_warm`) e
`refresh.py` (três lugares) abrem `engine.begin()` cru — sem `SET LOCAL ROLE` —
e leem `feature_snapshots`/`feature_baselines` e **escrevem** `feature_baselines`
(`SqlBaselineStore.append`). Hoje isso funciona porque o login é o dono; sob
`hunter_runtime` é *permission denied*, que é precisamente o comportamento que a
§27.1 item 1 comprou.

O conserto é uma linha em cada uma (`SET LOCAL ROLE hunter_worker` como primeiro
statement da transação) e é do dono de `services/**`. Fica registrado aqui como
**pré-requisito do passo (d)** do runbook — não da migração: a `0015` pode ser
aplicada a qualquer momento sem tocar em nada, e é a troca do `DATABASE_URL` que
depende desse conserto. Declarado em vez de descoberto depois, no padrão da
§21.6 e da §22.5.

### 27.6 Pooler e trava

Nada aqui depende de estado de sessão: um papel, duas memberships e um grant de
banco. Sem prepared statement de sessão, sem `LISTEN`/`NOTIFY`, sem advisory
lock de sessão. E nenhum `ALTER TABLE`: a revisão não toma trava em relação
nenhuma e **não abre janela de manutenção**, ao contrário da `0010` e da `0012`
(§15.6, §24.7).

Uma observação que vale para o dia a dia depois de (d): `SET LOCAL ROLE` é
escopado à transação, então o pooler em modo transação continua entregando a
mesma conexão física para o próximo chamador **sem** papel herdado — a mesma
propriedade que o `SET LOCAL statement_timeout` do §1.2a tem, e o motivo pelo
qual trocar o login não muda nada no comportamento atrás do pooler.

## 28. Uma exchange que ninguém coleta não é um feed quebrado — M3 (`0016_exchange_status_planned`)

Décima sexta revisão. **Um rótulo de enum.** Nenhuma tabela, nenhuma coluna,
nenhum índice, nenhuma constraint, nenhum trigger, nenhuma política, nenhuma
partição, nenhum `GRANT`.

Ela responde ao brief `.claude/state/brief-T3.44c-exchange-status-planned.md`,
que a T3.44b escreveu **em vez de** editar uma migração — o brief dela já previa
esta saída ("se `exchanges.status` não tiver um valor `planned` no seu
CHECK/enum, diga isso e acione o database-architect").

O sintoma estava no topbar. `exchanges` tem `binance` e `bybit`, a Bybit nunca
teve coletor implantado, e `build_market_status` renderiza **uma linha por
entrada de `exchanges`** de propósito (uma exchange que o worker nunca tocou tem
de aparecer, e não sumir em silêncio). Então a redução "pior de todas" sobre
`ws_state` lia **`2 exchanges · UNAVAILABLE`** enquanto a Binance estava
conectada o tempo inteiro. O rótulo que faltava não era um valor de linha: era um
estado que o tipo não sabia dizer.

### 28.1 Desvio declarado em relação à §15.1

A §15.1 fixou `exchange_status` = `active|inactive` ("ciclo de vida mínimo — nada
nos documentos distingue um terceiro estado"). **Este documento agora distingue**,
e a linha de lá foi anotada em vez de reescrita: ela descreve o que a `0001`
criou, que é o que "congelado por revisão" significa (§16.5, §17.1). A §1 nomeia
`ALTER TYPE ... ADD VALUE` por migração como *o* mecanismo para exatamente isto,
então a extensão é o caminho previsto, não uma exceção a ele — o que muda é a
afirmação de que dois rótulos bastavam.

**Por que um terceiro rótulo e não uma segunda coluna.** O brief deixou a escolha
em aberto e nomeou a alternativa (`has_collector boolean`, ou um
`onboarding_status` próprio). `exchange_status` **já é** o ciclo de vida da
exchange para nós, e `planned` é um ponto dele, não um segundo eixo: catalogada
sem coleta → coletada → desligada. Um booleano seria um fato de *implantação* ao
lado de uma coluna de *ciclo de vida*, duas coisas a manter de acordo sem
constraint capaz de dizer como, e todo leitor teria de aprender que
`status = 'active' AND NOT has_collector` significa o que um rótulo significa. E
`inactive` não serve: ninguém desligou a Bybit — o rótulo diria que alguém
desligou, e a §16.2 já registra o padrão de recusar um rótulo que mente sobre o
que aconteceu.

**Posição: `BEFORE 'active'`** (`ddl/enums.py`, `EXCHANGE_PLANNED_ADDED_VALUES`).
`enumsortorder` faz parte do contrato (§17.1) e
`hunter_core.domain.enums.ExchangeStatus` declara `PLANNED` primeiro para casar:
uma exchange é planejada antes de ser coletada.

| Rótulo | O que significa | Quem escreve |
|---|---|---|
| `planned` | catalogada, **sem coletor implantado** | `infra/scripts/seed.py` (`seed_reference.EXCHANGES`), depois do commit da migração |
| `active` | coletada agora — o default de coluna que a `0001` deu, e continua dando | idem, e é o que toda linha existente já era |
| `inactive` | desligada por alguém | ninguém hoje |

### 28.2 Dentro da transação da migração, e isso não é descuido

O brief pedia o `ADD VALUE` **fora** de um bloco de transação, "como o Postgres
exige". O Postgres 12+ não exige nada disso: o que ele proíbe é **usar** o rótulo
novo na mesma transação, em `DEFAULT`, predicado de índice ou qualquer outro DDL
(§17.1, §18.1). Esta revisão acrescenta o rótulo e não escreve nenhum —
`exchanges.status` mantém o `server_default 'active'` da `0001` — e `planned`
alcança uma linha pela primeira vez através do seed, depois do commit. Passar por
`autocommit_block()` não compraria nada e custaria a atomicidade da revisão, que
é o preço que a `0004` paga só porque o `CONCURRENTLY` não lhe deixa escolha
(§17.5). **Desvio declarado em relação ao brief.**

### 28.3 O downgrade reconstrói o tipo, e recusa antes

Não existe `ALTER TYPE ... DROP VALUE`. `ddl/exchange_planned.py` renomeia o
tipo, recria-o com os rótulos que a `0001` congelou, retipa `exchanges.status`
**em volta do default** (um default guardado já vem coagido ao tipo antigo e
bloquearia a troca) e derruba o original — a receita que a `0003` estabeleceu
(§17.1).

Antes de tudo isso, uma guarda conta as exchanges ainda marcadas `planned` e
**recusa**, nomeando-as:

| Guarda | O que se perderia |
|---|---|
| `exchanges` com `status = 'planned'` | os dois rótulos que sobrevivem mentem sobre essa exchange — `active` a devolve ao agregado que esta revisão existe para consertar, `inactive` diz que alguém a desligou. "A migração reverteu sem erro" seria o único relatório dessa reescrita |

Ela não apaga nada: conta, nomeia e manda decidir qual dos dois rótulos cada
exchange de fato é — o mesmo limite declarado da §18.9, §24.6 e §25.6 (o
downgrade de um banco povoado não é operação de rotina). Num banco onde nenhuma
exchange foi marcada — todo banco antes do próximo seed — a guarda conta zero e o
downgrade segue.

**A guarda percorre a mesma tupla congelada que o rebuild percorre**, e não a
única coluna que existe hoje: uma guarda que conferisse uma coluna enquanto o
rebuild retipa várias falharia *dentro* do rebuild com *invalid input value for
enum*, que não nomeia saída nenhuma.

**`EXCHANGE_STATUS_COLUMNS_0016` nomeia as colunas em vez de descobri-las**, como
toda lista congelada deste pacote. Uma revisão futura que ponha `exchange_status`
numa segunda coluna e não estenda o *próprio* rebuild dela não perde a coluna em
silêncio: o `DROP TYPE` do tipo renomeado falha enquanto essa coluna ainda depende
dele, o que é um erro alto nomeando a dependência, e não um retype que esqueceu
uma.

### 28.4 Guardas de upgrade, grants, RLS e trava

**Não há guarda de upgrade, e isso é afirmação** (§19.5, §20.5, §21.4, §24.6,
§25.6): o rótulo é acrescentado, nada que já esteja gravado passa a ser
irrepresentável, e toda linha existente mantém o rótulo que tem — que era
`active`, e continua sendo até o seed dizer outra coisa.

**Nenhum `GRANT` e nenhuma mudança de RLS.** `exchanges` é tabela de referência
global (§1.1): sem `organization_id`, sem política, `SELECT` para `hunter_app` e
escrita para `hunter_worker` desde a `0001`. Um rótulo não é coluna, então
nenhuma ACL está envolvida — a mesma aritmética que a §24.5 registra, um degrau
antes.

**Trava.** `ALTER TYPE ... ADD VALUE` toma `ACCESS EXCLUSIVE` no **tipo**, em
`pg_type`, nunca em `exchanges`: leitor e escritor da tabela não são bloqueados e
esta revisão **não abre janela de manutenção** (ao contrário da `0010` e da
`0012`, que fazem `ALTER TABLE` validante). Quem toma `ACCESS EXCLUSIVE` em
`exchanges` é o downgrade, sobre uma tabela de duas linhas.

**Pooler.** Nada aqui depende de estado de sessão: um `ALTER TYPE`. Sem prepared
statement de sessão, sem `LISTEN`/`NOTIFY`, sem advisory lock de sessão.

`0016_exchange_status_planned` tem 28 caracteres; o teto de
`alembic_version.version_num` continua sendo 32 (§17.6).

### 28.5 O seed passa a escrever `status`, e ganha `--only exchanges`

`seed_exchanges` **não nomeava `status`** nem no `INSERT` nem no
`ON CONFLICT DO UPDATE`: uma linha nova caía no default e uma linha existente
ficava congelada no rótulo com que foi escrita pela primeira vez. Isso não era
uma escolha — era a consequência de não haver rótulo a escolher. Agora
`seed_reference.EXCHANGES` carrega `(code, name, status, capabilities)` e o valor
viaja nas duas metades do upsert, então **re-semear é como uma exchange que
ganhou (ou perdeu) coletor é corrigida**. `bybit` é `planned`; no dia em que um
coletor subir para ela, essa linha vira `ACTIVE` e o comando abaixo aplica.

`exchanges` entra em `seed_dry_run.TABLE_CHOICES` (a quinta tabela "diffável",
chaveada por `code`) e em `seed_cli._run_only`. O brief T3.44c registrava que
`seed.py --only exchanges` **não existia** — a correção é esta, e o comando do
operador é:

```bash
bash infra/vps/compose.sh run --rm ops python infra/scripts/seed.py --only exchanges --dry-run
bash infra/vps/compose.sh run --rm ops python infra/scripts/seed.py --only exchanges
```

O `--dry-run` imprime a linha `exchanges.bybit: status: 'active' -> 'planned'` e
não commita nada; o segundo comando escreve. O portão de `--yes` continua sendo
só o de `risk_profiles` (a diretiva de risco, §17.8) — `--only exchanges` não o
dispara —, e o portão de execução não assistida (diff não vazio, `stdin` sem TTY)
continua valendo para ele como para qualquer outro.

### 28.6 O que a API passa a devolver, e o que ela deixa de contar

`MarketStatusOut` ganha **`exchanges_planned: list[str]`**, aditivo e com default
`[]` — nada que já lê o modelo precisa mudar, e o contrato de patch do `rt:system`
(uma linha de exchange por mensagem, nunca esta lista) fica exatamente como
estava. `build_market_status` passa a ler `(code, status)`
(`MarketRepository.list_exchanges_with_status`) e a exchange `planned`:

- **não vira linha** em `exchanges` — não há feed dela para estar em apuros;
- **não é lida no Redis** — não há heartbeat a procurar;
- **não conta no teste "todas as leituras falharam"**, e essa é a parte que não é
  cosmética: com a Bybit na lista, uma queda real do Redis numa implantação de um
  coletor só seria *uma* falha em *duas* exchanges, ficaria aquém de "todas" e
  responderia `200` em vez de `503` — exatamente a resposta saudável durante uma
  indisponibilidade que a regra (G4) existe para impedir;
- **não entra em `markets_monitored_total`**, que passa a somar só as exchanges
  coletadas: os mercados de uma exchange planejada podem carregar `is_monitored`
  de uma sincronização de catálogo e ninguém os lê, então contá-los faria o
  cabeçalho discordar da soma das linhas abaixo dele — que é o número que o
  cliente web calcula por conta própria (`totalMonitoredFrom`).

No topbar (`apps/web/components/system/live-status.tsx`) o rótulo passa a ser
`binance · CONNECTED · 200 mercados · há Ns (bybit planejada)`; o painel completo
ganha uma linha `bybit planejada · sem coletor` em vez de perder a exchange da
tela — sumir com ela seria a outra metade da mesma mentira.

**Nenhum status é filtrado além de `planned`.** `inactive` continua entrando no
agregado como sempre entrou: nenhuma exchange está `inactive` hoje, o brief não
pediu, e "desligada por alguém" é um fato que o operador deve ver no painel.
Declarado aqui em vez de descoberto.

### 28.7 O terceiro módulo irmão do seed (`seed_risk_reference.py`)

O rótulo novo custou linhas a `seed_reference.py` (uma coluna a mais em cada
linha de `EXCHANGES`, o `import` de `ExchangeStatus` e o comentário da tupla), e
isso o levou a **356 linhas** — sobre o orçamento de 350 do
`infra/scripts/check_file_size.py`. O corte é o mesmo que a §17.8 fez em T2.1,
uma tabela adiante: `seed_risk_reference.py` passa a ser o conteúdo de
**`risk_profiles`** — `RISK_LIMITS`, `REGIME_MULTIPLIERS`, `RISK_PRESETS`,
`PAPER_V1_NAME` e `PAPER_V1_LIMITS` —, que é uma tabela inteira e nada além dela;
`seed_reference.py` fica com os catálogos (exchanges, estratégias, entitlements,
flags, features) e os vetores de peso, e cai para 291 linhas.

**Os cinco nomes continuam sendo lidos de `seed_reference`, por reexportação.** É
o precedente do `execution.py` da §18.10 e do `create_partitions.py` da §1.3: uma
divisão de módulo que quebra um import é uma refatoração que quebrou alguma coisa
— e aqui não são só os irmãos (`seed.py`, `seed_dry_run.py`, `seed_paper.py`),
são também **três módulos de teste que carregam `seed_reference.py` por caminho**
e leem os atributos dele (`test_schema_paper.py::_shipped_paper_limits`,
`packages/indicators/tests/unit/test_weights_contract.py` e
`services/scanner-worker/tests/policies.py`). Os três põem `infra/scripts` no
`sys.path` antes de executar o módulo, então o `import` irmão de dentro dele
resolve — verificado carregando o arquivo pelos três caminhos.

Nenhum valor muda: os dois blocos foram movidos **byte a byte** (comparados entre
o arquivo antigo e o novo, no espírito da prova que a §18.8 exige do `paper_v1`),
a ordem das linhas de `EXCHANGES`/`STRATEGIES` é a mesma, e `PAPER_V1_LIMITS`
continua sendo `hunter_risk.limits.PAPER_V1` despejado — isto é, continua tendo
uma fonte só (§18.8).

## 29. O contexto em que uma versão pode decidir — M3 (`0017_eligibility_policy`)

Décima sétima revisão. **Uma coluna** (`strategy_versions.eligibility_policy jsonb NULL`)
e **um corpo de gatilho substituído**. Nenhuma tabela, nenhum enum, nenhum índice,
nenhuma constraint, nenhuma política, nenhuma partição, nenhum `GRANT`.

Ela responde ao brief `.claude/state/brief-T3.52-regime-gate-elegibilidade.md`: a
série horária de regime que a T3.43 passou a escrever (`market_regimes`,
`scope = 'btc'`, `classifier_version = 'regime_hourly_v1'`) existe desde
2026-09-08 e **nada que decide a lê**. Fazer uma versão recusar-se a decidir fora
do regime para o qual ela foi construída precisa de um lugar onde isso esteja
escrito, e esse lugar não podia ser nenhum dos que já existiam.

**T3.59 acrescenta uma segunda regra ao mesmo envelope, sem migração nova.** A
coluna já era JSONB e o corpo já era um *mapa* de políticas com uma política
dentro (a T3.52 escreveu isso de propósito, §29.2); a T3.59 preenche a segunda
posição do mapa com a regra `hours` (janela de hora do dia, `hours_gate.py`), ao
lado da regra `regime` (§29.6). O envelope pode conter uma regra, as duas, ou
nenhuma (`NULL`) — nunca um mapa vazio (§29.2). §29.8 descreve a regra `hours` e
o desenho de duas regras; as subseções anteriores, que descrevem só `regime`,
continuam valendo para essa regra e não foram reescritas.

### 29.1 Por que não é parâmetro (a alternativa que o brief deixou em aberto)

Três razões, cada uma bastando sozinha:

1. **O `parameters_schema` congelado do pai é quem valida o conjunto**
   (`hunter_strategy_worker.activation.validate_parameters`) e ele não declara a
   chave; `derive_variant.py` recusa explicitamente um `--set` de parâmetro que o
   schema não declara. Para caber em `default_parameters`, o schema teria de
   mudar — e schema é congelado por ativação (§16.1).
2. **`default_parameters` é o que a estratégia lê.** O portão é avaliado pelo
   worker ao montar o `StrategyContext`; nenhuma linha de
   `hunter_core.strategies` o consulta. Uma chave que o código do fecho ignora
   faria `params_hash` distinguir experimentos que o código não distingue.
3. **Mudar o fecho custaria os digests.** `code_ref` é o sha256 do módulo da
   estratégia mais o fecho de imports dela (`hunter_strategy_worker.code_ref`);
   editar `schema.py` moveria `ab2e0398…` (momentum_v1) e `a970c9d9…`
   (mean_reversion_v1), e o worker recusaria **toda** versão ativada por
   `code_ref_mismatch`.

Uma tabela 1:1 (`strategy_version_policies`) também foi considerada e recusada: a
política nasce e morre com a versão, não tem histórico próprio e nunca é filtrada
em SQL — seria uma junção a mais em todo carregamento de roster para representar
um campo que é lido junto com a linha. JSONB é exatamente o caso que a §1 reserva
("dados de forma variável"), e a proibição da mesma seção ("nunca para campos que
serão filtrados com frequência") não se aplica a um campo filtrado nunca.

### 29.2 A forma, e quem a valida

```json
{"regime": {"scope": "btc", "classifier_version": "regime_hourly_v1",
            "rule": "previous_closed_hour", "allow": ["SIDEWAYS"]}}
```

**Não há CHECK.** A gramática é validada por quem lê. Desde a T3.59 isso é duas
camadas: `hunter_strategy_worker.gate_policy.parse_policy` lê o **envelope** —
recusa chave que não seja `regime`/`hours`, objeto vazio (`{}`, §29.2) e qualquer
coisa que não seja um objeto JSON — e despacha o corpo de cada chave para o
parser da regra (`regime_gate.parse_regime_policy`, `hours_gate.parse_hours_policy`,
§29.8). O leitor **falha fechado** nas duas camadas: escopo desconhecido, regra
desconhecida, rótulo que não é `MarketRegime`, `allow` vazia e `UNKNOWN` dentro de
`allow` (regime); limite fora de 0–24, não inteiro, janela vazia, janelas que se
sobrepõem ou cobrem as 24 horas (hours) — e uma versão cuja política não se lê
**não entra no roster** (`policy_unreadable`), em vez de decidir sem o portão que
ela declara. Um CHECK congelaria a gramática em DDL e obrigaria uma migração a
cada política nova; a recusa do leitor é a mesma garantia com o custo no lugar
certo. O `derive_variant.py` usa **as mesmas funções** para validar `--policy`,
então o que o operador consegue gravar é exatamente o que o worker consegue
honrar.

`NULL` é "sem portão" — e é o que toda versão anterior a esta revisão honestamente
é. Não há backfill e não há guarda de upgrade (§22, §28.4): nada que já esteja
gravado passa a ser irrepresentável.

### 29.3 O gatilho é substituído, e a lista copiada é a da `0012`

`ddl/eligibility_policy.py` derruba e recria `shadow_freeze_strategy_version` com
`_FROZEN_COLUMNS_0017` = a lista da `0012` (§24) **mais** `eligibility_policy`.
Congelar é o ponto: uma política que pudesse mudar depois da ativação mudaria em
silêncio o significado de toda coorte já medida sob aquele `strategy_version_id`
— "decide em SIDEWAYS" para os sinais de segunda e "decide em qualquer coisa"
para os de terça, sem nada no ledger capaz de separar os dois.

**Copiar a lista da `0012` e não a da `0010` é o detalhe que quase passou.** A
primeira versão deste módulo copiou a `0010` (o precedente mais óbvio) e teria
**estreitado** o gatilho de volta, desprotegendo `replication_parent_id`/
`replication_index` — um irmão de replicação poderia ser reapontado para outro pai
depois de ativado, reatribuindo em silêncio um experimento cujos sinais já estão
gravados. Quem pegou foi `test_0012_freezes_the_lineage_but_leaves_the_marker_writable`,
que existe exatamente para isso. O downgrade chama o criador da própria `0012`
(`ddl.replication.replace_strategy_version_freeze`), como o da `0012` chama o da
`0010` e o da `0010` chama o da `0002`.

`promising_at`/`promising_by` continuam fora, pela razão da §24: são escritos
**depois** da ativação por definição.

### 29.4 Nenhum `GRANT`, e é isso que dá a permissão certa

A `0010` revogou o `INSERT`/`UPDATE` de tabela do `hunter_worker` em
`strategy_versions` e re-concedeu **coluna a coluna**, nomeando as colunas de
então (`WORKER_COLUMNS_EXCEPT_PURPOSE`, §22). Uma coluna acrescentada depois fica,
por construção, fora de toda concessão que a tabela tem: só a conexão dona
(`DATABASE_URL_MIGRATIONS` — que é como `infra/scripts/derive_variant.py` escreve)
consegue gravá-la. É a privilegiação que esta política precisa, e ela não custa uma
linha de DDL — é a forma que a `0010` deliberadamente deixou pronta. O `SELECT` das
duas roles vem do `GRANT` de tabela da `0001` e cobre a coluna nova pelo mesmo
mecanismo (§24.5).

**Duas provas, e a segunda é a que vale.** `test_0017_leaves_the_gate_readable_by_both_roles_and_writable_by_neither`
(`packages/core/tests/integration/test_migrations.py`) pergunta ao catálogo
(`has_column_privilege`) — mostra o mapa de concessões, e um mapa é uma afirmação
sobre o que *deveria* acontecer. A prova de que o banco recusa é feita **como o
papel**: `test_the_worker_cannot_write_any_of_the_replication_columns`
(`packages/core/tests/integration/test_schema_privileges.py`) ganhou o caso
`("eligibility_policy", "'{}'::jsonb")` e roda um `UPDATE` real numa conexão
`hunter_worker`, esperando `permission denied`. Provar por ausência de concessão
é exatamente o erro que a §15.6 registrou com `ALTER DEFAULT PRIVILEGES`: a
ausência de uma linha de `GRANT` não é uma recusa medida.

**Sem índice:** a coluna nunca é predicado — é lida com a linha, pelo
`load_version_roster`, que já varre a dúzia de versões `active`.

### 29.5 O downgrade recusa

Enquanto existir linha com `eligibility_policy IS NOT NULL`, o downgrade conta,
nomeia e para (§17.7, como a `0010` e a `0016`): derrubar a coluna faria uma versão
construída para decidir só em `SIDEWAYS` voltar a decidir em qualquer regime, em
silêncio, e nada do que sobra permite reconstruir a intenção. Num banco onde
ninguém foi restringido — todo banco antes da primeira derivação com `--policy` —
a guarda conta zero e o downgrade segue.

**Trava.** `ADD COLUMN` sem default não reescreve a tabela (PG 11+): `ACCESS
EXCLUSIVE` pelo tempo de uma atualização de catálogo, sobre uma tabela de algumas
dezenas de linhas. A troca do gatilho toma a mesma trava, no mesmo instante. Não
abre janela de manutenção.

`0017_eligibility_policy` tem 23 caracteres; o teto de `alembic_version.version_num`
continua sendo 32 (§17.6).

### 29.6 Quem lê, e com que regra de corte

`hunter_strategy_worker.regime_gate.load_gate` escolhe **a última linha horária
fechada antes do corte** (`end_time <= source_bar_close`, `ORDER BY start_time
DESC LIMIT 1`, `scope` e `classifier_version` da política) e responde
`regime_gate:<RÓTULO>` na recusa. Uma decisão das 15:30 é cortada pela linha
`[14:00, 15:00)`, nunca pela `[15:00, 16:00)`. A justificativa completa (inclusive
por que a linha que **contém** o corte também não seria antecipação, e por que
mesmo assim não é ela que vale) está em `docs/PIPELINE.md` §4b e no cabeçalho do
módulo. Linha inexistente, `UNKNOWN` do classificador e linha mais velha que duas
horas recusam com `regime_gate:unknown` — o portão nunca decide sem contexto.

### 29.7 O par `(scope, classifier_version)` é conferido contra a série, no momento de escrever

`scope`, `rule` e cada rótulo de `allow` têm lista fechada: o parser
(`hunter_strategy_worker.regime_gate.parse_policy`) recusa o que não conhece.
**`classifier_version` não tem, e não pode ter** — o nome nasce no produtor
(T3.43, `regime_hourly_v1`) e um classificador novo aparece lá antes de aparecer
em qualquer lugar que decida. Uma gramática que fechasse essa lista tornaria
cada classificador novo uma migração.

O buraco que isso deixava era silencioso, e é a única razão desta subseção: um
`classifier_version` (ou um `scope`) sem série por trás **passa** na validação, a
versão entra no roster e recusa **toda** barra com `regime_gate:unknown` /
`detail = no_row`. Fecha, como deve — mas em silêncio, e o operador só descobre
pela ausência de sinais, semanas depois, num braço que ele acha que está medindo.

Então quem fecha a lista é o banco, na escrita: `infra/scripts/derive_variant.py`
(`_refuse_a_gate_with_no_series`) recusa `--policy` quando
`SELECT 1 FROM market_regimes WHERE scope = ... AND classifier_version = ... LIMIT 1`
não devolve nada, e a mensagem **nomeia o par**. É `SELECT` puro, pela conexão dona
que o script já usa, sobre uma tabela global (sem `organization_id`, sem RLS — §5),
e vale também no `--dry-run`, que é onde o operador espera ouvir isso.

**A checagem é de escrita, não de leitura**, e o limite é deliberado: um portão
**herdado** não é reconferido. Ele já passou por aqui quando foi escrito, e
reconferi-lo faria uma variante de `--set` — que não fala de portão nenhum — ser
recusada porque a série do produtor foi podada. Quem cobra a série ausente em tempo
de decisão é o próprio portão (§29.6), que é o lugar certo. Provado em
`services/strategy-worker/tests/test_derive_variant.py`:
`test_it_refuses_a_gate_whose_pair_has_no_series_in_market_regimes` e
`test_an_inherited_gate_is_not_re_checked_against_the_series`.

**Não é um `CHECK` nem uma FK.** Uma FK de `strategy_versions` para uma série
horária não existe para ser feita (o alvo é um par de colunas de uma tabela de
fatos, sem unicidade), e um `CHECK` não consegue consultar outra tabela. A trava
é do script porque é lá que a intenção do operador entra no sistema — o mesmo
lugar onde `--set` já é validado contra o `parameters_schema` congelado (§29.2).

### 29.8 T3.59: a regra `hours`, o envelope de duas regras e o bug de tipos pego antes da escrita

**Nenhuma migração.** A coluna já era JSONB e o corpo já era um mapa de
políticas (§29.2); esta tarefa preenche a segunda posição do mapa
(`hunter_strategy_worker.hours_gate`, ao lado de `regime_gate`) e move o
envelope para um módulo próprio (`hunter_strategy_worker.gate_policy`) — o
`code_ref` congelado de cada estratégia não muda, porque o portão é lido pelo
worker ao montar o `StrategyContext`, nunca pela estratégia (§29.1).

**A forma, com as duas regras:**

```json
{"regime": {"scope": "btc", "classifier_version": "regime_hourly_v1",
            "rule": "previous_closed_hour", "allow": ["SIDEWAYS"]},
 "hours":  {"utc": [[12, 15]]}}
```

`hours.utc` é uma lista de janelas meia-abertas `[start, end)`, em UTC — o
quadro `utc` é escrito no JSON, não suposto, para que um futuro `brt` seja uma
chave nova com a discussão de horário de verão dela própria. Uma janela pode
cruzar a meia-noite (`[22, 2]` cobre 22, 23, 0, 1). O parser
(`hours_gate.parse_hours_policy`) recusa: quadro diferente de `utc`, limite
fora de 0–24, valor não inteiro (`True` incluído, que é `int` em Python), lista
vazia, par que não é `[início, fim]`, janelas que se sobrepõem e qualquer
conjunto de janelas que cubra as 24 horas — um portão que nunca recusa não é
um portão.

**Toda regra declarada tem de passar — é `AND`, nunca `OR`.** Uma versão com
`regime` e `hours` decide na interseção das duas; declarar as duas é pedir a
interseção, não a união. Chave que o envelope não conhece (isto é, que não é
`regime` nem `hours`) é recusada, e um objeto vazio (`{}`) também — uma linha
em que a política foi esvaziada por acidente não vira "decide em qualquer
contexto" (§29.2). A ordem de avaliação (hora antes de regime, em
`hunter_strategy_worker.context`) é de custo, não de contrato: a janela de
horas não lê nada (nenhuma consulta, nenhum relógio), e recusar por ela poupa a
leitura indexada de `market_regimes` (§29.6) em toda barra fora da janela. A
consequência é de vocabulário, não de dado: uma barra que falharia nas duas
regras é reportada só como `hours_gate:HH` — a fatia de `regime_gate:*` de uma
versão com as duas regras não é comparável com a da mesma versão só com
regime. Está descrito também em `docs/PIPELINE.md` §4b item 10 e no cabeçalho
de `hours_gate.py`.

**A coluna recebe inteiros nativos; o envelope da decisão guarda strings — e as
duas coisas estão certas, por contratos diferentes.** `default_parameters`
passa por `canonical_json`, que emite todo número como string decimal
normalizada (o contrato de `params_format = 1`, para `Decimal("1.50")` e `1.5`
serem o mesmo parâmetro) — e é isso que `hunter_strategy_worker.variant` grava
para o **conjunto de parâmetros**. Uma janela de horas não é um parâmetro
(§29.1) e não pode passar pela mesma função: `[[12, 15]]` gravado por
`canonical_json` voltaria da coluna como `[["12", "15"]]`, o parser recusaria
(`start '12' is not an integer hour`) e a versão sairia do roster com
`policy_unreadable` — calada, atrás de um `/ready` verde, sem mensagem nenhuma
para o operador. Por isso `variant.py` separa as duas formas:

| função | usada para | forma dos números |
|---|---|---|
| `stored_policy()` | a **escrita** na coluna `eligibility_policy` | os tipos que a política tem — inteiros para `hours` |
| `canonical_policy()` | a **comparação** (dedup de variante, `--policy` que só troca o portão) | `canonical_json`, números como string — os dois lados da comparação passam pela mesma função, então o comportamento não muda |

Já o envelope de decisão gravado em `agent_signals.supporting_features`
(`provenance.hours_gate`) **guarda a hora como string** (`{"hour": "12",
"policy": {"utc": [["12", "15"]]}}`) — e isso é o contrato certo, não outro bug:
o envelope inteiro é serializado pela forma canônica (o z-score, o ATR e o
preço também são strings ali), e mudar só a regra `hours` quebraria essa
uniformidade. **Coluna = inteiros nativos** (senão o parser recusa);
**envelope de decisão = strings canônicas** (porque é essa a forma do
envelope). Round-trip provado em `services/strategy-worker/tests/test_hours_gate.py`.

**`--policy` não pode largar uma regra do pai em silêncio.**
`variant.resolve_policy` recusa quando o argumento novo não menciona uma regra
que o pai declara: `--policy hours=12-15` sobre um pai com portão de regime
substituiria o portão inteiro, e a filha decidiria em mais contexto que o pai
sem que isso apareça em lugar nenhum. A saída exige uma frase: repetir a regra
no argumento, `<portão>=none` para tirar só ela, ou `--policy none` para tirar
o portão inteiro. Largar um portão continua possível — só não em silêncio.

## 30. Uma fatia é uma janela **e** os mercados que ela visitou — M3 (`0018_replay_runs_slice_markets`)

Décima oitava revisão. **Uma coluna, um gatilho e uma chave trocada.** Nenhuma
tabela, nenhum enum, nenhum índice próprio, nenhuma partição, nenhum `GRANT`,
nenhuma política de RLS.

Ela fecha o CONCERN 1 da `.claude/state/notes-T3.62.md`. A `0013` (§25) fez o
recibo de um replay virar evidência durável e o chaveou em
`uq_replay_runs_slice (run_id, window_from, window_to)`. Essa chave nomeia uma
**janela**; a unidade que ela deveria nomear é a **fatia**, que é uma janela
*mais* os mercados sobre os quais ela foi despachada. A T3.62 mediu a diferença
com um desenho legítimo — *uma coorte por versão, quatro fatias de mercado
dentro de cada janela*, porque o `--stress` recebe uma coorte só e é ele que
produz o veredito:

| | o que aconteceu | o que `replay_runs` guardou |
|---|---|---|
| corridas | 32 fatias, 190 464 barras, 806 decisões | **8 linhas** |
| a `v6` | 16 mercados, 47 616 barras, 147 decisões | `mkts = 4, bars = 5760, signals = 11` |

**Nada falhou e nada logou acima de `info`.** `record_slice` insere com
`ON CONFLICT ... DO NOTHING`, então a segunda, a terceira e a quarta fatia de
mercado de uma janela pareciam *a primeira reexecutada* — a idempotência que
protege uma repetição estava comendo o trabalho vizinho. O recibo inteiro
sobreviveu só em `system_events` (retenção de 30 dias, §1.3) e num JSONL que
existe se alguém guardou o arquivo, isto é, exatamente nos dois lugares que a
`0013` existe porque **não** são duráveis (§25).

`0018_replay_runs_slice_markets` tem 30 caracteres; o teto de
`alembic_version.version_num` continua sendo 32 (§17.6) — é o id mais longo do
projeto e sobra por dois (§30.7). As listas desta revisão estão congeladas em
`ddl/replay_runs_slice_markets.py`, no padrão de
§15.6/§16.5/§17.6/§18.9/§19/§20/§21/§22/§24/§25/§29.

A frase que organiza tudo abaixo: **uma chave que não distingue duas coisas
diferentes não protege a segunda — ela apaga.**

### 30.1 A coluna, e por que um digest e não o próprio array

```
replay_runs  (+) markets_digest text NOT NULL
  CHECK markets_digest ~ '^[0-9a-f]{64}$'          -- ck_replay_runs_markets_digest_is_a_sha256
  CHECK array_position(markets, NULL::text) IS NULL -- ck_replay_runs_markets_has_no_unnamed_member
  UNIQUE (run_id, window_from, window_to, markets_digest)   -- uq_replay_runs_slice (mesmo nome)
```

`markets_digest` é o **sha256 (hex) da lista ordenada de `markets`**, unida por
`chr(10)`. Três alternativas foram consideradas e recusadas:

| Alternativa | Por que não |
|---|---|
| `UNIQUE (..., markets)` — o próprio `text[]` na chave | igualdade de array é **sensível à ordem**, e `markets` é gravado na ordem em que os mercados foram despachados (`run.py`). Os mesmos quatro mercados na outra ordem seriam uma segunda fatia de um trabalho que já tem recibo. E uma UNIQUE sobre array de tamanho livre é uma chave cujo tamanho ninguém limita |
| `market_count` na chave | duas fatias **diferentes** de quatro mercados colidiriam. É a coluna que a §25.2 já recusou como coluna, e ela não distingue o que precisa ser distinguido |
| uma coorte por fatia de mercado | não é decisão de schema, e a T3.62 explica por que ela custa caro: o `--stress` recebe **uma** coorte e é ele que dá o veredito; quatro coortes por versão dariam quatro estresses de 4 mercados e **nenhum** sobre os 16 |

**A chave nova é um superconjunto estrito da antiga**, e é isso que torna esta
revisão segura em banco povoado: acrescentar coluna a uma UNIQUE só pode
*afrouxá-la*, então nenhuma linha já gravada passa a colidir. Daí **não haver
guarda de upgrade sobre a chave**, e isso é afirmação, não esquecimento.

**O nome da constraint não muda.** `uq_replay_runs_slice` sempre significou "a
chave de uma fatia"; o que esta revisão corrige é *o que uma fatia é*. Toda
mensagem de erro, log e nota que já cita esse nome continua apontando para a
constraint certa.

### 30.2 O backfill deriva; não existe sentinela

`markets text[] NOT NULL` está na linha desde a `0013`, então **toda linha já
guardada carrega exatamente a entrada de que o digest é calculado**: o backfill
é derivação, não invenção — a fronteira que a `0002` fixou (fazer backfill do
que as colunas existentes *implicam*; recusar o que elas apenas sugerem, §16.2,
§17.7). A ordem é: `ADD COLUMN` anulável → `UPDATE` derivando cada linha →
`SET NOT NULL` → CHECKs.

**Nenhum `'legacy'`, e não por disciplina: por DDL.**
`ck_replay_runs_markets_digest_is_a_sha256` recusa `'legacy'`, `''` e `'none'`.
Se o digest não fosse derivável da própria linha, o brief desta tarefa mandava
usar a sentinela e declarar; ele é, e a sentinela não existe em lugar nenhum.
Medido num round trip real sobre tabela povoada
(`test_0018_derives_a_stored_receipt_instead_of_stamping_a_sentinel`): derrubar
a coluna e reaplicar a revisão devolve o mesmo digest **byte a byte**.

### 30.3 A mesma função escrita duas vezes, e o gatilho que compara as duas

| Metade | Onde | Quem usa |
|---|---|---|
| Python | `hunter_core.domain.digests.markets_digest` | o escritor (`ReplayRun.markets_digest`, `replay/ledger.py`) |
| SQL | `ddl/replay_runs_slice_markets.digest_sql` | o backfill e o gatilho, que rodam **dentro** do banco |

Cópia e nunca import, pela razão de sempre (`ddl/paper_geometry.py`: o contrato
do banco não pode seguir em silêncio uma edição posterior de uma constante
Python), e
`test_migrations.py::test_0018_the_python_digest_and_the_sql_expression_are_one_function`
compara as duas sobre as mesmas listas. Três detalhes são contrato, não
implementação:

- **`ORDER BY m COLLATE "C"`** — ordem de byte, que para UTF-8 é ordem de code
  point, que é o que o `sorted()` do Python dá. Ordenar pela colação padrão do
  banco faria o digest depender de `lc_collate`: a mesma lista de mercados
  hashearia diferente em dois clusters, e um recibo escrito por um pareceria
  trabalho novo para o outro;
- **`chr(10)` como separador** — `("a","bc")` e `("ab","c")` são dois conjuntos
  e não podem dividir um digest. Escrito como `chr(10)` para significar a mesma
  coisa no módulo Python, no corpo do gatilho e numa sessão `psql`;
- **`convert_to(..., 'UTF8')`** — o digest é sobre bytes, e quais bytes não fica
  por conta do encoding do servidor.

**Uma cópia que pode discordar da fonte é pior que nenhuma cópia** (§18.2, o
precedente é `portfolio_currency_anchor_matches_observation`). O digest é cópia
de algo que a própria linha já tem, então
`replay_runs_digest_names_the_markets` (`BEFORE INSERT OR UPDATE`) recalcula e:

- **preenche** quando o escritor mandou `NULL` — todo escritor anterior a esta
  revisão continua correto em vez de quebrar (as fixtures da API, um `INSERT` de
  operador), e nenhum recibo se perde por ordem de deploy. Preencher uma
  ausência não é sobrescrever um valor: é a doutrina de backfill da `0002`
  aplicada linha a linha;
- **recusa** quando o escritor mandou um digest que não é o de `NEW.markets`. Um
  digest errado não é erro cosmético aqui: duas fatias de mercado que dividam
  um digest errado voltam a colidir na chave, que é o defeito inteiro.

O escritor **manda** o digest (não deixa para o gatilho) exatamente para que as
duas metades sejam comparadas em todo insert, em vez de concordarem por
suposição.

### 30.4 `array_position(markets, NULL::text) IS NULL` — a única coisa sobre a qual o digest não consegue ser honesto

`array_to_string` **descarta** um membro `NULL`, então `{a, NULL}` e `{a}`
hashe­ariam igual: uma ambiguidade dentro de uma chave UNIQUE. O CHECK torna
isso irrepresentável daqui em diante e uma guarda de upgrade fica na frente
dele, contando os infratores e nomeando a exportação em vez de morrer dentro do
`ALTER TABLE` com uma violação que não nomeia saída (o argumento da `0016`,
§28.3). Em todo banco de hoje ela conta **zero**: o único escritor monta cada
chave como `f"{exchange}:{symbol}"`.

**Limite declarado:** uma chave de mercado que contivesse o próprio separador
tornaria dois conjuntos indistinguíveis. A metade Python recusa (`ValueError`);
a metade SQL **não consegue** — um CHECK não carrega subconsulta —, então ela
calcularia um digest para um valor que o único escritor não produz. Fica escrito
em vez de descoberto.

### 30.5 Guardas

**Guarda de upgrade:** uma só, a do §30.4. **Nenhuma sobre a chave**, e isso é
afirmação — a chave nova é superconjunto estrito da antiga (§30.1).

**O downgrade recusa** enquanto qualquer janela já guardar mais de uma fatia de
mercado (§17.7: reverter é permitido, perder evidência não é). A chave da `0013`
é **mais estreita**: um banco que já gravou o que esta revisão tornou gravável
não volta sem **apagar recibos de replays que de fato rodaram**. O Postgres
recusaria a constraint de qualquer forma; a guarda recusa **antes**, contando as
janelas e nomeando o `COPY`, em vez de morrer dentro do `ADD CONSTRAINT`.

| Guarda | Momento | O que se perderia |
|---|---|---|
| membro `NULL` em `markets` | upgrade | qual mercado o `NULL` era — nenhuma coluna que sobra diz, e o digest ficaria ambíguo dentro da chave |
| janela com duas fatias de mercado | downgrade | os recibos das fatias excedentes: a evidência que a `0013` existe para guardar |

**Derrubar a coluna não é guardado, e isso é decisão.** O digest é derivado de
`markets`, que fica; reaplicar a `0018` reproduz cada valor byte a byte. É a
diferença entre esta guarda e a da `0013` (§25.6): uma protege recibo, a outra
não protegeria nada. Nenhuma das duas apaga coisa alguma — contam, nomeiam e
param, com a instrução de exportar antes; o mesmo limite declarado do §18.9, do
§24.6 e do §25.6 (exportar não muda predicado nenhum, e o downgrade de um banco
que já replayou não é operação de rotina).

### 30.6 Grants, RLS, trava e pooler

**Nenhum `GRANT`, e é aritmética de ACL, não descuido.** A `0013` concedeu
`SELECT` de **tabela** ao `hunter_app` e `SELECT`/`INSERT` de **tabela** ao
`hunter_worker` (§25.4); um privilégio de tabela alcança coluna nova por
construção. O que **não** existe continua não existindo: nem `UPDATE` nem
`DELETE`, para nenhum dos dois — que é a §25.1 inteira, porque com `UPDATE` a
opção (b) (uma linha por corrida, acumulada) voltaria a ser possível e um recibo
passaria a ser editável pelo processo que o escreveu. Medido como o papel, não
perguntado ao catálogo:
`test_0018_leaves_replay_runs_global_and_append_only`.

**Nenhuma política de RLS, e a ausência é asserida.** `replay_runs` continua
**global** (§1.1, §25.5): sem `organization_id`, portanto sem política. O
isolamento entre organizações aqui é a *ausência de dado de tenant*, não uma
política que alguém possa esquecer — e o mesmo teste conta zero em
`information_schema.columns` (para `organization_id`) e zero em `pg_policy`,
porque "não precisa de política" e "alguém esqueceu a política" são
indistinguíveis de fora. Uma coluna de tenant aparecendo aqui um dia passa a
exigir RLS, e o teste é o que obriga a conversa.

**Trava.** `ADD COLUMN` anulável não reescreve a tabela (PG 11+); o `UPDATE` de
backfill e a troca de constraint tomam `ACCESS EXCLUSIVE` pelo tempo de uma
construção de índice sobre uma tabela de dezenas de linhas por dia e sem
retenção (§1.3) — a mesma ordem de grandeza da janela que a `0012` abre (§24.7),
não uma classe nova de risco. O único escritor é o CLI de replay, que não roda
durante um deploy.

**Pooler.** Nada aqui depende de estado de sessão: um `ALTER TABLE`, um `UPDATE`,
um gatilho que lê só `NEW` e uma constraint trocada. Sem prepared statement de
sessão, sem `LISTEN`/`NOTIFY`, sem advisory lock de sessão.

### 30.7 A lista de revisões, e o teto de 32 caracteres vira teste

`alembic_version.version_num` é `VARCHAR(32)` (§17.6), e o projeto aprendeu isso
caro: `0005_feature_baselines_lock_grant` (33) **rodou a revisão inteira** e só
então falhou no `UPDATE alembic_version`. Desde então cada seção declara o
tamanho do próprio id — `0016` tem 28, `0017` tem 23, esta tem 30 —, e uma
declaração em prosa é uma declaração que ninguém executa.

A convenção passa a ter uma verificação:
`test_migrations.py::test_every_revision_id_fits_the_alembic_version_column`
percorre `infra/migrations/versions/` e exige, de cada arquivo:

1. que ele **declare** um `revision: str = "..."`;
2. que o id tenha **≤ 32 caracteres**;
3. que o id seja **o próprio nome do arquivo** — um id que discorde do nome é um
   id que `pytest -k <id>` não seleciona e uma história que ninguém lê num `ls`;
4. que dois arquivos não declarem o mesmo id;
5. que o **último** arquivo em ordem seja o `HEAD_REVISION` que o módulo afirma —
   que é o mesmo papel que aquela constante já cumpre desde a `0002` ("o único
   lugar que percebe um arquivo de revisão que nunca rodou").

A lista viva, portanto, é o diretório; este documento é a *descrição* dela, uma
seção por revisão, e cada seção continua congelada no que a sua revisão fez —
anotada quando uma posterior a corrige (§28.1, e o bloco novo no §25.1), nunca
reescrita.

### 30.8 Desvios em relação ao brief, declarados

| Brief | O que foi feito, e por quê |
|---|---|
| "backfill com sentinela `'legacy'` se a lista não estiver persistida — e diga isso" | **está persistida**: `markets text[] NOT NULL` desde a `0013`. O backfill deriva o digest em SQL da própria linha e a sentinela não existe; um CHECK a torna irrepresentável (§30.2) |
| "o escritor em `replay/run.py` calcula e insere o digest" | `run.py` não muda: o digest é **propriedade** de `ReplayRun` (`replay/ledger.py`), derivada de `markets`, que é o que `run.py` fornece. Um campo de construtor poderia receber um digest que não descreve os mercados — a segunda verdade que a §19.3 recusa sobre `applied_attempts` —, e é justamente um digest errado que faz duas fatias colidirem de novo |
| (o brief não pede gatilho) | `replay_runs_digest_names_the_markets` entrou (§30.3). Sem ele, "o digest está certo" seria promessa do escritor; com ele, é propriedade do banco — e é o que mantém todo escritor anterior à revisão funcionando em vez de quebrado |
| (o brief não pede CHECK sobre `markets`) | `ck_replay_runs_markets_has_no_unnamed_member` entrou, com guarda de upgrade (§30.4): sem ele o digest não é total no domínio da coluna, e a ambiguidade fica **dentro** de uma chave UNIQUE |

### 30.9 O que as tarefas vizinhas têm de saber

| Onde | O que muda |
|---|---|
| `hunter_strategy_worker/replay/ledger.py` | `ReplayRun.markets_digest` (propriedade), a coluna no `INSERT` e `markets_digest` no alvo do `ON CONFLICT`. `to_jsonable()` passa a carregar o digest, então o JSONL e o `system_events` nomeiam a mesma fatia que a linha — o que torna possível casar as três metades do recibo |
| `apps/api/**` (placar, `GET /lab/shadow/replays`) | **nada a mudar**, e uma consequência a esperar: uma corrida de quatro fatias de mercado passa a aparecer como **quatro** linhas onde antes aparecia como uma. A listagem já agrupa por `run_id` e soma `bars_evaluated` (T3.25), então o total fica *certo* onde antes estava dividido por quatro |
| quem lê `replay_runs` em SQL de pesquisa | somar `bars_evaluated` por `run_id` continua reconstruindo a corrida; `signals`/`outcomes_resolved`/`outcomes_open` continuam sendo **da coorte inteira** no instante em que a fatia terminou (§25.2), e agora há quatro linhas com esse total corrente por janela em vez de uma. **Somá-los multiplica a população** — a armadilha do denominador que a §25.2 já declarava, um pouco mais fácil de cair agora |
| as 32 corridas da T3.62 | **não voltam.** Os 24 recibos perdidos não são reconstruíveis a partir de `replay_runs`; o que existe deles está em `system_events` (`replay_engine`/`replay_run_finished`, 32 linhas, com `market_count` e a lista de mercados no `data`) até a retenção de 30 dias os apagar, e nos 32 JSONL. Quem quiser o recibo durável daquela família precisa **refazer** as corridas depois desta revisão — e a `notes-T3.62.md` §8 já pede o refazimento em 70 dias por outra razão |

## 31. A amplitude do universo vira série — M3 (`0019_market_breadth`)

`market_breadth` guarda uma leitura de `breadth_5m` por minuto fechado por exchange: a fração das perpétuas monitoradas cuja `close` caiu na janela que termina em `end_time`, com `covered`/`universe_size` ao lado. **Global e sem RLS** (§1.1) — o universo é da exchange, não de uma organização —, e **imutável por privilégio, não por gatilho**: `SELECT` para `hunter_app`, `SELECT`/`INSERT` para `hunter_worker`, nada mais para nenhum dos dois, e nada para `hunter_runtime`, que chega pelos dois papéis via `SET ROLE` (§27.1). Não existe `UPDATE` legal, então o gatilho que `market_betas` precisou (§18.6) aqui não teria o que proteger. O portão da T3.77 lê por igualdade exata (`end_time = source_bar_close`) e o replay lê a mesma linha — é isso que faz a decisão viva e a simulada compararem o mesmo número em vez de dois folds de tabelas diferentes.

| Decisão | Como está escrita |
|---|---|
| idempotência | `uq_market_breadth_reading (exchange_id, breadth_version, window_minutes, end_time)` mais `ON CONFLICT ... DO NOTHING RETURNING id`. Dois produtores no mesmo minuto: o segundo não escreve **e sabe** que não escreveu |
| linha inutilizável | `value IS NULL` com `reason`, sob `usable = (reason IS NULL)`. "O universo não respondeu" é fato daquele minuto e sobrevive; "ninguém rodou" é a **ausência** da linha, e são dois problemas de operação diferentes |
| **sem reparo** | não há regra de conserto: um minuto gravado como `insufficient_coverage` está **encerrado** naquele `breadth_version`, inclusive depois de um backfill de velas — refazê-lo é uma versão nova da série, nunca uma reescrita. Consequência operacional: uma recusa **é** uma escrita, e a linha resultante é lápide permanente |
| o backfill pula o que o relatório reprovou | por isso `infra/scripts/backfill_breadth.py --apply` dobra **só** os minutos dos dias cuja cobertura densa alcança `MIN_COVERAGE`; os demais não são tentados. Noventa dias com onze aproveitáveis seriam ~114 mil lápides compradas para ganhar ~15 mil leituras. `--include-unusable` dobra a janela inteira mesmo assim, para o operador que quer a ausência registrada como fato — escolha feita diante do relatório, nunca padrão. O plano é puro e vive em `infra/scripts/breadth_windows.py` (`days_above_the_floor`, `fold_windows`), separado do executor pelo mesmo motivo que `partition_plan` (§1.3). Fronteira declarada: os cinco primeiros minutos de um dia mantido dobram velas do dia anterior, então, se aquele dia foi pulado, esses poucos minutos ainda podem cair como `insufficient_coverage` — lápides **medidas**, não adivinhadas |
| **não particionada, e a conta** | 525 600 linhas/ano **por (exchange, `breadth_version`, `window_minutes`)** — uma série numa venue é 53 % do limiar de 1 M/ano; duas venues, ou uma segunda janela, cruzam o limiar. A leitura do portão não mudaria com `RANGE (end_time)`, mas a **troca não é indolor**: a PK é `id` sozinha e a §15.2 exige a coluna de partição na PK, então particionar é uma revisão que **reconstrói** a tabela, não um `ATTACH` |
| **um índice só** | o índice da UNIQUE é o único que a tabela carrega. O portão faz quatro igualdades sobre exatamente as quatro colunas de `uq_market_breadth_reading`, na ordem dela, e a checagem `RESTRICT` da FK usa `exchange_id`, que é a coluna líder — nada mais tem leitor. A primeira versão da `0019` (antes de sair de container de teste) tinha ainda `ix_market_breadth_lookup`, cópia coluna a coluna da UNIQUE, e `ix_market_breadth_exchange_id`, prefixo dela: três btrees mantidos num caminho de escrita de uma linha por minuto onde um responde tudo |
| FK indexada pelo prefixo | o modelo **não** declara `index=True` em `exchange_id`. A §1 exige "todo FK indexado" e um composto que *começa* pela coluna da FK **é** esse índice — a mesma regra que os compostos liderados por `organization_id` já expressam nas tabelas de tenant. Registrado aqui porque "não precisava" e "esqueceram" se parecem de fora |
| nomes de constraint | `pk_market_breadth`, `fk_market_breadth_exchange_id_exchanges` e `uq_market_breadth_reading` são escritos à mão no DDL literal da `0019`, iguais aos que `hunter_core.db.base.NAMING_CONVENTION` dá ao modelo. Sem isso o Postgres cunharia `market_breadth_pkey`/`market_breadth_exchange_id_fkey`, o `alembic check` **não** notaria (ele não compara nomes de constraint) e a revisão que um dia particionar esta tabela — que precisa de `DROP CONSTRAINT` pelo nome para pôr `end_time` na PK (§15.2) — seria escrita contra um nome que não existe |
| provas | imutabilidade por privilégio é medida *como o papel*, não perguntada ao catálogo: `packages/core/tests/integration/test_schema_privileges.py` prova que `hunter_worker` insere e apanha `permission denied` em `UPDATE`/`DELETE`, que `hunter_app` só lê, que os dois conjuntos de privilégios são exatamente `{SELECT}` e `{SELECT, INSERT}`, e que `hunter_runtime` não alcança a tabela sem `SET ROLE` (`NOINHERIT`, §27.1). A recusa do downgrade com uma leitura na mesa, o *round trip* com a tabela vazia (incluindo os grants que voltam), os três nomes de constraint e o plano do portão estão em `test_migrations.py` (`-k 0019`) |

**O plano do portão, medido uma vez.** Com `enable_seqscan = off` (a tabela está
vazia no banco de teste; a pergunta é se *existe* índice capaz, que é uma
propriedade do schema e não da cardinalidade do momento), a consulta de
`hunter_strategy_worker.breadth_gate._LOOKUP` sai assim:

```
Nested Loop  (cost=0.30..20.96 rows=1 width=79)
  Join Filter: (b.exchange_id = e.id)
  ->  Index Scan using uq_market_breadth_reading on market_breadth b
        Index Cond: ((breadth_version = 'breadth_v1'::text)
                 AND (window_minutes = '5'::smallint)
                 AND (end_time = '2026-09-09 22:08:00+00'::timestamptz))
  ->  Index Scan using uq_exchanges_code on exchanges e
        Index Cond: (code = 'binance'::text)
```

A sonda cai no índice da UNIQUE, que é o que a queda dos dois redundantes tinha
de preservar. Registrado com honestidade: numa tabela vazia o planejador começa
por `market_breadth` e deixa `exchange_id` como *join filter*, isto é, usa três
das quatro colunas como `Index Cond`; com estatísticas reais ele resolve a venue
primeiro (uma linha em `exchanges`) e as quatro viram condição de índice. Em
nenhum dos dois casos há `Seq Scan`, e é por isso que a asserção do teste é sobre
o **nome do índice**, não sobre a forma do *join*.

## 33. O radar de memecoins vira schema — M4 (`0021_meme_radar`)

Vigésima primeira revisão. **Cinco tabelas** (três delas `RANGE` mensal), seis
índices, **uma visão**, dois gatilhos e grants por subtração. Nenhum enum,
nenhuma política de RLS, nenhuma coluna acrescentada a tabela existente.

> **§32 é da `0020_market_dispersion`** (T3.90, em voo enquanto isto é escrito).
> O número está reservado pelo docstring daquela revisão; esta seção pula para
> 33 em vez de disputar a numeração.

Ela entrega o T4.2 sobre o adapter da T4.1
(`packages/exchange-adapters/hunter_exchanges/pumpfun/`), o plano
`docs/plans/T4-MEME-RADAR.md` e as correções da Astra
(`.claude/state/notes-A4.1b-mayhem.md`). O contrato de leitura foi congelado
**antes** do código, em `.claude/state/notes-T4.2.md` §contrato, para a T4.3
(API + web) construir em paralelo.

A frase que organiza tudo abaixo: **ausência de fonte não é zero, e o schema é
onde isso deixa de depender de quem escreve a consulta.**

### 33.1 Global, sem RLS — e a ausência é asserida

As cinco tabelas são **globais** (§1.1): um token on-chain pertence à cadeia, não
a uma organização. Sem `organization_id`, portanto sem política — a forma que
`markets`, `market_regimes`, `market_breadth` e `market_dispersion` já têm.

A ausência é **provada**, não suposta, no padrão que a §25.5 fixou para
`replay_runs`: `test_migrations.py::test_0021_keeps_the_meme_tables_global_and_free_of_policies`
e `test_schema_privileges.py::test_the_meme_tables_are_global_and_carry_no_tenant_column`
contam zero em `information_schema.columns` (para `organization_id`) e zero em
`pg_policy`. "Não precisa de política" e "alguém esqueceu a política" são
indistinguíveis de fora, e uma coluna de tenant aparecendo aqui um dia passa a
exigir RLS — o teste é o que obriga a conversa.

### 33.2 As cinco tabelas

```
meme_tokens                                  (global, não particionada)
  mint text PK
  name, symbol, uri, creator                 -- todos ANULÁVEIS: NULL = não observado
  created_at, bonding_curve
  initial_virtual_sol_reserves, initial_virtual_token_reserves NUMERIC(28,10)
  initial_real_token_reserves NUMERIC(28,10) -- o denominador do progresso
  total_supply NUMERIC(28,10), pool
  mayhem_enabled boolean NULL                -- NULL = desconhecido, nunca DEFAULT false
  mayhem_mode, mayhem_state                  -- dois eixos, não um
  completed_at, migrated_at, migrated_pool   -- dois eventos, não um
  first_seen_source, first_seen_at, last_seen_at, updated_at  (NOT NULL)
  INDEX (created_at), INDEX (first_seen_at)
  CHECKs: rótulos de mayhem; `mayhem_enabled IS FALSE` proíbe `mayhem_state`;
          `migrated_at` exige `migrated_pool`; identidade observada não é string vazia

meme_curve_snapshots            PARTITION BY RANGE (observed_at), mensal
  PK (observed_at, mint, source)
  received_at, virtual_*/real_* reserves, total_supply, complete,
  mcap_sol NUMERIC(28,10) GENERATED ALWAYS AS
      ((virtual_sol_reserves / NULLIF(virtual_token_reserves,0)) * total_supply) STORED,
  slot, commitment, mayhem_enabled/state/mode
  INDEX (mint, observed_at)

meme_trades                     PARTITION BY RANGE (block_time), mensal
  PK (block_time, signature, event_index)
  mint, slot, received_at, outer_ix_index, inner_ix_index, trader, side,
  sol_lamports bigint, token_amount, price, quote_mint, token_decimals,
  commitment, is_mayhem_agent boolean NULL, source
  INDEX (mint, block_time)

meme_features_1m                PARTITION BY RANGE (end_time), mensal
  PK (end_time, mint, features_version)
  curve_progress_pct + progress_reason, mcap_sol + curve_reason,
  unique_buyers + reason, buy_sell_ratio + reason,
  top10_share + reason, creator_sold + reason,
  age_minutes, coverage NOT NULL, snapshot_observed_at, snapshot_source, computed_at
  INDEX (mint, end_time)
  seis CHECKs bicondicionais: valor nulo ⟺ motivo não nulo

meme_ingest_gaps                             (global, append-only)
  id uuid7 PK, stream, mint NULL, gap_start, gap_end, detected_at, reason,
  generation, detail jsonb
  INDEX (stream, gap_start)
```

### 33.3 Três particionadas, com a conta escrita

O limiar do §1.3 é **1 M linhas/ano** (a mesma régua que a §31 aplica a
`market_breadth`):

| tabela | teto | por quê |
|---|---|---|
| `meme_curve_snapshots` | 60 linhas/min ≈ **31 M/ano** | o orçamento REST grátis **é** 60 req/60 s, então esse é o teto físico do poller |
| `meme_features_1m` | 120 mints × 1 440 min ≈ **63 M/ano** | uma linha por mint rastreado por minuto fechado, no teto padrão |
| `meme_trades` | ilimitado por transação | sem produtor hoje, e o §15.2 faz de "particionar depois" uma **reconstrução** da tabela |
| `meme_tokens` | ~40 mil/dia, podada por linha | a chave é o mint, não um instante: não há partição mensal a criar |
| `meme_ingest_gaps` | uma linha por buraco | dezenas por dia no pior caso |

**`meme_features_1m` particionada é desvio declarado em relação ao brief**, que a
deixava de fora: com 63 M linhas/ano ela seria a maior tabela não particionada do
schema por duas ordens de grandeza, e a retenção nela seria um `DELETE` de dezenas
de milhões de linhas em vez de um `DROP` — exatamente a troca que o §1.3 faz por
`candles`.

Toda coluna de partição é a **primeira da PK** (§15.2), e em `meme_features_1m`
ela é também a ordem de leitura do Radar: "o último minuto fechado em todos os
mints" é varredura por prefixo, nunca um `sort`.

As doze partições iniciais (2026-09 a 2026-12) são fixas pelo mesmo motivo do
§15.5 — uma migração reaplicada no futuro tem de produzir o mesmo schema — e são
criadas já endurecidas (`REVOKE ALL` nos dois papéis; não há metade de tenant a
instalar, porque as pais são globais). Daí em diante quem cria é
`infra/scripts/create_partitions.py`, que **já as planeja sem uma linha nova**:
ele deriva os pais dos modelos (`monthly_partition_parents()`).

### 33.4 Retenção: 90 dias, e a mesma janela para graduado e não graduado

`MEME_RETENTION_DAYS` (`Settings.meme_retention_days`, padrão 90) entra em
`infra/scripts/partition_retention.py` para os **três** pais particionados, que
são podados por `DROP` de mês inteiro — razão pela qual nenhum dos dois papéis tem
`DELETE` neles.

A janela é **idêntica para mints graduados e não graduados**, e isso é decisão
registrada (T4-MEME-RADAR.md §8, decisão 2): a proposta original — guardar tudo 30
dias e depois só os `complete = true` — foi **rejeitada pela revisão da Astra**,
porque selecionar por sucesso depois do fato apaga os controles e cria
sobrevivência seletiva no próprio dado histórico, contaminando qualquer análise
futura sobre o que separa um rug de uma graduação.

`meme_tokens` é a exceção estrutural: a chave é o mint, então não há partição a
derrubar. Ela é podada **linha a linha**, em lotes, pelo meme-worker — e por isso
é a única tabela desta revisão em que `hunter_worker` tem `DELETE` (§33.6).

### 33.5 O que é NULL com motivo, e por que isso é o produto

Quatro colunas de `meme_features_1m` são **NULL com motivo em toda linha que esta
fatia escreve**, e isso fecha o MUST-FIX 1 da Astra — "ausência de feed lida como
'ninguém comprou' ou 'o dev não vendeu'" era o erro mais grave do desenho
original:

| coluna | motivo hoje | o que falta |
|---|---|---|
| `unique_buyers`, `buy_sell_ratio` | `no_trade_feed` | o canal de trades do PumpPortal é pago (0,01 SOL/10 000 eventos) e o decodificador on-chain é a T4.2b |
| `top10_share`, `creator_sold` | `no_holders_reader` | ninguém lê holders ainda; quando ler, tem de agregar **por owner** e excluir a curva, o pool e endereços de burn, senão o próprio programa aparece como top holder |

Os seis CHECKs bicondicionais (`valor IS NULL` ⟺ `motivo IS NOT NULL`) são o
precedente do `no_entry_reason` (§16.2) seis vezes: não existe linha com valor
ausente e sem motivo, nem linha com valor **e** motivo.

**`curve_reason` e `progress_reason` são dois, e a separação é uma correção feita
ao escrever o produtor** (`.claude/state/notes-T4.2.md` §contrato, emenda 1). Com
um motivo só, um mint cujo snapshot chegou mas cujo
`initial_real_token_reserves` nunca foi observado tinha **mcap conhecido** e
**progresso desconhecido** — e a bicondicional única obrigaria o coletor a jogar
fora um número real para caber no CHECK. Duas ausências com duas causas ganham
dois motivos.

`age_minutes` é anulável **sem** coluna de motivo, e isso é decisão: a única causa
é `meme_tokens.created_at` desconhecido, e a linha do token já diz isso — uma
sexta coluna de motivo seria a segunda verdade do §19.3.

Vocabulário congelado (a T4.3 renderiza estes e só estes):
`no_trade_feed`, `no_holders_reader`, `denominator_unknown`, `not_polled`,
`rate_limited`, `insufficient_coverage`, `unsupported_quote`.

### 33.6 Grants: leitura para a API, acréscimo para o motor, e uma exceção

| Classe (congelada em `ddl/meme_radar.py`) | Papel | Privilégios | Tabelas |
|---|---|---|---|
| `MEME_APP_READ_ONLY_TABLES` | `hunter_app` | `SELECT` | as cinco |
| `MEME_WORKER_APPEND_TABLES` | `hunter_worker` | `SELECT`/`INSERT` | snapshots, trades, features, gaps |
| `MEME_WORKER_UPSERT_TABLES` | `hunter_worker` | `SELECT`/`INSERT`/`UPDATE`/`DELETE` | `meme_tokens` |

As quatro append-only são a forma de `replay_runs`/`market_breadth`/
`market_dispersion` (§25.4, §31): **imutabilidade por privilégio, não por
gatilho**, porque não existe `UPDATE` legal nelas — um segundo olhar no mesmo
instante da mesma fonte é a *mesma* linha (a PK diz isso).

`meme_tokens` é a única exceção, e as duas metades dela têm dono:

- **`UPDATE`** porque o ciclo de vida de um token de fato se move depois da
  descoberta (conclusão, migração, o estado do agente Mayhem). O que impede isso
  de virar reescrita de história **não é o grant, é o gatilho**:
  `meme_tokens_identity_is_written_once` recusa alterar qualquer identidade ou
  carimbo já conhecido, **para todo papel, dono incluído** — a fechadura mais
  forte das duas, o argumento do `feature_baselines_immutable` (§17.2). `NULL` →
  valor é permitido **uma vez**;
- **`DELETE`** porque esta é a tabela que a retenção não poda por partição, e ~40
  mil mints novos por dia não é algo que alguém guarde para sempre. O precedente é
  `ANALYSIS_WORKER_APPEND_TABLES` (§17.6), e como lá a exclusão é **declarada**:
  `meme_tokens_retention_is_declared` recusa todo `DELETE` sem
  `SET LOCAL app.meme_retention = 'on'`. O marcador é **isolamento, não
  autorização** (a correção do §18.8: um `SET LOCAL` que qualquer um escreve não
  autentica ninguém) — o que ele compra é que apagar histórico de descoberta seja
  um ato, não um acidente.

Nenhuma classe nova e nenhuma tabela reclassificada:
`test_schema_privileges.py::test_the_grant_lists_cover_every_table_exactly_once`
une esta lista às anteriores e a partição do schema continua exata. Provado **como
o papel**, não perguntado ao catálogo:
`test_the_worker_appends_a_meme_observation_and_can_never_edit_it` e
`test_the_api_role_reads_the_meme_radar_and_writes_none_of_it`.

### 33.7 `mcap_sol` é gerado pelo banco, e o `NULLIF` é o §15.8 intacto

```sql
mcap_sol numeric(28,10) GENERATED ALWAYS AS
  ((virtual_sol_reserves / NULLIF(virtual_token_reserves, 0)) * total_supply) STORED
```

Nenhum produtor escreve essa coluna. Uma cópia calculada pelo escritor poderia
discordar das reservas ao lado dela, e "uma cópia que pode discordar da fonte é
pior que nenhuma cópia" (§18.2, o precedente é
`portfolio_currency_anchor_matches_observation`).

O `NULLIF` é o que mantém a regra do §15.8 (tabelas de market data não levam CHECK
de domínio, porque "um feed emite ocasionalmente um zero, e um CHECK ali
transformaria um dado estranho em falha de ingestão"): uma divisão crua faria
**pior** que um CHECK — levantaria `division by zero` dentro do `INSERT`. Reserva
zero produz `mcap_sol NULL` e a linha entra.
`test_0021_generates_the_market_cap_and_a_zero_reserve_is_not_an_outage` mede as
duas metades.

E o número é **sempre teórico** (§4 do plano): preço marginal × oferta, nunca o
que uma venda realizaria — a curva desliza contra o próprio vendedor.

### 33.8 `meme_trades` nasce sem produtor, de propósito

O canal de trades do PumpPortal é pago e o decodificador on-chain é a T4.2b. A
tabela existe agora para o schema ficar inteiro e para as quatro colunas
dependentes poderem ser NULL **com motivo** em vez de silenciosamente zero.

A PK é `(block_time, signature, event_index)`, e o `event_index` é o MUST-FIX 2 da
Astra: chaveado só em `(signature, ts)`, **dois trades dentro da mesma transação
eram uma linha** e o segundo sumia no `ON CONFLICT DO NOTHING` — o mesmo silêncio
que custou 24 recibos ao replay da T3.62 (§30). `outer_ix_index`/`inner_ix_index`
ficam ao lado como procedência; a *chave* é um inteiro só porque um CPI e o log do
mesmo fill contam uma vez (A4.1b §6).

`is_mayhem_agent` é `boolean NULL`: `NULL` = atribuição incompleta, `false`
**só** depois de atribuir a operação a outro trader. A A4.1b §5.2 mediu uma compra
real do agente com `signer: false`, vinda de lookup table — um filtro por fee payer
a classificaria como orgânica. As três métricas orgânicas só podem ser calculadas
sobre `is_mayhem_agent IS FALSE`; um `NULL` é cobertura pendente, nunca um trade
orgânico.

### 33.9 A visão que a API lê

```sql
CREATE VIEW meme_radar_features_v1 AS
SELECT f.*, t.name, t.symbol, t.creator, t.created_at AS token_created_at, t.pool,
       t.mayhem_enabled, t.mayhem_mode, t.mayhem_state, t.completed_at,
       t.migrated_at, t.migrated_pool, t.first_seen_source, t.last_seen_at
FROM meme_features_1m f JOIN meme_tokens t ON t.mint = f.mint;
```

(a lista real de colunas é explícita em `ddl/meme_radar.py`; `f.*` aqui é
abreviação de leitura). `SELECT` para os dois papéis.

A visão **não filtra tempo nem ordena**, e isso é decisão: quem pagina é o
chamador, e os predicados descem para a partição do mês (`end_time`) ou para a PK
(`mint`). Uma visão que embutisse `max(end_time)` viraria varredura a cada
requisição — por isso "o último minuto" é parâmetro da API, não mágica da visão.

### 33.10 Guardas

**Não há guarda de upgrade, e isso é afirmação** (§19.5, §20.5, §21.4, §24.6,
§25.6, §30.5): a revisão cria tabelas que não existiam, então não há linha
guardada que ela possa tornar irrepresentável.

**O downgrade recusa** enquanto qualquer uma das cinco tiver linha (§17.7), cada
uma com o seu motivo nomeado:

| Guarda | O que se perderia |
|---|---|
| `meme_tokens` | o universo de criações contra o qual toda taxa de graduação e de rug é contada — e ele **não é recomputável**: o feed do PumpPortal é efêmero e o espelho REST só lista o que é recente |
| `meme_curve_snapshots` | ninguém serve o estado que uma curva teve num instante passado; estas linhas são a única cópia |
| `meme_features_1m` | os snapshots de que saíram expiram na mesma janela de 90 dias, então o fold não é reproduzível depois disso |
| `meme_trades` | trades decodificados com a atribuição de agente por operação |
| `meme_ingest_gaps` | uma janela em que ninguém estava ouvindo não é redescobrível depois, e perdê-la transforma um buraco conhecido em continuidade aparente |

Nenhuma apaga nada: contam, nomeiam e param, com a instrução de exportar antes —
o mesmo limite declarado do §18.9, §24.6, §25.6 e §30.5. Em todo banco de hoje as
cinco contam zero, que é exatamente por que o round trip passa sem exportar nada.

### 33.11 Trava, pooler e orçamento de nome

**Trava.** `CREATE TABLE` não toma trava em relação que ainda não existe, os
`GRANT` travam só o catálogo (a medição da `0005`, §15.6) e as doze partições são
criadas vazias. Esta revisão **não abre janela de manutenção**.

**Pooler.** Nada depende de estado de sessão: cinco `CREATE TABLE`, seis
`CREATE INDEX`, uma `CREATE VIEW`, doze partições, dois gatilhos e os grants. Sem
prepared statement de sessão, sem `LISTEN`/`NOTIFY`, sem advisory lock de sessão —
o único GUC envolvido, `app.meme_retention`, é escrito com `SET LOCAL` e lido com
`NULLIF(current_setting(..., true), '')`, exatamente como `app.current_org`
(§15.4).

`0021_meme_radar` tem 15 caracteres; o teto de `alembic_version.version_num`
continua sendo 32 (§17.6), e desde a §30.7 isso é teste e não prosa.

### 33.12 O que as tarefas vizinhas têm de saber

| Onde | O que muda |
|---|---|
| T4.3 (`apps/**`) | o contrato está congelado em `.claude/state/notes-T4.2.md` §contrato: as cinco tabelas, a visão, o vocabulário de motivos e o que **não** se pode assumir (somar volume, contar compradores ou afirmar "o dev não vendeu" — as quatro colunas são NULL com motivo hoje **e em toda linha**) |
| `services/meme-worker/**` | o único escritor. Consome o WS, respeita o orçamento de 60/60 s, reconcilia o top-K por mcap no RPC, dobra o minuto e poda `meme_tokens` atrás do marcador |
| `infra/scripts/create_partitions.py` / `prune_partitions.py` | **nada a mudar em código**: os dois derivam os pais dos modelos; `partition_retention.py` ganhou as três linhas de política |
| `packages/exchange-adapters/**` | nada a mudar. Uma necessidade futura, registrada: o `NormalizedMemeTrade` entrega SOL em unidade humana e `meme_trades.sol_lamports` é inteiro de unidade-base — a conversão (×10⁹, exata, porque SOL tem 9 casas) é do produtor da T4.2b |
| `packages/risk-core/**`, `services/execution-worker/**` | **nada, e por construção**: nenhuma tabela desta revisão é alcançável por caminho de execução, e `hunter_app` tem `SELECT` e nada mais nas cinco |


## 34. O Lab meme contínuo vira schema — M4 (`0022_meme_lab`)

Vigésima segunda revisão. **Quatro tabelas**, sete índices, **duas vistas**, uma
semente de dois conjuntos de regras e grants por subtração. Nenhum enum, nenhuma
política de RLS, nenhuma partição, nenhuma coluna acrescentada a tabela existente,
nada tocado na `0021`.

Ela entrega o T4.6 sobre o armazenamento da T4.2 (`0021_meme_radar`), o simulador
de papel da T4.5 (`hunter_indicators.meme`) e o contrato
`.claude/state/contrato-T4.6-T4.7-mesa-meme.md`, congelado em 12/09 04:25 BRT para
que a Mesa do operador (T4.7, `apps/**`) e o laço (T4.6, `services/meme-worker/`)
fossem construídos em paralelo. Todo desvio do contrato é uma linha em "Emendas"
dele — treze da T4.6, nenhuma reescrita.

A frase que organiza tudo abaixo: **quem escreve o quê é privilégio, não promessa
— e toda aposta é papel por CHECK, não por convenção.**

### 34.1 Global, sem RLS — e a ausência é asserida

As quatro tabelas são **globais** (§1.1), como as cinco da `0021`: uma aposta de
papel numa curva on-chain pertence ao Lab, não a uma organização. Sem
`organization_id`, portanto sem política. Os dois testes `LIKE 'meme%'` da §33.1
(`test_0021_keeps_the_meme_tables_global_and_free_of_policies`,
`test_the_meme_tables_are_global_and_carry_no_tenant_column`) já contam estas
quatro — uma coluna de tenant aparecendo aqui vira conversa, não buraco.

### 34.2 As quatro tabelas

```
meme_rule_sets                               (um conjunto de regras congelado)
  id uuid PK, name, version                  -- UNIQUE (name, version)
  kind ∈ {research_only, operator}           -- o laço aprova sozinho | espera o aval da mesa
  params jsonb                               -- porta, saídas, tamanho, tetos; decimais como STRING
  code_ref, exp_ref (NULL só para operator), status ∈ {active, retired}, created_at, retired_at
  CHECKs: rótulos; retired ⟺ retired_at; research nomeia o EXP-M<n>; identidade não vazia

meme_proposals                               (uma intenção de compra)
  id uuid PK, mint, rule_set_id FK, origin ∈ {rules, operator}
  status ∈ {proposed, approved, rejected, expired, filled, unfilled}
  proposed_at, expires_at (> proposed_at), features_end_time (obrigatório para rules)
  quote jsonb, reasons jsonb, suggested jsonb, decision jsonb
  decided_by, decided_at, bet_id FK (use_alter), refusal
  INDEX (status, proposed_at), INDEX (mint, proposed_at)
  UNIQUE (rule_set_id, mint, features_end_time) WHERE origin = 'rules'   -- idempotência do laço
  CHECKs: decided_at ⟺ decided_by; estado decidido carrega decisão;
          filled ⟺ bet_id; unfilled ⟺ refusal

meme_paper_bets                              (a aposta, uma linha por entrada)
  id uuid PK, proposal_id FK UNIQUE, rule_set_id FK, mint
  mode text CHECK (mode = 'paper')           -- a T4.8 acrescenta 'live' com revisão própria
  status ∈ {open, closed}, entry_at, entry jsonb, initial_risk_sol (= sol_spent, §5 da doutrina)
  params jsonb (os quatro números efetivos + piso), exit_intent jsonb (a regra que disparou,
  esperando a fotografia seguinte), exit_at, exit jsonb, pnl_sol, r_multiple,
  mark_sol, mark_at, high_water_x, sol_usd_at_entry, sol_usd_at_exit
  INDEX (status, entry_at), INDEX (rule_set_id, entry_at), INDEX (mint)
  CHECKs: closed ⟺ exit_at; exit_at ⟺ exit ⟺ pnl_sol ⟺ r_multiple (tudo ou nada);
          exit_at > entry_at; mark_sol ⟺ mark_at; initial_risk_sol > 0

meme_operator_commands                       (ordem do operador)
  id uuid PK, bet_id FK NULL, proposal_id FK NULL  -- exatamente um dos dois
  command ∈ {sell_now → bet_id, cancel → proposal_id}
  issued_by, issued_at, applied_at, result jsonb   -- applied_at ⟺ result
  INDEX (issued_at) WHERE applied_at IS NULL       -- a leitura quente do laço
```

O ciclo `meme_proposals.bet_id → meme_paper_bets.proposal_id → meme_proposals` é
fechado por `ALTER TABLE` depois das duas existirem (`use_alter` no modelo) e
desfeito primeiro no downgrade.

### 34.3 As duas vistas

`meme_lab_scoreboard_v1` — por `rule_set_id` × **dia de entrada em Brasília**
(`(entry_at AT TIME ZONE 'America/Sao_Paulo')::date`): `bets`, `closed`, `wins`
(`pnl_sol > 0`), `pnl_sol`, `pnl_usd` (só apostas com `sol_usd_at_exit`),
`unpriced_usd` (quantas não têm cotação), `r_sum`, `max_drawdown_sol` (a maior
queda do PnL acumulado do dia, ordenado por `exit_at`, abaixo da máxima corrente
com piso zero — magnitude; `NULL` sem fechadas), `rugs`
(`exit->>'reason' = 'rug_no_snapshot'`), mais `name`/`version`/`kind`/`exp_ref`/
`rule_set_status` do conjunto.

`meme_desk_v1` — `meme_proposals JOIN meme_rule_sets LEFT JOIN meme_tokens LEFT
JOIN meme_paper_bets`: a linha da mesa. `LEFT JOIN` no token de propósito
(Emenda 5): a retenção de 90 dias poda a dimensão e a proposta não pode sumir da
mesa por isso. A T4.7 acabou lendo as tabelas base (Emenda dela); a vista fica.

### 34.4 Grants: quem escreve o quê

| Classe (congelada em `ddl/meme_lab.py`) | Papel | Privilégios | Tabelas |
|---|---|---|---|
| `MEME_LAB_APP_READ_ONLY_TABLES` | `hunter_app` | `SELECT` | `meme_rule_sets`, `meme_paper_bets` |
| `MEME_LAB_APP_APPEND_TABLES` | `hunter_app` | `SELECT`/`INSERT` | `meme_operator_commands` |
| `MEME_LAB_APP_DECISION_TABLES` | `hunter_app` | `SELECT`/`INSERT` + `UPDATE (status, decision, decided_by, decided_at)` | `meme_proposals` |
| `MEME_LAB_WORKER_READ_ONLY_TABLES` | `hunter_worker` | `SELECT` | `meme_rule_sets` |
| `MEME_LAB_WORKER_UPSERT_TABLES` | `hunter_worker` | `SELECT`/`INSERT`/`UPDATE` | `meme_proposals`, `meme_paper_bets` |
| `MEME_LAB_WORKER_APPLY_TABLES` | `hunter_worker` | `SELECT` + `UPDATE (applied_at, result)` | `meme_operator_commands` |

**Ninguém tem `DELETE`** em nenhuma das quatro: uma aposta é evidência e uma
proposta `unfilled` é a recusa que explica uma mesa vazia. A API decide e ordena
(aprovar, recusar, compra manual, vender agora, cancelar) e não toca a cotação,
o `bet_id` nem a recusa; o laço propõe, preenche, marca e responde à ordem, e não
aposenta conjunto nem emite ordem. Três classes novas de `hunter_app` entram na
união de `test_the_grant_lists_cover_every_table_exactly_once`; provado **como o
papel** em `test_the_api_role_decides_a_meme_proposal_and_touches_nothing_else` e
`test_the_worker_writes_the_meme_lab_and_never_deletes_it`.

### 34.5 A semente está na revisão

Dois conjuntos ativos (`ddl/meme_lab_views.py`, ids fixos para dois bancos
concordarem): `meme_paper_v0/1` (`research_only`, `EXP-M1`) e `operator/1`
(`operator`, mesma porta, só propõe). Os `params` são o perfil `meme_paper_v0` de
`docs/RISK_ENGINE_MEME.md` §3.1 como a EXP-M1 os congelou: porta idade 30–600 s,
progresso 2–50 %, participação ≤ 1 %, criador não vendedor líquido; saídas 2× /
trailing 30 % / 900 s / piso 50 %; `size_sol` 0,05; tetos `wallet_max_sol` 2,0,
`max_sol_per_bet` 0,05, `daily_loss_cap_sol` 0,20, 3 posições; `fee_pct` 1,75
(curva 1,25 + caminho local 0,5 — o papel nunca simula caminho mais barato que o
live, §10.2); `priority_fee_sol` **0 e declarado**: nenhum priority fee foi
observado pelo projeto, e a EXP-M1 já diz que todo número dela é teto otimista.
Decimais são **strings** no jsonb (`"0.05"`), para `Decimal` ler byte a byte.
Um Lab sem conjunto seria um laço que roda e não propõe parecendo vivo — o zero
silencioso que o contrato proíbe.

### 34.6 Guardas

**Sem guarda de upgrade, e isso é afirmação**: a revisão cria tabelas que não
existiam. **O downgrade recusa** enquanto `meme_paper_bets`, `meme_proposals` ou
`meme_operator_commands` tiverem linha (§17.7), cada uma com o motivo nomeado; a
semente **não** é guardada, senão o round trip de um rollback recusaria em todo
banco que esta revisão tocou. `test_0022_refuses_a_downgrade_that_would_lose_a_bet`
e `test_0022_reverses_with_the_seed_alone_and_comes_back_seeded` medem as duas
metades; os testes da `0021` passaram a se posicionar em `0021_meme_radar` antes
de reverter (`"-1"` a partir do head reverte a `0022`).

### 34.7 A máquina de estados, e onde a não-antecipação vira linha

```
proposta:  proposed ──(research_only: o próprio laço, decided_by='rules')──▶ approved
           proposed ──(API: aprovar/recusar; expires_at: laço)──▶ approved | rejected | expired
           approved ──(1.ª fotografia com observed_at > decided_at, tetos)──▶ filled (bet_id)
           approved ──(sem fotografia em 3 min; teto estourado)──▶ unfilled (refusal)
aposta:    open ──(cada fotografia nova: mark_sol, high_water_x)──▶ open
           open ──(regra dispara na fotografia k: exit_intent)──▶ open (esperando k+1)
           open ──(venda na fotografia k+1)──▶ closed (exit.reason, pnl_sol, r_multiple)
           open ──(sem fotografia posterior em 3 min)──▶ closed (rug_no_snapshot, sol_received 0)
```

`exit.reason` ∈ {`target`, `trailing`, `time_stop`, `migrated`, `creator_dump`,
`sell_now`, `rug_no_snapshot`, `max_loss`}; `refusal` é o vocabulário fechado de
`hunter_meme_worker.paper_engine.FILL_REFUSALS` mais `rule_set_inactive`.
`initial_risk_sol = sol_spent`: numa curva o risco é o valor gasto inteiro (§5 da
doutrina), e `rug_no_snapshot` é esse §5 escrito em aritmética — sem fotografia
para vender, o resultado plausível é −100 %, nunca um fill fabricado à última
marca. A carteira de um conjunto **não é coluna**: `wallet_max_sol + Σ pnl
fechado − Σ stake aberto`, derivada de `meme_paper_bets` a cada leitura, no laço e
na API, para que um restart não seja um reset.

### 34.8 Trava, pooler e orçamento de nome

**Trava.** `CREATE TABLE` não toma trava em relação que ainda não existe, o
`ALTER TABLE` do backlink trava só as duas tabelas vazias e os `GRANT` só o
catálogo: esta revisão **não abre janela de manutenção**. **Pooler.** Nada
depende de estado de sessão: quatro `CREATE TABLE`, um `ALTER`, sete `CREATE
INDEX`, duas `CREATE VIEW`, um `INSERT` e os grants. `0022_meme_lab` tem 13
caracteres; o teto de `alembic_version.version_num` continua 32 (§17.6).

### 34.9 O que as tarefas vizinhas têm de saber

| Onde | O que muda |
|---|---|
| T4.7 (`apps/**`, mesa) | escreve só `meme_proposals` (decisão) e `meme_operator_commands`; lê as tabelas base; as chaves de `quote`/`entry`/`exit` que ela lê estão nas Emendas do contrato |
| `services/meme-worker/**` | o único escritor de apostas: `lab.py` (tick), `proposals.py` (porta), `paper_engine.py` (fill/marca/saída), `lab_repo*.py`; heartbeat `lab_*` em `hb:meme:radar` |
| `GET /api/v1/orgs/{org}/meme/lab` | placar por conjunto por dia (Brasília), carteira derivada, meta (conta sobre o alvo), `sources.lab_status` |
| `infra/scripts/meme_diary.py` | lê como `hunter_app` e escreve `obsidian/09-OPERATIONS/Diario-Meme/<dia>.md` (`--dry-run`/`--apply`) |
| T4.8 (caminho de assinatura) | acrescenta `'live'` ao CHECK de `mode` com revisão própria, atrás de `ENABLE_MEME_LIVE_TRADING`; até lá nenhum papel escreve uma aposta que se diga real |
| `packages/risk-core/**`, `services/execution-worker/**` | **nada, e por construção**: nenhuma tabela desta revisão é alcançável por caminho de execução |

## 35. Os boards do site e a fita de trades viram schema — M4 (`0023_meme_boards_trades`)

Vigésima terceira revisão. **Duas tabelas** (pais `RANGE` mensais), três índices, oito partições,
quinze colunas e nove CHECKs acrescentados a `meme_features_1m`, uma coluna relaxada em
`meme_trades`, grants por subtração. Nenhum enum, nenhuma política de RLS, nenhuma vista alterada,
nada tocado na `0022`. Entrega a T4.2c sobre a `0021` (T4.2) e a `0022` (T4.6).

### 35.1 Global, sem RLS — e a ausência é asserida

As duas tabelas são **globais** (§1.1): um board é o que todo visitante vê; uma leitura de risco é
sobre uma moeda na cadeia. Os testes `LIKE 'meme%'` da §33.1 contam estas duas também.

### 35.2 As duas tabelas

```
meme_board_observations            (uma linha por mint por board por MINUTO fechado)
  observed_at PK₁, board PK₂ ∈ {new, graduating, graduated, movers}, mint PK₃
  minute_end (bucket pelo NOSSO received_at), received_at, mint_updated_at, version, position, patches
  chain, program, platform, quote_asset, name, symbol
  market_cap_usd, progress_pct, volume_{sol,usd}, volume_{5m,15m,1h,24h}_{sol,usd}, tx_5m, age_s
  kol_count, snipers, is_mayhem, mayhem_state, has_{social,twitter,website,telegram}
  graduated_at, ath_market_cap_usd, buys, sells, txs, holders, top10_share, dev_share (frações)
  cashback, dev_wallet, is_live, participants, fees_{sol,usd}
  first_seen_in_board_at, last_seen_in_board_at, left_board_at, exposure_censored, extra jsonb, source
  CHECKs: board conhecido; posição/patches ≥ 0; last_seen ≥ first_seen; censurado ⇒ sem left_board_at
  RANGE (observed_at); INDEX (mint, observed_at); INDEX (minute_end, board)

meme_risk_snapshots                (uma leitura de /in-memory-coin)
  observed_at PK₁, mint PK₂, received_at, source, program, platform, quote_mint, quote_asset
  holders, top10_share, dev_share, snipers, sniper_share, bundled_share, progress_pct, graduated_at
  is_mayhem, mayhem_state, raw jsonb NOT NULL (os 65 campos, crus)
  RANGE (observed_at); INDEX (mint, observed_at)
```

**`observed_at` de uma linha de board** é o último `serverTs` do board no minuto (o board ainda
listava o mint então); `mint_updated_at` é o `serverTs` do último patch do próprio mint, que pode ser
mais velho. Um board que não enviou nada num minuto não produz linha nele: não observado não é "ainda
lá". **Exposição** (A4.0g §2): `left_board_at` só com um `remove` visto; `exposure_censored = true`
quando o mint some no snapshot de uma reconexão — sumiço que ninguém viu é censura, não saída.

### 35.3 O que a `0023` muda nas tabelas da `0021`

`meme_features_1m` ganha, cada valor com seu motivo (CHECK bicondicional, o padrão da §33.5):
`holders` (+ `holders_observed_at`, `holders_source` — a procedência da leitura, que também é a de
`top10_share`), `dev_share`, `snipers`, `buys_1m`/`sells_1m`/`net_sol_flow_1m`/`curve_volume_1m_sol`
(um `tape_reason` para os quatro: vêm de uma fonte e faltam juntos), `creator_net_seller`
(`Σ vendas − Σ compras do criador > 0` em SOL sobre a fita coberta; distinto de `creator_sold`, que
é *qualquer* venda). Vocabulário de motivo: os sete da §33.5 mais **`no_sells`** (razão compra/venda
sem vendas não é número).

`meme_trades.commitment` vira **anulável** (`CHECK (commitment IS NULL OR commitment IN (…))`): a
`0021` escreveu `NOT NULL` para um decodificador on-chain que declara finalidade; o produtor que de
fato pousou (`swap-api`) não declara nenhuma, e `NULL` é a mesma palavra que
`meme_curve_snapshots.commitment` usa para o espelho REST.

**Não-antecipação é propriedade do produtor, declarada no modelo:** um valor numa linha com
`end_time = T` foi calculado só de observações com `received_at <= T`. Um trade com `block_time`
dentro do minuto que chegou depois de `T` **não** está em `buys_1m` — está em minuto nenhum; a conta
por minuto é "o que se sabia em T", nunca "o que aconteceu até T".

### 35.4 Grants, guardas, trava

| Classe (`ddl/meme_boards.py`) | Papel | Privilégios | Tabelas |
|---|---|---|---|
| `MEME_BOARDS_APP_READ_ONLY_TABLES` | `hunter_app` | `SELECT` | as duas |
| `MEME_BOARDS_WORKER_APPEND_TABLES` | `hunter_worker` | `SELECT`/`INSERT` | as duas |

Partições `2026-09..12` criadas e endurecidas como as da `0021`; retenção por `DROP` de mês
(`MEME_RETENTION_DAYS`). **Sem guarda de upgrade** (colunas anuláveis sem default e `DROP NOT NULL`
não tornam linha nenhuma irrepresentável). **O downgrade recusa** com linha em qualquer das duas
tabelas, com linha de feature carregando coluna da `0023`, ou com trade de `commitment NULL`
(restaurar `NOT NULL` falharia no meio). `ADD COLUMN` anulável e `DROP NOT NULL` são só catálogo no
PG 16; `ADD CONSTRAINT … CHECK` varre `meme_features_1m` uma vez — segundos hoje. Nome com 23
caracteres (§17.6). Testes: `test_0023_*` em `test_migrations.py`; união de grants em
`test_schema_privileges.py`; persistência em `services/meme-worker/tests/test_boards_trades_persistence.py`.

### 35.5 O que as tarefas vizinhas têm de saber

| Onde | O que muda |
|---|---|
| `services/meme-worker/**` | escreve as duas tabelas (`repo_boards.py`) e `meme_trades` (`source='swap_api'`); lê `meme_paper_bets` (`status='open'`) para a prioridade |
| `GET /api/v1/orgs/{org}/meme/sources` | por fonte: conectada?, último `observed_at`, atraso, erros na última hora, orçamento usado, e a última linha da tabela como segunda testemunha |
| T4.6 (`lab_repo.load_gate_rows`) | as colunas que o portão pede existem: `curve_volume_1m_sol` e `creator_net_seller` — dois ajustes de uma linha fora desta tarefa |
| `apps/web/**` | nada nesta tarefa; `MemeSource` ganhou `trenches_ws` e `NullReason` ganhou `no_sells` na API (`pnpm gen:types` pendente) |

## 36. O que "graduou" quer dizer — quatro sinais, o denominador com procedência, a matriz — M4 (`0024_meme_graduation`)

Vigésima quarta revisão. **Seis colunas anuláveis** em `meme_tokens`, quatro CHECKs, a função do
trigger de escrita única substituída, a vista `meme_radar_features_v1` substituída com as seis colunas
**acrescentadas no fim**, a vista nova `meme_graduation_matrix_v1`, um backfill a partir das tabelas
de evidência. Nenhuma tabela nova, nenhum enum, nenhuma política de RLS, nada tocado na `0022`/`0023`.
Entrega a T4.2d sobre a `0023` (T4.2c).

**O fato medido que a motiva** (plantão, run 5, 12/09/2026 05:51 BRT): das 140 moedas que a REST dizia
`complete = true`, 77 tinham `real_sol_reserves = 0` (47 Mayhem, mcap mediano US$ 9,57) e 72 não estavam
no board `graduated`; e das 68 que estavam, 31 também mostravam reserva zero — a curva migrada esvazia
para a pool. Must-fixes da Astra: manter os indicadores separados; reserva zero não classifica.

### 36.1 As quatro colunas de conclusão, e a redução

| coluna | a primeira fotografia que… | quem escreve |
|---|---|---|
| `rest_complete_seen_at` | disse `complete = true` (REST/RPC) | `curve_rows.py` |
| `curve_filled_seen_at` | tinha `real_sol_reserves ≥` o limiar de enchimento **derivado** de `/global-params` (85,005 SOL para o registro de 18/07/2025: `buy_cost` dos 793,1 M tokens reais numa curva virgem, com o arredondamento do programa — `quote.curve_fill_threshold_lamports`) | `curve_rows.py` |
| `graduated_board_seen_at` | listou o mint no board `graduated` (o `serverTs` do board), para **toda** entrada pump/SOL, rastreada ou não | `boards.py` |
| `pool_created_at` + `pool_created_source` | reportou uma pool: o `gd` do indexer (`trenches_ws` \| `indexer_rest:/boards` \| `indexer_rest:/in-memory-coin`) ou o `migrate` do PumpPortal (`pumpportal_ws`) — o que este radar viu primeiro | `boards.py`, `risk.py`, `discovery.py` |

`completed_at` **deixa de ser observação e vira redução**: a mais antiga das quatro, **exceto** que um
`complete` da REST cuja fotografia tinha reserva zero não conta sozinho — nem empresta o instante
(`services/meme-worker/hunter_meme_worker/graduation.py::earliest_completion`). Sai da lista de escrita
única e ganha um ramo próprio no trigger: escrito com `LEAST(existente, novo)`, **só pode recuar** (o `gd`
do indexer é retrospectivo), nunca avançar, nunca voltar a NULL. As quatro estampas e as duas fontes são
de escrita única (`WRITE_ONCE_COLUMNS_0024`, copiada em `repo._IDENTITY_COLUMNS`).

### 36.2 O denominador ganha procedência

`progress_denominator_source` ∈ {`observed_virgin`, `global_params`}, bicondicional com
`initial_real_token_reserves` (CHECK); desconhecido é NULL nos dois, que a API renderiza como `unknown`.
`observed_virgin` é a regra da `0021` (primeira fotografia com `real_sol_reserves = 0`); `global_params`
é a T4.2d: uma curva **padrão** vista depois da primeira compra toma o `initial_real_token_reserves` do
registro de `/global-params/{criação}` (793,1 M hoje). **Mayhem nunca toma o registro**: o agente cunha
1 bilhão de tokens extra e `set_mayhem_virtual_params` move as reservas (RISK_ENGINE_MEME §8.3); a
fixture `2sduGq…` (Mayhem pausada) tem 822,6 M tokens reais na curva, *mais* que os 793,1 M — nem `Global`
nem `/global-params` trazem um parâmetro de reserva Mayhem, o campo certo vive na conta `mayhem_state`,
que este projeto não decodifica. O mesmo guarda recusa qualquer curva com mais tokens reais que o
inicial do registro. Consequência declarada: uma Mayhem só ganha denominador se observada virgem.

### 36.3 O backfill é de evidência, nunca de palpite

Com o trigger da `0021` **desligado só durante o backfill** (`DISABLE TRIGGER`/`ENABLE TRIGGER` na
mesma transação — o único instante em que o cadeado se levanta é a revisão que redefine a coluna):
`rest_complete_seen_at` = `min(observed_at)` das fotografias com `complete`; `graduated_board_seen_at` =
`min(first_seen_in_board_at)` do board `graduated`; `pool_created_at` = `migrated_at` (fonte
`pumpportal_ws`, o socket foi quem ouviu) senão o `gd` mais antigo de qualquer linha de board com a fonte
dessa linha; `progress_denominator_source = observed_virgin` para todo denominador existente (a fotografia
virgem era o único escritor); `completed_at` recomputado pela regra — `LEAST` de tudo NULL é NULL, logo as
77 "só REST com reserva zero" ficam sem veredito, que é o que são. `curve_filled_seen_at` **não** é
preenchida: o limiar precisa do registro, que uma migração não lê; a série começa no deploy e a matriz
diz isso contando.

### 36.4 As vistas

`meme_radar_features_v1` = a projeção da `0021` com as seis colunas **no fim** (`CREATE OR REPLACE`
mantém nomes, tipos, ordem e grants). `meme_graduation_matrix_v1`: uma linha por **dia de Brasília do
sinal mais antigo** de cada mint com algum sinal — `mints`, `completed`, contagem por sinal
(`rest_complete`, `curve_filled`, `graduated_board`, `pool_created`), `signals_1..4`, os seis pares que
discordam (`disagree_rest_filled`, `disagree_rest_board`, `disagree_rest_pool`, `disagree_filled_board`,
`disagree_filled_pool`, `disagree_board_pool` — um presente e o outro ausente) e `rest_only_unclassified`
(REST disse completa, nada mais disse: os 77). Sem ORDER BY; `SELECT` para `hunter_app` e
`hunter_worker`. A API lê o dia de hoje pedindo ao banco o dia (`timezone('America/Sao_Paulo', now)`),
nunca subtraindo três horas.

### 36.5 Grants, guardas, trava, séries

Nenhum grant novo além da vista. **Sem guarda de upgrade** (colunas anuláveis sem default; os CHECKs
entram depois do backfill que os satisfaz). **O downgrade recusa** com qualquer linha que carregue um
sinal de conclusão ou um denominador `global_params` (a primeira visão de uma graduação não se
reobserva); `DROP VIEW` + `CREATE VIEW` restauram o texto da `0021` (copiado, congelado) e os grants;
`create_meme_token_guards` da `0021` devolve a função de escrita única com `completed_at` de novo. `ADD
COLUMN` anulável é só catálogo; o backfill varre `meme_curve_snapshots` uma vez (segundos); `ADD
CONSTRAINT … CHECK` varre `meme_tokens` sob `SHARE ROW EXCLUSIVE`. Nome com 20 caracteres (§17.6).
**`meme_features_1m.features_version` passa a `meme_features_v2`** para as linhas novas: o
`curve_progress_pct` pode agora vir de um denominador `global_params`; as linhas `v1` não são reescritas,
a série quebra no deploy e o Lab lê a versão que a sua config nomeia. Testes: `test_0024_*` em
`test_migrations.py` (colunas/CHECKs/vista, escrita única + recuo, backfill sobre uma base `0023`,
recusa, ida e volta); `services/meme-worker/tests/test_graduation_persistence.py`.

### 36.6 O que as tarefas vizinhas têm de saber

| Onde | O que muda |
|---|---|
| `services/meme-worker/**` | `repo.upsert_token` escreve as seis colunas (`LEAST` em `completed_at`); `_LOAD_TRACKED` exclui por `rest_complete_seen_at` e traz de volta, para uma leitura final, quem concluiu por board/pool; `GlobalParamsStore` lê `/global-params` uma vez por hora no orçamento da curva |
| `GET /api/v1/orgs/{org}/meme/tokens[/{mint}]` | os quatro sinais, `pool_created_source`, `progress_denominator_source` (`unknown` para NULL); `completed_at` no payload |
| `GET /api/v1/orgs/{org}/meme/overview` | `graduation_matrix` = a linha de hoje (Brasília) da vista, ou `null` |
| `GET /api/v1/orgs/{org}/meme/sources` | `discovery_blind_share_1h` + contagens + `discovery_blind_explanation` (heartbeat `blind_share_1h`, `new_board_entries_1h`, `new_board_non_pump_1h`) |
| `apps/web` (`/meme`, `/meme/{mint}`) | faixa "Graduação hoje — quatro sinais separados" (discordâncias em âmbar); bloco "Sinais de conclusão" e marcas no gráfico de mcap; filtro `completed` = `completed_at` |

## 37. O denominador das curvas Mayhem — `mayhem_state` — M4 (`0025_meme_mayhem_denominator`)

Vigésima quinta revisão. **Um CHECK alargado** em `meme_tokens`
(`ck_meme_tokens_denominator_source_is_a_known_label` ganha `'mayhem_state'`), e nada mais: nenhuma
coluna, tabela, vista, trigger, enum ou política. Entrega a T4.2e sobre a `0024` (T4.2d).

**O fato que a motiva** (`docs/PUMPFUN-ONCHAIN.md` §3.5): a T4.2d deixou toda curva Mayhem sem
denominador porque a fixture `2sduGq…` tinha 822,6 M tokens reais, mais que os 793,1 M do registro. A
T4.2e leu na cadeia, no mesmo slot, as quatro contas de cinco moedas Mayhem (`bonding_curve`,
`MayhemState`, cofre do agente, mint): a reserva inicial **é a do registro**; o excesso é o bilhão do
agente (supply do mint 2 B contra `token_total_supply` 1 B da curva) vendido líquido para a curva —
`822 644 036,902123 = 793 100 000 + 29 544 036,902123`, até a subunidade. `mayhem_state` significa: o
inicial do registro, escrito **só depois** de a identidade `cofre + líquido = supply − supply_da_curva`
fechar naquela leitura (`services/meme-worker/hunter_meme_worker/mayhem.py`). Bicondicional com
`initial_real_token_reserves` (CHECK da `0024`, intocado); escrita única (`WRITE_ONCE_COLUMNS_0024`).

**Sem guarda de subida — e isso é uma asserção:** a lista nova é superconjunto da antiga. O CHECK é
adicionado `NOT VALID` e depois `VALIDATE CONSTRAINT` (`SHARE UPDATE EXCLUSIVE`, que deixa os upserts
do coletor passarem; ~40 k linhas/dia, podadas a 90 dias). **A descida recusa** enquanto houver uma
linha com `mayhem_state` (§17.7: contar, nomear, parar; `COPY` antes).

**Efeitos fora do esquema, declarados:** `curve_progress_pct` de uma Mayhem pode ser **negativo**
(`1 − rt/inicial` com o agente vendedor líquido; o site trunca em 0, o radar guarda — §15.8, sem CHECK de
domínio; o portão da EXP-M1 recusa por `progress_below_min`); `curve_filled_seen_at` não é reivindicado
para Mayhem (`set_mayhem_virtual_params` move o SOL virtual). Correção de bug na mesma tarefa:
`repo._UPSERT_TOKEN` não inseria `mayhem_state`/`mayhem_mode` (o `INSERT` os omitia e `excluded.*` era
sempre NULL) — `meme_tokens.mayhem_state` passa a ser preenchido, o `OR mayhem_state IN
('active','paused')` de `_LOAD_TRACKED` passa a valer, com o mesmo `CASE` do CHECK
`a_disabled_token_has_no_agent_state` no `VALUES`. `tape_reason` ganha `not_polled` (palavra já do
vocabulário: o orçamento da fita não alcançou o mint no ciclo).

| Onde | O que muda |
|---|---|
| `services/meme-worker/**` | `graduation.mayhem_denominator`, laço `mayhem.py` (25 mints por `getMultipleAccounts`, uma vez por minuto), `repo._UPSERT_TOKEN` insere `mayhem_state`/`mayhem_mode` |
| `GET /api/v1/orgs/{org}/meme/tokens[/{mint}]` | `progress_denominator_source` ∈ {`observed_virgin`, `global_params`, `mayhem_state`, `unknown`} |
| `GET /api/v1/orgs/{org}/meme/sources` | `progress_coverage_pct`, `tape_coverage_pct`, `fold_minute`, `fold_rows`, `tape_cycle_s`, `tape_*`, `mayhem_pending`, `mayhem_denominators_60s`, `coverage_explanation` |
| `apps/web` | **pendente**: `labels.ts` tipa `Record<MemeDenominatorSource, string>` exaustivo — precisa do rótulo `mayhem_state` e de `pnpm gen:types` (fora do escopo da T4.2e) |
