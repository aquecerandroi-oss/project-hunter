# Arquitetura — PROJECT HUNTER

Plataforma SaaS de inteligência quantitativa para criptomoedas. Este documento é a referência de arquitetura. Decisões e justificativas estão em `SPEC_REVIEW.md`; o fluxo de dados detalhado em `PIPELINE.md`; o schema em `DATABASE.md`.

## 1. Princípios

1. **Cloud-first.** Nenhum estado em arquivo local. Postgres é a fonte de verdade durável; Redis é estado quente e transporte de eventos.
2. **Orientado a eventos.** Cada etapa consome eventos de um stream e publica em outro. A ordem do pipeline é ordem de dependência de dados, não chamadas síncronas.
3. **Dados globais, decisões por tenant.** Market data, features, anomalias, regime, oportunidades e sinais são computados uma vez e compartilhados. Portfolios, propostas, ordens, posições, trades e risco pertencem a uma organização.
4. **Nenhum agente executa.** Agente produz sinal. Sinal vira proposta por portfolio. Proposta passa pelo Risk Engine. Só proposta aprovada chega ao Execution Engine.
5. **Explicável.** Toda decisão persiste sua decomposição (features, pesos, checks de risco) no momento em que foi tomada.
6. **Degradação segura.** Qualquer falha de dado, worker ou LLM leva o sistema para "não abrir posições novas", nunca para "executar algo inseguro".
7. **Uma imagem, vários papéis.** O backend Python é um único artefato Docker; a variável `HUNTER_ROLE` escolhe qual processo roda.

## 2. Stack final

| Camada | Escolha | Observações |
|---|---|---|
| Frontend | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS 4, shadcn/ui, TanStack Table/Query, Recharts para gráficos simples, lightweight-charts (TradingView OSS) para candles | Server Components por padrão; client components em tabelas realtime, gráficos e formulários |
| Auth | Clerk | Identidade, sessões, e-mail, reset de senha, social login. Organizações e RBAC no nosso banco. |
| API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic | OpenAPI gerado; tipos TypeScript gerados a partir dele |
| Workers | Mesmo código Python; `asyncio`; `HUNTER_ROLE` | Ver §4 |
| Numérico | NumPy, Polars | Sem pandas no hot path |
| Banco | PostgreSQL 16 (Neon em produção) | Partições mensais; RLS |
| Cache / eventos | Redis 7 (protocolo padrão; Upstash ou Railway/Fly) | Streams, pub/sub, hashes, sorted sets, rate limiting |
| Filas robustas | Não agora. Interface `JobRunner` abstrai; Temporal é o candidato | Só quando houver workflows longos (backtests grandes, reconciliação live) |
| Observabilidade | Sentry, logs JSON estruturados (structlog), métricas Prometheus-style expostas por `/metrics`, health endpoints | |
| Product analytics | PostHog | Eventos listados em `PRODUCT.md` |
| LLM | Anthropic API (`claude-opus-5` padrão; modelo configurável) | Desligada no MVP; `ENABLE_LLM_ANALYSIS` |
| Frontend hosting | Vercel | |
| Backend hosting | Railway (padrão de referência), compatível com Render, Fly.io, AWS ECS | Dockerfile único |
| CI/CD | GitHub Actions | `DEPLOYMENT.md` |
| Monorepo | pnpm workspaces + Turborepo (TS); `uv` workspace (Python) | |
| Testes | pytest, pytest-asyncio, testcontainers; Vitest; Playwright | |

### Por que Clerk
Ver `SECURITY.md` §1. Resumo: requisito de "não implementar autenticação própria insegura" mais fluxo completo (confirmação de e-mail, reset, sessões, social) sem código nosso; JWT verificável no FastAPI sem chamada de rede por request (JWKS em cache); custo zero até 10k MAU; frontend Next.js de primeira classe. O que **não** usamos do Clerk: Organizations e Roles. Multi-tenant e RBAC vivem no nosso Postgres, porque o isolamento financeiro precisa ser aplicado no banco e no backend, não num provedor externo.

## 3. Topologia

