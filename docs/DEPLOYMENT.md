# Deploy e operação

## 1. Ambientes

| Ambiente | Web | API + workers | Postgres | Redis |
|---|---|---|---|---|
| Local | `pnpm dev` ou compose | compose (`HUNTER_ROLE=all`) | compose | compose |
| Preview (PR) | Vercel preview | Railway PR environment (opcional) | Neon branch | Upstash dev |
| Staging | Vercel | Railway (api, market, scanner, strategy, execution, analytics) | Neon branch `staging` | Redis Railway |
| Produção | Vercel | Railway ou Fly.io | Neon `main` (pooler) | Redis Railway / Upstash fixo |

Nada em produção lê arquivo local. Configuração só por env — a lista completa
de variáveis está no §7.

## 2. Imagens

- `infra/docker/Dockerfile.api-workers`: Python 3.12 slim, `uv sync --frozen`, usuário não-root, `ENTRYPOINT infra/docker/entrypoint.sh`: `HUNTER_COMMAND=migrate|seed` executa Alembic ou o seed e sai; caso contrário `HUNTER_ROLE=api` sobe o uvicorn e os papéis de worker (`market|scanner|strategy|execution|analytics|all`) imprimem que ainda não têm entrypoint e saem com 0 até o M1 (sem processo falso).
- `infra/docker/Dockerfile.web`: Next.js standalone (usado só se o web não for na Vercel). `NEXT_PUBLIC_*` são baked no bundle em build time — passar os reais via `--build-arg` num deploy de verdade.
- Tag = SHA do commit; `release` do Sentry = mesmo SHA.

## 3. docker-compose (dev)

Serviços: `postgres:16`, `redis:7`, `migrate` (`HUNTER_COMMAND=migrate`, roda uma vez), `api` (depende do `migrate` concluído), `worker` (`HUNTER_ROLE=all`, sai com 0 até o M1), `web`. Volumes só para os bancos. `docker-compose.test.yml` sobe Postgres (porta 55432) e Redis (porta 56379) efêmeros para testes de integração locais.

Funciona sem nenhum `.env` (usa defaults de dev embutidos no compose para as chaves do Clerk — build/boot não falham, mas o sign-in real não funciona); um `.env` na raiz (gerado por `infra/scripts/setup_env.ps1`, nunca commitado) sobrepõe esses defaults.

- API: `http://localhost:8000` (`/health` = vivo, `/ready` = Postgres + Redis alcançáveis, 200 só quando ambos respondem, `/metrics` atrás de `METRICS_TOKEN`).
- Web: `http://localhost:3000` (redireciona para o sign-in do Clerk).
- `worker` (`HUNTER_ROLE=all`) sobe, imprime que o papel ainda não tem entrypoint e sai com código 0 — `hunter_core.runtime.RoleRegistry` só é populado a partir do Milestone 1; isso é esperado, não uma falha.

Comandos reais (instalação, `.env`, subir a stack, migrar/seedar manualmente,
rodar o web fora do compose) estão no §8.

## 4. CI (GitHub Actions)

`ci.yml` em cada PR e push na `main`:

1. `python-lint` — ruff, ruff format --check, pyright, file-size gate.
2. `python-lint-strict` — tier estrito (`packages/config/ruff.strict.toml`), não bloqueia; conta de violações no job summary.
3. `python-test` — pytest (`unit` + `integration`) com testcontainers.
4. `migrations` — `alembic upgrade head` em banco limpo, `alembic check` (sem drift entre models e migrações), `alembic downgrade -1 && upgrade head`, `create_partitions.py --dry-run`.
5. `node` — eslint, `tsc --noEmit`, vitest, `next build`.
6. `types-drift` — gera `packages/shared-types` do OpenAPI e falha se houver diff não commitado.
7. `e2e` — Playwright contra `docker compose`; sempre roda (`signup-onboarding.spec.ts` se autoexclui sem `CLERK_E2E_*`).
8. `security` — `gitleaks`, `pip-audit --skip-editable`, `bandit`, `pnpm audit --audit-level high`.
9. `forbidden-patterns` — falha se aparecer `sqlite`, `localhost` fora de config de dev/testes, escrita de JSON de estado, `print(` em código de produção.
10. `docker-build` — build das duas imagens (guardado até `infra/docker/Dockerfile.*` existir — já existe desde o M0).
11. `gate` — status obrigatório; verde só se todo job acima, exceto o `-strict`, passou.

