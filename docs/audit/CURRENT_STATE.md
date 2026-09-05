# Estado atual do repositório — auditoria de 2026-09-05

**Commit auditado:** `744fdf8` (fim do Milestone 0). **Método:** três auditores independentes, somente leitura (backend + banco + workers; frontend; infra + CI + testes + docs), cada afirmação com `arquivo:linha`; comandos executados listados no fim. Nenhum arquivo foi alterado durante a auditoria.

**Veredito em uma linha:** existe uma fundação real e testada (auth multi-tenant, organizações, RLS, auditoria, schema completo das 54 tabelas, Docker, CI, shell de worker, streams Redis) e **zero** implementação do pipeline de trading. O que falta não está mockado nem quebrado: está **ausente**. O próprio código diz isso (`infra/docker/entrypoint.sh:45-48`, `apps/api/hunter_api/app.py:7-8`, `apps/web/app/(app)/[orgSlug]/system/page.tsx:34`).

Pipeline pedido: EXCHANGE → MARKET COLLECTOR → NORMALIZATION → FEATURE ENGINE → ANOMALY ENGINE → OPPORTUNITY ENGINE → AGENTS → RISK ENGINE → PAPER EXECUTION → PAPER WALLET → PNL/ANALYTICS → DATABASE → DASHBOARD.

| Estágio | Estado | Onde |
|---|---|---|
| Exchange (Binance/Bybit REST+WS) | NÃO IMPLEMENTADO | `packages/exchange-adapters/hunter_exchanges/__init__.py` (só docstring) |
| Market Collector | NÃO IMPLEMENTADO | `services/market-worker/hunter_market_worker/__init__.py` (só docstring) |
| Normalization | NÃO IMPLEMENTADO | tipos `Normalized*` não existem em `hunter_core.domain` |
| Feature / Anomaly / Regime / Opportunity | NÃO IMPLEMENTADO | `packages/indicators/hunter_indicators/__init__.py` vazio; `services/scanner-worker` vazio |
| Agents (Strategy framework) | NÃO IMPLEMENTADO | não há `hunter_core/strategies/`; `services/strategy-worker` vazio |
| Risk Engine | NÃO IMPLEMENTADO | `packages/risk-core/hunter_risk/__init__.py` vazio; presets em `risk_profiles` só copiados no onboarding |
| Paper Execution / Wallet | NÃO IMPLEMENTADO | não há `hunter_core/execution/`; `services/execution-worker` vazio |
| PnL / Analytics | NÃO IMPLEMENTADO | `services/analytics-worker` vazio |
| Database | FUNCIONAL (schema) | 54 tabelas modeladas, migração `0001_initial_schema`, 61 tabelas com RLS, 70 policies, partições; só 9 tabelas recebem escrita hoje |
| Dashboard | PARCIAL (honesto) | cards reais de org/workspace/membros; estados vazios dizem "M1"/"M3" |

---

## FUNCIONAL

Tudo que funciona de ponta a ponta hoje, com a prova.

