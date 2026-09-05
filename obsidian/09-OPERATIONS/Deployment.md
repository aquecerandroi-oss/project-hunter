---
tags: [operacoes, deploy]
updated: 2026-09-05
status: parcial
---

# Deployment

## O que existe hoje

**Dev local** — funcional: `docker compose -f infra/docker/docker-compose.yml up -d --build` sobe `postgres:16-alpine`, `redis:7-alpine`, roda `migrate` uma vez, depois `api` (porta 8000 + 8001 de health), `worker` (sai com 0 — ver [[Workers]]) e `web` (porta 3000). Verificado end-to-end em 2026-09-05 (`.claude/state/milestone.json`): stack sobe, `/health` e `/ready` respondem 200.

**CI** — GitHub Actions (`ci.yml`) roda em todo PR e push na `main`: lint, typecheck, testes Python/web, verificação de migrações (`alembic check`), geração de tipos, scans de segurança, build de imagem Docker, e2e (Playwright, condicional), `forbidden-patterns`. Ver [[Infrastructure]].

## O que é planejado, ainda não configurado de fato

| Ambiente | Web | API + workers | Postgres | Redis |
|---|---|---|---|---|
| Preview (PR) | Vercel preview | Railway PR environment (opcional) | Neon branch | Upstash dev |
| Staging | Vercel | Railway | Neon branch `staging` | Redis Railway |
| Produção | Vercel | Railway ou Fly.io | Neon `main` (pooler) | Redis Railway / Upstash fixo |

Nenhum desses ambientes remotos está provisionado ainda — o M0 entrega "deploy manual em Railway + Vercel documentado e testado uma vez" como critério de saída, mas o foco deste levantamento é o estado do código, não a infraestrutura externa provisionada.

**Deploy automatizado planejado:** `deploy-api.yml` (`railway up` por serviço ou `fly deploy`) e `deploy-web.yml` (integração nativa Vercel) só rodam se as 8 primeiras etapas do CI passarem. Migrações rodam como job separado antes dos serviços novos subirem, com lock em Redis.

## Playbook de incidente (especificado; sem produção real para exercitar ainda)

| Sintoma | Ação prevista |
|---|---|
| Exchange offline | `data_degraded`; entradas bloqueadas; posições geridas com último preço |
| Redis fora | Workers pausam consumo com buffer de 60 s; api serve REST do Postgres |
| Postgres lento | Escritas em lote com fila limitada; propostas não decididas sem persistir |
| Execution-worker morto | Nenhuma ordem nova; reconstrói posições ao subir |
| Perda súbita anormal | OWNER aciona kill switch da org; operador pode acionar o de sistema |
| Suspeita de vazamento de tenant | Revogar sessão no Clerk; auditar `audit_logs`; RLS é a barreira final |

## Relacionadas

[[Infrastructure]] · [[Environment Variables]] · [[Monitoring]]

## Fontes

`docs/DEPLOYMENT.md`, `.claude/state/milestone.json`
