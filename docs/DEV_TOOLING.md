# Ferramentas, extensões e MCPs que aceleram o desenvolvimento (item 80.10)

## 1. Ferramentas de linha de comando (instalar antes do M0)

| Ferramenta | Para quê |
|---|---|
| `uv` | Gerenciar Python, workspace e lock |
| `pnpm` + `turbo` | Workspace TypeScript |
| Docker Desktop | Compose local e testcontainers |
| `ruff`, `pyright` | Lint e tipos Python |
| `eslint`, `prettier`, `tsc` | Lint e tipos TS |
| `alembic` | Migrações |
| `openapi-typescript` | Tipos TS a partir do OpenAPI |
| `playwright` | E2E |
| `gitleaks`, `pip-audit`, `bandit` | Segurança em CI |
| `railway` CLI, `vercel` CLI, `neonctl` | Deploy e branches de banco |
| `k6` | Carga em WS e API (M5) |
| `pgcli` / `redis-cli` | Inspeção |

## 2. MCPs úteis para o Claude Code neste projeto

| MCP | Ganho |
|---|---|
| **Postgres/Neon MCP** | Inspecionar schema, rodar `EXPLAIN`, validar RLS e partições direto do chat; criar branches Neon para testar migrações |
| **Redis MCP** | Ler hot state, tamanho de streams e lag de consumer groups durante o debug de workers |
| **GitHub MCP** | PRs, checks de CI, issues por milestone |
| **Playwright MCP** (o navegador integrado já cobre parte) | E2E e inspeção visual do dashboard |
| **Sentry MCP** | Ler erros de produção e stack traces sem sair do editor |
| **Context7 / docs MCP** | Documentação atualizada de Next.js 15, FastAPI, SQLAlchemy 2, Clerk, APIs da Binance e Bybit |
| **Vercel MCP** e **Railway MCP** | Logs de deploy, env vars, status dos serviços |
| **Linear ou GitHub Projects MCP** | Rastrear milestones e known issues |

Regra: MCPs de produção (Postgres, Redis, Railway) só com credenciais de leitura ou de staging.

## 3. Extensões e práticas

- `pre-commit` com ruff, prettier, gitleaks.
- `CLAUDE.md` na raiz descrevendo comandos (`make dev`, `make test`, `make migrate`), convenções e o que é proibido (§68 da especificação).
- `Makefile` ou `justfile` com alvos padronizados para humano e agente usarem os mesmos comandos.
- Fixtures gravadas de exchange versionadas no repositório para testes offline determinísticos.
- Um script `scripts/replay.py` (M2) que injeta candles gravados nos streams para reproduzir cenários sem exchange.