### Identidade, tenancy e API
- **Clerk real**: verificação RS256 contra JWKS com cache, cooldown e staleness máxima (`apps/api/hunter_api/auth/clerk.py`, `auth/jwks.py`); provisionamento JIT; webhook Svix idempotente em duas fases (`services/clerk_webhook.py`, `services/webhook_delivery.py`, tabela `processed_events`).
- **RBAC + RLS**: escada VIEWER<ANALYST<TRADER<ADMIN<OWNER com 404 para outro tenant (`auth/rbac.py:38-159`); `SET LOCAL ROLE hunter_app` + GUCs `app.current_org`/`app.current_user` por transação (`packages/core/hunter_core/db/session.py:84-198`). Verificado no Postgres vivo: 61 tabelas com `relrowsecurity`, 70 policies, roles `hunter_app` (sem BYPASSRLS) e `hunter_worker` (BYPASSRLS).
- **Routers**: `me`, `organizations`, `workspaces`, `members`, `invitations`, `audit`, `webhooks` (`apps/api/hunter_api/app.py:167-175`). Toda mutação tenant passa por `SqlAuditSink` na mesma transação (`deps.py:87-98`) e grava em `audit_logs`.
- **Middleware**: request id, RFC 9457 (422 sem eco de input), rate limit por IP/principal/webhook em Redis, cap de corpo em streaming, security headers, CORS allowlist, `/metrics` com token.
- **Realtime gateway**: WS auth-first, gramática de canais (`realtime/channels.py:28-38`), throttling por classe, revalidação de membership, ponte Redis pub/sub → WS por canal (`realtime/redis_bridge.py`). **Nada publica nesses canais ainda.**
- **Health**: `/health` → `{"status":"ok","role":"api"}`, `/ready` → `{"database":true,"redis":true}` (verificado ao vivo), `/api/v1/system/info` com feature flags vindas do `Settings`.

### Núcleo (`packages/core`)
- `Settings` com todas as variáveis (tabela abaixo), validação de obrigatórias em staging/prod (`settings.py:104-141`).
- Logging structlog JSON com redação de segredos (`logging.py:20`).
- `WorkerRuntime` (`runtime.py`): heartbeat `hb:{role}:{instance}` a cada 10 s com TTL 30 s, `/health` `/ready` `/metrics` por processo, SIGTERM/SIGINT com shutdown limpo. `RoleRegistry = {}` (`runtime.py:179`): nenhum papel registrado.
- Eventos: `EventEnvelope` (uuid7, type, ts, producer, key, payload), `publish` (XADD MAXLEN ~), `consume` (grupo, XAUTOCLAIM, idempotência por `hunter:processed:{consumer}`), 16 streams nomeados em `events/streams.py` com MAXLEN. 178 testes verdes. **Zero chamadas a `publish` fora de testes.**
- Chaves Redis do hot state em `redis.py:48-117` (`mkt:*`, `feat:*`, `opp:*`, `radar:scores`, `regime:current`, `ks:*`, `hb:*`, `rl:*`, `lock:*`). **Só `heartbeat`, `processed` e `lock` têm chamadores reais.**

### Banco
- Migração única `infra/migrations/versions/0001_initial_schema.py` + módulos DDL (enums, tabelas, partições, policies, grants, security). Postgres vivo: 139 relações (61 base + filhas de partição), 44 enums, `alembic_version = 0001_initial_schema`; `test_alembic_check_reports_no_drift` passou.
- Seeds idempotentes (`infra/scripts/seed.py`): `exchanges` (binance, bybit), 8 `strategies` + `strategy_versions` v1 `draft`, `plan_entitlements`, `feature_flags`, 3 `risk_profiles` de sistema, `opportunity_weights` v1 ativo.
- Scripts: `create_partitions.py --dry-run` → 84 partições garantidas; `prune_*`, `check_file_size.py` (85 arquivos, 0 acima do limite), `dump_openapi.py`, `forbidden_patterns.sh`.

### Frontend (`apps/web`)
- Rotas reais: `/` (roteia por `/api/v1/me`), auth Clerk, `accept-invite`, onboarding 6 passos (passo 1 `POST /api/v1/orgs`; passo 6 `PUT .../onboarding` idempotente), `/{org}/dashboard`, `/{org}/system` (info + readiness com Server Action de refresh + flags), `/{org}/settings/{profile,organization,members,security,appearance}`, `/_design` (dev).
- Todos os controles fazem algo real (convidar, revogar, mudar papel, remover, salvar org, aceitar convite, tema/densidade client-side por design). Os itens de menu "planejados" são `aria-disabled` de propósito e somem em produção.
- **Nenhum número financeiro inventado, nenhum `Math.random` fora do jitter do WS, nenhum "coming soon".**
- Camada de dados: `lib/server/api.ts` (server-only, bearer Clerk, `X-Request-ID`, RFC 9457 → `ApiError`).
- Qualidade (logs turbo de 01:08, depois do HEAD): eslint limpo, tsc limpo, vitest 15 arquivos / 138 testes.