Deploy só roda se o `gate` passou. `deploy-api.yml` faz `railway up` por serviço (ou `fly deploy`); `deploy-web.yml` é a integração nativa da Vercel — os dois existem hoje só como esboço (T10), sem execução real documentada. Migrações rodam como job separado **antes** dos serviços novos subirem (`alembic upgrade head` com lock em Redis, quando o deploy automático existir).

## 5. Operação

- Escala: market-worker por número de mercados (1 processo por ~400 mercados); scanner por CPU; strategy e execution 1 réplica cada no MVP (consumer groups permitem N depois); api por conexões WS.
- Health: `/health` (processo vivo), `/ready` (Postgres e Redis alcançáveis). Railway/Fly usam `/ready`.
- Alarmes mínimos: worker `stale` > 60 s; lag de stream > 5 000; erro de exchange > 10/min; partição faltando; Sentry error rate.
- Backups: Neon PITR (7 dias no plano padrão); exportação semanal de `trades`, `audit_logs`, `risk_events` para object storage (Fase 2).

## 6. Playbook de incidente

| Sintoma | Ação |
|---|---|
| Exchange offline | Nada automático além de `data_degraded`; entradas bloqueadas por check 3; posições geridas com último preço; se > 60 s em posição → risk event |
| Redis fora | Workers pausam consumo, mantêm buffer 60 s, marcam `degraded`; api serve REST do Postgres, WS envia `degraded`; ao voltar, hot state reconstrói do Postgres (candles) e das exchanges (book) |
| Postgres lento | Escritas de market data em lote com fila limitada; propostas não são decididas sem persistir (bloqueia entradas); alarme |
| Execution-worker morto | Nenhuma ordem nova; ao subir, reconstrói posições abertas; propostas aprovadas antigas expiram |
| Perda súbita anormal | OWNER aciona kill switch da org (`TRADING_DISABLED`); operador pode acionar `SYSTEM_KILL_SWITCH` |
| Suspeita de vazamento de tenant | Revogar sessão no Clerk; auditar `audit_logs` por `request_id`; RLS é a barreira final |

## 7. Variáveis de ambiente

Fonte da verdade: `packages/core/hunter_core/settings.py` (`Settings`, lido por
`api` e por todo worker) e `apps/api/hunter_api/settings.py` (`ApiSettings`,
estende `Settings` só para `HUNTER_ROLE=api`). `.env.example` espelha os dois
1:1. `Settings._require_settings_in_prod` recusa subir (`ValueError` na
construção) em `HUNTER_ENV=staging|production` se faltar qualquer variável
marcada **obrigatória** abaixo — as demais têm default de dev seguro.

### Ambiente e processo (api + todo worker)

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `HUNTER_ENV` | não | `development` | `development \| test \| staging \| production`; só `production` ativa `is_production` (ex.: fecha `/docs`) |
| `HUNTER_ROLE` | não | `all` | `api \| market \| scanner \| strategy \| execution \| analytics \| all` — escolhe o processo no `entrypoint.sh`. Workers ainda saem com 0 no M0 (`RoleRegistry` vazio até M1) |
| `LOG_LEVEL` | não | `INFO` | nível do `structlog` |
| `WEB_ORIGIN` | **sim** | `http://localhost:3000` | origem(ns) do web, separadas por vírgula; base do CORS quando `CORS_ALLOWED_ORIGINS` não é setado |
| `API_URL` | **sim** | `http://localhost:8000` | usado pelo web server-side (`lib/server/api.ts`) |
| `NEXT_PUBLIC_API_URL` | **sim** | `http://localhost:8000` | base da API para o browser |
| `NEXT_PUBLIC_WS_URL` | **sim** | `ws://localhost:8000/ws` | endpoint do WebSocket para o browser |
| `HEALTH_PORT` | não | `8001` | porta de `/health`, `/ready`, `/metrics` nos processos `HUNTER_ROLE != api` (a `api` expõe os três na própria `API_PORT`) |