```
                     ┌──────────────────────────┐
   Browser ◄───────► │  apps/web  (Next.js)     │  Vercel
      │              │  SSR / RSC / rotas        │
      │  WS          └───────────┬──────────────┘
      │                          │ REST (Bearer JWT Clerk)
      ▼                          ▼
   ┌─────────────────────────────────────────────┐
   │  apps/api  (FastAPI)          HUNTER_ROLE=api│  Railway / Fly
   │  REST /api/v1  ·  WS /ws  ·  /health /metrics│
   └──────┬──────────────────────────┬───────────┘
          │ SQL (pooler)             │ Redis (streams, pub/sub, cache)
          ▼                          ▼
   ┌──────────────┐          ┌──────────────────┐
   │  PostgreSQL  │◄────────►│      Redis        │
   │   (Neon)     │          │ (Upstash/Railway) │
   └──────▲───────┘          └───────▲──────────┘
          │                          │
   ┌──────┴──────────────────────────┴──────────────────────────────────┐
   │  Workers (mesma imagem Docker, um processo por HUNTER_ROLE)         │
   │                                                                      │
   │  market-worker     WS Binance/Bybit → normaliza → Redis hot state    │
   │                    → candles 1m no Postgres → stream market.*        │
   │  scanner-worker    features → anomalias → regime → opportunity       │
   │  strategy-worker   agentes → sinais → propostas por portfolio → risk │
   │  execution-worker  propostas aprovadas → paper/shadow fills          │
   │                    → posições → trades → PnL                         │
   │  analytics-worker  equity snapshots, estatísticas, retenção, outcomes│
   └──────────────────────────────────────────────────────────────────────┘
```

Em desenvolvimento e em deployments pequenos, `HUNTER_ROLE=all` roda todos os workers em um processo com tasks `asyncio`. Em produção cada papel é um serviço separado, escalável e reiniciável isoladamente.

## 4. Serviços e responsabilidades

| Serviço | Papel | Cadência | Escreve em | Publica |
|---|---|---|---|---|
| `api` | REST, WebSocket gateway, auth, RBAC, onboarding, CRUD | request | Postgres (via repositórios tenant-scoped) | `audit`, `rt:*` |
| `market-worker` | Conexões WebSocket com exchanges, recovery REST, normalização, universo de mercados, book em memória, candles | contínuo | Redis hot state; Postgres `candles`, `market_snapshots`, `funding_rates`, `open_interest_history`, `liquidations` | `market.ticks`, `market.candles.closed`, `market.book`, `market.liquidations`, `market.derivatives` |
| `scanner-worker` | Feature Engine, Anomaly Engine, Regime Engine, Opportunity Engine | evento + 1 min | `feature_snapshots`, `anomalies`, `market_regimes`, `opportunities`, `opportunity_history` | `features.updated`, `anomalies.detected`, `regime.changed`, `opportunities.updated` |
| `strategy-worker` | Agentes (estratégias), consenso, geração de propostas por portfolio, Risk Engine | evento | `agent_signals`, `trade_proposals`, `risk_events` | `signals.emitted`, `proposals.decided` |
| `execution-worker` | ExecutionAdapter (paper, shadow; live desativado), ordens, fills, posições, trades, stops e alvos, kill switch enforcement | evento + 1 s (marcação a mercado) | `orders`, `fills`, `positions`, `trades`, `portfolio_equity_snapshots` | `executions.completed`, `positions.updated`, `risk.events` |
| `analytics-worker` | Estatísticas por agente/estratégia/regime, `signal_outcomes` (shadow de sistema), jobs de retenção, heartbeats consolidados | 1 min / 1 h / diário | `agent_stats`, `signal_outcomes`, `system_events` | `analytics.updated` |

**Isolamento do execution-worker.** É o único processo que, no futuro, terá acesso a chaves descriptografadas de exchange. Ele não expõe HTTP além de `/health`. O `api` nunca descriptografa chaves.

## 5. Comunicação

### 5.1 Redis Streams (worker → worker)
Cada evento tem envelope fixo:

```json
{
  "event_id": "uuid7",
  "type": "opportunities.updated",
  "ts": "2026-09-04T12:00:00.250Z",
  "producer": "scanner-worker@host:pid",
  "key": "binance:BTCUSDT",
  "payload": { }
}
```