### Infra e CI
- Compose dev: postgres, redis, migrate (run-once), api, worker, web; healthchecks. Ao vivo: api/postgres/redis saudáveis; `migrate` e `worker` `Exited (0)`.
- Imagem única api/workers com `entrypoint.sh` (`HUNTER_ROLE`, `HUNTER_COMMAND=migrate|seed`); imagem web standalone.
- `ci.yml`: ruff, pyright, pytest com testcontainers, pnpm lint/typecheck/test/build, gitleaks, pip-audit, bandit, pnpm audit, forbidden-patterns, docker build, migrations (`alembic upgrade head` + `check`), e2e (compose + Playwright).
- Testes: Python 515 coletados (319 unit + 196 integration); `pytest packages` → 178 passed (324 s); `pytest apps/api` → 337 passed (839 s, 2026-09-05); web 138; e2e 6.
- ruff `All checks passed!`; pyright `0 errors`.

---

## PARCIAL

Existe, mas incompleto.

| Item | O que existe | O que falta | Evidência |
|---|---|---|---|
| Worker shell | `WorkerRuntime` completo e testado | nenhum papel registrado; `HUNTER_ROLE=market\|scanner\|strategy\|execution\|analytics\|all` imprime "no entrypoint yet" e sai 0 | `runtime.py:179`, `entrypoint.sh:45-48` |
| Heartbeats | escritos em Redis pelo runtime | ninguém lê `hb:*`; tabela `worker_heartbeats` nunca escrita; System page mostra texto fixo "nenhum processo registrado ainda (M1)" | `system/page.tsx:34` |
| Realtime | gateway WS completo; cliente `lib/ws.ts` + `hooks/useRealtime.ts` completos | nenhum componente chama `useRealtime`; nenhum worker publica em `rt:*`; sem indicador de dado atrasado | grep repo |
| Métricas | 8 métricas registradas | só `events_*` e `worker_errors_total` são incrementadas; `exchange_latency_seconds`, `candle_gaps_total`, `proposals_total`, `fills_simulated_total`, `stream_lag` sempre 0 | `observability.py:44-93` |
| Kill switch | enum, colunas em `organizations`/`portfolios`, `kill_switch_transitions`, `SYSTEM_KILL_SWITCH`, chaves `ks:*` | nenhum endpoint, nenhuma leitura, nenhuma imposição | `settings.py:90`, `redis.py:88-97` |
| Risk profiles | 3 presets seedados e copiados para a org no onboarding | nenhum avaliador lê `limits` | `repositories/workspaces.py:80-116` |
| Feature flags | `feature_flags` + `organization_feature_overrides` modeladas e seedadas | `/system/info` lê só o `Settings`; camada de override nunca lida | `health.py:75-92` |
| Audit log na UI | `lib/api/audit.ts` implementado; endpoint real | não importado por nenhuma página; MVP.md diz que `/settings/security` mostra o log | `apps/web/lib/api/audit.ts` |
| Seletor de organização | modelo permite multi-org | topbar mostra só o slug fixo; `TODO(T09)` | `components/layout/topbar.tsx:65-70` |
| PostHog | SDK no backend (`hunter_api/analytics.py`) gated por env | `capture()` sem chamadores; nada no web | grep |
| Sentry | backend inicializado por env | nada em `apps/web` | `observability.py:24-41` |
| `.env.example` × `Settings` | 60+ variáveis espelhadas | `OPENAI_API_KEY`, `OPENAI_MODEL`, `LLM_PROVIDER`, `LLM_MODEL` só em `.env.example:56-61` (lidas direto por `infra/scripts/ask_astra.py`) | `settings.py:3-4` (docstring promete espelho) |
| shared-types | gerado por `pnpm gen:types` | não regenerado após os últimos commits da API (nenhum schema de resposta mudou, mas não foi verificado por execução) | `packages/shared-types` |
| Deploy workflows | reutilizam o gate do CI | passo de deploy é `exit 1` deliberado | `deploy-api.yml:44-50` |
| E2E | 3 specs, 6 testes | `signup-onboarding.spec` pula sem `CLERK_E2E_*`; teste de chave fake do `/sign-in` falha localmente porque a chave real está configurada | `ci.yml:196-231` |