### Só `apps/api` (`ApiSettings`)

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `API_PORT` | não | `8000` | porta HTTP do uvicorn |
| `CORS_ALLOWED_ORIGINS` | não | cai para `WEB_ORIGIN` | allowlist exata do middleware CORS, uma ou mais origens separadas por vírgula |
| `RATE_LIMIT_PER_MINUTE` | não | `120` | limite por endereço, antes do roteamento — cobre a superfície não autenticada |
| `RATE_LIMIT_PER_MINUTE_PRINCIPAL` | não | `600` | limite por principal autenticado, checado após verificar o token |
| `ENABLE_OPENAPI_DOCS` | não | `false` | em `HUNTER_ENV=production`, reabre `/docs`, `/redoc`, `/openapi.json` se `true`; em dev/staging ficam sempre abertos |
| `READY_CHECK_TIMEOUT_S` | não | `3.0` | timeout por dependência (Postgres/Redis) em `/ready` |
| `FORWARDED_ALLOW_IPS` | não | `127.0.0.1` | em produção, apontar para o ingress da plataforma — só esse IP tem `X-Forwarded-For` confiado pelo uvicorn |
| `METRICS_TOKEN` | não | vazio | se setado, `/metrics` exige `Authorization: Bearer <token>`; vazio em staging/produção desativa `/metrics` (404) |
| `MAX_REQUEST_BODY_BYTES` | não | `1048576` | limite de corpo em `/api/*`, checado no `Content-Length` e nos bytes efetivamente recebidos |
| `JWKS_REFRESH_COOLDOWN_S` | não | `60.0` | intervalo mínimo entre dois refetches do JWKS disparados por um `kid` desconhecido |
| `JWKS_MAX_STALE_S` | não | `86400.0` | por quanto tempo o JWKS em cache continua valendo enquanto todo refetch falha; depois disso a auth responde 503 |
| `WEBHOOK_CLAIM_STALE_S` | não | `300.0` | tempo que um claim em `processed_events` pode ficar inacabado antes de uma redelivery poder retomá-lo |
| `WS_HANDSHAKES_PER_MINUTE` | não | `30` | handshakes `/ws` por endereço por minuto, checado antes do `accept()`; excedente → 4429 |
| `WS_MAX_CONNECTIONS_PER_PRINCIPAL` | não | `5` | conexões `/ws` vivas por principal neste processo; excedente fecha com 4429 |
| `WS_REVALIDATE_INTERVAL_S` | não | `60.0` | de quanto em quanto tempo um WS aberto revalida a associação do principal; perda de acesso fecha com 4403 |

### Banco e cache

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `DATABASE_URL` | **sim** | `postgresql+asyncpg://hunter:hunter@localhost:5432/hunter` | engine assíncrono (SQLAlchemy 2 + asyncpg) |
| `DATABASE_URL_MIGRATIONS` | não | `postgresql://hunter:hunter@localhost:5432/hunter` | conexão direta (sem pooler) só para o Alembic |
| `REDIS_URL` | **sim** | `redis://localhost:6379/0` | Streams + pub/sub |
| `DB_POOL_SIZE` | não | `5` | tamanho do pool do engine assíncrono |
| `DB_MAX_OVERFLOW` | não | `5` | conexões extras além do pool sob carga |

### Auth (Clerk)

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | web precisa para funcionar (não validado pelo `Settings` do backend) | vazio | chave pública do Clerk, para o browser |
| `CLERK_SECRET_KEY` | **sim** | vazio | chamadas server-side ao Clerk (provisioning just-in-time) |
| `CLERK_WEBHOOK_SECRET` | **sim** — só quando a API é pública (webhook `user.created/updated/deleted` do Clerk chega por HTTP) | vazio | verificação Svix do webhook |
| `CLERK_JWKS_URL` | **sim** | vazio | `https://<instance>.clerk.accounts.dev/.well-known/jwks.json`, cache de chaves para verificar JWT |
| `CLERK_ISSUER` | **sim** | vazio | `iss` esperado no JWT |