- Streams com `MAXLEN ~ N` (aparado) por tipo; consumer groups por serviço consumidor; `XAUTOCLAIM` para mensagens presas de instância morta.
- Idempotência: consumidor grava `event_id` em `hunter:processed:{consumer}` (SET, TTL 24h) antes de agir sobre efeitos duráveis; efeitos duráveis também têm chave única no Postgres.
- Lista completa de streams, produtores e consumidores em `PIPELINE.md`.

### 5.2 Redis pub/sub (workers → api → browser)
Canais `rt:market:{exchange}:{symbol}`, `rt:radar`, `rt:org:{org_id}:portfolio:{id}`, `rt:org:{org_id}:risk`, `rt:system`. O `api` assina apenas os canais que algum cliente WebSocket pediu, com autorização por organização, e reenvia com throttling (250 ms para preços, 1 s para radar, imediato para risk events).

### 5.3 Redis hot state
| Chave | Tipo | Conteúdo | TTL |
|---|---|---|---|
| `mkt:{ex}:{sym}:ticker` | HASH | último preço, bid, ask, volume 24h, ts | 30 s |
| `mkt:{ex}:{sym}:book` | STRING (msgpack) | top 25 níveis | 10 s |
| `mkt:{ex}:{sym}:trades` | LIST (ring, LTRIM 2000) | últimos trades | — |
| `mkt:{ex}:{sym}:candles:1m` | LIST (LTRIM 1500) | últimos 1500 candles | — |
| `mkt:{ex}:{sym}:deriv` | HASH | OI, funding, mark, index | 120 s |
| `feat:{ex}:{sym}` | HASH | features atuais + versão | 120 s |
| `opp:{ex}:{sym}` | HASH | score, confidence, status, decomposition | 300 s |
| `radar:scores` | ZSET | symbol → opportunity score | — |
| `regime:current` | HASH | regime, confidence, since | — |
| `ks:system` / `ks:org:{id}` / `ks:pf:{id}` | STRING | estado do kill switch | — |
| `hb:{role}:{instance}` | HASH | heartbeat, last_success, errors | 30 s |
| `rl:{exchange}:{bucket}` | STRING | token bucket para REST | 1 s |
| `lock:{name}` | STRING | locks distribuídos (SET NX PX) | variável |

O que está em Redis pode ser perdido. Tudo que importa para auditoria ou contabilidade está no Postgres.

## 6. Interfaces entre módulos (PASSO 6)

Definições em Python (pacote `hunter_core`); nomes finais.

```python
# packages/exchange-adapters — hunter_exchanges
class ExchangeAdapter(Protocol):
    code: str                                    # "binance" | "bybit"
    async def list_markets(self, market_type: MarketType) -> list[NormalizedMarket]: ...
    async def fetch_candles(self, symbol, timeframe, start, end) -> list[NormalizedCandle]: ...
    async def fetch_ticker(self, symbol) -> NormalizedTicker: ...
    async def fetch_order_book(self, symbol, depth=25) -> NormalizedOrderBook: ...
    async def fetch_funding(self, symbol) -> NormalizedFunding: ...
    async def fetch_open_interest(self, symbol) -> NormalizedOpenInterest: ...
    def stream(self, symbols, channels) -> AsyncIterator[NormalizedEvent]: ...  # WS
    # privado (pós-MVP, só execution-worker):
    async def place_order(self, req: OrderRequest) -> OrderAck: ...
    async def cancel_order(self, id) -> None: ...
    async def fetch_permissions(self) -> ApiKeyPermissions: ...

# packages/indicators — hunter_indicators
class FeatureCalculator(Protocol):
    definition: FeatureDefinition               # name, version, params, description
    requires: set[str]                          # inputs: "candles:1m", "book", "trades", "deriv"
    def compute(self, ctx: MarketContext) -> dict[str, float]: ...

class AnomalyDetector(Protocol):
    anomaly_type: AnomalyType
    def evaluate(self, features: FeatureVector, history: FeatureHistory) -> Anomaly | None: ...

class RegimeClassifier(Protocol):
    version: str
    def classify(self, btc_ctx: MarketContext, breadth: MarketBreadth) -> RegimeAssessment: ...

class OpportunityScorer(Protocol):
    weights_version: str
    def score(self, features, anomalies, regime, signals) -> OpportunityAssessment: ...
    # retorna score, confidence, direction, decomposition[component] = {raw, weight, contribution}

# packages/core — hunter_core.strategies
class Strategy(Protocol):
    key: str; version: str; parameters_schema: type[BaseModel]
    def evaluate(self, ctx: MarketContext, opp: OpportunityAssessment, regime, params) -> Signal | None: ...
    # Signal: market, direction, confidence, entry_zone, stop, targets, invalidations,
    #         expected_holding, reason, supporting_features

# packages/risk-core — hunter_risk
class RiskEngine(Protocol):
    def evaluate(self, proposal: TradeProposal, portfolio: PortfolioState,
                 limits: RiskLimits, market: MarketLiquidity, ks: KillSwitchState) -> RiskDecision: ...
    # RiskDecision: approved: bool, sized_qty, sized_notional, risk_pct, checks: list[RiskCheck]
    # RiskCheck: name, passed, value, limit, message

# packages/core — hunter_core.execution
class ExecutionAdapter(Protocol):
    mode: ExecutionMode                         # PAPER | SHADOW | LIVE
    async def submit(self, order: OrderIntent, market: MarketState) -> ExecutionResult: ...
    async def cancel(self, order_id) -> None: ...
    async def mark_to_market(self, positions, prices) -> list[PositionUpdate]: ...
```

