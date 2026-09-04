# PROJECT HUNTER

Autonomous Crypto Intelligence & Trading SaaS. Plataforma multi-tenant de inteligência quantitativa para criptomoedas: monitora mercados em tempo real, detecta anomalias, pontua oportunidades, gera sinais por agentes, aplica risco e executa em paper e shadow. Live trading só na Fase 4.

**Estado atual:** fase de arquitetura concluída; Milestone 0 ainda não iniciado.

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

## Regras inegociáveis

- Nenhum agente executa ordens. Toda entrada passa pelo Risk Engine.
- Nenhum dado de produção em arquivo local, SQLite ou navegador.
- Nenhum mock, botão inerte, gráfico falso ou número inventado em produção.
- Segredos só em variáveis de ambiente do provedor. Nunca no frontend, no repositório ou em logs.
- Live trading desativado até a Fase 4.