### Segredos de aplicação (reservados — nenhum código de produto os lê ainda)

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `AUTH_SECRET` | não (ainda) | vazio | assinatura de tokens internos (tickets de WS, convites) — reservado, nenhum caminho de código o usa no M0 |
| `HUNTER_MASTER_KEY` | não (ainda) | vazio | dev: base64 de 32 bytes; prod: KMS. Reservado |
| `KMS_KEY_ID` | não (ainda) | vazio | Fase 3. Reservado |

### Observabilidade e produto

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `SENTRY_DSN` | não | vazio | sem DSN = Sentry desligado |
| `SENTRY_ENVIRONMENT` | não | `development` | tag de ambiente no Sentry |
| `NEXT_PUBLIC_POSTHOG_KEY` | não | vazio | sem chave = PostHog desligado |
| `NEXT_PUBLIC_POSTHOG_HOST` | não | `https://us.i.posthog.com` | host do PostHog |

### LLM (Fase 2 — ADR `docs/decisions/0002-camada-de-provedores-llm.md`)

Nenhuma destas alimenta o produto no M0 (`hunter_core.llm` ainda não existe;
`ENABLE_LLM_ANALYSIS=false`). `OPENAI_API_KEY`/`OPENAI_MODEL` já têm um
consumidor hoje, mas é **ferramenta de desenvolvimento**, não o produto: o
executor Astra (`infra/scripts/ask_astra.py`, Codex CLI) os lê para pedir uma
segunda opinião fora do fluxo de execução do Claude Code — nunca no caminho
AGENT → PROPOSAL → RISK → EXECUTION (`CLAUDE.md`).

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | não | vazio | reservado para `hunter_core.llm.AnthropicProvider` (Fase 2); não lido por nenhum código no M0 |
| `ANTHROPIC_MODEL` | não | `claude-opus-5` | idem |
| `OPENAI_API_KEY` | não | vazio | **hoje:** só `infra/scripts/ask_astra.py` (dev tooling, opcional, pedido pelo `setup_env.ps1`). **Fase 2:** `hunter_core.llm.OpenAIProvider` |
| `OPENAI_MODEL` | não | `gpt-6-astra` | idem |
| `LLM_PROVIDER` | não | `anthropic` | seleção de provedor (`anthropic \| openai`) para a Fase 2; nenhum código o lê no M0 |
| `LLM_MODEL` | não | vazio (usa o default do provedor) | idem |

### Exchanges (opcionais no MVP)

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | não | vazio | só elevam rate limit de dados públicos; nunca com permissão de saque; usados a partir do M1 |
| `BYBIT_API_KEY` / `BYBIT_API_SECRET` | não | vazio | idem |

### Feature flags de sistema

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `ENABLE_LIVE_TRADING` | não | `false` | live trading; `LiveExecutionAdapter` levanta `LiveTradingDisabled` enquanto for `false` (sempre, até a Fase 4) |
| `ENABLE_SOCIAL_INTELLIGENCE` | não | `false` | Fase 2 |
| `ENABLE_ONCHAIN` | não | `false` | Fase 3 |
| `ENABLE_STRIPE` | não | `false` | Fase 3 |
| `ENABLE_LLM_ANALYSIS` | não | `false` | Fase 2 |
| `ENABLE_ARENA` | não | `false` | M6 |
| `ENABLE_BACKTESTS` | não | `false` | M6 |
| `SYSTEM_KILL_SWITCH` | não | `ACTIVE` | `ACTIVE \| WARNING \| TRADING_DISABLED \| EMERGENCY` — estado inicial do kill switch de sistema (o motor que o transiciona chega no M4) |