Regras: `Strategy.evaluate` é uma função pura (sem IO); `RiskEngine.evaluate` é pura e determinística (testável com tabelas de casos); `ExecutionAdapter` é o único lugar com efeitos de execução.

## 7. Estrutura do monorepo (PASSO 4)

```
project-hunter/
├── apps/
│   ├── web/                          # Next.js (Vercel)
│   │   ├── app/
│   │   │   ├── (auth)/sign-in, sign-up, forgot-password
│   │   │   ├── (onboarding)/onboarding/[step]
│   │   │   ├── (app)/[orgSlug]/
│   │   │   │   ├── dashboard/  radar/  markets/[exchange]/[symbol]/
│   │   │   │   ├── opportunities/  portfolio/  trades/[id]/
│   │   │   │   ├── agents/[id]/  arena/  strategies/  backtests/
│   │   │   │   ├── analytics/  intelligence/  risk/  exchanges/
│   │   │   │   ├── alerts/  system/  settings/(profile|organization|members|security|risk|notifications|api|billing|appearance)
│   │   │   └── api/                  # route handlers só para webhooks (Clerk)
│   │   ├── components/ (ui/, layout/, radar/, charts/, portfolio/, risk/ ...)
│   │   ├── lib/ (api-client.ts, auth.ts, ws.ts, nav-registry.ts, feature-flags.ts, format.ts)
│   │   ├── hooks/
│   │   └── tests/ (vitest)
│   └── api/                          # FastAPI — pacote hunter_api
│       ├── hunter_api/
│       │   ├── main.py  app.py  deps.py  settings.py
│       │   ├── auth/         (clerk_verifier.py, principal.py, rbac.py)
│       │   ├── routers/      (orgs, workspaces, onboarding, markets, radar, opportunities,
│       │   │                  portfolios, trades, agents, risk, analytics, system, audit, ws)
│       │   ├── schemas/      (Pydantic request/response)
│       │   ├── services/     (casos de uso; chamam repositórios)
│       │   ├── realtime/     (redis_bridge.py, ws_manager.py, throttle.py)
│       │   └── middleware/   (request_id, rate_limit, security_headers, tenant_context)
│       ├── tests/
│       └── pyproject.toml
├── services/                         # entrypoints finos; lógica está em packages/
│   ├── market-worker/     hunter_market_worker/  (ingest.py, universe.py, recovery.py, persist.py)
│   ├── scanner-worker/    hunter_scanner_worker/ (feature_runner.py, anomaly_runner.py, regime_runner.py, opportunity_runner.py)
│   ├── strategy-worker/   hunter_strategy_worker/(agent_runner.py, proposal_builder.py, risk_gate.py)
│   ├── execution-worker/  hunter_execution_worker/(paper.py, shadow.py, position_manager.py, mtm.py)
│   └── analytics-worker/  hunter_analytics_worker/(stats.py, outcomes.py, retention.py, equity.py)
├── packages/
│   ├── core/              hunter_core     # settings, db (models, session, RLS), redis, events (envelopes, streams),
│   │                                      # domain (enums, value objects), strategies base, execution base, audit, logging, worker runtime
│   ├── exchange-adapters/ hunter_exchanges # base.py, binance/, bybit/, normalization.py, rate_limit.py, testing/ (fixtures gravadas)
│   ├── indicators/        hunter_indicators# features/ (registry.py, price.py, volume.py, volatility.py, orderflow.py, derivatives.py),
│   │                                      # anomalies/, regime/, opportunity/
│   ├── risk-core/         hunter_risk     # limits.py, checks/, sizing.py, kill_switch.py, engine.py
│   ├── shared-types/                      # TS gerado do OpenAPI (openapi-typescript) + enums espelhados
│   └── config/                            # eslint, tsconfig, tailwind preset, ruff/pyright base
├── infra/
│   ├── docker/            Dockerfile.api-workers  Dockerfile.web  docker-compose.yml  docker-compose.test.yml
│   ├── migrations/        alembic.ini  env.py  versions/
│   └── scripts/           seed.py  create_partitions.py  gen_types.sh  check_migrations.sh
├── docs/                  (este diretório)
├── tests/
│   ├── integration/       (api + db + redis via testcontainers)
│   └── e2e/               (Playwright)
├── .github/workflows/     ci.yml  deploy-api.yml  deploy-web.yml
├── pyproject.toml         (uv workspace)
├── package.json  pnpm-workspace.yaml  turbo.json
├── .env.example
└── README.md
```

