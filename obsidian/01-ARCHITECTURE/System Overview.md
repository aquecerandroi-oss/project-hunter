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

## Acrescentado no M1 (2026-09-05)

- **API de mercado (T1.4):** cinco rotas autenticadas sobre dados **globais** (sem RLS, lidas com o role `hunter_app` e sem `app.current_org`): `GET /api/v1/markets`, `GET /api/v1/markets/{exchange}/{symbol}` (o detalhe já traz o book snapshot top 20 e os últimos trades), `/candles`, `GET /api/v1/system/workers` e `GET /api/v1/system/market-status`. Postgres dá a identidade do mercado, o hot state do Redis dá preço e frescor. Qualidade **por componente** (`ticker`, `book`, `mark` obrigatórios, com `ts`/`age_ms`/`quality` próprios; open interest e funding com idade própria fora da regra de 10 s) e agregado na precedência `unavailable > degraded > stale > ok`, preservando os motivos individuais e `has_open_gap`. `stale_after_ms` vai no payload para a tela usar o mesmo limiar. Falha de leitura do Redis é `503` explícito ou `hot_state_ok: false`, nunca uma lista vazia disfarçada de "não há nada". Em `apps/api/hunter_api/{routers,schemas,services,repositories}` (`markets*`, `system*`).
- **Telas de mercado (T1.5):** `/[orgSlug]/markets` (tabela real com busca, ordenação, virtualização e badge de qualidade) e `/[orgSlug]/markets/[exchange]/[symbol]` (candles com `lightweight-charts`, book top 20, trades, funding/OI/mark com idade por componente). Widget **Live Market Status** no dashboard e no topbar (`rt:system`), tabela de workers real na página **System** no lugar do placeholder do M0, e `markets` passa a `available` no `nav-registry`. As páginas se atualizam sozinhas (`components/auto-refresh.tsx`, pausado em aba oculta, cadência derivada de `stale_after_ms`) e o preço só conta como fresco pelo `price_ts` do evento de tempo real. Tipos vêm de `packages/shared-types`, gerado do OpenAPI real.
- **Polimento de UX/UI (T1.5b):** o contrato visual de `docs/DESIGN.md` aplicado à interface inteira. Escala tipográfica de cinco tamanhos (12/14/16/20/28) com três exceções nomeadas (13px no corpo da tabela para as colunas numéricas caberem sem truncar, 11px em metadado de linha, 10px na dica de atalho); duas densidades reais de tabela (40px confortável, 32px compacta) lidas de um único `data-density` no `<html>`, com CSS e constante de virtualização compartilhando a mesma fonte. O **vocabulário de staleness** passa a ter dois eixos separados que nunca se misturam: o do dado (`OK` / `atrasado Ns` / `gap` / `sem dado`) e o do componente (`operacional` / `degradado` / `indisponível` / `sem verificação`) — ausência de verificação é estado próprio, nunca alarme de queda. **Command palette** (`Ctrl`/`⌘K`) sobre o `q=` real de `GET /api/v1/markets`, via Server Action que falha fechada sem sessão, mínimo de dois caracteres e `q` limitado a 64. Painel de snapshot rotulado "Snapshot · há N min" dizendo explicitamente que não é fita ao vivo; candles verde/vermelho; navegação por setas com `aria-activedescendant` e árvore ARIA completa (`role="row"`/`"columnheader"`/`"gridcell"` mais `aria-rowcount`/`aria-rowindex`) sobre a tabela virtualizada; `prefers-reduced-motion` respeitado globalmente. Todo acesso a `localStorage` passa por `apps/web/lib/safe-storage.ts`, porque Web Storage bloqueado **lança** em vez de devolver `null`. Ver [[Open Bugs]] para os itens adiados ao M2.
- **Limitações conhecidas** destas duas tarefas estão em `docs/plans/M1.md` → "Limitações conhecidas do M1"; os defeitos ainda abertos, em [[Open Bugs]].

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
