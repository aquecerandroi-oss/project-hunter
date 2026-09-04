# Deploy e operação

## 1. Ambientes

| Ambiente | Web | API + workers | Postgres | Redis |
|---|---|---|---|---|
| Local | `pnpm dev` ou compose | compose (`HUNTER_ROLE=all`) | compose | compose |
| Preview (PR) | Vercel preview | Railway PR environment (opcional) | Neon branch | Upstash dev |
| Staging | Vercel | Railway (api, market, scanner, strategy, execution, analytics) | Neon branch `staging` | Redis Railway |
| Produção | Vercel | Railway ou Fly.io | Neon `main` (pooler) | Redis Railway / Upstash fixo |

Nada em produção lê arquivo local. Configuração só por env.

## 2. Imagens

- `infra/docker/Dockerfile.api-workers`: Python 3.12 slim, `uv sync --frozen`, usuário não-root, `CMD ["python", "-m", "hunter_core.runtime"]` que lê `HUNTER_ROLE`.
- `infra/docker/Dockerfile.web`: Next.js standalone (usado só se o web não for na Vercel).
- Tag = SHA do commit; `release` do Sentry = mesmo SHA.

## 3. docker-compose (dev)

Serviços: `postgres:16`, `redis:7`, `api`, `worker` (`HUNTER_ROLE=all`), `web`. Volumes só para os bancos. `docker-compose.test.yml` sobe Postgres e Redis efêmeros para testes de integração.

## 4. CI (GitHub Actions)

`ci.yml` em cada PR e push na `main`:

1. `lint` — ruff, eslint, prettier check.
2. `typecheck` — pyright, `tsc --noEmit`.
3. `test-python` — pytest com Postgres e Redis como services; cobertura mínima 80 % em `hunter_risk`, `hunter_indicators`, `hunter_core.execution`.
4. `test-web` — vitest.
5. `migrations` — `alembic upgrade head` em banco limpo, `alembic check` (sem drift entre models e migrações), `alembic downgrade -1 && upgrade head` para a última migração.
6. `types` — gera `packages/shared-types` do OpenAPI e falha se houver diff não commitado.
7. `security` — `gitleaks`, `pip-audit`, `pnpm audit --audit-level high`, `bandit`.
8. `build` — Docker build da imagem api/workers; `next build`.
9. `e2e` — Playwright contra compose (só na `main` e em PRs com label `e2e`).
10. `forbidden-patterns` — falha se aparecer `sqlite`, `localhost` fora de config de dev/testes, escrita de JSON de estado, `print(` em código de produção.

Deploy só roda se 1–8 passaram. `deploy-api.yml` faz `railway up` por serviço (ou `fly deploy`); `deploy-web.yml` é a integração nativa da Vercel. Migrações rodam como job separado **antes** dos serviços novos subirem (`alembic upgrade head` com lock em Redis).

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
