---
tags: [arquitetura, sistema, m0]
updated: 2026-09-05
status: parcial
---

# System Overview

Visão de alto nível do PROJECT HUNTER. Resumo de `docs/ARCHITECTURE.md`; ver lá o detalhe completo (interfaces Python, monorepo, comunicação Redis).

## Princípios (valem desde o M0, não mudam com o roadmap)

1. **Cloud-first.** Nenhum estado em arquivo local; Postgres é a fonte de verdade, Redis é estado quente/transporte.
2. **Orientado a eventos.** Redis Streams entre workers; a ordem é dependência de dados, não chamada síncrona.
3. **Dados globais, decisões por tenant.** Market data, features, anomalias, regime, oportunidades e sinais são computados uma vez e compartilhados; portfolios, propostas, ordens, posições e risco pertencem a uma organização.
4. **Nenhum agente executa.** AGENTE → PROPOSTA → RISK ENGINE → EXECUÇÃO. Ver [[Risk Engine]].
5. **Explicável.** Toda decisão persiste sua decomposição no momento em que foi tomada.
6. **Degradação segura.** Qualquer falha leva a "não abrir posições novas", nunca a "executar algo inseguro".
7. **Uma imagem, vários papéis.** O backend Python é um único artefato Docker; `HUNTER_ROLE` escolhe o processo. Ver [[Workers]].

## O que existe hoje (fim do M0)

- **Auth e tenancy:** Clerk para identidade/sessão; `users`, `organizations`, `organization_members`, `organization_invitations` no Postgres próprio; RBAC com 5 papéis (OWNER/ADMIN/TRADER/ANALYST/VIEWER); isolamento de tenant duplo (repositórios `org_id`-scoped + RLS). Implementado em `apps/api/hunter_api/auth/` (`clerk_verifier.py`, `principal.py`, `rbac.py`) e nas migrações `infra/migrations/versions/0001_initial_schema.py`.
- **Frontend shell:** Next.js 15 App Router, dark-first, `lib/nav-registry.ts` como fonte única da sidebar, páginas de onboarding (passos 1–5, salvam preferências), `/dashboard` com cards de sistema reais (sem números financeiros inventados), `/system`, `/settings/*` (profile, organization, members, security, appearance).
- **API:** FastAPI com routers `orgs`, `workspaces`, `members`, `invitations`, `me`, `system`, `audit`; middleware de request id, security headers, rate limit (Redis), CORS; erros RFC 9457; `/health`, `/ready`, `/metrics` (token-gated).
- **Banco:** schema completo das 54 tabelas descritas em `docs/DATABASE.md` já existe nas migrações (para o schema nascer inteiro), mesmo que a maioria (market data, features, anomalias, propostas, ordens, etc.) não tenha nenhum processo escrevendo nelas ainda.
- **Infra:** Docker (`infra/docker/Dockerfile.api-workers`, `Dockerfile.web`, `docker-compose.yml`), CI (`ci.yml`) com lint, typecheck, testes, migrations check, security scans. Ver [[Infrastructure]].

## O que é planejado (não existe ainda)

- Todos os workers (`market`, `scanner`, `strategy`, `execution`, `analytics`) — hoje `HUNTER_ROLE=all` sobe e sai com código 0 imediatamente, porque `hunter_core.runtime.RoleRegistry` está vazio. Ver [[Workers]].
- Coleta de mercado, features, anomalias, regime, oportunidades — M1/M2. Ver [[Market Collector]], [[Features]], [[Anomalies]].
- Agentes, propostas, Risk Engine, execução paper — M3/M4. Ver [[Risk Engine]], [[Execution Engine]], [[Agents Overview]].
- Analytics, estatísticas por agente — M5. Ver [[Performance Overview]].

## Topologia (alvo; hoje só `apps/web`, `apps/api`, Postgres e Redis rodam de fato)

```
Browser ◄──► apps/web (Next.js, Vercel)
                │ REST (Bearer JWT Clerk) / WS
                ▼
        apps/api (FastAPI)  HUNTER_ROLE=api
                │ SQL (pooler)      │ Redis
                ▼                   ▼
           PostgreSQL (Neon)    Redis (Streams, pub/sub)
                ▲                   ▲
        Workers (mesma imagem Docker; hoje sem papéis implementados)
        market · scanner · strategy · execution · analytics
```

## Relacionadas

[[Data Flow]] · [[Infrastructure]] · [[Workers]] · [[Architecture Decisions]]

## Fontes

`docs/ARCHITECTURE.md`, `docs/PRODUCT.md`, `docs/ROADMAP.md` (M0)
