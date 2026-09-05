# PROJECT HUNTER

Autonomous Crypto Intelligence & Trading SaaS. Plataforma multi-tenant de inteligência quantitativa para criptomoedas: monitora mercados em tempo real, detecta anomalias, pontua oportunidades, gera sinais por agentes, aplica risco e executa em paper e shadow. Live trading só na Fase 4.

**Estado atual:** Milestone 0 entregue em 2026-09-05 (em fechamento — ver `docs/reports/M0.md`); Milestone 1 (market data) é o próximo.

## Quickstart (desenvolvedor novo)

Pré-requisitos (versões verificadas em `.claude/state/milestone.json`):

| Ferramenta | Versão | Instalar (Windows) |
|---|---|---|
| Node.js | 22+ (verificado com 24.20) | `winget install OpenJS.NodeJS.LTS` |
| pnpm | 10+ (verificado com 11.25) | `corepack enable && corepack prepare pnpm@latest --activate` |
| uv | última (instala Python 3.12 sozinho) | `winget install astral-sh.uv` |
| Docker Desktop | última (WSL2) | `winget install Docker.DockerDesktop` |
| Conta Clerk (dev) | — | https://clerk.com — instância de teste, chaves nunca vão para o repo |

```powershell
# 1. dependências (workspace pnpm + workspace uv)
pnpm install
uv sync --all-packages

# 2. .env local — pede as chaves do Clerk na tela, digitação oculta,
#    nunca aparecem em chat/log/commit
powershell -ExecutionPolicy Bypass -File infra\scripts\setup_env.ps1

# 3. sobe postgres, redis, roda a migração e sobe api + web
docker compose -f infra/docker/docker-compose.yml up -d --build
```

- API: http://localhost:8000 (`/health`, `/ready`, `/docs`)
- Web: http://localhost:3000 (redireciona para o sign-in do Clerk)
- `/_design`: página de tokens de design (paleta, tipografia, componentes) — só existe em desenvolvimento, nunca em produção

Para desenvolver o web com hot reload real em vez da imagem `standalone` do
compose, rode `pnpm dev` dentro de `apps/web` com `apps/api` de pé — comando
completo e variáveis em `docs/DEPLOYMENT.md` §8.

**Comandos de verificação** (os mesmos do CI e do `CLAUDE.md`):

```bash
pnpm lint && uv run ruff check . && uv run ruff format --check .
pnpm typecheck && uv run pyright
pnpm test && uv run pytest
pnpm build
```

Documentação completa: `docs/DEPLOYMENT.md` (ambientes, variáveis de
ambiente, Docker, CI/CD, operação) e `CLAUDE.md` (regras do agente, comandos
canônicos, roster de especialistas). `docs/ROADMAP.md` tem o escopo de cada
milestone; `docs/plans/M0.md` o plano de execução do M0 e `docs/reports/M0.md`
o relatório de fechamento.

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/SPEC_REVIEW.md](docs/SPEC_REVIEW.md) | Revisão crítica da especificação, decisões e riscos |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Stack, topologia, serviços, interfaces, árvore do monorepo |
| [docs/PIPELINE.md](docs/PIPELINE.md) | Market → Features → Anomaly → Regime → Opportunity → Agent → Risk → Execution |
| [docs/DATABASE.md](docs/DATABASE.md) | Schema, RLS, particionamento, retenção |
| [docs/RISK_ENGINE.md](docs/RISK_ENGINE.md) | Limites, checks, sizing, kill switch |
| [docs/SECURITY.md](docs/SECURITY.md) | Auth (Clerk), RBAC, isolamento, segredos |
| [docs/EXCHANGE_INTEGRATION.md](docs/EXCHANGE_INTEGRATION.md) | Adapters Binance e Bybit, normalização, resiliência |
| [docs/MVP.md](docs/MVP.md) | Escopo exato do MVP e critérios de sucesso |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Milestones 0–6 e fases 2–4 |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Ambientes, Docker, CI/CD, operação |
| [docs/PRODUCT.md](docs/PRODUCT.md) | Onboarding, navegação, planos, analytics de produto |
| [docs/EXTERNAL_SERVICES.md](docs/EXTERNAL_SERVICES.md) | Serviços externos por fase |
| [docs/DEV_TOOLING.md](docs/DEV_TOOLING.md) | Ferramentas e MCPs para o desenvolvimento |
| [docs/DESIGN.md](docs/DESIGN.md) | Identidade visual: paleta dourado/verde/preto/branco, tokens, regras de uso |
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | Fluxo de desenvolvimento com Claude Code (vibe-coding-toolkit): ondas, revisão, commits, gates, memória |
| [docs/plans/M0.md](docs/plans/M0.md) | Plano de execução do Milestone 0 em ondas paralelas |
| [docs/decisions/](docs/decisions/README.md) | ADRs (camada dois da memória do projeto) |
| [CLAUDE.md](CLAUDE.md) | Instruções para o agente: regras, comandos canônicos, roster de especialistas |

## Estrutura

```
apps/        web (Next.js) · api (FastAPI)
services/    market-worker · scanner-worker · strategy-worker · execution-worker · analytics-worker
packages/    core · exchange-adapters · indicators · risk-core · shared-types · config
infra/       docker · migrations · scripts
tests/       integration · e2e
docs/
```

## Docker

Uma imagem para api + workers (`HUNTER_ROLE` escolhe o processo) e uma para o web, mais um `docker-compose.yml` de desenvolvimento e um `docker-compose.test.yml` só com Postgres/Redis (`docs/DEPLOYMENT.md` §2–§3 tem os detalhes).

```sh
# build manual das duas imagens
docker build -f infra/docker/Dockerfile.api-workers -t hunter-api:dev --build-arg GIT_SHA=$(git rev-parse --short HEAD) .
docker build -f infra/docker/Dockerfile.web -t hunter-web:dev --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_... .

# stack completa de dev (postgres, redis, migrate, api, worker, web)
docker compose -f infra/docker/docker-compose.yml up -d --build
```

Funciona sem nenhum arquivo `.env` (usa os defaults de dev do próprio compose); um `.env` na raiz (nunca commitado) sobrepõe esses defaults — por exemplo com chaves reais do Clerk para o login funcionar de verdade.

- API: `http://localhost:8000` (`/health` = vivo, `/ready` = Postgres + Redis alcançáveis, 200 só quando ambos respondem).
- Web: `http://localhost:3000` (redireciona para o sign-in até haver chaves reais do Clerk em `.env`).
- `worker` (`HUNTER_ROLE=all`) sobe, imprime que o papel ainda não tem entrypoint e sai com código 0 — `hunter_core.runtime.RoleRegistry` só é populado a partir do Milestone 1; isso é esperado, não uma falha.

Para testes de integração locais sem testcontainers:

```sh
docker compose -f infra/docker/docker-compose.test.yml up -d   # Postgres em 55432, Redis em 56379
docker compose -f infra/docker/docker-compose.test.yml down -v
```

## Regras inegociáveis

- Nenhum agente executa ordens. Toda entrada passa pelo Risk Engine.
- Nenhum dado de produção em arquivo local, SQLite ou navegador.
- Nenhum mock, botão inerte, gráfico falso ou número inventado em produção.
- Segredos só em variáveis de ambiente do provedor. Nunca no frontend, no repositório ou em logs.
- Live trading desativado até a Fase 4.
