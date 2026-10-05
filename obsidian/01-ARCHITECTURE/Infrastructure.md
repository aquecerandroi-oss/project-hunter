---
tags: [arquitetura, infra, docker, ci]
updated: 2026-10-05
status: implementado
owner: sexta-feira
---

# Infrastructure

## O que existe hoje

**Docker (dev).** `infra/docker/docker-compose.yml` sobe `postgres:16-alpine`, `redis:7-alpine`, um job `migrate` (`HUNTER_COMMAND=migrate`, roda uma vez e sai), `api` (`HUNTER_ROLE=api`, expõe 8000 e 8001), `worker` (`HUNTER_ROLE=all`) e `web` (Next.js). Volumes só para os dois bancos; tudo o resto é stateless e reconstruído a cada `up --build`. Funciona sem `.env` (defaults de dev no compose); um `.env` na raiz sobrescreve para credenciais reais (Clerk etc.).

**`worker` sai com código 0 imediatamente** — comentário explícito no compose: `hunter_core.runtime.RoleRegistry` ainda está vazio (ver [[Workers]]); os papéis reais chegam no M1.

**Imagens.** `Dockerfile.api-workers`: Python 3.12 slim, `uv sync --frozen`, usuário não-root, `entrypoint.sh` decide entre `HUNTER_COMMAND` (migrate/seed) e `HUNTER_ROLE` (api ou worker, hoje sem processo real). `Dockerfile.web`: Next.js standalone. Tag = SHA do commit; `release` do Sentry usa o mesmo SHA.

**CI (`ci.yml`, GitHub Actions).** Em cada PR e push na `main`: `lint` (ruff, eslint, prettier), `typecheck` (pyright, tsc), `test-python` (pytest com Postgres/Redis como services), `test-web` (vitest), `migrations` (`alembic upgrade head`, `alembic check`, downgrade/upgrade), `types` (gera `packages/shared-types` do OpenAPI, falha se houver diff), `security` (gitleaks, pip-audit, pnpm audit, bandit), `build` (Docker + `next build`), `e2e` (Playwright, só na `main` ou PR com label), `forbidden-patterns` (falha em `sqlite`, `localhost` fora de dev/test, escrita de JSON de estado, `print(` em produção). Deploy só roda se lint→build (1–8) passaram.

**CI vermelho em 05/10 — causas e o que mudou** (reproduzido localmente; detalhe do gitleaks em [[Gitleaks-CI-2026-10-05]]).
- **`python-lint`:** `ruff check` falhava por F401 em `infra/research/tests/test_queue_and_report.py` e por UP031/UP032/B007 em `infra/scripts/research/2026-09-16-r20-sim-saidas-15s.py`. Por trás dele, **`ruff format --check` e `pyright` nunca tinham rodado** (o passo anterior abortava o job): 11 arquivos a formatar (inclusive os blocos ```` ```python ```` de 5 notas de `obsidian/`, que o ruff 0.16 formata; `docs/**` é excluído, `obsidian/**` não) e 228 erros de pyright (scripts de pesquisa sem tipos, fakes de teste que não seguiam o `Protocol` `ChainSource`, `reportPrivateUsage` em testes).
- **`types-drift`:** o job não instalava uv/Python/membros do workspace, e `pnpm gen:types` chama `uv run python infra/scripts/dump_openapi.py` — falhava em ~1 s. Agora tem `setup-uv`, `uv python install` e `uv sync --all-packages` como os outros jobs. O `api.d.ts` versionado confere com a geração local.
- **`python-test`:** saída 2 (coleta interrompida), não falha de teste: `infra/scripts/tests/test_meme_rule_set_pullback.py` usava import relativo numa pasta sem `__init__.py` (os testes irmãos fazem `sys.path.insert` + import simples). Depois dele, `packages/core/tests/unit/test_runtime.py::test_role_registry_starts_empty_for_t03` falhava em execução completa (os `services/*` registram o papel ao importar; `RoleRegistry == {}` só valia isolado).
- **`forbidden-patterns`:** o padrão `print\(` casava `fingerprint(` (agora exige que não haja caractere de identificador antes; `--self-test` cobre os dois lados); docstrings escreviam `ENABLE_LIVE_TRADING=true` literalmente (reescritas); `services/execution-worker/proof/run_proof.py` usava `print`. O script varre ~3000 arquivos rastreados com um `grep` por padrão e arquivo: no Windows passou de 30 min sem terminar (a verificação local foi feita com `git grep` e o mesmo critério por arquivo); o tempo no runner Linux ainda não foi medido neste registro.
- **`security`/gitleaks:** `actions/checkout` com `fetch-depth: 0` e `GITLEAKS_VERSION: 8.30.1` (versão fixada: a padrão da ação, 8.24.3, ignora `allowlists` globais); `.gitleaks.toml` revisado. Config e CI devem ser testados com a mesma versão.

## O que é planejado

- **Ambientes reais** (preview/staging/produção): Vercel (web), Railway ou Fly.io (api/workers), Neon (Postgres), Redis Railway/Upstash. Documentado em [[Deployment]] mas ainda não configurado de fato além de dev local.
- **Escala por papel:** market-worker por número de mercados, scanner por CPU, strategy/execution 1 réplica no MVP — só faz sentido quando os workers existirem (M1+).
- **Alarmes e backups em produção** (Neon PITR, exportação semanal) — dependem de um ambiente de produção real, que ainda não existe.

## Relacionadas

[[System Overview]] · [[Workers]] · [[Deployment]] · [[Environment Variables]] · [[Gitleaks-CI-2026-10-05]]

## Fontes

`docs/DEPLOYMENT.md`, `infra/docker/docker-compose.yml`, `.github/workflows/ci.yml` (via `docs/DEPLOYMENT.md` §4)