---

## MOCK

Dados falsos apresentados como reais. **Nenhum encontrado.** Casos-limite, todos rotulados no próprio código:

- `worker` do compose sai com código 0 sem fazer nada (`entrypoint.sh:45-48`, mensagem explícita).
- `OPENAPI_TAGS` lista 14 tags (`markets`, `radar`, `opportunities`, `portfolios`, `trades`, `agents`, `risk`, `analytics`…) sem nenhuma rota; a docstring de `app.py:7-8` avisa que é metadado de onde os routers vão morar.
- Métricas Prometheus dormentes (sempre 0) listadas em PARCIAL.
- `RISK_LIMITS_TABLE` (`apps/web/lib/api/schemas.ts:44-58`) é um espelho estático de `docs/RISK_ENGINE.md`, exibido como tabela de presets no onboarding, somente leitura.
- Lista de exchanges do onboarding hardcoded em `schemas.ts:29` (binance, bybit) porque não existe `GET /exchanges`; validada no servidor ao enviar.

---

## QUEBRADO

- Nada crasha. `ruff`, `pyright`, `pytest packages` (178), `pytest apps/api` (337), vitest (138), compose saudável.
- Corrigidos nesta mesma data e já commitados: menu passando função/componente do servidor para o cliente (500 em toda rota `/[orgSlug]`, `541ef78`); `setup_env.ps1` gerando `.env` de uma linha (`b2e48b5`); 8 testes dependentes de ordem por balde de rate limit compartilhado (`744fdf8`).
- Comentário obsoleto em `ci.yml:97-99` ("migrations job stays red until T04 lands") — T04 já existe.
- `.claude/memory/MEMORY.md:3` diz que a máquina não tem node/pnpm/uv/docker; `milestone.json` registra os quatro instalados.

---

## NÃO IMPLEMENTADO

Necessário para o laboratório autônomo e ausente hoje.

### Pacotes e workers (0 linhas de lógica)
- `hunter_exchanges`: `ExchangeAdapter`, `BinanceAdapter`, `BybitAdapter`, `Normalized*`, rate limit por token bucket (`rl:*`), fixtures gravadas. Dependências `httpx`, `websockets`, `msgpack` já declaradas e instaladas.
- `hunter_market_worker`: universo (`MARKET_UNIVERSE_SIZE`), assinaturas WS, hot state Redis, persistência (`candles`, `market_snapshots`, `funding_rates`, `open_interest_history`, `liquidations`), recovery e `ingestion_gaps`, publicação em `market.*`.
- `hunter_indicators`: registro de features, calculadoras, baselines, detectores de anomalia, regime, Opportunity Scorer. `numpy`/`polars` já instalados.
- `hunter_scanner_worker`, `hunter_strategy_worker`, `hunter_execution_worker`, `hunter_analytics_worker`: vazios.
- `hunter_core/strategies/` e `hunter_core/execution/` (bases `Strategy`, `ExecutionAdapter`, `PaperExecutionAdapter`): não existem.
- `hunter_risk`: `RiskEngine`, checks, sizing, kill switch: vazio.

### API
- Routers ausentes: `markets`, `radar`, `opportunities`, `anomalies`, `portfolios`, `positions`, `orders`, `trades`, `agents`, `signals`, `proposals`, `risk`, `analytics`, `system/workers`, `lab`, `journal`.
- Nenhum publisher em `rt:market:*`, `rt:radar`, `rt:system`, `rt:org:*`.