Convenções: nomes de pacotes Python com prefixo `hunter_`; rotas do frontend sob `[orgSlug]` para tornar a organização explícita na URL; nenhum código de domínio em `services/` (só composição e loop).

## 8. Frontend

- **Auth:** middleware do Clerk protege `(app)` e `(onboarding)`. Server Components chamam o `api` com o token da sessão.
- **Contexto de organização:** `[orgSlug]` na URL; o `api` valida membership em cada request. Trocar de organização é trocar de URL.
- **Dados:** Server Components para carga inicial (SSR); TanStack Query para mutações e refetch; hook `useRealtime(channel)` para WS com reconexão e fallback para polling de 5 s se o WS cair.
- **Tabelas:** TanStack Table com virtualização a partir de 200 linhas (Radar, Trades).
- **Navegação:** `lib/nav-registry.ts` é a única fonte da sidebar, com `status` e `minRole` por item.
- **Mobile:** layout de overview com cards; tabelas viram listas de cards; kill switch sempre acessível.
- **Tema:** dark-first com tokens; light suportado desde o M0 (custo baixo se feito no início).

## 9. Backend (api)

- Versionamento de rota: `/api/v1/...`. Rotas com tenant: `/api/v1/orgs/{org_id}/...`.
- Dependências: `current_principal` (verifica JWT), `current_org(role>=X)` (carrega membership, aplica `SET LOCAL app.current_org`), `rate_limited`.
- Repositórios tenant-scoped: `TenantRepository(session, org_id)`; toda query passa por eles. Repositórios globais (`MarketRepository`) só leitura para tenants.
- Erros em formato RFC 9457 (`application/problem+json`).
- Paginação por cursor em toda lista.
- Audit: decorator `@audited(action, entity)` nos serviços que mutam.

## 10. Ambiente e configuração

Uma classe `Settings` (pydantic-settings) em `hunter_core.settings`, carregada de variáveis de ambiente. Nenhum arquivo `.env` é lido em produção. `feature_flags` do sistema têm valor padrão em env (`ENABLE_*`) e podem ser sobrescritas na tabela `feature_flags` sem redeploy. Lista completa em `.env.example`.

## 11. Observabilidade

- Logs JSON com `request_id`, `org_id`, `role`, `event_id`.
- `/health` (liveness), `/ready` (Postgres + Redis), `/metrics` em cada processo.
- Heartbeat por worker em Redis (`hb:*`) e consolidado a cada minuto em `worker_heartbeats`.
- Sentry em `api` e workers com `release` = SHA do commit.
- Métricas mínimas: eventos por stream (produzidos, consumidos, lag), latência por exchange, gaps de candle, propostas aprovadas/rejeitadas por check, fills simulados, erro por worker.

## 12. Ordem de implementação

Ver `ROADMAP.md`. O MVP é M0 a M5. Nada de live trading antes da Fase 4.
