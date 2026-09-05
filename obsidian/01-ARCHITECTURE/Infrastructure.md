---
tags: [arquitetura, infra, docker, ci]
updated: 2026-09-05
status: implementado
---

# Infrastructure

## O que existe hoje

**Docker (dev).** `infra/docker/docker-compose.yml` sobe `postgres:16-alpine`, `redis:7-alpine`, um job `migrate` (`HUNTER_COMMAND=migrate`, roda uma vez e sai), `api` (`HUNTER_ROLE=api`, expõe 8000 e 8001), `worker` (`HUNTER_ROLE=all`) e `web` (Next.js). Volumes só para os dois bancos; tudo o resto é stateless e reconstruído a cada `up --build`. Funciona sem `.env` (defaults de dev no compose); um `.env` na raiz sobrescreve para credenciais reais (Clerk etc.).

**`worker` sai com código 0 imediatamente** — comentário explícito no compose: `hunter_core.runtime.RoleRegistry` ainda está vazio (ver [[Workers]]); os papéis reais chegam no M1.

**Imagens.** `Dockerfile.api-workers`: Python 3.12 slim, `uv sync --frozen`, usuário não-root, `entrypoint.sh` decide entre `HUNTER_COMMAND` (migrate/seed) e `HUNTER_ROLE` (api ou worker, hoje sem processo real). `Dockerfile.web`: Next.js standalone. Tag = SHA do commit; `release` do Sentry usa o mesmo SHA.

**CI (`ci.yml`, GitHub Actions).** Em cada PR e push na `main`: `lint` (ruff, eslint, prettier), `typecheck` (pyright, tsc), `test-python` (pytest com Postgres/Redis como services), `test-web` (vitest), `migrations` (`alembic upgrade head`, `alembic check`, downgrade/upgrade), `types` (gera `packages/shared-types` do OpenAPI, falha se houver diff), `security` (gitleaks, pip-audit, pnpm audit, bandit), `build` (Docker + `next build`), `e2e` (Playwright, só na `main` ou PR com label), `forbidden-patterns` (falha em `sqlite`, `localhost` fora de dev/test, escrita de JSON de estado, `print(` em produção). Deploy só roda se lint→build (1–8) passaram.

## O que é planejado

- **Ambientes reais** (preview/staging/produção): Vercel (web), Railway ou Fly.io (api/workers), Neon (Postgres), Redis Railway/Upstash. Documentado em [[Deployment]] mas ainda não configurado de fato além de dev local.
- **Escala por papel:** market-worker por número de mercados, scanner por CPU, strategy/execution 1 réplica no MVP — só faz sentido quando os workers existirem (M1+).
- **Alarmes e backups em produção** (Neon PITR, exportação semanal) — dependem de um ambiente de produção real, que ainda não existe.

## Relacionadas

[[System Overview]] · [[Workers]] · [[Deployment]] · [[Environment Variables]]

## Fontes

`docs/DEPLOYMENT.md`, `infra/docker/docker-compose.yml`, `.github/workflows/ci.yml` (via `docs/DEPLOYMENT.md` §4)