### Frontend
- Páginas: `markets`, `radar`, `opportunities`, `portfolio`, `trades`, `agents`, `risk`, `analytics`, `lab`, `journal` (as duas últimas nem constam na spec/nav-registry ainda), `strategies`, `backtests`, `arena`, `intelligence`, `exchanges`, `alerts`.
- Widget de status ao vivo (WS conectado, último tick, mercados monitorados, anomalias, paper mode, risk engine).
- Consumo de WebSocket e indicação de dado atrasado.

### Tabelas modeladas sem nenhum escritor (39 de 54)
`api_keys`, `organization_feature_overrides`, `assets`, `markets`, `candles`, `market_snapshots`, `funding_rates`, `open_interest_history`, `liquidations`, `ingestion_gaps`, `feature_definitions`, `feature_snapshots`, `anomalies`, `market_regimes`, `opportunities`, `opportunity_history`, `agent_signals`, `signal_outcomes`, `agents`, `agent_stats`, `portfolios`, `portfolio_equity_snapshots`, `trade_proposals`, `orders`, `fills`, `positions`, `trades`, `risk_events`, `kill_switch_transitions`, `exchange_connections`, `backtests`, `backtest_results`, `backtest_trades`, `intelligence_sources`, `intelligence_events`, `alert_rules`, `notifications`, `system_events`, `worker_heartbeats`.

Com escrita real hoje: `users`, `organizations`, `organization_members`, `organization_invitations`, `workspaces`, `subscriptions`, `risk_profiles`, `audit_logs`, `processed_events`. Só seed: `exchanges`, `strategies`, `strategy_versions`, `plan_entitlements`, `feature_flags`, `opportunity_weights`.

### Operação contínua
- Nenhum worker roda de forma contínua; nenhum scheduler (partições e prunes só por `uv run` manual).
- Watchdog de dados (stale → bloquear ordens, `RISK_EVENT_DATA_STALE`): não existe (o único "watchdog" é o de liveness do WS da API).
- Criptografia de chaves de exchange (`HUNTER_MASTER_KEY`/`KMS_KEY_ID`): só campos.
- Base de conhecimento `obsidian/`: decidida (ADR 0003), em criação.

### Sem nenhum teste porque sem código
Normalização, features, anomalias, score, Risk Engine, carteira paper, fees, slippage, PnL, take-profit parcial, stop, reciclagem de capital, ciclo de vida de ordem, watchdog.

---

## Inventário de testes

| Área | Arquivos | Testes | Infra |
|---|---|---|---|
| `apps/api/tests/unit` | 21 | 161 | nenhuma |
| `apps/api/tests/integration` | 10 | 82 | testcontainers Postgres+Redis |
| `packages/core/tests/unit` | 11 | 88 | nenhuma |
| `packages/core/tests/integration` | 8 | 68 | testcontainers |
| `packages/{exchange-adapters,indicators,risk-core}` | 0 | 0 | — |
| `services/*-worker` (5) | 0 | 0 | — |
| `apps/web/tests` | 15 | 138 | vitest |
| `tests/e2e` | 3 | 6 | compose + Playwright |

## Variáveis de ambiente (resumo)

