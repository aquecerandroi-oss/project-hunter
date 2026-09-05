---
tags: [operacoes, monitoramento, observabilidade]
updated: 2026-09-05
status: parcial
---

# Monitoring

## O que existe hoje

- **`/health`** — liveness do processo `api` (e de `HEALTH_PORT` nos workers, quando existirem).
- **`/ready`** — checa Postgres e Redis alcançáveis, com timeout configurável (`READY_CHECK_TIMEOUT_S`) e branch testado de banco fora do ar.
- **`/metrics`** — exposto, protegido por token (`METRICS_TOKEN`); vazio em staging/produção desativa o endpoint (404) em vez de expor métricas sem autenticação.
- **Logs estruturados** — JSON via `structlog` (nunca `print`), com `request_id`, `org_id`, `role`. Regra de lint (`quality/no-direct-console` no TS) força uso de `@/lib/logger` no frontend.
- **Sentry** — inicializado atrás de env (`SENTRY_DSN`); sem chave = desligado. `release` planejado para ser o SHA do commit quando houver deploy real.
- **Auditoria** — `audit_logs` (append-only, RLS, particionado mensalmente) já existe e é gravado por `@audited` nos serviços que mutam dados de tenant no M0 (orgs, workspaces, membros, convites).

## O que é planejado, ainda sem implementação

- **Heartbeats de worker** (`hb:{role}:{instance}` em Redis, consolidados em `worker_heartbeats` a cada minuto) — dependem dos workers existirem (M1+). Hoje `worker_heartbeats` é uma tabela vazia.
- **Watchdog / staleness** — `/system` mostrando latência, último dado, conexões WS por exchange (M1); heartbeat por exchange `hb:market:{exchange}` com `stale` se `last_event_at` > 10 s (M1).
- **Alarmes mínimos**: worker `stale` > 60 s, lag de stream > 5.000, erro de exchange > 10/min, partição faltando, taxa de erro do Sentry — todos dependem de dado real fluindo pelos streams, que ainda não existem.
- **Métricas específicas do pipeline**: eventos por stream (produzidos, consumidos, lag), latência por exchange, gaps de candle, propostas aprovadas/rejeitadas por check, fills simulados, erro por worker — nenhuma tem produtor ainda.
- **PostHog** (product analytics) — inicializado atrás de env, mas a lista de eventos de `docs/PRODUCT.md` §6 (`user_signed_up`, `portfolio_created`, etc.) ainda não está instrumentada em todo o fluxo — só o essencial de auth/onboarding do M0.

## Relacionadas

[[Deployment]] · [[Infrastructure]] · [[Environment Variables]]

## Fontes

`docs/ARCHITECTURE.md` §11, `docs/DEPLOYMENT.md` §5, `docs/SECURITY.md` §5, `.env.example`