### Dimensionamento

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `MARKET_UNIVERSE_SIZE` | não | `200` | tamanho do universo de mercados monitorados (M1) |
| `BOOK_DEPTH` | não | `25` | níveis de book capturados (M1) |
| `TICK_COALESCE_MS` | não | `250` | janela de coalescência de ticks (M1) |
| `FEATURE_THROTTLE_MS` | não | `1000` | cadência de cálculo de features (M2) |
| `RADAR_PUSH_MS` | não | `1000` | cadência de push do Radar (M2) |
| `RETENTION_CANDLES_1M_DAYS` | não | `90` | retenção de candles de 1 minuto |
| `RETENTION_FEATURE_SNAPSHOTS_DAYS` | não | `14` | retenção de snapshots de features |

## 8. Comandos locais reais

Do zero, nesta ordem (`docs/plans/M0.md` tem os pré-requisitos de máquina —
Node 22, pnpm, uv, Docker Desktop):

```powershell
# 1. dependências
pnpm install
uv sync --all-packages

# 2. .env local — pede as chaves do Clerk na tela (nunca aparecem em chat/log)
powershell -ExecutionPolicy Bypass -File infra\scripts\setup_env.ps1

# 3. stack (postgres, redis, migrate, api, worker, web) via Docker
docker compose -f infra/docker/docker-compose.yml up -d --build

# variante: só a infraestrutura de dados, para rodar api/web fora do compose
docker compose -f infra/docker/docker-compose.yml up -d postgres redis migrate api
```

`migrate` roda uma vez (`HUNTER_COMMAND=migrate`, ver abaixo) e sai; `api`
espera `service_completed_successfully` dele. `worker` (`HUNTER_ROLE=all`)
sobe e sai com 0 de propósito — sem entrypoint real até o M1.

### Web fora do compose (`pnpm dev`)

Para desenvolver o Next.js com hot reload real (o compose builda uma imagem
`standalone`, sem watch):

```bash
cd apps/web
API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws \
WEB_ORIGIN=http://localhost:3000 \
pnpm dev
```

As chaves do Clerk (`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`)
vêm do `.env` da raiz — o Next.js já o lê automaticamente (`dotenv` embutido).
`apps/api` precisa estar de pé (compose, passo 3, serviços `postgres redis
migrate api`) para o `api-client` e o SSR terem o que chamar.

### Migrate e seed manuais (`HUNTER_COMMAND`)

`migrate`/`seed` não são valores de `HUNTER_ROLE` (que só aceita os papéis
reais de processo) — são acionados pela variável separada `HUNTER_COMMAND`,
lida primeiro pelo `entrypoint.sh`:

```bash
# upgrade head dentro da rede do compose (reaproveita a imagem hunter-api:dev)
docker compose -f infra/docker/docker-compose.yml run --rm migrate

# comando explícito também funciona (um argumento sempre vence o dispatch de role)
docker compose -f infra/docker/docker-compose.yml run --rm migrate \
  alembic -c infra/migrations/alembic.ini check

docker compose -f infra/docker/docker-compose.yml run --rm \
  -e HUNTER_COMMAND=seed migrate
```

Rodar o Alembic direto do host (`uv run alembic -c infra/migrations/alembic.ini
upgrade head`) só funciona se `DATABASE_URL_MIGRATIONS` apontar para um
Postgres alcançável do host — o `postgres` do `docker-compose.yml` **não**
publica a porta 5432 no host de propósito (só os serviços do próprio compose
o alcançam). Para isso, ou use `docker-compose.test.yml` (expõe
`localhost:55432`, ver `infra/docker/docker-compose.test.yml`), ou rode via
`docker compose run --rm migrate` acima.

### Testes de integração locais sem testcontainers

```bash
docker compose -f infra/docker/docker-compose.test.yml up -d   # Postgres em 55432, Redis em 56379
DATABASE_URL_MIGRATIONS=postgresql://hunter:hunter@localhost:55432/hunter_test \
  uv run alembic -c infra/migrations/alembic.ini upgrade head
uv run pytest -m integration
docker compose -f infra/docker/docker-compose.test.yml down -v
```

CI usa testcontainers direto (`tests/integration/README.md`,
`apps/api/tests/integration/conftest.py`); isto é só a conveniência local.