Definidas em `packages/core/hunter_core/settings.py` e `apps/api/hunter_api/settings.py`: `HUNTER_ENV`, `HUNTER_ROLE`, `LOG_LEVEL`, `WEB_ORIGIN`, `API_URL`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`, `DATABASE_URL`, `DATABASE_URL_MIGRATIONS`, `REDIS_URL`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SECRET`, `CLERK_JWKS_URL`, `CLERK_ISSUER`, `AUTH_SECRET`, `HUNTER_MASTER_KEY`, `KMS_KEY_ID`, `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `NEXT_PUBLIC_POSTHOG_KEY`, `NEXT_PUBLIC_POSTHOG_HOST`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `BINANCE_API_KEY/SECRET`, `BYBIT_API_KEY/SECRET`, `ENABLE_LIVE_TRADING` (false; `forbidden_patterns.sh:144` bloqueia `true` literal), `ENABLE_SOCIAL_INTELLIGENCE`, `ENABLE_ONCHAIN`, `ENABLE_STRIPE`, `ENABLE_LLM_ANALYSIS`, `ENABLE_ARENA`, `ENABLE_BACKTESTS`, `SYSTEM_KILL_SWITCH`, `MARKET_UNIVERSE_SIZE` (200), `BOOK_DEPTH` (25), `TICK_COALESCE_MS` (250), `FEATURE_THROTTLE_MS` (1000), `RADAR_PUSH_MS` (1000), `RETENTION_CANDLES_1M_DAYS` (90), `RETENTION_FEATURE_SNAPSHOTS_DAYS` (14), `HEALTH_PORT` (8001); API: `API_PORT`, `CORS_ALLOWED_ORIGINS`, `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_PER_MINUTE_PRINCIPAL`, `ENABLE_OPENAPI_DOCS`, `READY_CHECK_TIMEOUT_S`, `FORWARDED_ALLOW_IPS`, `METRICS_TOKEN`, `JWKS_REFRESH_COOLDOWN_S`, `JWKS_MAX_STALE_S`, `MAX_REQUEST_BODY_BYTES`, `WEBHOOK_CLAIM_STALE_S`, `WS_HANDSHAKES_PER_MINUTE`, `WS_MAX_CONNECTIONS_PER_PRINCIPAL`, `WS_REVALIDATE_INTERVAL_S`. Fora do `Settings`: `OPENAI_API_KEY`, `OPENAI_MODEL`, `LLM_PROVIDER`, `LLM_MODEL`.

## Comandos executados

```
docker compose -f infra/docker/docker-compose.yml ps        → api healthy, postgres healthy, redis healthy
docker compose ... ps -a                                    → migrate Exited (0), worker Exited (0)
docker compose ... logs worker                              → "role all has no entrypoint yet (lands in M1)"
curl http://localhost:8000/health                            → {"status":"ok","role":"api","version":"0.0.0"}
curl http://localhost:8000/ready                             → {"database":true,"redis":true}
psql: pg_tables public                                       → 139 ; enums → 44 ; RLS tables → 61 ; policies → 70 ; alembic_version → 0001_initial_schema
uv run ruff check .                                          → All checks passed!
uv run pyright                                               → 0 errors, 0 warnings, 0 informations
uv run pytest packages -q -p no:cacheprovider                → 178 passed in 324.80s
uv run pytest apps/api -q -p no:cacheprovider (2026-09-05)   → 337 passed in 839.53s
uv run pytest -m unit --collect-only -q                      → 319/515 collected
uv run python infra/scripts/check_file_size.py               → 85 files; 0 over budget
uv run python infra/scripts/create_partitions.py --dry-run   → 84 partitions would be ensured
vitest run (apps/web, log turbo 01:08)                       → 15 files, 138 tests passed
```

## O que isso significa para o laboratório autônomo

Nada precisa ser reescrito. A fundação (schema completo com partições/RLS/grants para todas as tabelas do pipeline, envelope/streams/idempotência, shell de worker com heartbeat/health/metrics, API multi-tenant) está pronta para receber, do zero: `hunter_exchanges`, `hunter_indicators`, `hunter_risk`, `hunter_core.strategies`, `hunter_core.execution`, os cinco entrypoints de worker, os routers e as páginas. Isso é exatamente o Milestone 1 ao 5 do `docs/ROADMAP.md`, mais Lab, Journal, memória de trade, modo autônomo, watchdog e `obsidian/` pedidos em 2026-09-05. Plano de execução: `docs/plans/M1.md` em diante.
